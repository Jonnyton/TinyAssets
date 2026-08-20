"""Durable, content-free outbox linking an app-originated background action run to
its Slack conversation, so its terminal result can be delivered as a follow-up.

Content-free by design (Slice 3): a row carries the run id, the originating
``(workspace, channel, thread)`` conversation, an opaque app-binding reference, and
the origin event id — NEVER a credential and NEVER a pre-authorized reply body.
Delivery authority is re-resolved fresh at delivery time (see
``action_result_delivery``); the outbox only remembers WHERE a result should go and
WHETHER it has been delivered.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from tinyassets.storage import db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_result_outbox (
    run_id            TEXT PRIMARY KEY,
    universe_id       TEXT NOT NULL,
    workspace_id      TEXT NOT NULL,
    channel_id        TEXT NOT NULL,
    thread_ts         TEXT NOT NULL,
    app_binding_ref   TEXT NOT NULL,
    origin_event_id   TEXT NOT NULL,
    created_at        REAL NOT NULL,
    state             TEXT NOT NULL CHECK (state IN ('pending','delivered','failed_final')),
    delivered_at      REAL,
    terminal_revision INTEGER
);
CREATE INDEX IF NOT EXISTS idx_action_result_outbox_state
    ON action_result_outbox(state);
"""


def _connect(base_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(Path(base_path)))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def record(
    base_path: str | Path,
    *,
    run_id: str,
    universe_id: str,
    workspace_id: str,
    channel_id: str,
    thread_ts: str,
    app_binding_ref: str,
    origin_event_id: str,
    now: float | None = None,
) -> bool:
    """Record a pending outbox entry for ``run_id``. Idempotent (INSERT OR IGNORE).

    Returns True if a NEW row was inserted, False if one already existed for this
    run (an action enqueued twice records once). Stores NO credential / reply body.
    """
    ts = time.time() if now is None else now
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO action_result_outbox (
                run_id, universe_id, workspace_id, channel_id, thread_ts,
                app_binding_ref, origin_event_id, created_at, state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                run_id, universe_id, workspace_id, channel_id, thread_ts,
                app_binding_ref, origin_event_id, ts,
            ),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def list_pending(base_path: str | Path, *, limit: int = 200) -> list[dict[str, Any]]:
    """Pending outbox rows (oldest first)."""
    conn = _connect(base_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM action_result_outbox
             WHERE state = 'pending'
             ORDER BY created_at ASC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_delivered(
    base_path: str | Path,
    *,
    run_id: str,
    terminal_revision: int | None,
    now: float | None = None,
) -> None:
    """Transition a pending entry to ``delivered`` (atomic)."""
    ts = time.time() if now is None else now
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE action_result_outbox
               SET state = 'delivered', delivered_at = ?, terminal_revision = ?
             WHERE run_id = ? AND state = 'pending'
            """,
            (ts, terminal_revision, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_failed_final(
    base_path: str | Path, *, run_id: str, now: float | None = None,
) -> None:
    """Transition a pending entry to ``failed_final`` (delivery gave up; never
    posted). Kept for audit, not retried."""
    ts = time.time() if now is None else now
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE action_result_outbox
               SET state = 'failed_final', delivered_at = ?
             WHERE run_id = ? AND state = 'pending'
            """,
            (ts, run_id),
        )
        conn.commit()
    finally:
        conn.close()
