"""Report git worktree pickup state for multi-provider TinyAssets sessions.

This complements scripts/claim_check.py. claim_check owns STATUS.md file
collisions; this script owns persistent local directories created by
``git worktree add``.

It also reports *independent clones* parked under ``.codex-worktrees/`` (see
``CODEX_CLONE_DIR``). Those are a different kind of thing from a linked
worktree — ``git worktree list`` cannot see them at all — so they are
discovered separately and rendered in their own table rather than being folded
into the worktree list as if they were equivalent.
"""

from __future__ import annotations

import argparse
import io
import json
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from git_squash_merge import is_merged_into  # noqa: E402  (sibling-script import)

STALE_AFTER_SECONDS = 24 * 60 * 60
MAIN_BRANCHES = {"main", "master", "production"}
REQUIRED_PURPOSE_FIELDS = (
    "Purpose:",
    "Provider:",
    "Branch:",
    "Base ref:",
    "STATUS/Issue/PR:",
    "PLAN refs:",
    "Ship condition:",
    "Abandon condition:",
    "Pickup hints:",
    "Memory refs:",
    "Related implications:",
    "Idea feed refs:",
)
STATE_PRIORITY = {
    "MISSING": 0,
    "DIRTY_CURRENT_NEEDS_PURPOSE": 0,
    "DIRTY_CURRENT_CHECKOUT": 1,
    "IN_FLIGHT_NEEDS_PURPOSE": 2,
    "IN_FLIGHT": 3,
    "NEEDS_PURPOSE": 4,
    "PURPOSE_INCOMPLETE": 5,
    "ORPHANED": 6,
    "NEEDS_PR_OR_STATUS": 7,
    "ACTIVE_LANE": 8,
    "PARKED_DRAFT": 9,
    "READY_TO_REMOVE": 10,
}

STATE_MAP_NOTE = (
    "# state map: ACTIVE_LANE/PARKED_DRAFT are canonical lanes; "
    "DIRTY_*/IN_FLIGHT*/NEEDS_*/PURPOSE_INCOMPLETE/ORPHANED/MISSING/"
    "READY_TO_REMOVE are action-required intermediates. "
    "Idea/reference-only lanes live in ideas/*.md or _PURPOSE.md idea refs."
)

# --- independent clones under .codex-worktrees/ -------------------------------
# These are NOT linked worktrees. Each has a real `.git` *directory* (its own
# object store), so `git worktree list` returns none of them — and no script
# scanned the path either. Every coordination tool therefore reported this
# directory as empty while it accumulated finished, unpushed work.
# (`git status` does show it as a single `?? .codex-worktrees/` entry, which
# says nothing about what is inside or whether any of it is published.)

CODEX_CLONE_DIR = ".codex-worktrees"

#: Top-level directory names that are sandbox test scratch, never real work.
#: AGENTS.md §Testing ("Sandbox test-temp hygiene") documents that some agent
#: sandboxes redirect pytest --basetemp *into* the checkout. Those dirs make a
#: clone look dirty and can be ACL-locked against traversal. Matched against the
#: FIRST path segment only — deliberately narrow, so a real file that merely
#: lives under a similarly-named nested dir is still reported as dirty.
SCRATCH_DIR_PREFIXES = (
    ".pytest-tmp",
    ".pytest_cache",
    ".test-tmp",
    ".codex-test-tmp",
    ".workflow-test-data",
)

# Two distinct unpublished states, because they carry different certainty.
# ABSENT is unambiguous: the canonical object store has never seen the commit.
# NO_ORIGIN_REF is weaker: the object exists locally but no origin ref contains
# it — which is ALSO what a squash-merged-then-deleted branch looks like. No
# read-only local graph query can separate those two, so that state explicitly
# routes the operator to PR metadata instead of pretending to know.
CLONE_STATE_PRIORITY = {
    "CLONE_UNPUBLISHED_ABSENT": 0,
    "CLONE_UNPUBLISHED_NO_ORIGIN_REF": 1,
    "CLONE_UNREADABLE": 2,
    "CLONE_UNKNOWN": 3,
    "CLONE_NO_COMMITS": 4,
    "CLONE_NOT_A_REPO": 5,
    "CLONE_PUBLISHED": 6,
}

