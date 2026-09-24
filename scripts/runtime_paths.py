#!/usr/bin/env python3
"""Does a commit range change what production runs? The deploy chain's one classifier.

Every deploy recreates the daemon container, and a recreate kills every
in-flight user turn and run. So a merge that changes nothing production runs
must not deploy -- and a merge that changes anything it runs must never be
skipped. This module is the single answer to "is this range runtime-affecting?"
for all three places that ask it:

* ``build-image.yml`` -- skip building (and therefore deploying) when the pushed
  head is runtime-equivalent to the sha production's receipt names.
* ``release-reconcile.yml`` -- the drift backstop asks for the newest
  runtime-affecting commit, so a skipped merge is never reported as drift and
  never re-deployed by the timer.
* ``deployed_sha.py --assert-contains`` -- a commit that is runtime-equivalent
  to the served sha is reported as served (exit 0, labelled as such), because
  the running image's source tree equals it on every runtime path.

What counts as runtime is read MECHANICALLY from the tree being judged, never
from a hand-kept list that can drift:

* every source of a ``COPY``/``ADD`` in the head's ``Dockerfile`` (plus the
  Dockerfile and ``.dockerignore`` themselves);
* every file ``deploy/install-host-uptime-services.sh`` installs on the host
  (its ``RUNTIME_FILES`` array), all of ``deploy/``, and the few scripts the
  deploy workflows ship to the host (:data:`HOST_SCRIPTS`);
* ``PLAN.md`` is copied into the image, but the daemon serves only a
  1400-character excerpt of each section named by ``_CHANGE_LOOP_PLAN_HEADINGS``
  (``_change_loop_plan_context`` in ``tinyassets/api/universe.py``). A
  ``PLAN.md`` change is runtime exactly when one of those served excerpts
  changed. The headings and the excerpt length are read from the head tree's
  own source, so a code change that serves more is itself a runtime change and
  deploys; if either cannot be read, the whole file counts.

**Fail open.** Anything this module cannot establish -- an unreadable
Dockerfile, a wildcard ``COPY``, an unknown production sha, a production sha
that is not an ancestor of the head, a git failure -- is answered "runtime /
build". It errs toward a redundant deploy, never toward skipping a change.

Stdlib only: it runs in privileged workflow jobs that install nothing.

    python scripts/runtime_paths.py decide --base <served-sha> --head <sha>
    python scripts/runtime_paths.py newest-runtime-commit --rev <sha>
    python scripts/runtime_paths.py classify --base <sha> --head <sha>
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOCKERFILE = "Dockerfile"
HOST_MANIFEST = "deploy/install-host-uptime-services.sh"
UNIVERSE_MODULE = "tinyassets/api/universe.py"
PLAN = "PLAN.md"
PLAN_HEADINGS_NAME = "_CHANGE_LOOP_PLAN_HEADINGS"

#: Changes to these always change production, whatever the Dockerfile says.
BUILD_DEFINITION = (DOCKERFILE, ".dockerignore")

#: Host inputs that are not in the image. ``deploy/`` is the compose bundle,
#: the fail-safe deploy script and every systemd unit; the scripts are the ones
#: ``deploy-prod.yml`` / ``install-host-services.yml`` put on the host (or whose
#: output they install there). A test asserts every ``scripts/*.py`` those two
#: workflows name is classified runtime, except the runner-only verifiers.
HOST_PATHS = ("deploy/",)
HOST_SCRIPTS = (
    "scripts/github-app-token-refresher.py",
    "scripts/retire_cheat_loop_deploy_fence.py",
    "scripts/prepare_expected_instance_state.py",
)

#: How far back ``newest-runtime-commit`` walks before giving up. Giving up
#: returns the starting commit, i.e. "treat it as runtime" (fail open).
DEFAULT_WALK_LIMIT = 2000

_GLOB_CHARS = re.compile(r"[*?\[]")


class ClassifyError(Exception):
    """git could not answer; callers must treat the range as runtime."""


# --- git -------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _git_ok(repo: Path, *args: str) -> str:
    proc = _git(repo, *args)
    if proc.returncode != 0:
        raise ClassifyError(f"git {' '.join(args)}: {(proc.stderr or '').strip()}")
    return proc.stdout


def _show(repo: Path, rev: str, path: str) -> str | None:
    """File content at ``rev``; None ONLY when the path is absent from that tree.

    Any other failure raises: reading "absent" on both sides of a PLAN.md
    comparison would make a git error look like "nothing served changed".
    """
    proc = _git(repo, "show", f"{rev}:{path}")
    if proc.returncode == 0:
        return proc.stdout
    if _git(repo, "cat-file", "-e", f"{rev}^{{commit}}").returncode != 0:
        raise ClassifyError(f"git show {rev}:{path}: {(proc.stderr or '').strip()}")
    if _git(repo, "cat-file", "-e", f"{rev}:{path}").returncode == 0:
        raise ClassifyError(f"git show {rev}:{path}: {(proc.stderr or '').strip()}")
    return None


def resolve(repo: Path, rev: str) -> str:
    return _git_ok(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return _git(repo, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0


# --- what the tree says is runtime ----------------------------------------


def _logical_lines(text: str) -> list[str]:
    """Dockerfile lines with ``\\`` continuations joined and comments dropped."""
    lines: list[str] = []
    buf = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not buf and (not stripped or stripped.startswith("#")):
            continue
        if buf and stripped.startswith("#"):
            continue  # comment lines inside a continuation are ignored by docker
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
            continue
        lines.append(buf + stripped)
        buf = ""
    if buf:
        lines.append(buf)
    return lines


def dockerfile_copy_sources(text: str) -> tuple[list[str], bool]:
    """Build-context sources of every ``COPY``/``ADD``.

    Returns ``(sources, everything)``. ``everything`` is True when a source
    cannot be bounded to a path -- ``.``, a wildcard at the context root, an
    unparseable JSON form -- so every path must count as runtime (fail open).
    Copies ``--from`` another stage read no build context and are skipped.
    """
    sources: list[str] = []
    everything = False
    for line in _logical_lines(text):
        parts = line.split(None, 1)
        if len(parts) < 2 or parts[0].upper() not in {"COPY", "ADD"}:
            continue
        rest = parts[1].strip()
        tokens: list[str] = []
        flags: list[str] = []
        # Flags always precede the operands, in both the shell and JSON forms.
        while rest.startswith("--"):
            flag, _, rest = rest.partition(" ")
            flags.append(flag)
            rest = rest.strip()
        if any(flag.startswith("--from") for flag in flags):
            continue
        if rest.startswith("["):
            try:
                parsed = json.loads(rest)
            except json.JSONDecodeError:
                everything = True
                continue
            if not isinstance(parsed, list) or not all(isinstance(t, str) for t in parsed):
                everything = True
                continue
            tokens = parsed
        else:
            tokens = rest.split()
        if len(tokens) < 2:
            everything = True
            continue
        for src in tokens[:-1]:
            if src.startswith("<<"):
                continue  # heredoc body: no build-context input
            if re.match(r"^[a-z][a-z0-9+.-]*://", src, re.IGNORECASE):
                continue  # remote ADD: not a repo path
            normalized = src
            while normalized.startswith("./"):
                normalized = normalized[2:]
            normalized = normalized.lstrip("/")
            match = _GLOB_CHARS.search(normalized)
            if match:
                # Bound a wildcard by the directory it sits under.
                normalized = normalized[: match.start()].rpartition("/")[0]
            normalized = normalized.rstrip("/")
            if normalized in {"", "."}:
                everything = True
                continue
            sources.append(normalized)
    return sources, everything


def host_manifest_files(text: str) -> list[str] | None:
    """The ``RUNTIME_FILES=( ... )`` array of the host-uptime installer."""
    match = re.search(r"^RUNTIME_FILES=\(\s*\n(.*?)^\)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return None
    files: list[str] = []
    for raw in match.group(1).splitlines():
        item = raw.split("#", 1)[0].strip().strip("'\"")
        if item:
            files.append(item)
    return files


PLAN_CONTEXT_FUNCTION = "_change_loop_plan_context"
PLAN_SHORTEN_FUNCTION = "_shorten"


@dataclass(frozen=True)
class PlanServing:
    """How the daemon serves PLAN.md: which headings, and how much of each.

    ``limit`` is None when the excerpt length could not be read; the full
    sections are then compared, which is strictly stricter.
    """

    headings: tuple[str, ...]
    limit: int | None


def _parse(source: str | None) -> ast.Module | None:
    if source is None:
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def plan_serving(universe_source: str | None) -> PlanServing | None:
    """Read the served headings and excerpt length from the daemon's source."""
    tree = _parse(universe_source)
    if tree is None:
        return None
    headings = plan_headings(tree)
    if headings is None:
        return None
    return PlanServing(headings=headings, limit=plan_excerpt_limit(tree))


