#!/usr/bin/env python3
"""Stop hook: don't end the turn while dispatched work is still running.

Founder, 2026-08-27, twice in one session: *"nothing will happen while waiting
on a process"*. Both times the session dispatched a Codex review, said it would
take the next lane, and then ended the turn instead. `AGENTS.md` already says
"a dispatched review gates landing, not your forward progress -- never idle on
one"; prose did not carry it, so this does.

**Why this blocks when `supervisor_check.py` deliberately does not.** That hook
watches the trajectory and refuses to gate, because a supervisor that can stop
a session is a new ratchet. This is the opposite operation: it does not stop
work, it declines to stop *early*. The failure it targets is idling, so the
only useful response is to keep going.

Three limits keep it from becoming the ratchet it is meant to prevent:

* **`stop_hook_active` short-circuits it.** Claude Code sets that when the turn
  is already continuing because of a stop hook, so this can never chain.
* **A hard per-session cap** (`_MAX_BLOCKS`). Past it the hook goes quiet for
  the rest of the session. A hook that can nag forever is worse than one that
  misses a case.
* **Fail open, always.** Every error path returns 0 with no decision. A hook
  that wedges a session on its own bug is not worth the case it catches.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Past this many blocks in one session, stay quiet. Chosen low on purpose: the
# point is to catch the reflex, not to drive the session.
_MAX_BLOCKS = 3

# Command-line fragments that mean "work this session started is still running".
# peer_agent.py is the dominant case -- a dispatched cross-family review.
_IN_FLIGHT_MARKERS = ("peer_agent.py",)

_TIMEOUT_S = 5


def _project_dir(payload: dict) -> Path:
    raw = payload.get("cwd") or payload.get("project_dir")
    return Path(raw) if raw else Path.cwd()


def _running_commands() -> list[str]:
    """Command lines of live processes, or [] if we cannot tell.

    [] means "no evidence", which fails open: the turn ends normally.
    """
    try:
        if os.name == "nt":
            out = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\""
                    " | Select-Object -ExpandProperty CommandLine",
                ],
                capture_output=True, text=True, timeout=_TIMEOUT_S,
            )
        else:
            out = subprocess.run(
                ["ps", "-eo", "args"],
                capture_output=True, text=True, timeout=_TIMEOUT_S,
            )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return [line for line in out.stdout.splitlines() if line.strip()]


def _in_flight(commands: list[str]) -> list[str]:
    """The distinct dispatched jobs still running, by their --out file."""
    hits = []
    for cmd in commands:
        if not any(marker in cmd for marker in _IN_FLIGHT_MARKERS):
            continue
        label = cmd
        if "--out" in cmd:
            parts = cmd.split()
            try:
                label = parts[parts.index("--out") + 1]
            except (ValueError, IndexError):
                pass
        if label not in hits:
            hits.append(label)
    return hits


def _state_path(project: Path, sid: str) -> Path:
    safe = "".join(c for c in sid if c.isalnum() or c in "-_")[:64] or "nosession"
    return project / ".agents" / "supervisor" / f"keep-working-{safe}.json"


def _blocks_so_far(path: Path) -> int:
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("blocks", 0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0


def _record_block(path: Path, count: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"blocks": count}), encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    # Already continuing because of a stop hook: never chain.
    if payload.get("stop_hook_active"):
        return 0

    project = _project_dir(payload)
    sid = str(payload.get("session_id") or "")
    state = _state_path(project, sid)

    blocks = _blocks_so_far(state)
    if blocks >= _MAX_BLOCKS:
        return 0

    pending = _in_flight(_running_commands())
    if not pending:
        return 0

    _record_block(state, blocks + 1)

    listed = "\n".join(f"  - {p}" for p in pending[:6])
    reason = (
        f"{len(pending)} dispatched job(s) still running:\n{listed}\n\n"
        "Do not end the turn to wait on them. AGENTS.md: a dispatched review "
        "gates landing, not your forward progress -- take the next lane while "
        "it runs, and never idle on one.\n\n"
        "Pick the next unblocked thing and do it now. If a lane is genuinely "
        "blocked on the running job, work a different one: another open PR, a "
        "failing test you have not triaged, durable state you owe a home. If "
        "you have checked and there is honestly nothing to advance, say so in "
        "one line and end -- but check first.\n\n"
        f"(This fires at most {_MAX_BLOCKS} times per session.)"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
