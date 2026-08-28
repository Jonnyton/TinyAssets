"""Pending requests the agent raises for its user to answer.

Founder, 2026-08-27, refining an earlier "credential popup" idea:

    "pending-request should show up as tabs on the left side screen of the app,
    the hedder notates what it is like api in this case you tap/click them to
    expand and in this case paist in the api right there. the agent can
    construct these pending requests really how ever he likes so they can be
    used in clever ways by the agent."

So this is deliberately NOT a credential feature. It is one general primitive —
*the agent asks its user something and waits* — of which "I need an API key" is
the first kind. The agent composes the header, the prose, and the fields, so
kinds nobody has written code for still work.

Why a durable store
-------------------
The turn is stateless: the agent asks in one turn and the user may answer
minutes later, from the web app, the desktop app, or the phone. A pending
request therefore has to outlive the turn that raised it and be readable from
every surface, which is also what makes it addressable from a phone at all
(same MCP read, no second mechanism).

The one rule the agent does not get to bend
-------------------------------------------
A ``secret`` field is only permitted when the request's action actually deposits
a credential (``connect_http``), and **a secret value is never written to this
table** — it goes straight to the vault through the deposit path. Without that
rule, "construct them however you like" would let an agent — including one
steered by injected content — craft a request that asks for a password and lands
it in readable storage. The generality is the point; this is the boundary that
makes the generality safe.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_NAME = ".pending_requests.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_requests (
    request_id  TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    fields_json TEXT NOT NULL,
    action_json TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL,
    status      TEXT NOT NULL,
    answer_json TEXT,
    feedback    TEXT,
    created_at  REAL NOT NULL,
    resolved_at REAL
);
-- "don't ask me this again" (founder 2026-08-27). Keyed on the request's own
-- dedupe key, so it suppresses THIS ask rather than a whole category the user
-- never meant to silence.
-- A STANDING DECISION, not merely a mute. `decision` is what the user settled
-- on: "allowed" means go ahead without asking again; "declined" means do not do
-- this and do not ask again. Storing only the silence lost the answer, which
-- made every remembered decision a refusal.
CREATE TABLE IF NOT EXISTS request_suppressions (
    dedupe_key  TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    feedback    TEXT,
    decision    TEXT NOT NULL DEFAULT 'declined',
    answer_json TEXT,
    created_at  REAL NOT NULL
);
-- A lifted mute is recorded, not just applied: the agent runs as the user's
-- own principal, so "who lifted this" cannot be decided at the gate.
CREATE TABLE IF NOT EXISTS request_unmutes (
    dedupe_key TEXT NOT NULL,
    lifted_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_requests_status
    ON pending_requests(status, created_at);
"""

#: A pending request occupies a tab in the user's face. More than this means
#: something is looping, and a rail of identical tabs is not a rail.
MAX_PENDING = 10

FIELD_TYPES = frozenset({"text", "secret", "choice"})


