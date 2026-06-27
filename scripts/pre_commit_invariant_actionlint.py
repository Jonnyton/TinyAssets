"""Pre-commit invariant: actionlint on staged GH Actions workflow files.

Runs `actionlint` against staged `.github/workflows/**/*.yml` files. Only
blocks the commit if actionlint EMITS FINDINGS on the staged files — pre-
existing repo-wide issues are out of scope per task #5 ("Don't run
actionlint across every existing workflow as part of this task").

Behavior
--------
- No staged workflow files: no-op, exit 0.
- actionlint binary not on PATH: warn to stderr + exit 0. CI will catch
  anything missed locally. Don't block commits on missing-tooling class.
- actionlint finds issues on staged files: exit 2 with the findings +
  install hint.
- actionlint runs clean: exit 0.

Exit codes
----------
  0 — invariant satisfied (no issues, or no-op because no workflow files
      staged, or actionlint unavailable).
  2 — invariant violated: actionlint emitted findings on staged files.

Install hint (cross-platform one-liner, printed on miss):
    choco install actionlint -y     # Windows
    brew install actionlint          # macOS
    go install github.com/rhysd/actionlint/cmd/actionlint@latest  # any Go

Usage (called by pre-commit hook):
    python scripts/pre_commit_invariant_actionlint.py

    # Explicit path(s) for manual invocation / tests:
    python scripts/pre_commit_invariant_actionlint.py path/to/tinyassets.yml
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_TINYASSETS_PREFIX = ".github/workflows/"


def _staged_workflow_files() -> list[str]:
    """Return list of staged files under .github/workflows/ (.yml / .yaml)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    return [
        line
        for line in result.stdout.splitlines()
        if line.startswith(_TINYASSETS_PREFIX)
        and (line.endswith(".yml") or line.endswith(".yaml"))
    ]


def _find_actionlint() -> str | None:
    """Return the path to the actionlint binary, or None if not installed."""
    return shutil.which("actionlint")


def _print_install_hint() -> None:
    print("pre-commit [actionlint]: binary not on PATH — skipping",
          file=sys.stderr)
    print("", file=sys.stderr)
    print("  Install one-liner:", file=sys.stderr)
    print("    Windows:  choco install actionlint -y", file=sys.stderr)
    print("    macOS:    brew install actionlint", file=sys.stderr)
    print("    Any Go:   go install github.com/rhysd/actionlint/cmd/"
          "actionlint@latest", file=sys.stderr)
    print("", file=sys.stderr)
    print("  CI runs actionlint on every PR that touches workflow files;",
          file=sys.stderr)
    print("  this local hook is a fast-feedback supplement, not a gate.",
          file=sys.stderr)


def _print_findings(output: str, paths: list[str]) -> None:
    print("pre-commit [actionlint]: INVARIANT VIOLATED", file=sys.stderr)
    print("", file=sys.stderr)
    print("  actionlint reported issues on the following staged files:",
          file=sys.stderr)
    for p in paths:
        print(f"    - {p}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Findings:", file=sys.stderr)
    for line in output.splitlines():
        print(f"    {line}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Fix the issues or override with --no-verify if intentional.",
          file=sys.stderr)


def run_actionlint(paths: list[str]) -> tuple[int, str]:
    """Run actionlint on the given paths. Returns (exit_code, combined_output)."""
    binary = _find_actionlint()
    if binary is None:
        return (0, "__actionlint_missing__")
    try:
        result = subprocess.run(
            [binary, *paths],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return (0, f"__actionlint_runtime_error__: {e}")
    # actionlint emits findings on stdout; stderr tends to hold only tool
    # errors. Combine both so callers see everything.
    combined = (result.stdout or "") + (result.stderr or "")
    return (result.returncode, combined)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if argv:
        # Explicit paths — tests + manual invocation.
        paths = [p for p in argv if Path(p).is_file()]
        if not paths:
            print("pre-commit [actionlint]: no valid paths given — skipping",
                  file=sys.stderr)
            return 0
    else:
        paths = _staged_workflow_files()
        if not paths:
            return 0  # no workflow files staged — no-op

    code, output = run_actionlint(paths)
    if output == "__actionlint_missing__":
        _print_install_hint()
        return 0
    if output.startswith("__actionlint_runtime_error__"):
        print(f"pre-commit [actionlint]: {output} — skipping", file=sys.stderr)
        return 0

    if code == 0:
        print(f"pre-commit [actionlint]: clean ({len(paths)} workflow "
              f"file(s) checked)", file=sys.stderr)
        return 0

    _print_findings(output, paths)
    return 2


if __name__ == "__main__":
    sys.exit(main())
