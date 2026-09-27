#!/usr/bin/env python3
"""Automatic disk hygiene for the Windows dev box — inventory first, remove only
what is provably disposable.

Why this exists: on 2026-09-26 the dev box's C: drive reached 0 bytes free and
every agent lane broke. None of it was project data. It was accumulated agent
scratch: 126 pytest ``--basetemp`` directories holding 7.9 GB, ~25 git worktrees
of this repo, Docker build cache, and repo scratch folders. The production
droplet already self-cleans (count-based image retention in
``scripts/daemon_image_retention.py``, the ``disk_watch.py`` timer); the dev side
had nothing, so the founder was asked about it "every so often" instead. Founder
directive 2026-09-26: *disk cleaning should be an automatic part of the
architecture, not something I'm asked about every so often.*

Four classes, each with its own proof of disposability:

``basetemp``
    Directories directly under the OS temp root whose name matches an
    agent-convention prefix AND whose contents have pytest's numbered-dir shape,
    untouched for ``--min-age-hours``.
``worktree``
    Git worktrees **of this repository only**, taken from ``git worktree list
    --porcelain``. Removed only when clean of tracked *and* ignored content,
    idle, and content-merged into ``origin/main``.
``docker``
    Build cache only, via ``docker builder prune`` with a keep budget, and only
    when the engine answers. Never volumes, never images, never other projects.
``scratch``
    A closed allowlist of this repo's own scratch directory names, only when git
    confirms the path is ignored and it is older than ``--min-age-days``.

Everything else is KEPT, with a reason. **Every unknown is a KEEP**: an
undecidable git query, a directory shape the collector does not recognise, and
an inventory that exceeds its entry budget all fail closed. That is Hard Rule 13
("Inventory before you destroy") expressed as code — the 2026-08-26 incident was
a checkout that *looked* like stale cruft and held 4,711 lines of unique
research, so a clean ``git status`` is not on its own a licence to delete.

Modes
-----
``--dry-run``   (default) print the inventory with sizes; touch nothing.
``--apply``     remove the REMOVE set and append every removal to the log.
``--if-low-disk GB``
                apply only when free space is below GB; otherwise report.
``--escalate-below GB``
                after the pass, if free space is still below GB, print a
                concrete escalation block and exit 3.

Exit codes
----------
0   Nothing to do, or the pass finished and free space is acceptable.
2   The environment could not be inventoried at all (bad --repo, no git).
3   Escalation: the disposable set cannot bring free space above the threshold.

Stdlib only. Runs from any cwd. See ``docs/reference/dev-disk-hygiene.md``.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import stat as stat_mod
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from git_squash_merge import is_merged_into  # noqa: E402  (sibling-script import)

CLASSES = ("basetemp", "worktree", "docker", "scratch")

# Temp-root directory names the agents actually produce. Measured from the repo's
# own review docs (docs/reviews/2026-09-*.md): ta-pt-*, ta-pt2, ta-rev-*,
# ta-root-*, ta-finq, ta-retirement-final-*, tinyassets-review-*, plus pytest's
# own default root. A prefix match alone never authorizes removal — see
# looks_like_pytest_tree.
BASETEMP_PREFIXES = ("ta-", "pytest-of-", "pytest-", "tinyassets-review-", "tinyassets-test-")

# A DRIVE root (C:\) is also a basetemp root here: lanes put short basetemps at
# C:\ta-<lane>N to stay under MAX_PATH, and nothing swept them — 34 were sitting
# there on 2026-09-26, some from July. Deliberately narrower than the temp-root set:
# a drive root holds system directories, so only the agents' own `ta-` convention
# is even a candidate, top level only.
DRIVE_ROOT_PREFIXES = ("ta-",)

# pytest's numbered-dir scheme: "<slug><N>" for tmp_path dirs, "pytest-<N>" under
# pytest-of-<user>, and "garbage-<uuid>" for its own deferred cleanup.
_NUMBERED_DIR = re.compile(r".*\d+\Z")

MAIN_BRANCHES = frozenset({"main", "master", "production"})

# Ignored paths inside a worktree that carry no unique work. Anything ignored and
# NOT on this list keeps the worktree: that is the Hard Rule 13 guard, and it is
# the one `git worktree remove` does not have (it decides cleanliness with
# `git status --porcelain`, which omits ignored files entirely).
DISPOSABLE_IGNORED = (
    ".venv/",
    "venv/",
    "env/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    "node_modules/",
    ".svelte-kit/",
    "dist/",
    "build/",
    ".egg-info/",
    # Per-session hook telemetry for loop detection: events.jsonl plus one
    # keep-working-<session-uuid>.json per session. Regenerated on demand, scoped
    # to a session that has ended, and never a work product — verified by reading
    # a lane's copy on 2026-09-26. Without this, nearly every Codex lane is held
    # back by machine state it wrote about itself.
    ".agents/supervisor/",
)
# Ignored FILES with no unique content. Matched against the whole relative path
# for a root-anchored name and against the final component otherwise — never as a
# substring or a bare prefix. `_PURPOSE.md` is root-only because `wt.py`'s archive
# only preserves the root copy, so a nested one would be accepted as disposable
# and then never archived (Codex round 1, P0).
DISPOSABLE_IGNORED_FILES_ROOT = ("_PURPOSE.md", "junit.xml")
DISPOSABLE_IGNORED_BASENAMES = (".DS_Store", "Thumbs.db")
# Compiled artifacts only. `*.db`/`*.db-wal`/`*.db-shm` were here and are NOT:
# this repo ignores `*.db` for the SQLite mirror of the YAML catalog, but the same
# pattern covers a user's own local database, and Codex round 1 reproduced a
# `research.db` being accepted as disposable. An extension is not a provenance.
DISPOSABLE_IGNORED_GLOBS = ("*.pyc", "*.pyo")

# `git status --ignored=matching` collapses a wholly-ignored directory into ONE
# entry, so accepting the entry says nothing about what is inside it (Codex round
# 1, answer 4). Tool-owned caches above need no content check — nothing but the
# tool writes them. `.agents/supervisor/` is repo state, so its contents are
# verified against the filenames its producers actually emit
# (`scripts/supervisor.py`, and a since-removed keep-working hook): one
# `events.jsonl`, one `seen.json`, and `keep-working-<session-uuid>.json`.
# Anything else in there keeps the worktree.
DISPOSABLE_DIR_CONTENT_RULES: dict[str, tuple[str, ...]] = {
    ".agents/supervisor": ("events.jsonl", "seen.json", "keep-working-*.json"),
}

# This repo's own scratch directory names. A closed list on purpose: `.codex-worktrees/`
# holds sandbox-owned INDEPENDENT repos and `output/`, `universes/`, `logs/`,
# `data-room/`, `.secrets/` hold real local state, so none of them appear here.
# `.tmp` and `.review` were here and are NOT: a generic name plus ignore status
# plus age proves nothing about provenance, and Codex round 1 reproduced a
# ten-day-old `.tmp/research.md` being removed. Every name left is one only a
# test run or an agent tool creates.
SCRATCH_NAMES = (
    "codex-tmp",
    ".pytest-tmp",
    ".codex-test-tmp",
    ".workflow-test-data",
)
SCRATCH_GLOBS = (".codex-scratch-*", ".codex-*.txt", "codex-scratch-*")

# KEEP reasons that are the system working as designed, not something the founder
# has to decide. Everything else lands in the escalation list.
EXPECTED_KEEPS = frozenset(
    {
        "primary_checkout",
        "in_use_by_this_process",
        "in_use_or_recent",
        "recently_active",
        "contains_cwd",
        "protected_branch",
        "path_missing",
        "nothing_reclaimable",
        "docker_engine_not_running",
        "not_git_ignored",
        "recent",
        "not_inventoried",
        "deferred_to_next_pass",
        "acl_locked_needs_elevation",  # summarized on its own line, with the fix
    }
)

# Fail closed rather than spend unbounded time measuring one tree.
MAX_TREE_ENTRIES = 200_000
DEFAULT_LOG = Path(".claude") / "logs" / "dev-hygiene.log"


class Undecidable(Exception):
    """Evidence unavailable. Never authorizes removal — the caller must KEEP."""


class AclLocked(Undecidable):
    """Windows denied access outright — needs an elevated clear, not a retry.

    Its own type because the remedy is different: a sandbox agent that pointed
    ``--basetemp``/``TMPDIR`` at a path under a restricted token leaves a
    directory the interactive user cannot read, list, or delete. Reported as
    ``acl_locked_needs_elevation`` with the elevated command, not folded into the
    generic "could not measure it" bucket.
    """


@dataclass
class Item:
    """One reclaimable candidate and the verdict on it."""

    kind: str
    path: str
    size_bytes: int
    verdict: str  # "REMOVE" | "KEEP"
    reason: str
    detail: str = ""
    # Class-specific payload the remover needs. Named fields rather than parsing
    # it back out of ``detail``: a human string is not a machine contract.
    branch: str = ""  # worktree class: the local branch to delete
    prune_flag: str = ""  # docker class: the keep-budget flag this CLI has

    @property
    def removable(self) -> bool:
        return self.verdict == "REMOVE"


@dataclass
class Report:
    items: list[Item] = field(default_factory=list)
    free_before_gb: float = 0.0
    free_after_gb: float = 0.0
    applied: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def reclaimable_bytes(self) -> int:
        return sum(i.size_bytes for i in self.items if i.removable)


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #


def run(args: list[str], cwd: Path | None = None, timeout: float = 30.0):
    """Run a command, never raising. Callers treat a non-zero rc as undecidable."""
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def git_ok(args: list[str], cwd: Path, timeout: float = 30.0) -> str:
    """Run git and return stdout, or raise Undecidable. Fail-closed by default."""
    proc = run(["git", *args], cwd=cwd, timeout=timeout)
    if proc.returncode != 0:
        raise Undecidable(
            f"git {' '.join(args)} -> rc={proc.returncode} {proc.stderr.strip()[:200]}"
        )
    return proc.stdout


def free_gb(path: Path) -> float:
    return shutil.disk_usage(str(path)).free / (1024**3)


def is_reparse_point(info: os.stat_result) -> bool:
    """True for a Windows reparse point (junction or symlink); False off Windows.

    ``entry.is_dir(follow_symlinks=False)`` returns **True** for a junction, so it
    is not on its own a no-follow guard. Symlinks need privilege on this host and
    junctions do not, so the junction is the case that actually occurs here.
    """
    attrs = getattr(info, "st_file_attributes", 0)
    return bool(attrs & getattr(stat_mod, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def is_link(info: os.stat_result) -> bool:
    """True for anything whose content lives somewhere else, on any platform.

    One predicate for both mechanisms so the walk behaves identically everywhere:
    a POSIX symlink (``S_ISLNK``) and a Windows junction or symlink (a reparse
    point) are the same fact — "this entry names another directory".
    """
    return stat_mod.S_ISLNK(info.st_mode) or is_reparse_point(info)


def tree_stats(root: Path, budget: int = MAX_TREE_ENTRIES) -> tuple[int, float]:
    """Return ``(total_bytes, newest_mtime)`` for a directory tree.

    Raises ``Undecidable`` when the tree exceeds ``budget`` entries or cannot be
    read — an unmeasurable tree is kept rather than guessed at.

    **One rule for every link, on every platform: it contributes nothing and is
    never descended into.** ``entry.is_dir(follow_symlinks=False)`` returns True for
    a Windows junction, so the walk used to cross into the target and count its
    bytes here; and a POSIX symlink's own ``lstat`` size is the length of its target
    path, which is not content inside this tree either. Both returns are
    load-bearing — size ranks the escalation, newest mtime is the worktree idleness
    gate — so counting either would be a lie about a different directory.

    An earlier version raised ``Undecidable`` on any reparse point. That was
    unnecessary once nothing is counted or followed, and it cost real coverage: it
    made 2 worktrees and 7 temp dirs permanently un-inventoriable on this box, and
    it would have refused every POSIX tree holding a ``.venv/bin`` symlink.
    ``shutil.rmtree`` also does **not** delete through a nested junction —
    ``shutil._rmtree_islink`` tests ``IO_REPARSE_TAG_MOUNT_POINT`` (Python 3.14),
    and a 2026-09-26 probe confirmed the target's contents survive removal of the
    parent — so the remaining link guard lives at the deletion boundary in
    ``remove_path``, which refuses a link handed to it directly.
    """
    total = 0
    newest = 0.0
    seen = 0
    stack = [root]
    try:
        root_info = os.stat(root, follow_symlinks=False)
    except PermissionError as exc:
        raise AclLocked(f"access denied on {root}: {exc}") from exc
    except OSError as exc:
        raise Undecidable(f"cannot stat {root}: {exc}") from exc
    if is_link(root_info):
        raise Undecidable(f"{root} is itself a link; this tool sizes real directories only")
    newest = root_info.st_mtime
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    seen += 1
                    if seen > budget:
                        raise Undecidable(f"{root} exceeds {budget} entries")
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if is_link(info):
                            continue  # counts nothing, and never descend through it
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                            newest = max(newest, info.st_mtime)
                            continue
                    except FileNotFoundError:
                        continue  # raced with a delete; it contributes nothing
                    except PermissionError as exc:
                        # Same class as a denied root, so it gets the same answer and
                        # the same elevated-fix pointer.
                        raise AclLocked(f"access denied on {entry.path}: {exc}") from exc
                    except OSError as exc:
                        # Anything else is an answer we do not have. The recursive
                        # newest mtime is the worktree idleness gate, so skipping
                        # an unreadable entry would silently under-report activity
                        # (Codex round 1, P2).
                        raise Undecidable(f"cannot stat {entry.path}: {exc}") from exc
                    total += info.st_size
                    newest = max(newest, info.st_mtime)
        except PermissionError as exc:
            raise AclLocked(f"access denied on {current}: {exc}") from exc
        except OSError as exc:
            raise Undecidable(f"cannot read {current}: {exc}") from exc
    return total, newest


ELEVATED_CLEAR = (
    "powershell -ExecutionPolicy Bypass -File scripts/clear_sandbox_temp_dirs.ps1 -Apply"
)


def keep_for(kind: str, path, exc: Undecidable, size: int = 0) -> Item:
    """Turn an undecidable measurement into the KEEP it must become."""
    if isinstance(exc, AclLocked):
        return Item(
            kind, str(path), size, "KEEP", "acl_locked_needs_elevation", f"needs: {ELEVATED_CLEAR}"
        )
    return Item(kind, str(path), size, "KEEP", "not_inventoriable", str(exc))


def human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def contains(parent: Path, child: Path) -> bool:
    return parent == child or parent in child.parents


# --------------------------------------------------------------------------- #
# (a) pytest basetemp directories
# --------------------------------------------------------------------------- #


def classify_temp_dir(path: Path) -> str:
    """Return ``"pytest"``, ``"acl_locked"``, or ``"unrecognized"``.

    A name prefix is a hint, not proof: something else could be called ``ta-…``,
    and on this box several ``ta-*`` directories are whole stale repo checkouts
    kept as audit oracles. Accepted shapes are pytest's own: the
    ``pytest-of-<user>`` root, a child directory using pytest's ``<slug><N>``
    numbered scheme, its ``.lock`` file, its ``garbage-*`` deferred-cleanup
    links, or an empty directory (``pytest --basetemp=X`` wipes and recreates X
    at session start, so an empty X holds zero bytes of anything).

    **Every** child must be one of those shapes. Accepting on the first match was
    enough for Codex round 1 to get ``ta-research/`` removed by adding a
    ``chapter1/`` next to a unique ``manuscript.md``: one plausible-looking child
    vouched for its siblings. A single unrecognised sibling now keeps the
    directory, and ``pytest-of-*`` is checked the same way rather than trusted on
    its name.

    ``acl_locked`` is its own answer, not a shrug: a sandbox agent that pointed
    ``--basetemp`` at the temp root under a restricted token leaves a directory
    the interactive user cannot read, list, or delete. Those need an elevated
    ``scripts/clear_sandbox_temp_dirs.ps1 -Apply``, so they belong in the
    escalation list rather than lumped in with shapes we simply do not know.
    """
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if not _is_pytest_artifact(entry):
                    return "unrecognized"
            return "pytest"  # every child vouched for, or the directory is empty
    except PermissionError:
        return "acl_locked"
    except OSError:
        return "unrecognized"


def _is_pytest_artifact(entry: os.DirEntry) -> bool:
    """Whether one entry inside a temp root is something pytest itself created."""
    name = entry.name
    if name in {".lock", "pytest-current"} or name.startswith("garbage-"):
        return True
    try:
        is_dir = entry.is_dir(follow_symlinks=False)
    except OSError:
        return False
    if is_dir:
        # tmp_path dirs ("test_foo0"), pytest-of-<user>'s "pytest-<N>" roots, and
        # the per-session numbered dirs underneath them all end in a digit.
        return bool(_NUMBERED_DIR.match(name))
    # pytest leaves "<name>-current" links beside its numbered dirs.
    return name.endswith("-current")


def collect_basetemps(
    temp_root: Path,
    *,
    min_age_hours: float,
    now: float,
    prefixes: tuple[str, ...] = BASETEMP_PREFIXES,
) -> list[Item]:
    """Inventory one temp root. ``prefixes`` is narrower for a drive root.

    Called once per configured root. The OS temp root takes the full agent-prefix
    set; a **drive root** like ``C:\\`` takes ``ta-`` only, because lanes put short
    basetemps there to dodge MAX_PATH and a drive root also holds system
    directories that must never be candidates.
    """
    items: list[Item] = []
    here = Path.cwd().resolve()
    try:
        children = sorted(temp_root.iterdir())
    except OSError as exc:
        return [Item("basetemp", str(temp_root), 0, "KEEP", "temp_root_unreadable", str(exc))]

    for child in children:
        name = child.name
        if not any(name.startswith(p) for p in prefixes):
            continue
        # A checkout is never basetemp, whatever it is called. The shape gate below
        # would refuse it anyway, but saying so by name keeps a repo at a drive root
        # out of this class entirely — it belongs to the worktree class, which
        # applies the unique-work checks.
        if (child / ".git").exists():
            items.append(
                Item(
                    "basetemp",
                    str(child),
                    0,
                    "KEEP",
                    "git_checkout_not_basetemp",
                    "has a .git entry; the worktree class owns this path",
                )
            )
            continue
        try:
            if not child.is_dir() or child.is_symlink():
                continue
        except OSError:
            continue
        resolved = child.resolve()
        shape = classify_temp_dir(child)
        if shape == "acl_locked":
            items.append(keep_for("basetemp", child, AclLocked("cannot list it")))
            continue
        if shape != "pytest":
            # Sized anyway: an unrecognized directory is exactly what the founder
            # has to make a call on, and a concrete escalation needs its size.
            try:
                size, _ = tree_stats(child)
            except Undecidable:
                size = 0
            items.append(
                Item(
                    "basetemp",
                    str(child),
                    size,
                    "KEEP",
                    "unrecognized_shape",
                    "not a pytest temp tree",
                )
            )
            continue
        if contains(resolved, here):
            items.append(Item("basetemp", str(child), 0, "KEEP", "contains_cwd"))
            continue
        try:
            size, newest = tree_stats(child)
        except Undecidable as exc:
            items.append(keep_for("basetemp", child, exc))
            continue
        age_hours = max(0.0, (now - newest) / 3600.0)
        if age_hours < min_age_hours:
            items.append(
                Item(
                    "basetemp",
                    str(child),
                    size,
                    "KEEP",
                    "in_use_or_recent",
                    f"{age_hours:.1f}h old",
                )
            )
            continue
        items.append(
            Item(
                "basetemp",
                str(child),
                size,
                "REMOVE",
                "stale_pytest_basetemp",
                f"{age_hours:.1f}h old",
            )
        )
    return items


# --------------------------------------------------------------------------- #
# (b) git worktrees of THIS repo
# --------------------------------------------------------------------------- #


@dataclass
class Worktree:
    path: Path
    head: str
    branch: str  # "" when detached
    detached: bool


def parse_worktrees(porcelain: str) -> list[Worktree]:
    out: list[Worktree] = []
    cur: dict[str, object] = {}

    def flush() -> None:
        if cur.get("path"):
            branch_ref = str(cur.get("branch") or "")
            out.append(
                Worktree(
                    path=Path(str(cur["path"])),
                    head=str(cur.get("head") or ""),
                    branch=branch_ref[len("refs/heads/") :]
                    if branch_ref.startswith("refs/heads/")
                    else "",
                    detached=bool(cur.get("detached")),
                )
            )

    for raw in porcelain.splitlines():
        line = raw.strip()
        if not line:
            flush()
            cur = {}
            continue
        if line.startswith("worktree "):
            flush()
            cur = {"path": line[len("worktree ") :]}
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD ") :]
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch ") :]
        elif line == "detached":
            cur["detached"] = True
    flush()
    return out


def is_disposable_ignored(rel: str) -> bool:
    """True when an ignored path inside a worktree carries no unique work.

    Matching is by **path component**, never by substring or bare prefix. The
    first version used ``norm.startswith(known)`` plus a ``"/" + known in
    "/" + norm`` substring test, and Codex round 1 reproduced three unique paths
    passing it: ``research.db`` (an extension is not a provenance),
    ``docs/_PURPOSE.md`` (accepted as disposable but only the root copy is ever
    archived), and ``_PURPOSE.md-git-credentials.txt`` (a prefix is not a
    filename). A component test refuses all three.
    """
    # Only a leading "./" is stripped. `str.lstrip("./")` would eat the leading
    # dot of every dotted path, turning ".ruff_cache/" into "ruff_cache/".
    norm = rel.replace("\\", "/")
    if norm.startswith("./"):
        norm = norm[2:]
    trimmed = norm.rstrip("/")
    if not trimmed:
        return False
    parts = trimmed.split("/")

    # A directory entry matches when it IS a component of the path, so
    # ".venv/", "a/.venv/" and "a/.venv/lib/x.py" all match while
    # ".venv-backup/" does not.
    for known in DISPOSABLE_IGNORED:
        segments = [s for s in known.strip("/").split("/") if s]
        if not segments:
            continue
        window = len(segments)
        if any(parts[i : i + window] == segments for i in range(len(parts) - window + 1)):
            return True

    if trimmed in DISPOSABLE_IGNORED_FILES_ROOT:  # root-anchored, exact
        return True
    if parts[-1] in DISPOSABLE_IGNORED_BASENAMES:  # exact final component
        return True
    return any(fnmatch.fnmatch(parts[-1], g) for g in DISPOSABLE_IGNORED_GLOBS)


def _status_entries(worktree: Path, *extra: str) -> list[tuple[str, str]]:
    """Parse ``git status --porcelain -z`` into ``(xy, path)`` pairs.

    NUL-delimited because git escapes and quotes a path with spaces or non-ASCII
    bytes in the newline form, and stripping the quotes leaves the escapes
    undecoded (Codex round 1, P2). Rename entries carry two NUL-separated paths;
    the origin path is returned as its own entry so neither half is lost.
    """
    raw = git_ok(["status", "--porcelain", "-z", "--untracked-files=all", *extra], worktree)
    fields = [f for f in raw.split("\0") if f]
    entries: list[tuple[str, str]] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if len(field) < 4 or field[2] != " ":
            continue  # not a status record; never silently treated as clean
        xy, path = field[:2], field[3:]
        entries.append((xy, path))
        if "R" in xy or "C" in xy:  # rename/copy: the next field is the origin
            if index < len(fields):
                entries.append((xy, fields[index]))
                index += 1
    return entries


def unexpected_dir_contents(worktree: Path, rel: str) -> list[str]:
    """Files under a content-ruled disposable directory that the rule does not allow.

    Raises ``Undecidable`` when the directory cannot be listed: an unreadable
    directory is not an empty one.
    """
    key = rel.replace("\\", "/").strip("/")
    allowed = DISPOSABLE_DIR_CONTENT_RULES.get(key)
    if allowed is None:
        return []
    root = worktree / key
    unexpected: list[str] = []
    try:
        for parent, _dirs, files in os.walk(root, onerror=_raise_walk_error):
            for name in files:
                if not any(fnmatch.fnmatch(name, pattern) for pattern in allowed):
                    unexpected.append(
                        str(Path(parent, name).relative_to(worktree)).replace("\\", "/")
                    )
    except OSError as exc:
        raise Undecidable(f"cannot list {root}: {exc}") from exc
    return unexpected


def _raise_walk_error(exc: OSError) -> None:
    raise exc


def unique_ignored_paths(worktree: Path) -> list[str]:
    """Ignored paths that are NOT provably disposable. Raises Undecidable on error."""
    found: list[str] = []
    for xy, path in _status_entries(worktree, "--ignored=matching"):
        if xy != "!!":
            continue
        if not is_disposable_ignored(path):
            found.append(path)
            continue
        found.extend(unexpected_dir_contents(worktree, path))
    return found


def dirty_paths(worktree: Path) -> list[str]:
    """Tracked modifications and non-ignored untracked paths. Raises Undecidable."""
    return [f"{xy} {path}" for xy, path in _status_entries(worktree) if xy != "!!"]


def unpushed_commits(worktree: Path, head: str) -> list[str]:
    """Commits reachable from HEAD but from no remote-tracking ref."""
    out = git_ok(["log", "--format=%h %s", head, "--not", "--remotes"], worktree)
    return [ln for ln in out.splitlines() if ln.strip()]


def pr_is_closed(branch: str, cwd: Path) -> bool | None:
    """``True``/``False`` for the branch's PR state, ``None`` when gh cannot say."""
    if not branch:
        return None
    proc = run(
        ["gh", "pr", "list", "--head", branch, "--state", "all", "--limit", "1", "--json", "state"],
        cwd=cwd,
        timeout=30,
    )
    if proc.returncode != 0:
        return None
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not rows:
        return None
    return str(rows[0].get("state", "")).upper() in {"CLOSED", "MERGED"}


