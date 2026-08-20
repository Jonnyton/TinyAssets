"""Durable, content-free outbox linking an app-originated background action run to
its Slack conversation, so its terminal result can be delivered as a follow-up.

Content-free by design (Slice 3): a row carries the run id, the originating
``(workspace, channel, thread)`` conversation, an opaque app-binding reference, and
the origin event id — NEVER a credential and NEVER a pre-authorized reply body.
Delivery authority is re-resolved fresh at delivery time (see
``action_result_delivery``); the outbox only remembers WHERE a result should go and
WHETHER it has been delivered.

State machine (Codex round-1 hardening): ``pending`` -> ``in_flight`` (atomically
CLAIMED by exactly one delivery tick before it posts, so concurrent ticks and a
crash-between-post-and-mark cannot double-post) -> ``delivered`` | ``failed_final``.
A claimed entry whose tick died is reclaimed back to ``pending`` after a timeout.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from tinyassets.storage import db_path

#: Defense-in-depth against a caller cramming a credential/body into an id field:
#: every stored field is an identifier-shaped value and is length-capped. A Slack
#: id/ts/app-id is well under this; a token or a message body is not.
MAX_FIELD_LEN = 256

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
    state             TEXT NOT NULL
        CHECK (state IN ('pending','in_flight','delivered','failed_final')),
    claimed_at        REAL,
    claim_token       TEXT,
    delivered_at      REAL,
    terminal_revision INTEGER
);
CREATE INDEX IF NOT EXISTS idx_action_result_outbox_state
    ON action_result_outbox(state);
CREATE TABLE IF NOT EXISTS action_result_receipts (
    idempotency_key TEXT PRIMARY KEY,
    receipt         TEXT NOT NULL,
    posted_at       REAL NOT NULL
);
"""

#: Columns added after the initial table shipped — migrated onto an existing DB so a
#: prior installation does not break with "no such column" (Codex hardening #3).
_MIGRATIONS = (("claimed_at", "REAL"), ("claim_token", "TEXT"))

_ID_FIELDS = (
    "run_id",
    "universe_id",
    "workspace_id",
    "channel_id",
    "thread_ts",
    "app_binding_ref",
    "origin_event_id",
)

#: Every stored field is an identifier — a bounded token WITHOUT whitespace/control
#: chars. A message body or a multi-line secret is neither, so this rejects the shapes
#: the outbox is contractually forbidden to hold (Codex hardening #4/#6).
_ID_SHAPE = re.compile(r"^[^\s\x00-\x1f]{1,128}$")


def _migrate_state_check(conn: sqlite3.Connection) -> None:
    """Rebuild the outbox table if its state CHECK constraint predates ``in_flight``.

    SQLite cannot ALTER a CHECK, so a DB created with the original
    ``CHECK (state IN ('pending','delivered','failed_final'))`` rejects the
    ``in_flight`` claim state forever — the additive column migration alone left
    ``claim()`` failing with "CHECK constraint failed" on a real predecessor DB
    (Codex re-review). Detect a stale/absent ``in_flight`` in the stored DDL and, if
    so, recreate the table with the current schema and copy every row across (by
    shared columns, so a pre-fencing table missing claim columns still copies).
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='action_result_outbox'"
    ).fetchone()
    if not row or not row["sql"] or "in_flight" in row["sql"]:
        return  # no table yet, or the CHECK already admits in_flight
    conn.execute(
        "ALTER TABLE action_result_outbox RENAME TO _action_result_outbox_legacy"
    )
    conn.executescript(_SCHEMA)  # recreate the table with the current CHECK
    old_cols = {
        r["name"]
        for r in conn.execute("PRAGMA table_info(_action_result_outbox_legacy)")
    }
    shared = ", ".join(
        r["name"]
        for r in conn.execute("PRAGMA table_info(action_result_outbox)")
        if r["name"] in old_cols
    )
    conn.execute(
        f"INSERT INTO action_result_outbox ({shared}) "
        f"SELECT {shared} FROM _action_result_outbox_legacy"
    )
    conn.execute("DROP TABLE _action_result_outbox_legacy")
    # The state index was renamed with the legacy table and dropped with it; the
    # IF NOT EXISTS recreate above skipped it while the name was still taken, so
    # recreate it now that the legacy table (and its index) are gone.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_result_outbox_state "
        "ON action_result_outbox(state)"
    )


def _connect(base_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(Path(base_path)))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    # Rebuild a table whose state CHECK predates 'in_flight' (must run before the
    # additive migration / any claim, or writing 'in_flight' raises).
    _migrate_state_check(conn)
    # Additive migration for tables created before the fencing/claim columns existed.
    have = {row["name"] for row in conn.execute("PRAGMA table_info(action_result_outbox)")}
    for col, decl in _MIGRATIONS:
        if col not in have:
            conn.execute(f"ALTER TABLE action_result_outbox ADD COLUMN {col} {decl}")
    conn.commit()
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
    Every field is an id-shaped value and is length-checked (content-free guard).
    """
    values = {
        "run_id": run_id,
        "universe_id": universe_id,
        "workspace_id": workspace_id,
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "app_binding_ref": app_binding_ref,
        "origin_event_id": origin_event_id,
    }
    for name in _ID_FIELDS:
        val = values[name]
        if not isinstance(val, str) or not val:
            raise ValueError(f"action_result_outbox: {name} must be a non-empty string")
        if not _ID_SHAPE.match(val):
            # Not an id shape (whitespace / control chars / >128) -> almost certainly a
            # body or multi-line secret; refuse content the outbox may not hold.
            raise ValueError(
                f"action_result_outbox: {name} is not a content-free identifier"
            )
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


