#!/usr/bin/env python3
"""Programmatic Kimi (kimi-k3) dispatch — offload a cross-family review to a
THIRD model family (Moonshot Kimi) on its OWN budget, without spending Claude
context. Mirrors ``scripts/codex_review.py`` for Codex.

Host directive 2026-07-20: call Kimi via the DIRECT CLI, not the MCP shim
(``kimi-mcp/server.js``). The shim isn't reliably connected and its build modes
are broken with the current CLI; the direct CLI is the default path.

Runs ``kimi -p <prompt> --output-format stream-json`` as a plain subprocess and
writes Kimi's final verdict to a file. Meant to be launched by the lead via a
BACKGROUND Bash call (``run_in_background``): the lead keeps working while Kimi
churns on Moonshot's quota, and reads the verdict file when the job completes.

READ-ONLY ONLY. ``kimi -p`` cannot combine with ``--yolo``/``--auto`` (CLI
0.27.0 rejects it), so ``-p`` can only READ + reason — reviews, second opinions,
diverse-perspective judging, and emitting a patch you apply yourself. It CANNOT
write files or run commands non-interactively. This wrapper therefore never
grants write access (there is no write mode to grant). Kimi is also SLOW — always
background this.

Usage (typically backgrounded):
  python scripts/kimi_review.py --out review.md --prompt "<review ask>"
  python scripts/kimi_review.py --out review.md --diff-base origin/main \
      --cwd /path/to/worktree --prompt "focus on the auth boundary"

Contract: the out file ALWAYS exists and ends in a ``VERDICT:`` line when this
process exits — ``approve|adapt|reject`` from Kimi, or ``VERDICT: error`` written
by this wrapper on timeout / launch failure / empty output. Background callers
poll the file; stderr of a background job is easy to lose, so failures must be
readable in-band. Per the dual-family rule, a Kimi verdict is EXTRA signal (a
third family), never a substitute for the Fable-5 + gpt-5.6-sol approval pair.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Kimi is slow (a full review can run many minutes). A run that outlives this is
# a stalled network/CLI, not a long think.
DEFAULT_TIMEOUT_S = 1800.0
MAX_OUTPUT_CHARS = 120_000

ADVERSARIAL_PREAMBLE = (
    "You are performing an opposite-family (third-model-family) code review as "
    "Kimi. Be adversarial: try to find the reason this is wrong before you "
    "approve it. Read the actual code and any cited sources — do not rubber-stamp. "
    "You are read-only: do not attempt to write files or run commands. Finish with "
    "a single line 'VERDICT: approve' | 'VERDICT: adapt' | 'VERDICT: reject', then "
    "the concrete findings / required adaptations (most important first)."
)


def build_prompt(ask: str, diff_base: str | None) -> str:
    if diff_base:
        ask = (
            f"Review the changes on this branch vs `{diff_base}` — run "
            f"`git diff {diff_base}...HEAD` and read the changed files. {ask}"
        )
    return f"{ADVERSARIAL_PREAMBLE}\n\n{ask}"


def resolve_kimi() -> list[str]:
    """Return the argv prefix to invoke Kimi.

    Prefer ``node <dist/main.mjs>`` (what the MCP shim does) because on Windows
    the npm ``kimi`` wrapper is a .cmd/.ps1 that CreateProcess rejects, and
    background Bash jobs run with a stripped PATH. Honor KIMI_CODE_MAIN, then the
    known npm install locations, then a plain ``kimi`` on PATH as a last resort.
    """
    main = os.environ.get("KIMI_CODE_MAIN")
    candidates = [main] if main else []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(
            str(Path(appdata) / "npm" / "node_modules" / "@moonshot-ai"
                / "kimi-code" / "dist" / "main.mjs")
        )
    candidates += [
        "/usr/local/lib/node_modules/@moonshot-ai/kimi-code/dist/main.mjs",
        str(Path.home() / ".npm-global" / "lib" / "node_modules"
            / "@moonshot-ai" / "kimi-code" / "dist" / "main.mjs"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            node = shutil.which("node") or "node"
            return [node, c]
    found = shutil.which("kimi")
    return [found] if found else ["kimi"]


def to_native_path(path: str) -> str:
    """Convert an MSYS / Git-Bash path (/c/foo) to a native path (C:/foo)."""
    match = re.match(r"^/([A-Za-z])/(.*)$", path)
    return f"{match.group(1).upper()}:/{match.group(2)}" if match else path


def build_cmd(prompt: str) -> list[str]:
    # read-only is implicit: no --yolo/--auto (rejected with -p anyway).
    return [*resolve_kimi(), "-p", prompt, "--output-format", "stream-json"]


def parse_stream_json(stdout: str) -> tuple[str, str | None]:
    """Extract assistant text + session id from Kimi's NDJSON stdout."""
    messages: list[str] = []
    session_id: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("role") == "assistant" and isinstance(obj.get("content"), str):
            messages.append(obj["content"])
        if obj.get("session_id"):
            session_id = obj["session_id"]
    return "\n".join(messages), session_id


