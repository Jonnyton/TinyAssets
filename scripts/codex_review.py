#!/usr/bin/env python3
"""Programmatic Codex dispatch — offload a cross-family review to Codex's OWN
budget without spending a Claude context.

Runs `codex exec` (read-only sandbox) as a plain subprocess and writes Codex's
final verdict to a file. Meant to be launched by the Claude Code lead via a
BACKGROUND Bash call (`run_in_background`): the lead keeps working while Codex
churns on its own quota, and reads the verdict file when the job completes.

Why this instead of a Claude "liaison teammate": a teammate is another Claude
context (opus, per `latest_model_guard.py`) — it burns Claude tokens / rate-limit
to relay, which defeats the point of offloading to Codex. This wrapper spends
ZERO Claude context; Codex does the reasoning on Codex's budget. The only Claude
cost is launching the job and reading back a short verdict.

Usage (typically backgrounded):
  python scripts/codex_review.py --out review.md --prompt "<review ask>"
  python scripts/codex_review.py --out review.md --diff-base origin/main \
      --prompt "focus on the auth boundary"

Contract: the out file ALWAYS exists and ends in a `VERDICT:` line when this
process exits — `approve|adapt|reject` from Codex, or `VERDICT: error` written
by this wrapper on timeout / launch failure / empty output. Background callers
poll the file; stderr of a background job is easy to lose, so failures must be
readable in-band.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# A background review that outlives this is a stalled network/CLI, not a long
# think. 30 min is generous for a repo-sized diff review.
DEFAULT_TIMEOUT_S = 1800.0

ADVERSARIAL_PREAMBLE = (
    "You are performing an opposite-provider (cross-family) code review. Be "
    "adversarial: try to find the reason this is wrong before you approve it. "
    "Re-check the actual code and any cited sources — do not rubber-stamp. Finish "
    "with a single line 'VERDICT: approve' | 'VERDICT: adapt' | 'VERDICT: reject', "
    "then the concrete findings / required adaptations (most important first)."
)


def build_prompt(ask: str, diff_base: str | None) -> str:
    if diff_base:
        ask = (
            f"Review the changes on this branch vs `{diff_base}` — run "
            f"`git diff {diff_base}...HEAD` and read the changed files. {ask}"
        )
    return f"{ADVERSARIAL_PREAMBLE}\n\n{ask}"


def resolve_codex() -> str:
    """Locate a runnable codex executable.

    Background Bash jobs run with a stripped PATH that often lacks ~/.local/bin,
    and on Windows the runnable entrypoint is `codex.cmd` — the bare `codex` there
    is a bash shim that CreateProcess rejects (WinError 193). So: honor an explicit
    CODEX_BIN, then PATH, then the known install dir preferring the .cmd/.exe.
    """
    override = os.environ.get("CODEX_BIN")
    if override and Path(override).exists():
        return override
    found = shutil.which("codex")
    if found:
        return found
    for name in ("codex.cmd", "codex.exe", "codex"):
        candidate = Path.home() / ".local" / "bin" / name
        if candidate.exists():
            return str(candidate)
    return "codex"  # last resort; surfaces a clear FileNotFoundError below


def to_native_path(path: str) -> str:
    """Convert an MSYS / Git-Bash path (/c/foo) to a native Windows path (C:/foo).

    The wrapper is usually launched from Git Bash but hands paths to the Windows
    `codex.cmd`, which cannot parse /c/... style paths (fails with os error 3).
    """
    match = re.match(r"^/([A-Za-z])/(.*)$", path)
    return f"{match.group(1).upper()}:/{match.group(2)}" if match else path


def build_cmd(args: argparse.Namespace) -> list[str]:
    # Only verified `codex exec` flags. read-only is hard-coded: this path never
    # grants Codex write access. Codex can still run git/read in its sandbox.
    return [
        resolve_codex(),
        "exec",
        "-s",
        "read-only",
        # Explicit no-approval so a background run can never hang on a prompt.
        # `exec` has no -a flag; approval is a config key (validated: accepted).
        "-c",
        "approval_policy=never",
        "-C",
        args.cwd,
        "-o",
        args.out,
        build_prompt(args.prompt, args.diff_base),
    ]


def _has_content(out: Path) -> bool:
    try:
        return out.exists() and out.stat().st_size > 0
    except OSError:
        return False


def ensure_verdict_file(out: Path, error: str | None) -> None:
    """Guarantee the out file is present and readable for the background caller.

    - Codex succeeded and wrote output: leave the file alone.
    - Codex failed but wrote partial output: append the failure as a trailing
      note (stderr of a background job is easy to lose; the file is the channel).
    - No/empty output: write a `VERDICT: error` file so a poller never waits on
      a file that will never appear, and never mistakes silence for approval.
    """
    if error is None and _has_content(out):
        return
    if error is None:
        error = "codex exec exited 0 but wrote no output"
    if _has_content(out):
        with out.open("a", encoding="utf-8") as fh:
            fh.write(f"\n\n[codex_review] WARNING: {error}\n")
        return
    out.write_text(
        "VERDICT: error\n"
        f"[codex_review] no verdict produced: {error}\n"
        "Do NOT treat this as approve — re-dispatch or fall back to an inline "
        "mcp__codex__codex gate.\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    args.cwd = to_native_path(args.cwd)
    args.out = to_native_path(args.out)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = build_cmd(args)
    print(f"[codex_review] dispatching to Codex (read-only); verdict -> {args.out}", flush=True)
    error: str | None = None
    rc = 0
    try:
        proc = subprocess.run(cmd, timeout=args.timeout)
        rc = proc.returncode
        if rc != 0:
            error = f"codex exec exited {rc}"
    except subprocess.TimeoutExpired:
        rc = 124
        error = f"codex exec timed out after {args.timeout:.0f}s (killed)"
    except FileNotFoundError:
        rc = 127
        error = (
            f"codex executable not runnable: {cmd[0]!r}. "
            "Set CODEX_BIN to the full path of codex.cmd (Windows) / codex."
        )

    if error:
        print(f"[codex_review] {error}", file=sys.stderr)
    ensure_verdict_file(out, error)
    return rc


def main() -> int:
    p = argparse.ArgumentParser(
        description="Background Codex review dispatcher (offloads to Codex's budget)."
    )
    p.add_argument("--prompt", required=True, help="The review ask / focus.")
    p.add_argument("--out", required=True, help="File to write Codex's final verdict to.")
    p.add_argument("--cwd", default=".", help="Repo/worktree root Codex reviews (default: cwd).")
    p.add_argument(
        "--diff-base",
        default=None,
        help="If set, ask Codex to review this branch's diff vs the given base branch.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help="Kill codex exec after this many seconds and write VERDICT: error "
        f"(default {DEFAULT_TIMEOUT_S:.0f}).",
    )
    return run(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
