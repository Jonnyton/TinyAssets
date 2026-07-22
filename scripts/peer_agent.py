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

Publication (--write only): a sandboxed codex --write lane cannot publish its
own work, so publication belongs to THIS process, which is unsandboxed:

  --publish            after a successful --write lane, push its HEAD branch
                       from here. Refuses main/master and a detached HEAD.
  --no-publish-check   opt out of the post-run audit below.

Why parent-side, rather than just granting the sandbox egress — measured on
codex-cli 0.145.0, 2026-07-22, and cross-checked by a Codex review that refuted
an earlier, stronger version of this claim:

  * A `--full-auto` lane cannot create `.git/index.lock` ("Permission denied")
    under EITHER windows.sandbox=elevated or =unelevated, and `--add-dir` on the
    git dir does not lift it. It therefore cannot commit, let alone push.
  * Egress itself IS grantable, contrary to what the schannel error suggests:
    `-c sandbox_workspace_write.network_access=true` plus
    `git -c http.sslBackend=openssl` reaches GitHub (verified twice). Plain
    schannel fails SEC_E_NO_CREDENTIALS only because the sandbox runs as a
    different Windows principal that cannot open the host's credential store.
  * So the case for parent-side publication is a security boundary, not an
    impossibility: granting egress would put push credentials beside an agent
    with outbound network, and that principal's authenticated-push path is
    unverified. Generation and publication stay separate.