def collect_worktrees(
    repo: Path,
    *,
    now: float,
    idle_hours: float,
    deadline: float | None = None,
    base_ref: str = "refs/remotes/origin/main",
    pr_state_fn=None,
    open_pr_fn=None,
) -> list[Item]:
    """Inventory this repo's worktrees. Never looks outside ``git worktree list``."""
    pr_state = pr_state_fn if pr_state_fn is not None else pr_is_closed
    try:
        porcelain = git_ok(["worktree", "list", "--porcelain"], repo)
        primary = Path(
            git_ok(["rev-parse", "--path-format=absolute", "--git-common-dir"], repo).strip()
        ).parent
    except Undecidable as exc:
        return [Item("worktree", str(repo), 0, "KEEP", "worktree_list_undecidable", str(exc))]

    # One liveness query for the whole pass. A branch with an OPEN PR is a lane
    # someone is still working, whatever its merge state looks like locally — and
    # with 115 removable worktrees the realistic failure is deleting the tree a
    # parallel builder is standing in. If gh cannot answer, the ENTIRE worktree
    # class is skipped: an unknown open-PR set is not a licence to remove any of
    # them (lead directive 2026-09-26).
    open_branches = (open_pr_fn if open_pr_fn is not None else open_pr_branches)(repo)
    if open_branches is None:
        return [
            Item(
                "worktree",
                str(repo),
                0,
                "KEEP",
                "open_pr_set_unknown",
                "gh could not list open PRs; the whole worktree class is skipped",
            )
        ]

    here = Path.cwd().resolve()
    items: list[Item] = []
    entries = parse_worktrees(porcelain)
    for index, wt in enumerate(entries):
        if deadline is not None and time.monotonic() > deadline:
            for remaining in entries[index:]:
                items.append(Item("worktree", str(remaining.path), 0, "KEEP", "not_inventoried"))
            break
        item = _judge_worktree(
            wt,
            repo=repo,
            primary=primary,
            here=here,
            now=now,
            idle_hours=idle_hours,
            base_ref=base_ref,
            pr_state=pr_state,
            open_branches=open_branches,
        )
        items.append(item)
    return items


