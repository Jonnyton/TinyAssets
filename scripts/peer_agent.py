#!/usr/bin/env python3
"""Peer-agent dispatch — hand a task to the Claude Code or Codex CLI as a
subprocess peer, on THAT subscription's budget (no API keys, no host-session
context spent). Generalizes scripts/codex_review.py to both CLIs and to
arbitrary prompts, for use by any provider session (Kimi, Claude Code,
Codex, Cursor, ...) from a foreground or background shell call.

Usage (typically backgrounded; result always lands in --out file):
  python scripts/peer_agent.py claude --out review.md --prompt-file brief.md
  python scripts/peer_agent.py codex --out fix.md --prompt "fix the flaky test" \
      --cwd ../wf-bug126 --write
  echo "summarize PLAN.md" | python scripts/peer_agent.py claude

Modes:
  default   read-only-ish. claude: plain `-p` (edit/bash tools denied).
            codex: `-s read-only -c approval_policy=never`.
  --write   full agent. claude: --dangerously-skip-permissions.
            codex: --full-auto (workspace-write sandbox; weak on Windows —
            point --cwd at a worktree, not the live checkout).

Output contract: on success the --out file holds the peer's final message;
on failure it holds a `[peer_agent] ERROR ...` block and the exit status is
non-zero. Before launch, the statuses are 2 for provider/usage error and 127
when the CLI is not launchable. After launch, Windows reports 124 for timeout,
125 when cleanup cannot be verified, and 126 for an I/O failure. On POSIX,
verified cleanup kills the wrapper-owned process group with SIGKILL, so the
parent observes ``-SIGKILL`` through ``subprocess`` (normally 137 from a
shell); the --out ERROR block is the authoritative failure detail. A POSIX
cleanup failure may still return 125 before group termination.
Argparse usage errors are the only failure that cannot write --out (the path
is not known yet). The full result is also printed to stdout, so a background
caller sees it in the task log. A pre-existing --out file is never mistaken
for a fresh result: the codex -o target is unlinked before dispatch.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from codex_review import resolve_codex, to_native_path  # noqa: E402

from tinyassets.providers.base import subprocess_env_for_provider  # noqa: E402

# codex v0.122+ can exit 0 with empty output on auth failure (see
# workflow/providers/codex_provider.py). Same heuristic here — stderr only,
# the transcript stdout can carry false-positive substrings ("401" in a git
# hash, "auth" in prose).
_AUTH_PATTERNS = ("401", "unauthorized", "reconnecting", "auth", "login")

# cmd.exe metacharacters. When the resolved CLI is a .cmd/.bat, Windows routes
# argv through cmd.exe parsing even with shell=False (BatBadBut class):
# list2cmdline quoting does NOT protect these, so reject them loudly instead.
_CMD_METACHARS = frozenset("&|%<>^\"")


class PeerCleanupError(RuntimeError):
    """The provider process tree could not be proven stopped and reaped."""


def resolve_claude() -> str:
    """Locate a runnable claude executable (mirrors codex_review.resolve_codex).

    Honors CLAUDE_BIN, then PATH, then the known install dir. On Windows an
    extensionless hit is a Git-Bash shim that CreateProcess rejects
    (WinError 193), so prefer the sibling .cmd/.exe.
    """
    override = os.environ.get("CLAUDE_BIN")
    if override and Path(override).exists():
        return override
    found = shutil.which("claude")
    if found:
        if sys.platform == "win32" and not os.path.splitext(found)[1]:
            for ext in (".cmd", ".exe"):
                if Path(found + ext).exists():
                    return found + ext
        return found
    for name in ("claude.cmd", "claude.exe", "claude"):
        candidate = Path.home() / ".local" / "bin" / name
        if candidate.exists():
            return str(candidate)
    return "claude"  # last resort; surfaces a clear launch error below


def resolve_prompt(args: argparse.Namespace) -> str:
    if args.prompt is not None:
        return args.prompt
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    return sys.stdin.read()


def build_claude_cmd(args: argparse.Namespace) -> list[str]:
    # Default model "fable": the alias tracks the latest Claude model on a Max
    # subscription (currently claude-fable-5). Bare `claude -p` does not
    # default to the frontier model.
    #
    # WORKFLOW_CLAUDE_MODEL overrides that default, mirroring WORKFLOW_CODEX_MODEL on
    # the codex path. This exists because when the pinned model is rate-limited the
    # CLI exits 1 after ~25s with COMPLETELY EMPTY stderr: every lane dies silently
    # while the dispatcher reports success, and a dead lane is indistinguishable from
    # a working one from outside. Four lanes were lost that way on 2026-07-21 before
    # anyone noticed. An explicit --model still wins.
    model = args.model or os.environ.get("WORKFLOW_CLAUDE_MODEL", "").strip() or "fable"
    cmd = [resolve_claude(), "-p", "--model", model]
    if args.write:
        cmd.append("--dangerously-skip-permissions")
    if args.system:
        cmd.extend(["--system-prompt", args.system])
    return cmd


def build_codex_cmd(args: argparse.Namespace, out_path: str) -> list[str]:
    cmd = [
        resolve_codex(),
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "-c",
        "approval_policy=never",
        "-C",
        args.cwd,
        "-o",
        out_path,
    ]
    if args.write:
        cmd.append("--full-auto")
    else:
        cmd.extend(["-s", "read-only"])
    # No -m by default: codex then uses the model from ~/.codex/config.toml,
    # which the host keeps at the subscription frontier (e.g. gpt-5.6-sol).
    # Pin only when explicitly asked via --model or WORKFLOW_CODEX_MODEL.
    model = args.model or os.environ.get("WORKFLOW_CODEX_MODEL", "").strip()
    if model:
        cmd.extend(["-m", model])
    if args.effort:
        cmd.extend(["-c", f"model_reasoning_effort={args.effort}"])
    return cmd


def unsafe_cmd_argv(cmd: list[str]) -> str | None:
    """Return the first argv value unsafe for a .cmd/.bat target, else None."""
    if not cmd[0].lower().endswith((".cmd", ".bat")):
        return None
    for arg in cmd[1:]:
        if any(c in _CMD_METACHARS for c in arg):
            return arg
    return None


def _ensure_own_process_group() -> None:
    """Make this wrapper the stable POSIX group leader before provider launch."""
    if sys.platform == "win32":
        return
    pid = os.getpid()
    if os.getpgrp() != pid:
        os.setpgid(0, 0)
    if os.getpgrp() != pid:
        raise PeerCleanupError(
            f"peer wrapper {pid} could not establish its own process group"
        )


def _terminate_own_process_group() -> None:
    """Flush diagnostics, then terminate wrapper and provider together."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (AttributeError, OSError, ValueError):
            pass
    pgid = os.getpgrp()
    os.killpg(pgid, getattr(signal, "SIGKILL", signal.SIGTERM))
    raise PeerCleanupError(
        f"process-group termination unexpectedly returned for peer wrapper {pgid}"
    )


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the whole process tree (Windows .cmd -> node grandchildren)."""
    if sys.platform != "win32":
        _terminate_own_process_group()
        return
    cleanup_error: PeerCleanupError | None = None
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
        )
    except OSError as exc:
        cleanup_error = PeerCleanupError(
            f"taskkill failed for provider process tree {proc.pid}: {exc}"
        )
    else:
        if result.returncode != 0:
            cleanup_error = PeerCleanupError(
                f"taskkill failed for provider process tree {proc.pid} "
                f"with exit code {result.returncode}"
            )
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired as exc:
        raise PeerCleanupError(
            f"provider wrapper {proc.pid} did not exit after process-tree cleanup"
        ) from exc
    except OSError as exc:
        raise PeerCleanupError(
            f"provider wrapper {proc.pid} could not be reaped: {exc}"
        ) from exc
    if cleanup_error:
        raise cleanup_error


def main() -> int:
    # Background pipes on Windows default to cp1252; peer output routinely
    # contains non-cp1252 chars (→, —, …) and must not crash the stdout echo.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(
        description="Dispatch a task to the claude/codex CLI as a peer agent."
    )
    p.add_argument("provider", choices=["claude", "codex"])
    p.add_argument(
        "--prompt", default=None, help="Task text (else --prompt-file, else stdin)."
    )
    p.add_argument("--prompt-file", default=None, help="Read task text from a file (utf-8).")
    p.add_argument(
        "--system", default=None, help="System prompt (codex: prepended to prompt)."
    )
    p.add_argument("--out", default=None, help="File for the peer's final message.")
    p.add_argument("--cwd", default=".", help="Working dir the peer operates in.")
    p.add_argument(
        "--timeout", type=int, default=1800, help="Seconds before kill (default 1800)."
    )
    p.add_argument(
        "--write", action="store_true", help="Grant write/exec autonomy (see docstring)."
    )
    p.add_argument("--model", default=None, help="Model override passed through to the CLI.")
    p.add_argument(
        "--effort", default=None, help="Codex reasoning effort (minimal/low/medium/high/xhigh)."
    )
    args = p.parse_args()

    # to_native_path BEFORE abspath: abspath("/c/Users/...") on Windows yields
    # <drive>:\c\Users\..., which the MSYS regex can no longer repair.
    args.cwd = os.path.abspath(to_native_path(args.cwd))
    if args.out:
        # Absolute: codex resolves a relative -o against ITS cwd (args.cwd),
        # not ours — a relative --out + --cwd combo breaks the write (os error 3).
        args.out = os.path.abspath(to_native_path(args.out))
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    owned_temp: str | None = None
    out_path = args.out

    def fail(msg: str, code: int) -> int:
        """Every non-argparse failure leaves an ERROR block in --out when set."""
        full = f"[peer_agent] ERROR: {msg}"
        if out_path:
            try:
                Path(out_path).write_text(full + "\n", encoding="utf-8")
            except OSError:
                pass  # stderr still carries the message
        print(full, file=sys.stderr, flush=True)
        return code

    if not Path(args.cwd).is_dir():
        return fail(f"--cwd is not a directory: {args.cwd}", 2)

    try:
        prompt = resolve_prompt(args)
    except OSError as exc:
        return fail(f"cannot read prompt: {exc}", 2)
    if not prompt.strip():
        return fail("empty prompt", 2)

    if args.provider == "claude":
        env = subprocess_env_for_provider("claude-code")
        cmd = build_claude_cmd(args)
    else:
        env = subprocess_env_for_provider("codex")
        if args.system:
            prompt = f"{args.system}\n\n{prompt}"
        if not out_path:
            fd, owned_temp = tempfile.mkstemp(
                prefix="peer_agent_codex_", suffix=".md"
            )
            os.close(fd)
            out_path = owned_temp
        else:
            # Never accept a pre-existing -o file as a fresh codex result.
            Path(out_path).unlink(missing_ok=True)
        cmd = build_codex_cmd(args, out_path)

    env.pop("TINYASSETS_VILLAGE_TOKEN", None)
    env.pop("WORKFLOW_MCP_TOKEN", None)

    bad_arg = unsafe_cmd_argv(cmd)
    if bad_arg is not None:
        return fail(
            f"argv value {bad_arg!r} contains a cmd.exe metacharacter, unsafe "
            f"for batch-file target {cmd[0]!r}. Point "
            f"{args.provider.upper()}_BIN at a native .exe, or remove the "
            "metacharacter (& % | < > ^ \").",
            2,
        )

    mode = "write" if args.write else "read-only"
    print(
        f"[peer_agent] dispatching to {args.provider} ({mode}); cwd={args.cwd}",
        file=sys.stderr,
    )
    start = time.monotonic()
    process_group: dict[str, object]
    if sys.platform == "win32":
        process_group = {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        }
    else:
        try:
            _ensure_own_process_group()
        except (OSError, PeerCleanupError) as exc:
            return fail(f"could not establish wrapper process group: {exc}", 125)
        process_group = {}
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=args.cwd,
            **process_group,
        )
    except OSError as exc:
        # Covers missing binary AND WinError 193 (extensionless bash shim).
        return fail(
            f"{args.provider} executable not launchable: {cmd[0]!r} ({exc}). "
            f"Set {args.provider.upper()}_BIN to the full path of the CLI "
            "(.cmd on Windows).",
            127,
        )
    try:
        stdout_b, stderr_b = proc.communicate(
            input=prompt.encode("utf-8"), timeout=args.timeout
        )
    except subprocess.TimeoutExpired:
        if sys.platform != "win32":
            code = fail(
                f"{args.provider} exceeded {args.timeout}s timeout — "
                "terminating wrapper process group.",
                124,
            )
            try:
                _terminate_own_process_group()
            except (OSError, PeerCleanupError) as exc:
                return fail(
                    f"{args.provider} cleanup could not be verified: {exc}",
                    125,
                )
            return code
        try:
            kill_tree(proc)  # .cmd -> node grandchildren must die too
            proc.communicate()  # reap once pipe handles are gone
        except PeerCleanupError as exc:
            return fail(
                f"{args.provider} cleanup could not be verified: {exc}",
                125,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return fail(
                f"{args.provider} timed out; pipe reaping could not be verified "
                f"after process-tree cleanup ({exc}).",
                125,
            )
        return fail(
            f"{args.provider} exceeded {args.timeout}s timeout — process tree killed.",
            124,
        )
    except OSError as exc:
        if sys.platform != "win32":
            fail(
                f"{args.provider} communication failed after launch ({exc}); "
                "terminating wrapper process group.",
                126,
            )
            try:
                _terminate_own_process_group()
            except (OSError, PeerCleanupError) as cleanup_exc:
                return fail(
                    f"{args.provider} communication failed after launch ({exc}); "
                    f"cleanup could not be verified: {cleanup_exc}",
                    125,
                )
            return 126
        try:
            kill_tree(proc)
            proc.communicate()
        except PeerCleanupError as cleanup_exc:
            return fail(
                f"{args.provider} communication failed after launch ({exc}); "
                f"cleanup could not be verified: {cleanup_exc}",
                125,
            )
        except (OSError, subprocess.TimeoutExpired) as reap_exc:
            return fail(
                f"{args.provider} communication failed after launch ({exc}); "
                f"pipe reaping could not be verified after cleanup ({reap_exc}).",
                125,
            )
        return fail(
            f"{args.provider} communication failed after launch ({exc}); "
            "process-tree cleanup verified.",
            126,
        )
    elapsed = time.monotonic() - start

    try:
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            return fail(
                f"{args.provider} exited {proc.returncode} after {elapsed:.0f}s\n"
                f"stderr: {stderr[:1500].strip() or '(empty)'}",
                2,
            )

        if args.provider == "codex":
            text = (
                Path(out_path).read_text(encoding="utf-8", errors="replace")
                if Path(out_path).exists()
                else ""
            )
        else:
            text = stdout.strip()

        if not text.strip():
            hint = ""
            if args.provider == "codex" and any(
                pat in stderr.lower() for pat in _AUTH_PATTERNS
            ):
                hint = " (auth/login signal detected)"
            return fail(
                f"{args.provider} produced empty output{hint}.\n"
                f"stdout tail: {stdout[-800:].strip() or '(empty)'}\n"
                f"stderr tail: {stderr[-800:].strip() or '(empty)'}",
                2,
            )

        if args.provider == "claude" and out_path:
            Path(out_path).write_text(text + "\n", encoding="utf-8")
        print(text)
        print(
            f"[peer_agent] {args.provider} done in {elapsed:.0f}s -> "
            f"{args.out or 'stdout'}",
            file=sys.stderr,
        )
        return 0
    finally:
        if owned_temp:
            Path(owned_temp).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
