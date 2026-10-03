"""Per-account rollout of the thin loop (change ``control-plane-agent-loop``).

One owner-scoped value has a typed home, not a preferences bag. This setting
and the engine path are temporary: task 3.4 deletes both once the thin loop
is the only path.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tinyassets.storage import DB_FILENAME

_SCHEMA = """
CREATE TABLE IF NOT EXISTS account_agent_loop (
    owner_user_id TEXT PRIMARY KEY,
    agent_loop TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);
"""


def _connect(base_path: str | Path, *, create: bool) -> sqlite3.Connection | None:
    path = Path(base_path) / DB_FILENAME
    if not create and not path.is_file():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(_SCHEMA)
    return conn


def _subject(owner_user_id: str) -> str:
    subject = str(owner_user_id or "").strip()
    if not subject or len(subject) > 400 or not subject.isprintable():
        raise ValueError("invalid account subject")
    return subject


def set_account_agent_loop(
    base_path: str | Path, *, owner_user_id: str, agent_loop: str, updated_by: str,
) -> str:
    """Record the rollout choice; a refused value leaves the previous one alone."""
    subject = _subject(owner_user_id)
    if agent_loop not in ("engine", "thin"):
        raise ValueError("agent_loop must be engine or thin")
    conn = _connect(base_path, create=True)
    assert conn is not None
    try:
        with conn:
            conn.execute(
                "INSERT INTO account_agent_loop "
                "(owner_user_id, agent_loop, updated_at, updated_by) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(owner_user_id) DO UPDATE SET "
                "agent_loop = excluded.agent_loop, updated_at = excluded.updated_at, "
                "updated_by = excluded.updated_by",
                (subject, agent_loop, datetime.now(timezone.utc).isoformat(), updated_by),
            )
    finally:
        conn.close()
    return agent_loop


def account_agent_loop(base_path: str | Path, *, owner_user_id: str) -> str:
    """Return the owner's choice, defaulting to engine without creating a DB."""
    subject = _subject(owner_user_id)
    conn = _connect(base_path, create=False)
    if conn is None:
        return "engine"
    try:
        row = conn.execute(
            "SELECT agent_loop FROM account_agent_loop WHERE owner_user_id = ?",
            (subject,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return "engine"
    stored = row["agent_loop"]
    if stored not in ("engine", "thin"):
        raise ValueError("stored agent_loop must be engine or thin")
    return stored