def commits_after_push(worktree: Path, branch: str, head: str) -> list[str]:
    """Commits on ``head`` that its own remote-tracking ref does not have.

    The case this exists for: a branch squash-merges, then someone adds a commit
    locally. ``is_merged_into`` compares the branch's *cumulative* diff against the
    base, so a later commit touching only files the merge already changed can leave
    that comparison still true — and the commit would be destroyed with the
    worktree. Comparing the tip against ``refs/remotes/origin/<branch>`` answers it
    directly.

    Empty when there is no remote-tracking ref (nothing to compare against, and the
    unpushed-commits and merge gates already cover that shape) or when git cannot
    answer — the callers that matter have already established the branch is merged,
    and this is an extra refusal, not the only one.
    """
    remote_ref = f"refs/remotes/origin/{branch}"
    if run(["git", "rev-parse", "--verify", "--quiet", remote_ref], cwd=worktree).returncode != 0:
        return []
    proc = run(["git", "log", "--format=%h %s", head, f"^{remote_ref}"], cwd=worktree, timeout=60)
    if proc.returncode != 0:
        return []
    return [line for line in (proc.stdout or "").splitlines() if line.strip()]


def open_pr_branches(repo: Path) -> set[str] | None:
    """Head branch names with an OPEN PR, or ``None`` when gh cannot say.

    ``None`` is not "no open PRs" — callers must treat it as undecidable and skip
    the whole class. One call per pass, not per worktree.
    """
    proc = run(
        ["gh", "pr", "list", "--state", "open", "--limit", "500", "--json", "headRefName"],
        cwd=repo,
        timeout=60,
    )
    if proc.returncode != 0:
        return None
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(rows, list):
        return None
    return {str(row.get("headRefName", "")) for row in rows if row.get("headRefName")}


