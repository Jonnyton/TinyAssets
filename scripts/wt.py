"""Worktree lifecycle wrapper (Layer 2): make teardown automatic.

Part of the branch lifecycle automation; see
``docs/design-notes/2026-06-24-branch-lifecycle-automation.md``.

One command for both halves of the loop so worktrees stop piling up:

    python scripts/wt.py new <slug> [--provider claude-code] [--branch name]
    python scripts/wt.py done [<slug-or-path>] [--force]
    python scripts/wt.py list

``new``  fetches, creates a worktree off the base ref, scaffolds _PURPOSE.md
         (with every field worktree_status.py requires), and logs a create
         event in .agents/worktrees.md.
``done`` verifies the branch merged into the base ref (refuses otherwise unless
         --force), removes the worktree, deletes the local branch, and logs a
         remove event. Remote-branch cleanup is the janitor's job.
``list`` passes through to worktree_status.py.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from git_squash_merge import is_merged_into  # noqa: E402  (sibling-script import)

PROVIDER_PREFIX = {
    "claude-code": "claude",
    "claude": "claude",
    "codex": "codex",
    "cursor": "cursor",
    "cowork": "cowork",
    "aider": "aider",
}

PURPOSE_TEMPLATE = """# Worktree purpose

Purpose: {slug}
Provider: {provider}
Branch: {branch}
Base ref: {base_ref}
STATUS/Issue/PR: TODO — link the STATUS.md row, issue, or PR
PLAN refs: TODO — relevant PLAN.md module(s)
Ship condition: TODO — what must be true to merge
Abandon condition: TODO — when to sweep this lane
Pickup hints: TODO — where to resume
Memory refs: TODO — prior-provider memory/artifact paths
Related implications: TODO — linked STATUS lanes / research artifacts
Idea feed refs: (none yet)
"""


def _force_utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        enc = (getattr(stream, "encoding", None) or "").lower().replace("_", "-")
        if enc == "utf-8":
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
                continue
            except (AttributeError, ValueError, OSError):
                pass


def _run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
    )


def repo_root() -> Path:
    proc = _run(["git", "rev-parse", "--show-toplevel"])
    if proc.returncode != 0:
        raise SystemExit("not inside a git repository")
    # In a worktree, point at the main checkout so siblings are consistent.
    common = _run(["git", "rev-parse", "--git-common-dir"])
    if common.returncode == 0 and common.stdout.strip():
        git_common = Path(common.stdout.strip()).resolve()
        if git_common.name == ".git":
            return git_common.parent
    return Path(proc.stdout.strip()).resolve()


def log_event(root: Path, line: str) -> None:
    path = root / ".agents" / "worktrees.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d", time.gmtime())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"- {stamp} {line}\n")


def cmd_new(args: argparse.Namespace) -> int:
    root = repo_root()
    slug = args.slug.strip().strip("/")
    prefix = PROVIDER_PREFIX.get(args.provider, args.provider)
    branch = args.branch or f"{prefix}/{slug}"
    wt_path = root.parent / f"wf-{slug}"
    if wt_path.exists():
        raise SystemExit(f"refusing to clobber existing path: {wt_path}")

    print(f"# fetch --prune {args.remote}")
    _run(["git", "fetch", "--prune", args.remote], cwd=root)
    add = _run(
        ["git", "worktree", "add", "-b", branch, str(wt_path), args.base_ref], cwd=root
    )
    if add.returncode != 0:
        raise SystemExit(f"git worktree add failed: {add.stderr.strip()}")
    (wt_path / "_PURPOSE.md").write_text(
        PURPOSE_TEMPLATE.format(
            slug=slug, provider=args.provider, branch=branch, base_ref=args.base_ref
        ),
        encoding="utf-8",
    )
    log_event(
        root,
        f"CREATE {wt_path.name} branch={branch} base={args.base_ref} provider={args.provider}",
    )
    print(f"created worktree {wt_path} on branch {branch}")
    print(f"  -> edit {wt_path / '_PURPOSE.md'} (fill the TODO fields)")
    return 0


def _branch_of(path: Path) -> str | None:
    proc = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    return proc.stdout.strip() if proc.returncode == 0 else None


def cmd_done(args: argparse.Namespace) -> int:
    root = repo_root()
    if args.target:
        wt_path = Path(args.target)
        if not wt_path.is_absolute():
            stem = args.target if args.target.startswith("wf-") else f"wf-{args.target}"
            wt_path = root.parent / stem
    else:
        wt_path = Path.cwd()
    wt_path = wt_path.resolve()
    if not wt_path.exists():
        raise SystemExit(f"no such worktree path: {wt_path}")

    branch = _branch_of(wt_path)
    if not branch or branch == "HEAD":
        raise SystemExit(f"could not resolve branch for {wt_path}")

    # Squash-aware: this repo squash-merges PRs, so a plain --is-ancestor check
    # would report every squash-merged lane as unmerged and refuse teardown.
    merged = is_merged_into(lambda a: _run(a, cwd=root), branch, args.base_ref)
    if not merged and not args.force:
        raise SystemExit(
            f"branch '{branch}' is NOT merged into {args.base_ref}. "
            f"Merge its PR first, or re-run with --force to discard the lane."
        )

    rm = _run(
        ["git", "worktree", "remove", *(["--force"] if args.force else []), str(wt_path)],
        cwd=root,
    )
    if rm.returncode != 0:
        raise SystemExit(f"git worktree remove failed: {rm.stderr.strip()}")
    flag = "-D" if args.force else "-d"
    delb = _run(["git", "branch", flag, branch], cwd=root)
    log_event(
        root,
        f"REMOVE {wt_path.name} branch={branch} merged={merged} forced={args.force}",
    )
    print(f"removed worktree {wt_path}")
    print(f"  branch delete: {'ok' if delb.returncode == 0 else delb.stderr.strip()}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = repo_root()
    script = root / "scripts" / "worktree_status.py"
    return _run_passthrough([sys.executable, str(script), *args.extra])


def _run_passthrough(cmd: list[str]) -> int:
    proc = subprocess.run(cmd)
    return proc.returncode


def main(argv: list[str]) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="create a worktree + branch + _PURPOSE.md")
    p_new.add_argument("slug")
    p_new.add_argument("--provider", default="claude-code")
    p_new.add_argument("--branch", default=None)
    p_new.add_argument("--base-ref", default="origin/main")
    p_new.add_argument("--remote", default="origin")
    p_new.set_defaults(func=cmd_new)

    p_done = sub.add_parser("done", help="verify merged, remove worktree + branch")
    p_done.add_argument("target", nargs="?", default=None, help="slug or path; defaults to cwd")
    p_done.add_argument("--base-ref", default="origin/main")
    p_done.add_argument("--force", action="store_true", help="discard even if unmerged/dirty")
    p_done.set_defaults(func=cmd_done)

    p_list = sub.add_parser("list", help="pass through to worktree_status.py")
    p_list.add_argument("extra", nargs=argparse.REMAINDER)
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