def plan_excerpt_limit(tree: ast.Module) -> int | None:
    """The literal ``N`` in ``_shorten(excerpt, N)`` inside the context builder."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == PLAN_CONTEXT_FUNCTION:
            limits = {
                call.args[1].value
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == PLAN_SHORTEN_FUNCTION
                and len(call.args) >= 2
                and isinstance(call.args[1], ast.Constant)
                and type(call.args[1].value) is int
            }
            return limits.pop() if len(limits) == 1 else None
    return None


def plan_headings(tree: ast.Module) -> tuple[str, ...] | None:
    """The served PLAN.md headings, read from the daemon's own constant."""
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if value is None:
            continue
        if any(isinstance(t, ast.Name) and t.id == PLAN_HEADINGS_NAME for t in targets):
            try:
                headings = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return None
            if isinstance(headings, (tuple, list)) and all(
                isinstance(h, str) for h in headings
            ):
                return tuple(headings)
            return None
    return None


def extract_plan_section(text: str, heading: str) -> str:
    """Mirror of ``tinyassets.api.universe._extract_plan_section``.

    ``tests/test_runtime_paths.py`` differential-tests the two against the real
    PLAN.md and edge cases, so a change to the daemon's extraction that this
    mirror misses fails CI in the PR that makes it.
    """
    lines = text.splitlines()
    start = None
    marker = f"## {heading}"
    for idx, line in enumerate(lines):
        if line.strip() == marker:
            start = idx
            break
    if start is None:
        return ""
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def shorten(value: str, max_chars: int) -> str:
    """Mirror of ``tinyassets.api.universe._shorten`` for a string value."""
    if len(value) <= max_chars:
        return value
    return value[: max(0, max_chars - 15)].rstrip() + "\n...[truncated]"