def _judge_worktree(
    wt: Worktree,
    *,
    repo: Path,
    primary: Path,
    here: Path,
    now: float,
    idle_hours: float,
    base_ref: str,
    pr_state,
    open_branches: set[str],
) -> Item:
    path = wt.path
    label = wt.branch or f"(detached {wt.head[:8]})"

    def keep(reason: str, detail: str = "", size: int = 0) -> Item:
        return Item("worktree", str(path), size, "KEEP", reason, detail or label)

    try:
        resolved = path.resolve()
    except OSError:
        return keep("path_unresolvable")
    if not path.exists():
        return keep("path_missing", "git worktree prune handles the admin record")
    if resolved == primary.resolve():
        return keep("primary_checkout")
    if contains(resolved, here):
        return keep("in_use_by_this_process")
    if wt.branch in MAIN_BRANCHES:
        return keep("protected_branch")
    if wt.detached or not wt.branch:
        return keep("detached_head", "no branch to prove merged; resolve by hand")
    if wt.branch in open_branches:
        return keep("open_pr", f"{label}: a PR is open on this branch")

    # LIVENESS FIRST. The size walk's recursive newest mtime is the idleness
    # answer, and it is taken BEFORE any git call: `git status` and `git log`
    # touch files under the gitdir, and the earlier direct-children-plus-index
    # check was invalidated by exactly that (measured 72.0h before the status
    # call, 0.0h after). Snapshot first, judge after.
    try:
        size, newest = tree_stats(path)
    except Undecidable as exc:
        return keep_for("worktree", path, exc)
    idle = max(0.0, (now - newest) / 3600.0)
    if idle < idle_hours:
        return keep("recently_active", f"{label}: touched {idle:.1f}h ago", size)

    try:
        dirty = dirty_paths(path)
    except Undecidable as exc:
        return keep("status_undecidable", str(exc), size)
    if dirty:
        return keep("dirty", f"{label}: {len(dirty)} changed/untracked path(s)", size)

    try:
        ignored = unique_ignored_paths(path)
    except Undecidable as exc:
        return keep("ignored_scan_undecidable", str(exc), size)
    if ignored:
        return keep(
            "ignored_content_exists_nowhere_else", f"{label}: {', '.join(ignored[:3])}", size
        )

    merged = is_merged_into(lambda a: run(list(a), cwd=path), wt.head, base_ref)
    try:
        unpushed = unpushed_commits(path, wt.head)
    except Undecidable as exc:
        return keep("unpushed_scan_undecidable", str(exc), size)

    if merged:
        # A squash-merged branch always has commits unreachable from any remote —
        # its pre-squash history. The invariant the unpushed check protects is
        # "no work exists only here", and is_merged_into already proved this
        # branch's cumulative diff is on the base, so those commits are
        # duplicates of landed content, not unique work.
        #
        # EXCEPT when the tip moved after the push. `is_merged_into` compares the
        # CUMULATIVE diff, so a commit added after the merge can leave that diff
        # still matching the base — and it would then be destroyed. Comparing the
        # tip against its own remote-tracking ref catches that directly.
        ahead = commits_after_push(path, wt.branch, wt.head)
        if ahead:
            return keep(
                "local_commits_after_push",
                f"{label}: {len(ahead)} commit(s) on top of origin/{wt.branch}, "
                "made after it merged",
                size,
            )
        detail = f"{label}: merged into {base_ref}"
        if unpushed:
            detail += f"; {len(unpushed)} pre-squash commit(s) superseded"
        return Item(
            "worktree", str(path), size, "REMOVE", "merged_and_clean", detail, branch=wt.branch
        )

    if unpushed:
        return keep("unpushed_commits", f"{label}: {len(unpushed)} commit(s) on no remote", size)

    closed = pr_state(wt.branch, repo)
    if closed:
        return Item(
            "worktree",
            str(path),
            size,
            "REMOVE",
            "pr_closed_branch_fully_pushed",
            f"{label}: PR closed/merged, every commit is on a remote",
            branch=wt.branch,
        )
    if closed is None:
        return keep("unmerged_pr_state_unknown", f"{label}: gh could not answer", size)
    return keep("unmerged_pr_open", f"{label}: PR still open", size)


