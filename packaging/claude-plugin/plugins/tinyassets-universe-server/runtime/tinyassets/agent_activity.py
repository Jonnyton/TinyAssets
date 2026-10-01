"""What the universe agent's tools are doing, for its owner to watch (harness S4).

Founder, 2026-10-01: the app should let him see the agent work, the way Claude
Code shows each tool as it runs. Production on 2026-10-01 had 109 tool rows in
``agent_turn_tools``, all from the HTTP loop and none from a native CLI turn, so
nobody (the founder or the agent) could see which tools a turn had called
(design #4172 §3.2).

Every adapter's tools run through the one per-universe engine process, so that
is where each call is recorded: once when it starts and once when it ends, with
a one-line summary (the command, the path, the target) and, on failure, the
first line of the real cause. This is an observation log, never authority: no
code decides anything from it, and losing a row loses nothing but the view.

The store sits beside the session records in the data root's
``.agent-sessions/<universe>/``, outside every universe folder. Each session
keeps its latest :data:`KEEP_PER_SESSION` calls.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path

from tinyassets import agent_sessions

#: Calls kept per session; older ones are dropped as new ones start.
KEEP_PER_SESSION = 200
#: Longest summary or error line stored.
MAX_LINE = 240

_FILE = "activity.db"
_SCHEMA = """CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL,
    tool TEXT NOT NULL,
    summary TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    ok INTEGER,
    error TEXT)"""


def _connect(universe_dir: Path) -> sqlite3.Connection:
    path = agent_sessions._records_dir(Path(universe_dir)) / _FILE
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute(_SCHEMA)
    return conn


def _line(text: object) -> str:
    one = " ".join(str(text or "").split())
    return one if len(one) <= MAX_LINE else one[: MAX_LINE - 1] + "…"


def summarize(tool: str, arguments: dict | None) -> str:
    """One line saying what a call does, from its own arguments."""
    args = arguments if isinstance(arguments, dict) else {}
    if tool == "bash":
        return _line(args.get("command"))
    if tool in ("read", "write", "edit"):
        return _line(args.get("path"))
    for key in ("target", "action", "operation", "name", "path"):
        if args.get(key):
            return _line(f"{key}={args.get(key)}")
    return ""


def started(universe_dir: Path, session_key: str, tool: str, summary: str) -> int:
    """Record a call starting; returns its id."""
    now = time.time()
    with closing(_connect(universe_dir)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            "INSERT INTO tool_calls (session_key, tool, summary, started_at) "
            "VALUES (?, ?, ?, ?)",
            (session_key, _line(tool), _line(summary), now),
        )
        conn.execute(
            "DELETE FROM tool_calls WHERE session_key = ? AND id NOT IN ("
            "SELECT id FROM tool_calls WHERE session_key = ? ORDER BY id DESC LIMIT ?)",
            (session_key, session_key, KEEP_PER_SESSION),
        )
        conn.execute("COMMIT")
    return int(cursor.lastrowid)


def finished(universe_dir: Path, call_id: int, *, ok: bool, error: str = "") -> None:
    """Record how a call ended: ``ok``, or the first line of its real cause."""
    first = str(error or "").strip().splitlines()
    with closing(_connect(universe_dir)) as conn:
        conn.execute(
            "UPDATE tool_calls SET finished_at = ?, ok = ?, error = ? WHERE id = ?",
            (time.time(), 1 if ok else 0, _line(first[0]) if first else "", call_id),
        )


def recent(universe_dir: Path, session_key: str, *, limit: int = 5,
           since: float | None = None) -> list[dict]:
    """The latest calls of ``session_key``, newest first, for the owner's view."""
    now = time.time()
    query = ("SELECT tool, summary, started_at, finished_at, ok, error FROM tool_calls "
             "WHERE session_key = ?")
    params: list = [session_key]
    if since is not None:
        query += " AND started_at >= ?"
        params.append(float(since))
    query += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 50)))
    path = agent_sessions._records_dir(Path(universe_dir)) / _FILE
    if not path.exists():
        return []
    with closing(_connect(universe_dir)) as conn:
        rows = conn.execute(query, params).fetchall()
    out = []
    for tool, summary, began, ended, ok, error in rows:
        item = {
            "tool": tool,
            "summary": summary,
            "state": "running" if ended is None else ("done" if ok else "failed"),
            "age_s": round(max(0.0, now - began), 1),
        }
        if ended is not None:
            item["took_s"] = round(max(0.0, ended - began), 1)
        if error:
            item["error"] = error
        out.append(item)
    return out
