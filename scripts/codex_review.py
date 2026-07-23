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

Contract: the out file ALWAYS exists and carries a `VERDICT:` line when this
process exits — `approve|adapt|reject` from Codex, or `VERDICT: error` written
by this wrapper on timeout / launch failure / empty output / unattributable
verdict. Background callers poll the file; stderr of a background job is easy to
lose, so failures must be readable in-band.

Attribution: every dispatch mints a nonce and tells Codex to echo it (with the
reviewed target) as an exact line. A verdict body that does not carry that line
is quarantined as `VERDICT: error` rather than returned. Without this, a verdict
file is unfalsifiable — it cannot be distinguished from a stale file left at the
same `--out` path or a review of a different lane, and a gate that can return
someone else's `approve` manufactures confidence instead of providing it.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
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

# Attribution: a verdict must be traceable to the request that asked for it.
# Without this a verdict file is just prose — it cannot be distinguished from a
# stale file left at the same --out path, or from a review of somebody else's
# lane. The nonce is machine-generated per dispatch, so it cannot appear in a
# body that was written before this dispatch existed.
ATTRIBUTION_PREFIX = "REVIEW-ATTRIBUTION"
# Attribution tags are echoed back by the model, so keep the target short enough
# to copy reliably; the full target text still goes in the prompt body.
TARGET_TAG_MAX = 80


def make_nonce() -> str:
    return secrets.token_hex(8)


def target_tag(target: str | None) -> str:
    """Short, copyable identifier for the reviewed target."""
    tag = " ".join((target or "unspecified").split())
    return tag[: TARGET_TAG_MAX - 1] + "…" if len(tag) > TARGET_TAG_MAX else tag


def attribution_line(nonce: str, target: str | None) -> str:
    """The exact line the reviewer must emit for its verdict to be accepted."""
    return f"{ATTRIBUTION_PREFIX} nonce={nonce} target={target_tag(target)}"


def build_prompt(ask: str, diff_base: str | None, nonce: str, target: str | None) -> str:
    if diff_base:
        ask = (
            f"Review the changes on this branch vs `{diff_base}` — run "
            f"`git diff {diff_base}...HEAD` and read the changed files. {ask}"
        )
    required = attribution_line(nonce, target)
    attribution = (
        "Your final message MUST begin with this line, copied exactly, on a line "
        f"of its own:\n{required}\n"
        "A verdict without that exact line is discarded unread, so do not "
        "paraphrase, reformat, or omit it."
    )
    scope = f"\n\nReview target: {target}" if target else ""
    return f"{ADVERSARIAL_PREAMBLE}\n\n{attribution}\n\n{ask}{scope}"


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
    #
    # The prompt goes over STDIN (the trailing `-`), never argv. `resolve_codex()`
    # resolves to `codex.CMD` on Windows, so argv is routed through cmd.exe, which
    # truncates an argument at its first newline: the multi-line prompt arrived at
    # Codex as the preamble alone, with the caller's entire ask silently dropped.
    # `codex exec` documents `-` as "read instructions from stdin", which is not
    # subject to cmd.exe parsing (newlines, `&|%<>^"`, or length limits).
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
        "-",
    ]


def _has_content(out: Path) -> bool:
    try:
        return out.exists() and out.stat().st_size > 0
    except OSError:
        return False


def _decorated(line: str) -> str:
    """Strip markdown decoration a model may wrap the attribution line in."""
    return line.strip().strip("`*_# ").strip()


def is_attributed(body: str, nonce: str, target: str | None) -> bool:
    """True iff `body` carries the exact attribution line for THIS dispatch.

    Exact whole-line match, not a substring scan: a body that merely mentions the
    nonce in prose (or a longer line that contains it) is not a verdict addressed
    to this request.
    """
    required = attribution_line(nonce, target)
    return any(_decorated(line) == required for line in body.splitlines())


def quarantine_unattributed(out: Path, nonce: str, target: str | None) -> None:
    """Fail closed on a verdict that is not attributable to this request.

    The body is preserved as evidence but every line is prefixed, so no line in
    the file is a bare `VERDICT: approve` that a naive reader could mistake for a
    result. This is the whole point of the gate: a stolen, stale, or contextless
    verdict must read as an error, never as an approval.
    """
    body = out.read_text(encoding="utf-8", errors="replace")
    quarantined = "\n".join(f"| {line}" for line in body.splitlines())
    out.write_text(
        "VERDICT: error\n"
        f"[codex_review] verdict rejected: missing attribution line for this request.\n"
        f"[codex_review] expected exactly: {attribution_line(nonce, target)}\n"
        "This body could not be attributed to this dispatch — it may be a stale "
        "file left at the --out path, a review of a different lane, or a reply "
        "that never received the ask. Do NOT treat it as a gate result; "
        "re-dispatch. Unattributed body preserved below as evidence:\n\n"
        f"{quarantined}\n",
        encoding="utf-8",
    )


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
    nonce = getattr(args, "nonce", None) or make_nonce()
    target = getattr(args, "target", None)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # A pre-existing file at --out is indistinguishable from a fresh verdict once
    # codex has run: if codex writes nothing (it can exit 0 with empty output on
    # auth failure), the caller reads back whatever was already there — which is
    # how one lane received another lane's `VERDICT: approve`. Clear it first so
    # "file has content" can only ever mean "this dispatch produced it".
    out.unlink(missing_ok=True)

    # `required=True` only demands the flag, not content: `--prompt ""` (an unset
    # shell variable, a failed expansion) would dispatch a review with no ask and
    # collect whatever Codex says to a bare preamble. Refuse to spend the run.
    if not args.prompt.strip():
        ensure_verdict_file(out, "empty --prompt: refusing to dispatch a review with no ask")
        print("[codex_review] empty --prompt; not dispatching", file=sys.stderr)
        return 2

    cmd = build_cmd(args)
    prompt = build_prompt(args.prompt, args.diff_base, nonce, target)
    print(f"[codex_review] dispatching to Codex (read-only); verdict -> {args.out}", flush=True)
    print(f"[codex_review] attribution nonce={nonce} target={target_tag(target)}", flush=True)
    error: str | None = None
    rc = 0
    try:
        proc = subprocess.run(
            cmd, input=prompt, text=True, encoding="utf-8", timeout=args.timeout
        )
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

    # Attribution is checked against what codex itself wrote, BEFORE
    # ensure_verdict_file may synthesize a file of its own — otherwise the
    # wrapper's own `VERDICT: error` body would be quarantined a second time.
    if error is None and _has_content(out):
        body = out.read_text(encoding="utf-8", errors="replace")
        if not is_attributed(body, nonce, target):
            print(
                "[codex_review] verdict is not attributable to this request — "
                "quarantined as VERDICT: error",
                file=sys.stderr,
            )
            quarantine_unattributed(out, nonce, target)
            rc = rc or 65

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
        "--target",
        default=None,
        help="What is under review (sha, PR number, branch, file list). Echoed in "
        "the attribution line so a verdict is traceable to its request.",
    )
    p.add_argument(
        "--nonce",
        default=None,
        help="Attribution nonce (default: freshly generated). A verdict that does "
        "not echo it exactly is rejected as unattributable.",
    )
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