# --------------------------------------------------------------------------- #
# (c) Docker build cache
# --------------------------------------------------------------------------- #


def docker_keep_flag(help_text: str) -> str:
    """Pick the keep-budget flag this Docker CLI actually has.

    Docker Desktop routes ``docker builder prune`` through buildx, which renamed
    ``--keep-storage`` to ``--reserved-space``. Probing the help text beats
    guessing: a wrong flag makes the prune a no-op that reports success.
    """
    if "--reserved-space" in help_text:
        return "--reserved-space"
    if "--keep-storage" in help_text:
        return "--keep-storage"
    raise Undecidable("docker builder prune has neither --reserved-space nor --keep-storage")


def collect_docker_cache(*, keep_gb: float, docker: str = "docker") -> list[Item]:
    probe = run([docker, "version", "--format", "{{.Server.Version}}"], timeout=20)
    server = (probe.stdout or "").strip()
    if probe.returncode != 0 or not server or "cannot find" in (probe.stderr or ""):
        return [Item("docker", "build-cache", 0, "KEEP", "docker_engine_not_running")]

    helped = run([docker, "builder", "prune", "--help"], timeout=20)
    if helped.returncode != 0:
        # Recognisable help text in a FAILED invocation is not a probe result
        # (Codex round 1, P2): the returncode is the answer, not the stdout.
        return [
            Item(
                "docker",
                "build-cache",
                0,
                "KEEP",
                "prune_flag_unknown",
                f"docker builder prune --help rc={helped.returncode}",
            )
        ]
    try:
        flag = docker_keep_flag(helped.stdout or "")
    except Undecidable as exc:
        return [Item("docker", "build-cache", 0, "KEEP", "prune_flag_unknown", str(exc))]

    df = run([docker, "system", "df", "--format", "{{json .}}"], timeout=40)
    if df.returncode != 0:
        return [
            Item("docker", "build-cache", 0, "KEEP", "docker_df_failed", df.stderr.strip()[:200])
        ]
    reclaimable = _build_cache_reclaimable(df.stdout or "")
    if reclaimable is None:
        return [Item("docker", "build-cache", 0, "KEEP", "build_cache_row_absent")]
    if reclaimable <= 0:
        return [Item("docker", "build-cache", 0, "KEEP", "nothing_reclaimable")]
    return [
        Item(
            "docker",
            "build-cache",
            reclaimable,
            "REMOVE",
            "docker_build_cache",
            f"builder prune {flag}={int(keep_gb * 1024**3)} "
            "(build cache only; never volumes or images)",
            prune_flag=flag,
        )
    ]


