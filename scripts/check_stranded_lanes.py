"""Detect local lanes that are ahead of main but not fully published.

This is a read-only detector, not a preventer or repair tool. It enumerates
registered worktrees together with known scratch-clone locations, then reports
lanes with commits ahead of ``origin/main`` that lack a pushed branch or pull
request. Inspection failures are reported as UNKNOWN instead of being skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

GitRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
PrChecker = Callable[[Path, str], bool]
RemoteBranchChecker = Callable[[Path, str], bool]


class InspectionError(RuntimeError):
    """A read-only external query could not determine lane state."""


@dataclass(frozen=True)
class LaneFinding:
    state: str
    path: Path
    branch: str = "(unknown)"
    head: str = "(unknown)"
    ahead: int | None = None
    detail: str = ""


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], 127, "", str(exc))


def discover_lanes(
    repo: Path,
    *,
    git_runner: GitRunner = run_git,
) -> tuple[list[Path], list[LaneFinding]]:
    """Return the union of registered worktrees and supported clone locations."""
    repo = _resolved(repo)
    candidates: list[Path] = [repo]
    unknown: list[LaneFinding] = []

    listed = git_runner(["worktree", "list", "--porcelain"], repo)
    if listed.returncode == 0:
        candidates.extend(_parse_worktree_paths(listed.stdout))
    else:
        unknown.append(
            LaneFinding(
                state="UNKNOWN",
                path=repo,
                detail=_command_error("git worktree list --porcelain", listed),
            )
        )

    candidates.extend(_scratch_candidates(repo))
    unique: dict[str, Path] = {}
    for candidate in candidates:
        resolved = _resolved(candidate)
        unique.setdefault(os.path.normcase(str(resolved)), resolved)
    return sorted(unique.values(), key=lambda path: str(path).lower()), unknown


def inspect_lane(
    lane: Path,
    *,
    base_ref: str = "origin/main",
    git_runner: GitRunner = run_git,
    remote_branch_exists: RemoteBranchChecker | None = None,
    pr_exists: PrChecker | None = None,
) -> LaneFinding | None:
    """Inspect one checkout; return STRANDED/UNKNOWN or None when clean."""
    lane = _resolved(lane)
    remote_branch_exists = remote_branch_exists or (
        lambda path, branch: _remote_branch_exists(path, branch, git_runner=git_runner)
    )
    pr_exists = pr_exists or _pr_exists

    try:
        head = _required_git(lane, ["rev-parse", "HEAD"], git_runner)
        ahead_text = _required_git(
            lane,
            ["rev-list", "--count", f"{base_ref}..HEAD"],
            git_runner,
        )
        try:
            ahead = int(ahead_text)
        except ValueError as exc:
            raise InspectionError(f"invalid ahead count: {ahead_text!r}") from exc
        if ahead <= 0:
            return None

        branch_result = git_runner(
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
            lane,
        )
        if branch_result.returncode == 0 and branch_result.stdout.strip():
            branch = branch_result.stdout.strip()
        elif branch_result.returncode == 1 and not (
            branch_result.stderr.strip() or branch_result.stdout.strip()
        ):
            branch = "(detached HEAD)"
        else:
            raise InspectionError(
                _command_error("git symbolic-ref --quiet --short HEAD", branch_result)
            )

        if branch == "(detached HEAD)":
            return LaneFinding(
                state="STRANDED",
                path=lane,
                branch=branch,
                head=head,
                ahead=ahead,
                detail="no_pushed_branch",
            )
        if not remote_branch_exists(lane, branch):
            return LaneFinding(
                state="STRANDED",
                path=lane,
                branch=branch,
                head=head,
                ahead=ahead,
                detail="no_pushed_branch",
            )
        if not pr_exists(lane, branch):
            return LaneFinding(
                state="STRANDED",
                path=lane,
                branch=branch,
                head=head,
                ahead=ahead,
                detail="no_pull_request",
            )
        return None
    except InspectionError as exc:
        return LaneFinding(state="UNKNOWN", path=lane, detail=str(exc))


def run_detector(
    repo: Path,
    *,
    base_ref: str = "origin/main",
    output: TextIO = sys.stdout,
    git_runner: GitRunner = run_git,
    remote_branch_exists: RemoteBranchChecker | None = None,
    pr_exists: PrChecker | None = None,
) -> int:
    lanes, findings = discover_lanes(repo, git_runner=git_runner)
    for lane in lanes:
        finding = inspect_lane(
            lane,
            base_ref=base_ref,
            git_runner=git_runner,
            remote_branch_exists=remote_branch_exists,
            pr_exists=pr_exists,
        )
        if finding is not None:
            findings.append(finding)

    findings.sort(key=lambda finding: (str(finding.path).lower(), finding.state))
    if not findings:
        output.write("CLEAN no stranded or unknown lanes\n")
        return 0
    for finding in findings:
        output.write(_render_finding(finding) + "\n")
    return 2


def _scratch_candidates(repo: Path) -> Iterable[Path]:
    patterns = (
        (repo, ".codex-scratch-*"),
        (repo / "codex-tmp", "*"),
        (repo / ".claude" / "worktrees", "*"),
        (repo.parent, "wf-*"),
    )
    for parent, pattern in patterns:
        if not parent.is_dir():
            continue
        for candidate in parent.glob(pattern):
            if candidate.is_dir() and (candidate / ".git").exists():
                yield candidate


def _parse_worktree_paths(text: str) -> list[Path]:
    paths: list[Path] = []
    for line in text.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line[len("worktree ") :]))
    return paths


def _required_git(lane: Path, args: list[str], git_runner: GitRunner) -> str:
    result = git_runner(args, lane)
    if result.returncode != 0:
        raise InspectionError(_command_error(f"git {' '.join(args)}", result))
    value = result.stdout.strip()
    if not value:
        raise InspectionError(f"git {' '.join(args)} returned empty output")
    return value


def _remote_branch_exists(
    lane: Path,
    branch: str,
    *,
    git_runner: GitRunner = run_git,
) -> bool:
    result = git_runner(
        ["ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
        lane,
    )
    if result.returncode != 0:
        raise InspectionError(_command_error("git ls-remote --heads origin", result))
    return bool(result.stdout.strip())


def _pr_exists(lane: Path, branch: str) -> bool:
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "number",
                "--limit",
                "1",
            ],
            cwd=lane,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InspectionError(f"gh pr list failed: {exc}") from exc
    if result.returncode != 0:
        raise InspectionError(_command_error("gh pr list", result))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InspectionError("gh pr list returned invalid JSON") from exc
    if not isinstance(payload, list):
        raise InspectionError("gh pr list returned a non-list JSON value")
    return bool(payload)


def _command_error(
    command: str,
    result: subprocess.CompletedProcess[str],
) -> str:
    message = result.stderr.strip() or result.stdout.strip() or "no error output"
    first_line = message.splitlines()[0]
    return f"{command} failed (exit {result.returncode}): {first_line}"


def _render_finding(finding: LaneFinding) -> str:
    if finding.state == "UNKNOWN":
        return f"UNKNOWN path={finding.path} error={finding.detail}"
    return (
        f"STRANDED path={finding.path} branch={finding.branch} head={finding.head} "
        f"ahead={finding.ahead} missing={finding.detail}"
    )


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Primary repository root to inspect (default: current directory).",
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Per-checkout base ref for ahead counts (default: origin/main).",
    )
    args = parser.parse_args(argv)
    if not args.base_ref or args.base_ref.startswith("-") or ".." in args.base_ref:
        parser.error("--base-ref must be one Git ref or commit, not a revision range")
    return run_detector(args.repo, base_ref=args.base_ref)


if __name__ == "__main__":
    raise SystemExit(main())
