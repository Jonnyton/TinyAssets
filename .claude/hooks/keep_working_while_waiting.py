#!/usr/bin/env python3
"""Stop hook: don't end the turn on an outstanding dispatch.

Founder, twice in one session on 2026-08-27: *"nothing will happen while
waiting on a process"*, then *"we might need a hook, something like, remain
active continuing towards our current objectives when waiting"*. `AGENTS.md`
already says "a dispatched review gates landing, not your forward progress --
never idle on one". Prose did not carry it, so this does.

**Three states, not one.** A first version watched only for a *running*
process, and would still have missed the case that prompted this: the turn
ended with a review that had already FINISHED, its verdict unread. A dispatch
that dies without writing its `--out` file is a third case again, and no
process listing can distinguish it from one that never started. So this reads
the ledger `peer_agent.py` writes, and reports:

* ``running``  -- started, not finished. Take another lane.
* ``ready``    -- finished, verdict not yet surfaced. Read it and act.
* ``vanished`` -- finished with no result file. Re-dispatch or move on.

Each row is surfaced **once**: the hook stamps what it has already said, so a
verdict you were told about does not nag every turn. That is the same property
`supervisor_check.py` keeps, and for the same reason -- a warning repeated on
every Stop is itself the endless-process pattern it exists to break.

**Why this blocks when `supervisor_check.py` deliberately does not.** That hook
watches the trajectory and refuses to gate, because a supervisor that can stop
a session is a new ratchet. This is the opposite operation: it does not stop
work, it declines to stop *early*.

Three limits keep it from becoming that ratchet:

* **`stop_hook_active` short-circuits it**, so it can never chain on its own
  continuation.
* **A hard per-session cap** (`_MAX_BLOCKS`), then silence for the session.
* **Fail open, always.** Every error path returns 0 with no decision. A hook
  that wedges a session on its own bug is not worth the case it catches.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_MAX_BLOCKS = 3

# A dispatch still "running" after this long is almost certainly gone: the
# longest --timeout used here is 1800s, and peer_agent closes its row in a
# `finally`. Past this, treat an open row as vanished rather than pretend.
_STALE_AFTER_S = 2 * 60 * 60


def _git_common_dir(start: Path) -> "Path | None":
    """The shared `.git` for this checkout, found WITHOUT running git.

    Deliberately filesystem-only. `peer_agent`'s own tests monkeypatch
    `subprocess` wholesale, so a `git rev-parse` here was intercepted by their
    fake process and broke eight of them -- a ledger has no business being
    reachable from the code under test.

    A linked worktree's `.git` is a FILE containing `gitdir: <path>/.git/
    worktrees/<name>`; the common dir is the part before `worktrees`. In a
    normal checkout `.git` is the directory itself.
    """
    for d in [start, *start.parents]:
        dot = d / ".git"
        if dot.is_dir():
            return dot
        if dot.is_file():
            try:
                text = dot.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if not text.startswith("gitdir:"):
                return None
            git_dir = Path(text.split(":", 1)[1].strip())
            if not git_dir.is_absolute():
                git_dir = (d / git_dir).resolve()
            parts = git_dir.parts
            if "worktrees" in parts:
                return Path(*parts[: parts.index("worktrees")])
            return git_dir
    return None


def _ledger_path(project: Path) -> Path | None:
    """Beside the SHARED git common dir, so every worktree sees one ledger."""
    common = _git_common_dir(project)
    return None if common is None else common / "tinyassets-dispatch-ledger.jsonl"


def _rows(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def outstanding(rows: list[dict], *, now: float) -> list[tuple[str, str]]:
    """(state, out) per dispatch, newest first. Only unfinished business."""
    by_pid: dict = {}
    for row in rows:
        key = (row.get("pid"), row.get("out"))
        by_pid.setdefault(key, {"out": row.get("out") or "(no --out)", "at": 0.0})
        entry = by_pid[key]
        entry["at"] = max(entry["at"], float(row.get("at") or 0.0))
        if row.get("event") == "finished":
            entry["finished"] = True
            entry["code"] = row.get("code")

    result = []
    for entry in sorted(by_pid.values(), key=lambda e: e["at"], reverse=True):
        out = entry["out"]
        has_result = out != "(no --out)" and Path(out).exists()
        if not entry.get("finished"):
            if now - entry["at"] > _STALE_AFTER_S:
                result.append(("vanished", out))
            else:
                result.append(("running", out))
        elif has_result:
            result.append(("ready", out))
        else:
            result.append(("vanished", out))
    return result


def _state_path(project: Path, sid: str) -> Path:
    safe = "".join(c for c in sid if c.isalnum() or c in "-_")[:64] or "nosession"
    return project / ".agents" / "supervisor" / f"keep-working-{safe}.json"


def _load_state(path: Path) -> dict:
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
        return got if isinstance(got, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _save_state(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


_ADVICE = {
    "running": "still running -- take a different lane, do not wait on it",
    "ready": "FINISHED and unread -- read it and act on the verdict",
    "vanished": "finished with no result file -- re-dispatch it or drop it",
}


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return 0

    raw = payload.get("cwd") or payload.get("project_dir")
    project = Path(raw) if raw else Path.cwd()
    state_path = _state_path(project, str(payload.get("session_id") or ""))
    state = _load_state(state_path)

    if int(state.get("blocks", 0)) >= _MAX_BLOCKS:
        return 0

    ledger = _ledger_path(project)
    if ledger is None or not ledger.exists():
        return 0

    pending = outstanding(_rows(ledger), now=time.time())
    told = set(state.get("told", []))
    fresh = [(s, o) for s, o in pending if f"{s}:{o}" not in told]
    if not fresh:
        return 0

    state["blocks"] = int(state.get("blocks", 0)) + 1
    state["told"] = sorted(told | {f"{s}:{o}" for s, o in fresh})
    _save_state(state_path, state)

    listed = "\n".join(f"  - [{s}] {o}\n      {_ADVICE[s]}" for s, o in fresh[:6])
    print(json.dumps({"decision": "block", "reason": (
        f"{len(fresh)} outstanding dispatch(es):\n{listed}\n\n"
        "Do not end the turn on these. AGENTS.md: a dispatched review gates "
        "landing, not your forward progress -- take the next lane while it "
        "runs, and never idle on one.\n\n"
        "Read anything marked FINISHED now, then pick the next unblocked thing "
        "and do it. If every lane is genuinely blocked on a running job, work "
        "something else: another open PR, an untriaged failing test, durable "
        "state you owe a home. If you have checked and there is honestly "
        "nothing to advance, say so in one line and end -- but check first.\n\n"
        f"(Each item is surfaced once; at most {_MAX_BLOCKS} blocks per session.)"
    )}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