def _build_cache_reclaimable(text: str) -> int | None:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("Type", "")).strip().lower() not in {"build cache", "buildcache"}:
            continue
        return parse_docker_size(str(row.get("Reclaimable", "0")))
    return None


_SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}


def parse_docker_size(text: str) -> int:
    """Parse docker's ``"1.234GB (100%)"`` size strings into bytes."""
    match = re.match(r"\s*([0-9.]+)\s*([A-Za-z]*)", text.replace("iB", "B"))
    if not match:
        return 0
    value = float(match.group(1))
    unit = (match.group(2) or "B").lower()
    return int(value * _SIZE_UNITS.get(unit, 1))


# --------------------------------------------------------------------------- #
# (d) repo scratch directories
# --------------------------------------------------------------------------- #


def collect_repo_scratch(repo: Path, *, min_age_days: float, now: float) -> list[Item]:
    items: list[Item] = []
    try:
        children = sorted(repo.iterdir())
    except OSError as exc:
        return [Item("scratch", str(repo), 0, "KEEP", "repo_unreadable", str(exc))]
    for child in children:
        name = child.name
        if name not in SCRATCH_NAMES and not any(fnmatch.fnmatch(name, g) for g in SCRATCH_GLOBS):
            continue
        # git must agree the path is ignored: a tracked or newly-added path is
        # never scratch, whatever it is called.
        if (
            run(["git", "check-ignore", "--quiet", "--", name], cwd=repo, timeout=20).returncode
            != 0
        ):
            items.append(Item("scratch", str(child), 0, "KEEP", "not_git_ignored"))
            continue
        try:
            size, newest = (
                tree_stats(child)
                if child.is_dir()
                else (child.stat().st_size, child.stat().st_mtime)
            )
        except OSError as exc:
            items.append(keep_for("scratch", child, Undecidable(str(exc))))
            continue
        except Undecidable as exc:
            items.append(keep_for("scratch", child, exc))
            continue
        age_days = max(0.0, (now - newest) / 86400.0)
        if age_days < min_age_days:
            items.append(
                Item("scratch", str(child), size, "KEEP", "recent", f"{age_days:.1f}d old")
            )
            continue
        items.append(
            Item(
                "scratch", str(child), size, "REMOVE", "stale_repo_scratch", f"{age_days:.1f}d old"
            )
        )
    return items


# --------------------------------------------------------------------------- #
# removal
# --------------------------------------------------------------------------- #


def remove_path(path: Path) -> tuple[bool, str]:
    """Delete a directory tree or file. One read-only retry, then give up loudly.

    ``shutil.rmtree``'s ``onerror`` is deprecated and ``onexc`` does not exist
    before 3.12, so neither is used: a read-only-attribute failure gets one
    explicit chmod sweep and a single retry instead.

    Refuses a **link** handed to it directly, on either platform. Not because
    ``shutil.rmtree`` would delete through one — it would not;
    ``shutil._rmtree_islink`` recognises ``IO_REPARSE_TAG_MOUNT_POINT`` and a
    2026-09-26 probe confirmed a junction's target survives removal of its parent —
    but because a path whose identity is a name for somewhere else is not a path
    this tool reasoned about when it sized it.
    """
    try:
        if is_link(os.stat(path, follow_symlinks=False)):
            return False, "refusing to delete a link (symlink/junction)"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, ""
    except PermissionError:
        pass
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    try:
        for parent, dirs, files in os.walk(path):
            for name in dirs + files:
                try:
                    os.chmod(os.path.join(parent, name), 0o700)
                except OSError:
                    continue
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    except OSError as exc:
        # rmtree deletes as it walks, so a failure here means the tree is PARTLY
        # gone. Saying so is the honest report (Codex round 1, P2); a bare "kept"
        # would imply the path is intact.
        return False, f"PARTIALLY REMOVED then failed — {type(exc).__name__}: {exc}"
    return True, "removed after chmod retry"