def served_plan_context(text: str, serving: PlanServing) -> dict[str, str]:
    """What ``_change_loop_plan_context`` returns for a given PLAN.md text.

    Differential-tested against the daemon's function. With no known limit the
    full sections are returned, which can only make MORE changes count.
    """
    sections: dict[str, str] = {}
    for heading in serving.headings:
        excerpt = extract_plan_section(text, heading)
        if not excerpt:
            sections[heading] = (
                f"[ERROR: unable to resolve bundled PLAN.md section: ## {heading}]"
            )
        elif serving.limit is None:
            sections[heading] = excerpt
        else:
            sections[heading] = shorten(excerpt, serving.limit)
    return sections


@dataclass(frozen=True)
class RuntimeInputs:
    """What production runs from one tree."""

    paths: tuple[str, ...]
    everything: bool = False
    plan: PlanServing | None = None
    notes: tuple[str, ...] = field(default=())

    def covers(self, path: str) -> bool:
        if self.everything:
            return True
        return any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.paths)


def runtime_inputs(repo: Path, rev: str) -> RuntimeInputs:
    """Runtime inputs as the tree at ``rev`` defines them."""
    return runtime_inputs_from(lambda path: _show(repo, rev, path))


def runtime_inputs_from(read: Callable[[str], str | None]) -> RuntimeInputs:
    """Runtime inputs from any tree; ``read(path)`` is None for a missing file."""
    notes: list[str] = []
    paths: list[str] = [*BUILD_DEFINITION, *HOST_PATHS, *HOST_SCRIPTS]
    everything = False

    dockerfile = read(DOCKERFILE)
    if dockerfile is None:
        everything = True
        notes.append("no Dockerfile at head -- every path counts as runtime")
    else:
        sources, wildcard = dockerfile_copy_sources(dockerfile)
        paths.extend(sources)
        if wildcard:
            everything = True
            notes.append("Dockerfile copies an unbounded source -- every path counts")

    manifest = read(HOST_MANIFEST)
    files = host_manifest_files(manifest) if manifest is not None else None
    if files is None:
        # Cannot tell which scripts the host runs: all of them count.
        paths.append("scripts/")
        notes.append("host manifest unreadable -- all of scripts/ counts as runtime")
    else:
        paths.extend(files)

    return RuntimeInputs(
        paths=tuple(dict.fromkeys(paths)),
        everything=everything,
        plan=plan_serving(read(UNIVERSE_MODULE)),
        notes=tuple(notes),
    )


# --- ranges ----------------------------------------------------------------


def changed_paths(repo: Path, base: str | None, head: str) -> list[str]:
    """Paths that differ between two trees; every file when there is no base.

    ``--no-renames`` so a file moved OUT of a runtime directory still reports
    its old path.
    """
    if base is None:
        out = _git_ok(repo, "ls-tree", "-r", "--name-only", head)
    else:
        out = _git_ok(repo, "diff", "--no-renames", "--name-only", base, head)
    return [line for line in out.splitlines() if line]


def runtime_changes(repo: Path, base: str | None, head: str) -> list[str]:
    """Runtime-affecting paths between ``base`` and ``head`` (tree to tree).

    Cumulative, not per-commit: a range of batched merges is judged as a whole,
    so a docs merge after an undeployed runtime merge still reports the runtime
    path. Raises :class:`ClassifyError` when git cannot answer.
    """
    inputs = runtime_inputs(repo, head)
    hits: list[str] = []
    for path in changed_paths(repo, base, head):
        if not inputs.covers(path):
            continue
        if path == PLAN and not inputs.everything and base is not None:
            if inputs.plan is None:
                hits.append(f"{PLAN} (served headings unreadable)")
                continue
            before = served_plan_context(_show(repo, base, PLAN) or "", inputs.plan)
            after = served_plan_context(_show(repo, head, PLAN) or "", inputs.plan)
            changed = [h for h in inputs.plan.headings if before[h] != after[h]]
            if changed:
                hits.append(f"{PLAN} (served section: {', '.join(changed)})")
            continue
        hits.append(path)
    return hits