#: States meaning "commits here may exist nowhere else" — the recovery signal.
CLONE_UNPUBLISHED_STATES = (
    "CLONE_UNPUBLISHED_ABSENT",
    "CLONE_UNPUBLISHED_NO_ORIGIN_REF",
)

CLONE_TABLE_NOTE = (
    "# .codex-worktrees/ — INDEPENDENT CLONES, not linked worktrees. "
    "`git worktree list` cannot see these; they are found by directory scan. "
    "CLONE_UNPUBLISHED_ABSENT = HEAD is not even an object in the canonical "
    "repo — those commits exist ONLY here, unambiguously. "
    "CLONE_UNPUBLISHED_NO_ORIGIN_REF = object exists locally but no "
    "refs/remotes/origin/* contains it; a squash-merged-then-deleted branch "
    "looks identical, so classify by PR state (`--check-prs` / `gh pr view`), "
    "never by reachability alone. "
    "Read-only: this tool never writes to a clone or to your git config."
)

DUBIOUS_OWNERSHIP_REMEDY = (
    'git config --global --add safe.directory "{path}"   '
    "# then re-run; NOT run automatically (read-only tool)"
)


def _force_utf8_stdio() -> None:
    """Keep Windows console encodings from crashing on non-ASCII output."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("_", "-")
        if encoding == "utf-8":
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
                continue
            except (AttributeError, ValueError, OSError):
                pass
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            try:
                setattr(
                    sys,
                    stream_name,
                    io.TextIOWrapper(
                        buffer,
                        encoding="utf-8",
                        errors="replace",
                        newline="\n",
                        line_buffering=True,
                    ),
                )
            except (AttributeError, ValueError, OSError):
                pass


@dataclass
class WorktreeEntry:
    path: str
    head: str | None
    branch_ref: str | None
    detached: bool = False

    @property
    def slug(self) -> str:
        return Path(self.path).name

    @property
    def branch(self) -> str:
        if not self.branch_ref:
            return "(detached HEAD)" if self.detached else "(unknown)"
        prefix = "refs/heads/"
        if self.branch_ref.startswith(prefix):
            return self.branch_ref[len(prefix) :]
        return self.branch_ref


@dataclass
class WorktreeStatus:
    slug: str
    path: str
    branch: str
    head: str | None
    state: str
    age_hours: float | None
    upstream: str
    dirty: bool
    current: bool
    live_safety: str
    status_ref: bool
    purpose_exists: bool
    purpose_missing_fields: list[str]
    purpose: str
    memory_refs: list[str]
    action: str


@dataclass
class CloneStatus:
    """State of one independent clone under .codex-worktrees/."""

    slug: str
    path: str
    kind: str
    state: str
    branch: str
    head: str | None
    published: str
    origin_refs: list[str]
    dirty: str
    dirty_paths: list[str]
    scratch_ignored: int
    pr: str
    action: str
    remedy: str | None = None
    memory_refs: list[str] = field(default_factory=list)


def discover_clone_dirs(repo: Path, clone_dir: str = CODEX_CLONE_DIR) -> list[Path]:
    """List candidate clone directories. Never recurses — one listdir only.

    `du -sh .codex-worktrees` times out (>120s) on this repo, so nothing here
    may walk the trees. Non-directories (e.g. a stray `*.bundle`) are skipped.
    """
    root = repo / clone_dir
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    dirs: list[Path] = []
    for entry in entries:
        try:
            if entry.is_dir():
                dirs.append(entry)
        except OSError:
            # Unreadable entry: still surface it rather than dropping it.
            dirs.append(entry)
    return dirs


def _scratch_first_segment(path_text: str) -> bool:
    normalised = path_text.strip().strip('"').replace("\\", "/")
    # Strip a leading "./" only. NOT lstrip("./") — that strips a character set
    # and would eat the leading dot of ".pytest-tmp", so nothing would match.
    if normalised.startswith("./"):
        normalised = normalised[2:]
    first = normalised.split("/", 1)[0]
    return any(first.startswith(prefix) for prefix in SCRATCH_DIR_PREFIXES)


def split_porcelain_paths(text: str) -> tuple[list[str], int]:
    """Split `git status --porcelain` output into (real changes, scratch count).

    Only UNTRACKED (`??`) entries under a root-anchored scratch directory are
    suppressed. Tracked modifications, deletions and renames are always real,
    even under a scratch path: `.codex-worktrees/wf-unified-authority` has 65
    *tracked* `.test-tmp/...` files showing as ` D` deletions, and filtering
    those by pathname would report a genuinely diverged clone as clean —
    concealing exactly the kind of state this tool exists to surface.
    """
    real: list[str] = []
    scratch = 0
    for raw in text.splitlines():
        if not raw.strip():
            continue
        # Porcelain v1: 'XY <path>' with the path at column 3; renames use
        # '<old> -> <new>' and the destination is what matters.
        code = raw[:2]
        payload = raw[3:] if len(raw) > 3 else raw.strip()
        candidate = payload.split(" -> ")[-1]
        if code == "??" and _scratch_first_segment(candidate):
            scratch += 1
        else:
            real.append(candidate.strip().strip('"'))
    return real, scratch


def _clone_head(path: Path) -> tuple[str | None, str | None, str | None]:
    """Return (sha, branch, failure-kind) for a clone.

    failure-kind is 'ownership' (sandbox-owned dir git refuses to read),
    'no-repo', 'no-commits' (unborn HEAD), or None on success.
    """
    if not (path / ".git").exists():
        return None, None, "no-repo"
    result = run_git(["rev-parse", "HEAD", "--abbrev-ref", "HEAD"], path)
    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "dubious ownership" in stderr:
            return None, None, "ownership"
        if "ambiguous argument 'head'" in stderr or "unknown revision" in stderr:
            return None, None, "no-commits"
        return None, None, "no-repo"
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return None, None, "no-commits"
    return lines[0], lines[1], None


def _published_state(repo: Path, sha: str) -> tuple[str, list[str]]:
    """Is `sha` reachable from any ref under refs/remotes/origin?

    Asked of the CANONICAL repo (freshly fetched), not the clone: a clone's own
    remote refs may be stale or never fetched. If the object is absent from the
    canonical store the answer is unambiguous — it was never pushed.
    """
    result = run_git(
        ["for-each-ref", "--contains", sha, "--format=%(refname)", "refs/remotes/origin"],
        repo,
    )
    if result.returncode != 0:
        stderr = result.stderr.lower()
        # The canonical store does not have the object at all. git says
        # "error: no such commit <sha>" here (NOT "not a valid object", which is
        # what cat-file says) — so this must match on the for-each-ref wording.
        # Absent from the canonical store => it was never pushed anywhere.
        absent_markers = ("no such commit", "not a valid object", "malformed object")
        if any(marker in stderr for marker in absent_markers):
            return "absent", []
        return "unknown", []
    # Only an exit-0 run makes "no refs printed" meaningful; a missing object
    # exits 129 and is handled above, so empty-here really does mean "no origin
    # ref contains this commit".
    refs = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return ("origin" if refs else "no-origin-ref"), refs


def probe_clone(repo: Path, path: Path, pr_index: dict[str, str] | None = None) -> CloneStatus:
    """Read-only inspection of a single clone. Three git calls, no tree walk."""
    slug = path.name
    base = CloneStatus(
        slug=slug,
        path=str(path),
        kind="independent-clone",
        state="CLONE_NOT_A_REPO",
        branch="-",
        head=None,
        published="unknown",
        origin_refs=[],
        dirty="-",
        dirty_paths=[],
        scratch_ignored=0,
        pr="-",
        action="Not a git repo; inspect by hand before any cleanup.",
    )

    sha, branch, failure = _clone_head(path)
    if failure == "ownership":
        base.state = "CLONE_UNREADABLE"
        base.remedy = DUBIOUS_OWNERSHIP_REMEDY.format(path=Path(path).as_posix())
        base.action = (
            "git refuses this dir (sandbox-owned). Publication state UNKNOWN — "
            "it may hold unpushed work. Run the remedy, then re-run."
        )
        return base
    if failure == "no-commits":
        base.state = "CLONE_NO_COMMITS"
        base.action = "Clone has no commits (unborn HEAD); nothing to recover."
        return base
    if failure is not None or sha is None or branch is None:
        return base

    base.head = sha
    base.branch = branch
    published, refs = _published_state(repo, sha)
    base.published = published
    base.origin_refs = refs

    status = run_git(["status", "--porcelain"], path)
    # ACL-locked scratch dirs emit "Permission denied" warnings on stderr but
    # git still exits 0 and reports the rest of the tree; only a hard failure
    # means we could not read the worktree.
    if status.returncode == 0:
        real, scratch = split_porcelain_paths(status.stdout)
        base.scratch_ignored = scratch
        base.dirty_paths = real[:20]
        base.dirty = "yes" if real else ("scratch" if scratch else "-")
    else:
        base.dirty = "unknown"

    if pr_index is not None:
        base.pr = pr_index.get(branch, "none")

    # Fail closed. "unknown" must never be reported as published: telling an
    # operator that unpushed work is safe is the one error this tool exists to
    # prevent, so an indeterminate answer gets its own state.
    base.state = {
        "absent": "CLONE_UNPUBLISHED_ABSENT",
        "no-origin-ref": "CLONE_UNPUBLISHED_NO_ORIGIN_REF",
        "origin": "CLONE_PUBLISHED",
    }.get(published, "CLONE_UNKNOWN")
    base.action = _clone_action(base)
    return base


def _clone_action(clone: CloneStatus) -> str:
    if clone.state in CLONE_UNPUBLISHED_STATES:
        head = (clone.head or "")[:8]
        if clone.state == "CLONE_UNPUBLISHED_ABSENT":
            detail = (
                f"UNPUBLISHED: {head} on '{clone.branch}' is not an object in "
                "the canonical repo at all — these commits exist ONLY here. "
                "Recover by pushing the branch (separate lane)."
            )
        else:
            detail = (
                f"UNPUBLISHED?: {head} on '{clone.branch}' is on no origin ref. "
                "Could be unpushed work OR a squash-merged branch. Classify via "
                "`gh pr view {branch}` before acting; do not sweep on this alone."
            ).replace("{branch}", clone.branch)
        if clone.dirty == "yes":
            detail += " Also has uncommitted changes."
        return detail
    if clone.state == "CLONE_UNKNOWN":
        return (
            "Publication state INDETERMINATE (git could not answer). Treat as "
            "possibly-unpublished; do not sweep until resolved by hand."
        )
    if clone.dirty == "yes":
        return "Published HEAD, but uncommitted changes remain; inspect before sweep."
    return "Published; HEAD is reachable from origin. No recovery action."


def collect_clones(
    repo: Path,
    clone_dir: str = CODEX_CLONE_DIR,
    *,
    pr_index: dict[str, str] | None = None,
    workers: int = 8,
) -> list[CloneStatus]:
    """Probe every clone concurrently. Each probe is independent subprocesses."""
    paths = discover_clone_dirs(repo, clone_dir)
    if not paths:
        return []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(lambda p: probe_clone(repo, p, pr_index), paths))
    results.sort(key=lambda c: (CLONE_STATE_PRIORITY.get(c.state, 99), c.slug))
    return results


def build_pr_index(repo: Path) -> dict[str, str]:
    """One batched `gh` call mapping branch -> PR number/state. Network; opt-in."""
    result = subprocess.run(
        [
            "gh", "pr", "list", "--state", "all", "--limit", "300",
            "--json", "number,state,headRefName",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return {}
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    index: dict[str, str] = {}
    for row in rows:
        branch = row.get("headRefName")
        if branch and branch not in index:
            index[branch] = f"#{row.get('number')}:{str(row.get('state', '')).lower()}"
    return index


def render_clone_table(clones: list[CloneStatus]) -> str:
    if not clones:
        return f"# no independent clones found under {CODEX_CLONE_DIR}/"
    headers = ("SLUG", "STATE", "PUBLISHED", "DIRTY", "SCRATCH", "PR", "BRANCH", "HEAD", "ACTION")
    rows = [
        (
            c.slug[:38],
            c.state,
            c.published,
            c.dirty,
            str(c.scratch_ignored) if c.scratch_ignored else "-",
            c.pr,
            c.branch[:44],
            (c.head or "-")[:8],
            c.action,
        )
        for c in clones
    ]
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [CLONE_TABLE_NOTE, fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    lines.extend(fmt.format(*row) for row in rows)
    unreadable = [c for c in clones if c.remedy]
    if unreadable:
        lines.append("")
        lines.append(
            "# unreadable clones — run these yourself; "
            "the tool will not touch your git config:"
        )
        lines.extend(f"#   {c.remedy}" for c in unreadable)
    absent = sum(1 for c in clones if c.state == "CLONE_UNPUBLISHED_ABSENT")
    no_ref = sum(1 for c in clones if c.state == "CLONE_UNPUBLISHED_NO_ORIGIN_REF")
    lines.append("")
    lines.append(
        f"# {len(clones)} clone(s); {absent + no_ref} with UNPUBLISHED commits "
        f"({absent} certain, {no_ref} need PR classification); "
        f"{len(unreadable)} unreadable."
    )
    return "\n".join(lines)


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(
            ["git", *args],
            127,
            "",
            str(exc),
        )


def parse_porcelain(text: str) -> list[WorktreeEntry]:
    entries: list[WorktreeEntry] = []
    current: dict[str, str | bool] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if current:
                entries.append(_entry_from_dict(current))
                current = None
            continue
        if line.startswith("worktree "):
            if current:
                entries.append(_entry_from_dict(current))
            current = {"path": line[len("worktree ") :]}
            continue
        if current is None:
            continue
        if line.startswith("HEAD "):
            current["head"] = line[len("HEAD ") :]
        elif line.startswith("branch "):
            current["branch_ref"] = line[len("branch ") :]
        elif line == "detached":
            current["detached"] = True
    if current:
        entries.append(_entry_from_dict(current))
    return entries


def _entry_from_dict(data: dict[str, str | bool]) -> WorktreeEntry:
    return WorktreeEntry(
        path=str(data.get("path", "")),
        head=str(data["head"]) if data.get("head") else None,
        branch_ref=str(data["branch_ref"]) if data.get("branch_ref") else None,
        detached=bool(data.get("detached", False)),
    )


def collect_worktrees(repo: Path) -> list[WorktreeEntry]:
    result = run_git(["worktree", "list", "--porcelain"], repo)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "git worktree list failed")
    return parse_porcelain(result.stdout)


def build_status(
    entry: WorktreeEntry,
    now: float | None = None,
    *,
    repo: Path | None = None,
    status_text: str = "",
) -> WorktreeStatus:
    now = time.time() if now is None else now
    path = Path(entry.path)
    if not path.exists():
        return WorktreeStatus(
            slug=entry.slug,
            path=entry.path,
            branch=entry.branch,
            head=entry.head,
            state="MISSING",
            age_hours=None,
            upstream="missing",
            dirty=False,
            current=False,
            live_safety=_live_safety(entry.branch),
            status_ref=_has_status_ref(status_text, entry),
            purpose_exists=False,
            purpose_missing_fields=list(REQUIRED_PURPOSE_FIELDS),
            purpose="-",
            memory_refs=[],
            action=(
                "Worktree path missing; log sweep/prune only after extracting "
                "useful branch or PR ideas."
            ),
        )
    dirty = _is_dirty(path)
    age = _last_commit_age_hours(path, now)
    upstream = _upstream_state(path, entry)
    purpose_exists, purpose = _purpose(path)
    missing_fields = _purpose_missing_fields(path)
    memory_refs = _memory_refs(path)
    current = _is_current_worktree(path, repo)
    status_ref = _has_status_ref(status_text, entry)
    live_safety = _live_safety(entry.branch)
    fully_merged = _is_fully_merged(path, entry)
    state = classify(
        dirty=dirty,
        purpose_exists=purpose_exists,
        purpose_complete=not missing_fields,
        age_hours=age,
        upstream=upstream,
        current=current,
        status_ref=status_ref,
        branch=entry.branch,
        fully_merged=fully_merged,
    )
    action = _action_for_state(
        state=state,
        current=current,
        live_safety=live_safety,
        status_ref=status_ref,
    )
    return WorktreeStatus(
        slug=entry.slug,
        path=entry.path,
        branch=entry.branch,
        head=entry.head,
        state=state,
        age_hours=age,
        upstream=upstream,
        dirty=dirty,
        current=current,
        live_safety=live_safety,
        status_ref=status_ref,
        purpose_exists=purpose_exists,
        purpose_missing_fields=missing_fields,
        purpose=purpose,
        memory_refs=memory_refs,
        action=action,
    )


def classify(
    *,
    dirty: bool,
    purpose_exists: bool,
    purpose_complete: bool = True,
    age_hours: float | None,
    upstream: str,
    current: bool = False,
    status_ref: bool = False,
    branch: str = "",
    fully_merged: bool = False,
) -> str:
    if dirty and current and not purpose_exists:
        return "DIRTY_CURRENT_NEEDS_PURPOSE"
    if dirty and current:
        return "DIRTY_CURRENT_CHECKOUT"
    if dirty and not purpose_exists:
        return "IN_FLIGHT_NEEDS_PURPOSE"
    if dirty:
        return "IN_FLIGHT"
    old = age_hours is not None and age_hours >= 24
    if fully_merged and not _is_main_branch(branch):
        return "READY_TO_REMOVE"
    if upstream == "gone":
        return "READY_TO_REMOVE"
    if not purpose_exists and old and upstream in {"none", "gone", "detached"}:
        return "ORPHANED"
    if not purpose_exists:
        return "NEEDS_PURPOSE"
    if not purpose_complete:
        return "PURPOSE_INCOMPLETE"
    if purpose_exists and not old and upstream in {"tracking", "ahead-behind"}:
        return "ACTIVE_LANE" if status_ref else "PARKED_DRAFT"
    if purpose_exists and old:
        return "ACTIVE_LANE" if status_ref else "PARKED_DRAFT"
    if status_ref:
        return "ACTIVE_LANE"
    if upstream in {"none", "detached"} and not _is_main_branch(branch):
        return "NEEDS_PR_OR_STATUS"
    return "PARKED_DRAFT"


def _is_dirty(path: Path) -> bool:
    result = run_git(["status", "--short"], path)
    return bool(result.stdout.strip()) if result.returncode == 0 else False


def _last_commit_age_hours(path: Path, now: float) -> float | None:
    result = run_git(["log", "-1", "--format=%ct"], path)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return max(0.0, (now - int(result.stdout.strip())) / 3600)


def _upstream_state(path: Path, entry: WorktreeEntry) -> str:
    if entry.detached or not entry.branch_ref:
        return "detached"
    branch = entry.branch
    upstream = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], path)
    if upstream.returncode != 0:
        return "none"
    track = run_git(["for-each-ref", "--format=%(upstream:track)", f"refs/heads/{branch}"], path)
    if "[gone]" in track.stdout:
        return "gone"
    if track.stdout.strip():
        return "ahead-behind"
    return "tracking"


def _is_fully_merged(path: Path, entry: WorktreeEntry) -> bool:
    if entry.detached or not entry.head or not entry.branch_ref:
        return False
    branch = entry.branch
    if _is_main_branch(branch):
        return False
    # Squash-aware: PRs here squash-merge, so a plain --is-ancestor check would
    # leave clean squash-merged lanes mislabelled instead of READY_TO_REMOVE.
    # is_merged_into prepends "git"; run_git takes args without it, so drop a[0].
    def _run(a: list[str]) -> subprocess.CompletedProcess[str]:
        return run_git(list(a)[1:], path)

    for base in _merge_base_candidates(path):
        if is_merged_into(_run, entry.head, base):
            return True
    return False


def _merge_base_candidates(path: Path) -> list[str]:
    candidates = [
        "refs/remotes/origin/main",
        "refs/remotes/origin/master",
        "refs/remotes/origin/production",
        "refs/heads/main",
        "refs/heads/master",
        "refs/heads/production",
    ]
    existing: list[str] = []
    for candidate in candidates:
        result = run_git(["rev-parse", "--verify", "--quiet", candidate], path)
        if result.returncode == 0 and result.stdout.strip():
            existing.append(candidate)
    return existing


def _purpose(path: Path) -> tuple[bool, str]:
    purpose = path / "_PURPOSE.md"
    if not purpose.exists():
        return False, "-"
    for line in purpose.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip(" -")
        if stripped and stripped not in {"---", "# Purpose"}:
            return True, stripped[:90]
    return True, "(empty _PURPOSE.md)"


def _purpose_missing_fields(path: Path) -> list[str]:
    purpose = path / "_PURPOSE.md"
    if not purpose.exists():
        return list(REQUIRED_PURPOSE_FIELDS)
    text = purpose.read_text(encoding="utf-8", errors="replace").lower()
    return [field for field in REQUIRED_PURPOSE_FIELDS if field.lower() not in text]


def _memory_refs(path: Path) -> list[str]:
    purpose = path / "_PURPOSE.md"
    if not purpose.exists():
        return []
    refs: list[str] = []
    in_memory_refs = False
    for line in purpose.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip(" -")
        lowered = stripped.lower()
        if lowered.startswith("memory refs:") or lowered.startswith("prior-provider memory refs:"):
            in_memory_refs = True
            if stripped.partition(":")[2].strip():
                refs.append(stripped)
            continue
        if in_memory_refs and _looks_like_purpose_heading(stripped):
            in_memory_refs = False
        if in_memory_refs and stripped:
            refs.append(stripped)
        elif _known_memory_ref(stripped):
            refs.append(stripped)
    return refs


def _looks_like_purpose_heading(text: str) -> bool:
    return any(text.lower().startswith(field.lower()) for field in REQUIRED_PURPOSE_FIELDS)


def _known_memory_ref(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            ".agents/activity.log",
            ".claude/agent-memory/",
            ".claude/projects/",
            ".codex/",
            ".cursor/",
            ".cursorrules",
            "copilot memory",
            "jules memory",
        )
    )


def _is_current_worktree(path: Path, repo: Path | None) -> bool:
    if repo is None:
        return False
    try:
        return path.resolve() == repo.resolve()
    except OSError:
        return False


def _is_main_branch(branch: str) -> bool:
    return branch.lower() in MAIN_BRANCHES


def _live_safety(branch: str) -> str:
    if branch == "(detached HEAD)":
        return "DETACHED"
    if _is_main_branch(branch):
        return "LIVE_MAIN"
    return "ISOLATED_UNTIL_MERGED"


def _has_status_ref(status_text: str, entry: WorktreeEntry) -> bool:
    haystack = status_text.lower()
    if not haystack:
        return False
    needles = {entry.slug.lower(), Path(entry.path).as_posix().lower()}
    branch = entry.branch.lower()
    if branch and branch not in MAIN_BRANCHES and not branch.startswith("("):
        needles.add(branch)
    return any(needle and needle in haystack for needle in needles)


def _action_for_state(
    *,
    state: str,
    current: bool,
    live_safety: str,
    status_ref: bool,
) -> str:
    current_warning = " Do not switch this dirty checkout to main." if current else ""
    if state == "DIRTY_CURRENT_NEEDS_PURPOSE":
        return "Add _PURPOSE.md before continuing; finish or isolate work." + current_warning
    if state == "DIRTY_CURRENT_CHECKOUT":
        return (
            "Dirty current lane; finish, commit, or park before branch changes."
            + current_warning
        )
    if state == "IN_FLIGHT_NEEDS_PURPOSE":
        return "Dirty lane without durable memory; add _PURPOSE.md immediately."
    if state == "IN_FLIGHT":
        return "Dirty lane; pickup only after reading purpose/STATUS/PR context."
    if state == "NEEDS_PURPOSE":
        return "Add _PURPOSE.md or sweep after extracting useful ideas."
    if state == "PURPOSE_INCOMPLETE":
        return "Complete _PURPOSE.md template fields before pickup or PR."
    if state == "ORPHANED":
        return "Extract useful ideas, log abandoned/swept, then remove worktree."
    if state == "NEEDS_PR_OR_STATUS":
        return "Promote to STATUS if active, or push branch and open draft PR."
    if state == "ACTIVE_LANE":
        return "Pickup through STATUS Files/Depends/Status; do not bypass gates."
    if state == "PARKED_DRAFT":
        prefix = "Confirm draft PR/body has blockers, gates, memory refs."
        if not status_ref:
            return prefix
        return "STATUS-backed parked lane; confirm PR before foldback."
    if state == "READY_TO_REMOVE":
        return "Log remove/sweep in .agents/worktrees.md after ideas are extracted."
    if live_safety == "LIVE_MAIN":
        return "Main worktree; production-impacting changes require live gates."
    return "Inspect before pickup."


def render_table(statuses: list[WorktreeStatus]) -> str:
    headers = (
        "SLUG",
        "STATE",
        "CUR",
        "DIRTY",
        "LIVE",
        "UPSTREAM",
        "BRANCH",
        "AGE_H",
        "MEM",
        "ACTION",
        "PURPOSE",
    )
    rows = [
        (
            s.slug[:30],
            s.state,
            "yes" if s.current else "-",
            "yes" if s.dirty else "-",
            s.live_safety,
            s.upstream,
            s.branch[:44],
            "-" if s.age_hours is None else f"{s.age_hours:.1f}",
            str(len(s.memory_refs)),
            s.action,
            s.purpose,
        )
        for s in statuses
    ]
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [
        STATE_MAP_NOTE,
        fmt.format(*headers),
        fmt.format(*("-" * w for w in widths)),
    ]
    lines.extend(fmt.format(*row) for row in rows)
    return "\n".join(lines)


def sweep_commands(statuses: list[WorktreeStatus]) -> list[str]:
    commands: list[str] = []
    for status in statuses:
        if status.state not in {"ORPHANED", "READY_TO_REMOVE"}:
            continue
        commands.append(f"git worktree remove {shlex.quote(status.path)}")
        if status.state == "READY_TO_REMOVE" and _branch_can_be_deleted(status.branch):
            # -D, not -d: READY_TO_REMOVE means proven-merged (squash-aware), but
            # `git branch -d` is ancestor-based and would refuse a squash-merged
            # branch, leaving it behind when the printed commands are run.
            commands.append(f"git branch -D {shlex.quote(status.branch)}")
    return commands


def _branch_can_be_deleted(branch: str) -> bool:
    return bool(branch and not branch.startswith("(") and not _is_main_branch(branch))


def main(argv: list[str]) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    parser.add_argument("--provider", help="Filter by provider/branch/slug substring.")
    parser.add_argument(
        "--sweep-orphaned",
        action="store_true",
        help=(
            "Print cleanup commands for ORPHANED entries and fully merged "
            "READY_TO_REMOVE branches. Dry-run only."
        ),
    )
    parser.add_argument(
        "--no-clones",
        action="store_true",
        help=f"Skip the {CODEX_CLONE_DIR}/ independent-clone scan.",
    )
    parser.add_argument(
        "--clones-only",
        action="store_true",
        help=f"Report only {CODEX_CLONE_DIR}/ clones; skip git worktrees.",
    )
    parser.add_argument(
        "--check-prs",
        action="store_true",
        help=(
            "Resolve each clone branch to a PR via one batched `gh pr list` "
            "call (network; off by default to keep session start fast)."
        ),
    )
    args = parser.parse_args(argv)

    repo = Path.cwd()
    status_text = _read_status_text(repo)
    statuses: list[WorktreeStatus] = []
    if not args.clones_only:
        statuses = [
            build_status(entry, repo=repo, status_text=status_text)
            for entry in collect_worktrees(repo)
        ]
    if args.provider:
        needle = args.provider.lower()
        statuses = [
            s
            for s in statuses
            if needle in s.slug.lower() or needle in s.branch.lower() or needle in s.path.lower()
        ]
    statuses.sort(key=lambda s: (STATE_PRIORITY.get(s.state, 99), s.slug))

    # `--json` without --clones-only keeps emitting a bare LIST of worktrees.
    # scripts/wt.py iterates that list (a dict would make `wt.py sweep` raise
    # AttributeError) and command_center/collector.py drops anything that is not
    # a list, so the shape is a contract. Clones get their own `--json
    # --clones-only` list rather than a new key. That also means the plain
    # `--json` path skips the clone scan entirely, so wt.py pays nothing for it.
    scan_clones = not args.no_clones and not (args.json and not args.clones_only)
    clones: list[CloneStatus] = []
    if scan_clones:
        pr_index = build_pr_index(repo) if args.check_prs else None
        clones = collect_clones(repo, pr_index=pr_index)
        if args.provider:
            needle = args.provider.lower()
            clones = [
                c
                for c in clones
                if needle in c.slug.lower()
                or needle in c.branch.lower()
                or needle in c.path.lower()
            ]

    if args.json:
        records = (
            [asdict(clone) for clone in clones]
            if args.clones_only
            else [asdict(status) for status in statuses]
        )
        print(json.dumps(records, indent=2))
    else:
        if not args.clones_only:
            print(render_table(statuses))
        if not args.no_clones:
            print()
            print(render_clone_table(clones))

    if args.sweep_orphaned:
        print("\n# Dry-run orphan/removable sweep commands")
        for command in sweep_commands(statuses):
            print(command)
        print("# Log any removal in .agents/worktrees.md before running it.")
    return 0


def _read_status_text(repo: Path) -> str:
    path = repo / "STATUS.md"
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