def remove_worktree(repo: Path, item: Item) -> tuple[bool, str]:
    """Remove one worktree via git, archiving its ignored ``_PURPOSE.md`` first.

    ``git worktree remove`` is used **without** ``--force``, so git's own
    cleanliness and lock checks stay in the path as a second net behind this
    script's verdict. The purpose archive reuses ``wt.py`` so an unpublished lane
    draft survives in ``.git/tinyassets-worktrees.log``.

    **A failed archive aborts the removal** when a ``_PURPOSE.md`` exists. The
    first version printed the error and carried on, which defeated the only
    preservation mechanism that file has (Codex round 1, P0) — a disk-full or
    permission error during the archive would have quietly destroyed the draft.
    """
    path = Path(item.path)
    branch = item.branch
    if not branch:
        return False, "no branch recorded on the candidate; refusing to remove"

    # Re-verify at the boundary. Inventory and removal are minutes apart on a full
    # pass, and `git worktree remove` re-checks tracked cleanliness but not ignored
    # content, so a unique ignored file written in between would be destroyed on a
    # verdict that predates it (Codex round 1, answer 6).
    try:
        if dirty_paths(path):
            return False, "changed since inventory: the worktree is now dirty"
        stale = unique_ignored_paths(path)
    except Undecidable as exc:
        return False, f"could not re-verify before removal: {exc}"
    if stale:
        return (
            False,
            f"changed since inventory: ignored content now present ({', '.join(stale[:3])})",
        )

    try:
        import wt  # noqa: PLC0415  (sibling script; only needed on the apply path)

        wt._archive_purpose(repo, path, branch, f"dev_hygiene: {item.reason}")
    except Exception as exc:  # noqa: BLE001 — any failure here must fail closed
        if (path / "_PURPOSE.md").exists():
            return False, f"refusing to remove: could not archive _PURPOSE.md ({exc})"
        print(
            f"  note: purpose archive skipped for {path.name} (none present): {exc}",
            file=sys.stderr,
        )

    proc = run(["git", "worktree", "remove", str(path)], cwd=repo, timeout=120)
    if proc.returncode != 0:
        return False, f"git worktree remove refused: {proc.stderr.strip()[:300]}"
    # The disk win is the worktree; a branch ref is ~41 bytes. So the ref is only
    # deleted for `merged_and_clean`, where the content is provably on the base
    # everything integrates into, and always with `-d` so git's own check is the
    # last word.
    #
    # The PR-closed path keeps its ref deliberately. `-D` would have forced it away
    # on the strength of `git log --not --remotes`, which reads LOCAL tracking refs
    # — and `-d` is no better here, since it also accepts "merged into its
    # upstream" from the same local ref. A tracking ref pruned after the PR closed
    # leaves nothing behind (Codex round 1, answer 7), so the ref stays and is the
    # recovery path.
    if item.reason != "merged_and_clean":
        return True, "worktree removed; branch ref kept as the recovery path"
    delete = run(["git", "branch", "-d", branch], cwd=repo, timeout=60)
    detail = (
        "branch deleted"
        if delete.returncode == 0
        else f"branch kept as the recovery ref ({delete.stderr.strip()[:120]})"
    )
    return True, detail


def prune_docker(item: Item, *, keep_gb: float, docker: str = "docker") -> tuple[bool, str]:
    flag = item.prune_flag
    if not flag:
        return False, "no keep-budget flag recorded on the candidate; refusing to prune"
    proc = run(
        [docker, "builder", "prune", "--force", flag, str(int(keep_gb * 1024**3))], timeout=600
    )
    if proc.returncode != 0:
        return False, f"docker builder prune failed: {proc.stderr.strip()[:300]}"
    tail = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return True, tail[-1].strip() if tail else "pruned"


def apply_removals(
    report: Report,
    repo: Path,
    *,
    keep_gb: float,
    log_path: Path | None,
    max_removals: int = 0,
) -> list[str]:
    """Remove the REMOVE set, at most ``max_removals`` per class (0 = unbounded).

    The per-class cap is the same idea as ``daemon_image_retention.MAX_REMOVALS``
    on the droplet: a pass that runs by itself should never be able to do
    something enormous, so a logic bug costs N items and shows up in the log
    before the next pass. Largest first, so a capped pass still reclaims the most.
    """
    lines: list[str] = []
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    done: dict[str, int] = {}
    order = sorted(report.items, key=lambda i: (i.kind, -i.size_bytes, i.path))
    for item in order:
        if not item.removable:
            continue
        if max_removals and done.get(item.kind, 0) >= max_removals:
            item.verdict = "KEEP"
            item.reason = "deferred_to_next_pass"
            item.detail = f"per-class cap of {max_removals} reached"
            continue
        done[item.kind] = done.get(item.kind, 0) + 1
        if item.kind == "worktree":
            ok, detail = remove_worktree(repo, item)
        elif item.kind == "docker":
            ok, detail = prune_docker(item, keep_gb=keep_gb)
        else:
            ok, detail = remove_path(Path(item.path))
        if ok:
            lines.append(
                f"{stamp} REMOVED {item.kind} {item.path} {human(item.size_bytes)} "
                f"{item.reason} {detail}".rstrip()
            )
        else:
            item.verdict = "KEEP"
            item.reason = "remove_failed"
            item.detail = detail
            lines.append(f"{stamp} FAILED  {item.kind} {item.path} {detail}")
    if log_path is not None and lines:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        except OSError as exc:
            report.notes.append(f"log write failed: {exc}")
    return lines


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def render(report: Report, *, verbose: bool) -> str:
    out: list[str] = []
    verb = "removed" if report.applied else "would remove"
    removes = [i for i in report.items if i.removable]
    keeps = [i for i in report.items if not i.removable]
    out.append(
        f"[dev-hygiene] free {report.free_before_gb:.1f} GB -> {report.free_after_gb:.1f} GB; "
        f"{verb} {len(removes)} item(s), {human(report.reclaimable_bytes)}; kept {len(keeps)}"
    )
    for item in sorted(removes, key=lambda i: -i.size_bytes):
        out.append(
            f"  REMOVE  {item.kind:9} {human(item.size_bytes):>9}  {item.path}  "
            f"[{item.reason}] {item.detail}".rstrip()
        )
    if verbose:
        for item in sorted(keeps, key=lambda i: -i.size_bytes):
            out.append(
                f"  KEEP    {item.kind:9} {human(item.size_bytes):>9}  {item.path}  "
                f"[{item.reason}] {item.detail}".rstrip()
            )
    for note in report.notes:
        out.append(f"  note: {note}")
    return "\n".join(out)