def first_parent(repo: Path, rev: str) -> str | None:
    out = _git_ok(repo, "rev-list", "--parents", "-n", "1", rev).split()
    return out[1] if len(out) > 1 else None


def runtime_commits(repo: Path, base: str, head: str) -> list[str]:
    """Commits in ``base..head`` that each changed runtime (vs first parent)."""
    commits = _git_ok(repo, "rev-list", f"{base}..{head}").split()
    return [c for c in commits if runtime_changes(repo, first_parent(repo, c), c)]


def newest_runtime_commit(repo: Path, rev: str, limit: int = DEFAULT_WALK_LIMIT) -> str:
    """Newest first-parent ancestor of ``rev`` (inclusive) that changed runtime.

    Returns ``rev`` itself when the walk cannot find one within ``limit``
    commits -- fail open, the caller then treats ``rev`` as undeployed runtime.
    """
    start = resolve(repo, rev)
    commits = _git_ok(
        repo, "rev-list", "--first-parent", f"--max-count={limit}", start
    ).split()
    for commit in commits:
        if runtime_changes(repo, first_parent(repo, commit), commit):
            return commit
    return start


@dataclass(frozen=True)
class Decision:
    build: bool
    reason: str
    runtime_paths: tuple[str, ...] = ()

    @property
    def word(self) -> str:
        return "build" if self.build else "skip"


def decide(repo: Path, base: str | None, head: str) -> Decision:
    """Should ``head`` be built and deployed, given production serves ``base``?"""
    try:
        head_sha = resolve(repo, head)
    except ClassifyError as exc:
        return Decision(True, f"cannot resolve head {head!r}: {exc}")
    if not base:
        return Decision(True, "production's served sha is unknown")
    try:
        base_sha = resolve(repo, base)
    except ClassifyError:
        return Decision(True, f"production serves {base[:12]}, which this checkout does not have")
    if not is_ancestor(repo, base_sha, head_sha):
        return Decision(
            True, f"production serves {base_sha[:12]}, which is not an ancestor of {head_sha[:12]}"
        )
    try:
        hits = runtime_changes(repo, base_sha, head_sha)
    except ClassifyError as exc:
        return Decision(True, f"could not classify {base_sha[:12]}..{head_sha[:12]}: {exc}")
    if hits:
        shown = ", ".join(hits[:8]) + (f" (+{len(hits) - 8} more)" if len(hits) > 8 else "")
        return Decision(
            True,
            f"runtime inputs changed since production's {base_sha[:12]}: {shown}",
            tuple(hits),
        )
    return Decision(
        False,
        f"production's {base_sha[:12]} already serves every runtime input of {head_sha[:12]}",
    )


# --- CLI -------------------------------------------------------------------


def _one_line(text: str) -> str:
    return " ".join(text.split())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", type=Path, default=REPO_ROOT)
    sub = ap.add_subparsers(dest="command", required=True)

    p_decide = sub.add_parser("decide", help="build/skip for head given the served sha")
    p_decide.add_argument("--base", default="", help="sha production serves ('' = unknown)")
    p_decide.add_argument("--head", required=True)
    p_decide.add_argument(
        "--github-output", type=Path, help="append decision=/reason= lines to this file"
    )

    p_newest = sub.add_parser("newest-runtime-commit")
    p_newest.add_argument("--rev", required=True)
    p_newest.add_argument("--limit", type=int, default=DEFAULT_WALK_LIMIT)

    p_classify = sub.add_parser("classify", help="list runtime paths changed base..head")
    p_classify.add_argument("--base", required=True)
    p_classify.add_argument("--head", required=True)

    args = ap.parse_args(argv)
    repo: Path = args.repo

    if args.command == "decide":
        decision = decide(repo, args.base.strip() or None, args.head)
        print(f"{decision.word}: {decision.reason}")
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as fh:
                fh.write(f"decision={decision.word}\n")
                fh.write(f"reason={_one_line(decision.reason)}\n")
        return 0

    try:
        if args.command == "newest-runtime-commit":
            print(newest_runtime_commit(repo, args.rev, args.limit))
            return 0
        hits = runtime_changes(repo, resolve(repo, args.base), resolve(repo, args.head))
    except ClassifyError as exc:
        print(f"cannot classify: {exc}", file=sys.stderr)
        return 2
    for hit in hits:
        print(hit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