#: Columns added to a table AFTER it first shipped, as
#: ``(table, column, declaration)``.
#:
#: ``CREATE TABLE IF NOT EXISTS`` silently leaves an existing table exactly as it
#: was, so a column added to ``_SCHEMA`` never reaches a database that already
#: exists — and every live universe has one. On 2026-08-28 that took the rail's
#: front door down in production: #2636 added ``decision`` and ``answer_json``
#: with no migration, so every ``create_request`` raised
#: ``sqlite3.OperationalError: no such column: decision``, was swallowed by the
#: catch-all below, and reached the agent as the generic
#: ``request_storage_unavailable``. It could not raise a single request.
#:
#: Add a row here whenever you add a column to ``_SCHEMA``. Names are module
#: constants, never caller input, so the interpolation below is safe.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("request_suppressions", "decision", "TEXT NOT NULL DEFAULT 'declined'"),
    ("request_suppressions", "answer_json", "TEXT"),
)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Bring an older database up to the current schema, in place."""
    seen: dict[str, set[str]] = {}
    for table, column, declaration in _ADDED_COLUMNS:
        columns = seen.get(table)
        if columns is None:
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            seen[table] = columns
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
            columns.add(column)


def _db(universe_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(universe_dir) / _DB_NAME), timeout=10.0)
    conn.executescript(_SCHEMA)
    _ensure_columns(conn)
    return conn


def create_request(
    universe_dir: Path,
    *,
    kind: str,
    title: str,
    body: str,
    fields: list[dict[str, Any]],
    action: dict[str, Any],
    dedupe_key: str,
) -> dict[str, Any] | None:
    """Record one pending request. Returns the row, or None on storage failure.

    Deduplicated on ``dedupe_key`` while pending, so an agent retrying the same
    ask does not open a second identical tab.
    """
    try:
        with _db(universe_dir) as conn:
            # A user who said "don't ask me this again" must not be asked again.
            # The agent is TOLD, rather than silently ignored, so it can stop
            # trying and say so instead of looping.
            settled = conn.execute(
                "SELECT feedback, decision, answer_json FROM request_suppressions "
                "WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            if settled:
                # The user already settled this. Hand back WHAT they decided so
                # the agent can act on a standing yes, instead of only learning
                # that it may not ask.
                return {
                    "settled": True,
                    "decision": settled[1] or "declined",
                    "feedback": settled[0] or "",
                    "answer": json.loads(settled[2]) if settled[2] else None,
                }
            existing = conn.execute(
                "SELECT request_id FROM pending_requests "
                "WHERE status = 'pending' AND dedupe_key = ? LIMIT 1",
                (dedupe_key,),
            ).fetchone()
            if existing:
                return get_request(universe_dir, existing[0])
            pending = conn.execute(
                "SELECT COUNT(*) FROM pending_requests WHERE status = 'pending'"
            ).fetchone()[0]
            if pending >= MAX_PENDING:
                return {"error": "too_many_pending"}
            row_id = "req_" + uuid.uuid4().hex[:24]
            conn.execute(
                "INSERT INTO pending_requests (request_id, kind, title, body, "
                "fields_json, action_json, dedupe_key, status, answer_json, "
                "created_at, resolved_at) VALUES (?,?,?,?,?,?,?,'pending',NULL,?,NULL)",
                (
                    row_id,
                    kind,
                    title,
                    body,
                    json.dumps(fields),
                    json.dumps(action),
                    dedupe_key,
                    time.time(),
                ),
            )
        return get_request(universe_dir, row_id)
    except Exception as exc:  # noqa: BLE001 - never break the turn that asked
        # Carry the REASON, do not just log it. On 2026-08-28 this returned a
        # bare None, the API turned it into the generic
        # ``request_storage_unavailable``, and the agent was told only that
        # storage was unavailable — so it retried the identical call, failed
        # identically, and stopped. The actual fault was one line
        # (``no such column: decision``) and sat only in a container log nobody
        # was tailing. A schema fault is not sensitive; withholding it just
        # costs an hour.
        logger.exception("pending_requests: create failed")
        return {"error": "request_storage_unavailable", "detail": str(exc)}


def _project(row: Any) -> dict[str, Any]:
    return {
        "request_id": row[0],
        "kind": row[1],
        "title": row[2],
        "body": row[3],
        "fields": json.loads(row[4] or "[]"),
        "action": json.loads(row[5] or "{}"),
        "status": row[6],
        "answer": json.loads(row[7]) if row[7] else None,
        "created_at": row[8],
        "resolved_at": row[9],
        "feedback": row[10],
        "dedupe_key": row[11],
    }


_SELECT = (
    "SELECT request_id, kind, title, body, fields_json, action_json, status, "
    "answer_json, created_at, resolved_at, feedback, dedupe_key FROM pending_requests"
)


def get_request(universe_dir: Path, request_id: str) -> dict[str, Any] | None:
    try:
        with _db(universe_dir) as conn:
            row = conn.execute(
                f"{_SELECT} WHERE request_id = ?", (request_id,)
            ).fetchone()
        return _project(row) if row else None
    except Exception:  # noqa: BLE001
        logger.warning("pending_requests: get failed", exc_info=True)
        return None


def list_pending(universe_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Oldest first — the rail reads top to bottom in the order asked."""
    try:
        with _db(universe_dir) as conn:
            rows = conn.execute(
                f"{_SELECT} WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [_project(r) for r in rows]
    except Exception:  # noqa: BLE001
        logger.warning("pending_requests: list failed", exc_info=True)
        return []


def resolve_request(
    universe_dir: Path,
    request_id: str,
    *,
    status: str,
    answer: dict[str, Any] | None = None,
    feedback: str = "",
    dont_ask_again: bool = False,
    decision: str = "",
) -> bool:
    """Close a request. Only a PENDING row moves, so one answer counts once.

    ``answer`` holds the NON-secret field values, for the agent to read back.
    Secret values never reach this function.
    """
    if status not in {"answered", "dismissed"}:
        return False
    try:
        with _db(universe_dir) as conn:
            cur = conn.execute(
                "UPDATE pending_requests SET status = ?, answer_json = ?, "
                "feedback = ?, resolved_at = ? "
                "WHERE request_id = ? AND status = 'pending'",
                (
                    status,
                    json.dumps(answer) if answer else None,
                    feedback or None,
                    time.time(),
                    request_id,
                ),
            )
            if cur.rowcount <= 0:
                return False
            if dont_ask_again:
                row = conn.execute(
                    "SELECT kind, title, dedupe_key FROM pending_requests "
                    "WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if row:
                    conn.execute(
                        "INSERT OR REPLACE INTO request_suppressions "
                        "(dedupe_key, kind, title, feedback, decision, "
                        "answer_json, created_at) VALUES (?,?,?,?,?,?,?)",
                        (
                            row[2], row[0], row[1], feedback or None,
                            decision or ("allowed" if status == "answered"
                                         else "declined"),
                            json.dumps(answer) if answer else None,
                            time.time(),
                        ),
                    )
            return True
    except Exception:  # noqa: BLE001
        logger.warning("pending_requests: resolve failed", exc_info=True)
        return False


def list_resolved(universe_dir: Path, limit: int = 20) -> list[dict[str, Any]]:
    """Recently answered requests — how the agent reads what it was told."""
    try:
        with _db(universe_dir) as conn:
            rows = conn.execute(
                f"{_SELECT} WHERE status != 'pending' "
                "ORDER BY resolved_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [_project(r) for r in rows]
    except Exception:  # noqa: BLE001
        logger.warning("pending_requests: list_resolved failed", exc_info=True)
        return []


def record_unmute(universe_dir: Path, dedupe_key: str) -> None:
    """Record that a mute was lifted, so the lift is visible in the rail."""
    try:
        with _db(universe_dir) as conn:
            conn.execute(
                "INSERT INTO request_unmutes (dedupe_key, lifted_at) VALUES (?,?)",
                (dedupe_key, time.time()),
            )
    except Exception:  # noqa: BLE001
        logger.warning("pending_requests: record_unmute failed", exc_info=True)


def list_unmutes(universe_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    try:
        with _db(universe_dir) as conn:
            rows = conn.execute(
                "SELECT dedupe_key, lifted_at FROM request_unmutes "
                "ORDER BY lifted_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [{"dedupe_key": r[0], "lifted_at": r[1]} for r in rows]
    except Exception:  # noqa: BLE001
        logger.warning("pending_requests: list_unmutes failed", exc_info=True)
        return []


def list_suppressions(universe_dir: Path) -> list[dict[str, Any]]:
    """What the user has said not to be asked again — visible, so it is undoable."""
    try:
        with _db(universe_dir) as conn:
            rows = conn.execute(
                "SELECT dedupe_key, kind, title, feedback, decision, created_at "
                "FROM request_suppressions ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
        return [
            {"dedupe_key": r[0], "kind": r[1], "title": r[2],
             "feedback": r[3], "decision": r[4], "created_at": r[5]}
            for r in rows
        ]
    except Exception:  # noqa: BLE001
        logger.warning("pending_requests: list_suppressions failed", exc_info=True)
        return []


def unsuppress(universe_dir: Path, dedupe_key: str) -> bool:
    """Undo a "don't ask again". A standing refusal the user cannot lift is a trap."""
    try:
        with _db(universe_dir) as conn:
            cur = conn.execute(
                "DELETE FROM request_suppressions WHERE dedupe_key = ?", (dedupe_key,)
            )
            return cur.rowcount > 0
    except Exception:  # noqa: BLE001
        logger.warning("pending_requests: unsuppress failed", exc_info=True)
        return False


__all__ = [
    "FIELD_TYPES",
    "MAX_PENDING",
    "create_request",
    "get_request",
    "list_pending",
    "list_resolved",
    "list_suppressions",
    "list_unmutes",
    "record_unmute",
    "resolve_request",
    "unsuppress",
]