def write_summary(path: Path, report: Report, *, escalation: str, classes: tuple[str, ...]) -> None:
    """Record one compact pass summary. The SessionStart hook reads this file
    instead of re-running a scan, so a session start costs no inventory time."""
    removed = [i for i in report.items if i.removable]
    payload = {
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "finished_epoch": time.time(),
        "classes": list(classes),
        "applied": report.applied,
        "free_before_gb": round(report.free_before_gb, 2),
        "free_after_gb": round(report.free_after_gb, 2),
        "removed_count": len(removed) if report.applied else 0,
        "reclaimable_bytes": report.reclaimable_bytes,
        "escalation": escalation,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        report.notes.append(f"summary write failed: {exc}")


def render_escalation(report: Report, threshold_gb: float) -> str:
    """The founder-facing block: what is left, why it was kept, what to decide."""
    out = [
        f"[dev-hygiene] ESCALATION: {report.free_after_gb:.1f} GB free is below the "
        f"{threshold_gb:.0f} GB floor and the disposable set cannot close the gap.",
        "Largest items this tool refused to remove, with the reason it refused:",
    ]
    keeps = [i for i in report.items if not i.removable and i.reason not in EXPECTED_KEEPS]
    for item in sorted(keeps, key=lambda i: (-i.size_bytes, i.path))[:12]:
        out.append(
            f"  {human(item.size_bytes):>9}  {item.path}  [{item.reason}] {item.detail}".rstrip()
        )
    if not keeps:
        out.append("  (nothing reclaimable was found — the space is real project or system data)")
    locked = [i for i in report.items if i.reason == "acl_locked_needs_elevation"]
    if locked:
        out.append(
            f"  PLUS {len(locked)} temp director(ies) this user cannot read, list, or delete "
            "(sandbox-token ACL; size unknown). Clear them with an ELEVATED shell: "
            "powershell -ExecutionPolicy Bypass -File scripts/clear_sandbox_temp_dirs.ps1 -Apply"
        )
    missing = [c for c in CLASSES if c not in {i.kind for i in report.items}]
    if missing:
        out.append(
            f"  NOT inventoried in this pass: {', '.join(missing)}. "
            "The full pass takes a couple of minutes: python scripts/dev_hygiene.py --verbose"
        )
    out.append(
        "Each of these needs a decision this tool will not make for you: a dirty or "
        "unmerged lane to land or abandon, ignored content that exists nowhere else, "
        "or non-repo data. `python scripts/dev_hygiene.py --verbose` shows the full set."
    )
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def inventory(
    *,
    repo: Path,
    temp_root: Path,
    classes: tuple[str, ...],
    min_age_hours: float,
    min_age_days: float,
    idle_hours: float,
    docker_keep_gb: float,
    now: float,
    deadline: float | None,
    extra_temp_roots: tuple[Path, ...] = (),
) -> list[Item]:
    items: list[Item] = []
    if "basetemp" in classes:
        items += collect_basetemps(temp_root, min_age_hours=min_age_hours, now=now)
        for root in extra_temp_roots:
            items += collect_basetemps(
                root, min_age_hours=min_age_hours, now=now, prefixes=DRIVE_ROOT_PREFIXES
            )
    if "scratch" in classes:
        items += collect_repo_scratch(repo, min_age_days=min_age_days, now=now)
    if "worktree" in classes:
        items += collect_worktrees(repo, now=now, idle_hours=idle_hours, deadline=deadline)
    if "docker" in classes:
        items += collect_docker_cache(keep_gb=docker_keep_gb)
    return items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev_hygiene.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply", action="store_true", help="remove the REMOVE set (default: dry-run)"
    )
    parser.add_argument("--dry-run", action="store_true", help="explicit dry-run (the default)")
    parser.add_argument(
        "--if-low-disk",
        type=float,
        metavar="GB",
        help="apply only when free space is below GB; otherwise report only",
    )
    parser.add_argument(
        "--escalate-below",
        type=float,
        metavar="GB",
        help="exit 3 with a concrete list when free space is still below GB after the pass",
    )
    parser.add_argument(
        "--classes",
        default=",".join(CLASSES),
        help=f"comma-separated subset of {','.join(CLASSES)} (default: all)",
    )
    parser.add_argument(
        "--min-age-hours", type=float, default=6.0, help="basetemp staleness (default 6)"
    )
    parser.add_argument(
        "--min-age-days", type=float, default=7.0, help="repo-scratch staleness (default 7)"
    )
    parser.add_argument(
        "--worktree-idle-hours", type=float, default=24.0, help="worktree idleness (default 24)"
    )
    parser.add_argument(
        "--docker-keep-gb", type=float, default=8.0, help="build-cache keep budget (default 8)"
    )
    parser.add_argument(
        "--max-removals",
        type=int,
        default=25,
        help="per-class cap on removals in one pass, 0 = unbounded (default 25)",
    )
    parser.add_argument("--budget-seconds", type=float, default=0.0, help="0 = unbounded (default)")
    parser.add_argument(
        "--summary-out",
        default="",
        help="write a compact JSON summary of this pass here (the SessionStart hook reads it)",
    )
    parser.add_argument("--repo", default="", help="repository root (default: this script's repo)")
    parser.add_argument("--temp-root", default="", help="OS temp root (default: %%TEMP%%)")
    parser.add_argument(
        "--extra-temp-root",
        action="append",
        default=None,
        metavar="DIR",
        help=(
            "additional basetemp root, scanned for top-level `ta-*` only "
            "(default: the repo's drive root; pass --extra-temp-root '' for none)"
        ),
    )
    parser.add_argument(
        "--log", default="", help=f"append removals here (default: <repo>/{DEFAULT_LOG})"
    )
    parser.add_argument("--no-log", action="store_true", help="do not write the removal log")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument(
        "--verbose", action="store_true", help="also print every KEEP with its reason"
    )
    parser.add_argument("--quiet", action="store_true", help="print only escalations")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parent.parent
    if not (repo / ".git").exists():
        print(f"[dev-hygiene] not a git repository: {repo}", file=sys.stderr)
        return 2
    temp_root = (
        Path(args.temp_root).resolve() if args.temp_root else Path(os.environ.get("TEMP") or "/tmp")
    )
    if args.extra_temp_root is None:
        # Default: the drive the repo lives on, which is where the short
        # MAX_PATH-dodging basetemps land. Data, not a hard-coded "C:\".
        extra_roots: tuple[Path, ...] = (Path(repo.anchor),) if repo.anchor else ()
    else:
        extra_roots = tuple(Path(r).resolve() for r in args.extra_temp_root if r.strip())
    extra_roots = tuple(r for r in extra_roots if r != temp_root)

    classes = tuple(c.strip() for c in args.classes.split(",") if c.strip())
    unknown = [c for c in classes if c not in CLASSES]
    if unknown:
        print(f"[dev-hygiene] unknown class(es): {', '.join(unknown)}", file=sys.stderr)
        return 2

    now = time.time()
    deadline = time.monotonic() + args.budget_seconds if args.budget_seconds > 0 else None
    report = Report(free_before_gb=free_gb(repo))
    report.free_after_gb = report.free_before_gb

    gated = args.if_low_disk is not None and report.free_before_gb >= args.if_low_disk
    if gated:
        report.notes.append(
            f"--if-low-disk {args.if_low_disk:.0f} GB not met "
            f"({report.free_before_gb:.1f} GB free): report only"
        )

    report.items = inventory(
        repo=repo,
        temp_root=temp_root,
        extra_temp_roots=extra_roots,
        classes=classes,
        min_age_hours=args.min_age_hours,
        min_age_days=args.min_age_days,
        idle_hours=args.worktree_idle_hours,
        docker_keep_gb=args.docker_keep_gb,
        now=now,
        deadline=deadline,
    )

    if args.apply and not args.dry_run and not gated:
        log_path = None if args.no_log else (Path(args.log) if args.log else repo / DEFAULT_LOG)
        apply_removals(
            report,
            repo,
            keep_gb=args.docker_keep_gb,
            log_path=log_path,
            max_removals=max(0, args.max_removals),
        )
        report.applied = True
        report.free_after_gb = free_gb(repo)

    escalating = args.escalate_below is not None and report.free_after_gb < args.escalate_below
    escalation = render_escalation(report, args.escalate_below) if escalating else ""

    if args.summary_out:
        write_summary(Path(args.summary_out), report, escalation=escalation, classes=classes)

    if args.json:
        print(
            json.dumps(
                {
                    "free_before_gb": round(report.free_before_gb, 2),
                    "free_after_gb": round(report.free_after_gb, 2),
                    "applied": report.applied,
                    "reclaimable_bytes": report.reclaimable_bytes,
                    "escalating": escalating,
                    "notes": report.notes,
                    "items": [asdict(i) for i in report.items],
                },
                indent=2,
            )
        )
    elif not args.quiet:
        print(render(report, verbose=args.verbose))
    if escalating:
        print(escalation)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