def write_verdict(out: Path, text: str, session_id: str | None, error: str | None) -> None:
    """Guarantee the out file exists and is readable for the background caller."""
    body = text.strip()
    if len(body) > MAX_OUTPUT_CHARS:
        body = body[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
    if not body and error is None:
        error = "kimi exited 0 but produced no assistant output"
    if error and not body:
        out.write_text(
            "VERDICT: error\n"
            f"[kimi_review] no verdict produced: {error}\n"
            "Do NOT treat this as approve — re-dispatch. Kimi is a third-family "
            "EXTRA signal; the Fable-5 + Codex pair still governs approval.\n",
            encoding="utf-8",
        )
        return
    trailer = ""
    if session_id:
        trailer += f"\n\n[kimi session_id: {session_id} — continue with `kimi -r {session_id} -p \"...\"`]"
    if error:
        trailer += f"\n\n[kimi_review] WARNING: {error}"
    out.write_text(body + trailer + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    args.cwd = to_native_path(args.cwd)
    args.out = to_native_path(args.out)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = build_cmd(build_prompt(args.prompt, args.diff_base))
    print(f"[kimi_review] dispatching to Kimi (kimi-k3, read-only); verdict -> {args.out}", flush=True)
    error: str | None = None
    rc = 0
    stdout = ""
    try:
        proc = subprocess.run(
            cmd,
            cwd=args.cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        stdout = proc.stdout or ""
        rc = proc.returncode
        if rc != 0:
            tail = "\n".join((proc.stderr or "").splitlines()[-8:])
            error = f"kimi exited {rc}. stderr tail:\n{tail}"
    except subprocess.TimeoutExpired as exc:
        rc = 124
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        error = f"kimi timed out after {args.timeout:.0f}s (killed)"
    except FileNotFoundError:
        rc = 127
        error = (
            f"kimi not runnable: {cmd[0]!r}. Install `@moonshot-ai/kimi-code` or "
            "set KIMI_CODE_MAIN to dist/main.mjs."
        )

    if error:
        print(f"[kimi_review] {error}", file=sys.stderr)
    text, session_id = parse_stream_json(stdout)
    write_verdict(out, text, session_id, error)
    return rc


def main() -> int:
    p = argparse.ArgumentParser(
        description="Background Kimi (kimi-k3) review dispatcher — third-family, "
        "read-only, offloads to Moonshot's budget. Default over the MCP shim."
    )
    p.add_argument("--prompt", required=True, help="The review ask / focus.")
    p.add_argument("--out", required=True, help="File to write Kimi's final verdict to.")
    p.add_argument("--cwd", default=".", help="Repo/worktree root Kimi reads (default: cwd).")
    p.add_argument(
        "--diff-base",
        default=None,
        help="If set, ask Kimi to review this branch's diff vs the given base branch.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"Kill kimi after this many seconds and write VERDICT: error "
        f"(default {DEFAULT_TIMEOUT_S:.0f}). Kimi is slow — keep this generous.",
    )
    return run(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