Whether or not --publish is used, a --write lane is audited afterwards: if
--cwd still holds commits reachable from no remote, OR uncommitted changes,
the peer's work never left the machine and this exits 3 rather than reporting
success (AGENTS.md Hard Rule 8 — fail loudly, never silently). Both halves are
load-bearing: on 2026-07-21 the unpushed-commit case silently stranded 36
finished codex lanes (PR #1539), and under the sandbox above a lane cannot
commit at all, so its work strands as an uncommitted diff instead.

Output contract: on success the --out file holds the peer's final message;
on failure it holds a `[peer_agent] ERROR ...` block and the exit code is
non-zero (2 provider/usage error, 3 work completed but unpublished, 124
timeout, 127 CLI not launchable). Exit 3 is the one failure that PRESERVES the
peer's report and appends its notice, because that work is recoverable and the
report is how you recover it. Argparse usage errors are the only failure that
cannot write --out (the path is not known yet). The full result is also printed
to stdout, so a background caller sees it in the task log. A pre-existing --out
file is never mistaken for a fresh result: the codex -o target is unlinked
before dispatch.
"""

from __future__ import annotations

import argparse
import os
import shutil
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


def git(cwd: str, *argv: str, timeout: int = 60) -> tuple[int, str]:
    """Run git in cwd. Returns (rc, stdout+stderr). rc -1 = git not launchable."""
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *argv], capture_output=True, timeout=timeout
        )
    except OSError:
        return -1, "git executable not launchable"
    except subprocess.TimeoutExpired:
        return 1, f"git {' '.join(argv)} exceeded {timeout}s"
    text = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    return proc.returncode, text


def worktree_baseline(cwd: str) -> frozenset[str] | None:
    """Snapshot dirty paths BEFORE dispatch, so the audit judges only this
    lane's output. Without it the audit trips over scratch that was already
    lying in the worktree (observed: fleet state files under .claude/), and a
    guard that cries wolf on someone else's mess gets ignored — which is how
    the silence it replaces got tolerated in the first place.
    """
    rc, porcelain = git(cwd, "status", "--porcelain")
    if rc != 0:
        return None
    return frozenset(ln for ln in porcelain.splitlines() if ln.strip())


def publication_state(
    cwd: str, baseline: frozenset[str] | None = None
) -> tuple[str, str, str]:
    """Classify whether cwd holds committed work that never reached a remote.

    Returns (state, branch, detail). State is one of:
      skip     nothing to publish — not a work tree, or HEAD is already
               reachable from a remote AND the work tree is clean.
      blocked  real local-only work: commits reachable from no remote, and/or
               uncommitted changes. BOTH count — a sandboxed lane that cannot
               write .git strands its work as an uncommitted diff, which an
               unpushed-commits-only check would wave through as success.
      unknown  git could not answer. NEVER collapsed into `skip`: the codex
               sandbox writes worktrees as a different Windows account, so
               `git -C` there fails `dubious ownership` (PR #1539) — the exact
               case where assuming "clean" would relaunch the silent failure.
    """
    rc, out = git(cwd, "rev-parse", "--is-inside-work-tree")
    if rc == -1:
        return "skip", "", "git not available"
    if rc != 0:
        if "not a git repository" in out.lower():
            return "skip", "", "not a git work tree"
        return "unknown", "", out

    # --porcelain honors .gitignore, so sandbox test-temp dirs and other
    # ignored scratch never count as unpublished work.
    rc, porcelain = git(cwd, "status", "--porcelain")
    if rc != 0:
        return "unknown", "", porcelain
    lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    if baseline is not None:
        lines = [ln for ln in lines if ln not in baseline]
    dirty = len(lines)

    # Unborn HEAD (init, no commit): only uncommitted work can be at stake.
    if git(cwd, "rev-parse", "--verify", "HEAD")[0] != 0:
        if dirty:
            return "blocked", "", f"{dirty} uncommitted change(s), no commit yet"
        return "skip", "", "no commits on HEAD"

    rc, branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return "unknown", "", branch

    # Commits on HEAD reachable from NO remote-tracking ref. Counting against
    # --remotes (not @{upstream}) is deliberate: a lane's branch is usually
    # brand new and has no upstream configured at all.
    rc, count = git(cwd, "rev-list", "--count", "HEAD", "--not", "--remotes")
    if rc != 0:
        return "unknown", branch, count

    reasons = []
    if count != "0":
        reasons.append(f"{count} commit(s) on HEAD reachable from no remote")
    if dirty:
        reasons.append(f"{dirty} uncommitted change(s) in the work tree")
    if not reasons:
        return "skip", branch, "HEAD is reachable from a remote; work tree clean"
    return "blocked", branch, "; ".join(reasons)


def publish_branch(cwd: str, branch: str) -> tuple[bool, str]:
    """Push branch to origin from THIS (unsandboxed) process."""
    if not branch or branch == "HEAD":
        return False, "HEAD is detached — no branch name to push"
    if branch in ("main", "master"):
        return False, f"refusing to push {branch!r} (AGENTS.md: never push to main)"
    rc, out = git(cwd, "push", "-u", "origin", f"HEAD:refs/heads/{branch}", timeout=300)
    return rc == 0, out


def settle_publication(
    cwd: str, publish: bool, baseline: frozenset[str] | None = None
) -> tuple[str, int]:
    """Publish if asked, then verify the work actually left the machine.

    Returns (notice, exit_code); exit_code 3 means real work is still local-only.
    """
    state, branch, detail = publication_state(cwd, baseline)
    pushed = ""

    # Only a push can fix unpushed commits; --publish deliberately does NOT
    # commit on the peer's behalf. Inventing a commit here would guess at the
    # message and the scope, which is the kitchen-sink-diff failure mode
    # CLAUDE.md calls out — the operator decides what a commit contains.
    if state == "blocked" and publish and "reachable from no remote" in detail:
        ok, out = publish_branch(cwd, branch)
        if ok:
            state, branch, detail = publication_state(cwd, baseline)
            if state == "skip":
                return f"\n[peer_agent] published {branch} -> origin\n", 0
            pushed = f"\n  push:     OK ({branch} -> origin), but work still remains"
        else:
            last = out.splitlines()[-1] if out else "no output"
            pushed = f"\n  push:     FAILED — {last}"

    if state == "skip":
        return "", 0

    if state == "unknown":
        body = (
            f"  detail:   git could not determine publication state — {detail}\n"
            "  This is the dubious-ownership case: a codex sandbox worktree is\n"
            "  owned by another Windows account. Grant access, then re-check:\n"
            f'      git config --global --add safe.directory "{cwd}"\n'
            f'      git -C "{cwd}" log --oneline @{{u}}..HEAD'
        )
    else:
        steps = []
        if "uncommitted" in detail:
            steps.append(f'      git -C "{cwd}" status   # then stage + commit what belongs')
        if "no remote" in detail or "uncommitted" in detail:
            target = branch or "<branch>"
            steps.append(f'      git -C "{cwd}" push -u origin HEAD:refs/heads/{target}')
        body = (
            f"  branch:   {branch or '(unborn)'}\n"
            f"  detail:   {detail}{pushed}\n"
            "  A sandboxed codex --write lane can neither commit nor push its own\n"
            "  work. Recover it from an unsandboxed shell:\n"
            + "\n".join(steps)
            + "\n  Re-dispatching with --publish pushes commits, but never creates them."
        )

    return (
        "\n[peer_agent] PUBLICATION BLOCKED — the peer finished, but its work "
        f"never left this machine.\n  worktree: {cwd}\n{body}\n"
    ), 3


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the whole process tree (Windows .cmd -> node grandchildren)."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True
        )
    else:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


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
    p.add_argument(
        "--publish",
        action="store_true",
        help="After a --write lane, push its HEAD branch from this (unsandboxed) process.",
    )
    p.add_argument(
        "--no-publish-check",
        action="store_true",
        help="Skip the post---write audit for committed-but-unpushed work.",
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
        print(full, file=sys.stderr)
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
    # Must be taken BEFORE the peer runs, or its own output lands in the
    # baseline and the audit excuses exactly what it exists to catch.
    baseline = (
        worktree_baseline(args.cwd)
        if args.write and not args.no_publish_check
        else None
    )
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=args.cwd,
        )
        try:
            stdout_b, stderr_b = proc.communicate(
                input=prompt.encode("utf-8"), timeout=args.timeout
            )
        except subprocess.TimeoutExpired:
            kill_tree(proc)  # .cmd -> node grandchildren must die too
            proc.communicate()  # reap once pipe handles are gone
            return fail(
                f"{args.provider} exceeded {args.timeout}s timeout — process tree killed.",
                124,
            )
    except OSError as exc:
        # Covers missing binary AND WinError 193 (extensionless bash shim).
        return fail(
            f"{args.provider} executable not launchable: {cmd[0]!r} ({exc}). "
            f"Set {args.provider.upper()}_BIN to the full path of the CLI "
            "(.cmd on Windows).",
            127,
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

        # The peer succeeded, but "succeeded" is not the same as "published".
        # Append rather than overwrite: unlike every other failure path, the
        # work behind an exit 3 is recoverable and this report is how you
        # recover it — clobbering it with fail() would destroy the evidence.
        notice, code = "", 0
        if args.write and not args.no_publish_check:
            notice, code = settle_publication(args.cwd, args.publish, baseline)
            if notice and out_path:
                try:
                    with open(out_path, "a", encoding="utf-8") as fh:
                        fh.write(notice)
                except OSError:
                    pass  # stdout/stderr still carry it

        print(text)
        if notice:
            print(notice)
            print(notice, file=sys.stderr)
        print(
            f"[peer_agent] {args.provider} "
            f"{'done' if code == 0 else 'UNPUBLISHED'} in {elapsed:.0f}s -> "
            f"{args.out or 'stdout'}",
            file=sys.stderr,
        )
        return code
    finally:
        if owned_temp:
            Path(owned_temp).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