def list_pending(
    base_path: str | Path, *, after_rowid: int = 0, limit: int = 200,
) -> list[dict[str, Any]]:
    """A page of ``pending`` outbox rows (by rowid, ascending) after ``after_rowid``.

    Cursor pagination (Codex round-1) so a backlog of still-running entries can never
    permanently hide a newer terminal one: the delivery tick walks ALL pages, not
    just the oldest fixed window. Each row includes its ``rowid`` for the next cursor.
    """
    conn = _connect(base_path)
    try:
        rows = conn.execute(
            """
            SELECT rowid AS rowid, * FROM action_result_outbox
             WHERE state = 'pending' AND rowid > ?
             ORDER BY rowid ASC
             LIMIT ?
            """,
            (after_rowid, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def claim(base_path: str | Path, *, run_id: str, now: float | None = None) -> str | None:
    """Atomically CLAIM a pending entry for delivery: ``pending`` -> ``in_flight``.

    Returns a fencing ``claim_token`` iff THIS caller won the claim, else None.
    Concurrent ticks race here; exactly one wins. The token must be presented to
    :func:`release` / :func:`mark_delivered` — so a STALE worker whose claim was
    reclaimed and re-granted to another tick cannot release or mark the NEWER claim by
    ``run_id`` alone (Codex hardening #1).
    """
    ts = time.time() if now is None else now
    token = secrets.token_hex(16)
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            UPDATE action_result_outbox
               SET state = 'in_flight', claimed_at = ?, claim_token = ?
             WHERE run_id = ? AND state = 'pending'
            """,
            (ts, token, run_id),
        )
        conn.commit()
        return token if cur.rowcount else None
    finally:
        conn.close()


def release(base_path: str | Path, *, run_id: str, claim_token: str) -> bool:
    """Return a claimed entry to ``pending`` (delivery HELD) — ONLY if ``claim_token``
    matches the current claim (fencing). Returns True if released."""
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            UPDATE action_result_outbox
               SET state = 'pending', claimed_at = NULL, claim_token = NULL
             WHERE run_id = ? AND state = 'in_flight' AND claim_token = ?
            """,
            (run_id, claim_token),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def reclaim_stale(
    base_path: str | Path, *, older_than_s: float, now: float | None = None,
) -> int:
    """Return in_flight entries claimed longer than ``older_than_s`` ago to pending.

    Crash recovery: a tick that died between claim and mark leaves an entry stuck
    ``in_flight``; this frees it (clearing the fencing token so the dead tick's stale
    token can no longer act on it) so a later tick can re-claim. Returns the count freed.
    """
    ts = time.time() if now is None else now
    cutoff = ts - older_than_s
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            UPDATE action_result_outbox
               SET state = 'pending', claimed_at = NULL, claim_token = NULL
             WHERE state = 'in_flight'
               AND (claimed_at IS NULL OR claimed_at < ?)
            """,
            (cutoff,),
        )
        conn.commit()
        return int(cur.rowcount)
    finally:
        conn.close()


def mark_delivered(
    base_path: str | Path,
    *,
    run_id: str,
    terminal_revision: int | None,
    claim_token: str,
    now: float | None = None,
) -> bool:
    """Transition a CLAIMED entry to ``delivered`` — ONLY if ``claim_token`` matches this
    claim (fencing). Returns True if marked. A stale worker's token cannot mark a newer
    claim delivered (Codex hardening #1)."""
    ts = time.time() if now is None else now
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            UPDATE action_result_outbox
               SET state = 'delivered', delivered_at = ?, terminal_revision = ?,
                   claim_token = NULL
             WHERE run_id = ? AND state = 'in_flight' AND claim_token = ?
            """,
            (ts, terminal_revision, run_id, claim_token),
        )
        conn.commit()
        return bool(cur.rowcount)
    finally:
        conn.close()


def receipt_seen(base_path: str | Path, *, idempotency_key: str) -> str | None:
    """A prior receipt for ``idempotency_key`` if the follow-up was already posted, else
    None — the adapter's crash-safety backstop so a reclaim+retry after a crash between
    post and mark cannot double-post (Codex hardening #1)."""
    conn = _connect(base_path)
    try:
        row = conn.execute(
            "SELECT receipt FROM action_result_receipts WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return str(row["receipt"]) if row else None
    finally:
        conn.close()


def record_receipt(
    base_path: str | Path, *, idempotency_key: str, receipt: str, now: float | None = None,
) -> None:
    """Record that ``idempotency_key`` was posted, with its receipt (INSERT OR IGNORE)."""
    ts = time.time() if now is None else now
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO action_result_receipts (idempotency_key, receipt, posted_at)"
            " VALUES (?, ?, ?)",
            (idempotency_key, receipt, ts),
        )
        conn.commit()
    finally:
        conn.close()


def mark_failed_final(
    base_path: str | Path, *, run_id: str, now: float | None = None,
) -> None:
    """Transition a claimed entry to ``failed_final`` (delivery gave up; never
    posted). Kept for audit, not retried."""
    ts = time.time() if now is None else now
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE action_result_outbox
               SET state = 'failed_final', delivered_at = ?
             WHERE run_id = ? AND state IN ('pending','in_flight')
            """,
            (ts, run_id),
        )
        conn.commit()
    finally:
        conn.close()
