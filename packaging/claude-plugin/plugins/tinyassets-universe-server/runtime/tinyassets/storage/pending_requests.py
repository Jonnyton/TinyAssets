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
    -- Optional answerable items: one request that holds several things, each
    -- with its own stable id and its own fields. Empty for every request that
    -- is a single question. See `request_item_answers`.
    items_json  TEXT NOT NULL DEFAULT '[]',
    dedupe_key  TEXT NOT NULL,
    status      TEXT NOT NULL,
    answer_json TEXT,
    feedback    TEXT,
    created_at  REAL NOT NULL,
    resolved_at REAL,
    -- Who raised it: "agent" (the universe's agent or the owner's chatbot) or
    -- "platform" (e.g. onboarding's model confirmation). Server-set, never
    -- read from the ask, because it decides what the agent may withdraw.
    origin      TEXT NOT NULL DEFAULT 'agent'
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
-- One item's answer. A separate table rather than a mutation of `items_json`
-- so that answering an item is an INSERT under a primary key: the same
-- "one answer counts once" guarantee the whole-request path gets from its
-- `status = 'pending'` guard, at item granularity.
--
-- An item with NO row here is not "unanswered" in storage -- it is DERIVED
-- (see `_item_state`): pending while the request is pending, unanswered once
-- the request closed. Storing it would mean writing a row to say nothing
-- happened, and a whole-request answer would have to fabricate one per item.
CREATE TABLE IF NOT EXISTS request_item_answers (
    request_id  TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    status      TEXT NOT NULL,
    answer_json TEXT,
    feedback    TEXT,
    resolved_at REAL NOT NULL,
    PRIMARY KEY (request_id, item_id)
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
MAX_PENDING = 50

#: Answerable items on ONE request. Payload validation of a single ask, the same
#: class as the API layer's `_MAX_FIELDS` -- a note of 200 tasks is not a note,
#: and the notification for it has to fit. NOT an account limit: a universe may
#: raise another request (founder 2026-09-30, account limits are storage and
#: agent-run seats only).
MAX_ITEMS = 50

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
    ("pending_requests", "origin", "TEXT NOT NULL DEFAULT 'agent'"),
    ("pending_requests", "items_json", "TEXT NOT NULL DEFAULT '[]'"),
)

#: Who may raise a request. Only ``agent`` requests can be withdrawn by the
#: agent; a platform-raised ask is the platform's to clear.
ORIGIN_AGENT = "agent"
ORIGIN_PLATFORM = "platform"
ORIGINS = frozenset({ORIGIN_AGENT, ORIGIN_PLATFORM})


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
    origin: str = ORIGIN_AGENT,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Record one pending request. Returns the row, or None on storage failure.

    Deduplicated on ``dedupe_key`` while pending, so an agent retrying the same
    ask does not open a second identical tab.

    ``items`` are the request's answerable parts, already validated by the
    caller (:func:`tinyassets.api.pending_requests._validated_items`). They are
    stored verbatim so the ids the agent chose are the ids it reads back.

    A returned row carries ``created``: ``True`` when this call inserted it,
    ``False`` when it deduplicated onto a tab that was already up. The caller
    strips it before answering -- it describes THIS call, not the request.
    """
    if origin not in ORIGINS:
        raise ValueError(f"unknown request origin {origin!r}")
    try:
        with _db(universe_dir) as conn:
            # A user who said "don't ask me this again" must not be asked again.
            # The agent is TOLD, rather than silently ignored, so it can stop
            # trying and say so instead of looping.
            #
            settled = conn.execute(
                "SELECT feedback, decision, answer_json FROM request_suppressions "
                "WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            # A standing ALLOW is only meaningful when the agent can act on it.
            # For an action-bearing ask the ANSWER IS THE ACT -- nothing widens a
            # grant, deposits a key or removes one except answering the tab, and
            # the served agent has no route to any of them. So a suppressed
            # allow returned "standing yes, proceed" and then nothing happened:
            # harmless-looking on extend_http, and on remove_http it tells the
            # owner a credential is gone while it sits in the vault. The tab is
            # the mechanism, so for those the tab opens anyway.
            #
            # A standing DECLINE is untouched, and deliberately: "do not do this
            # and stop asking" is honoured by doing nothing, which needs no
            # route. Refusing it too would make "stop asking me to connect
            # GitHub" an ask that returns forever -- the trap the mute exists to
            # prevent, and an existing test said so.
            if (
                settled
                and (settled[1] or "declined") == "allowed"
                and str((action or {}).get("type") or "answer") != "answer"
            ):
                settled = None
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
                # The SAME tab, already up. `created` tells the caller which of
                # the two this is, because "a request was raised" and "the one
                # you raised before is still waiting" are different events --
                # only the first is something to notify the owner about.
                same = get_request(universe_dir, existing[0])
                return {**same, "created": False} if same else None
            pending = conn.execute(
                "SELECT COUNT(*) FROM pending_requests WHERE status = 'pending'"
            ).fetchone()[0]
            if pending >= MAX_PENDING:
                return {"error": "too_many_pending"}
            row_id = "req_" + uuid.uuid4().hex[:24]
            conn.execute(
                "INSERT INTO pending_requests (request_id, kind, title, body, "
                "fields_json, action_json, items_json, dedupe_key, status, "
                "answer_json, created_at, resolved_at, origin) "
                "VALUES (?,?,?,?,?,?,?,?,'pending',NULL,?,NULL,?)",
                (
                    row_id,
                    kind,
                    title,
                    body,
                    json.dumps(fields),
                    json.dumps(action),
                    json.dumps(list(items or [])),
                    dedupe_key,
                    time.time(),
                    origin,
                ),
            )
        fresh = get_request(universe_dir, row_id)
        return {**fresh, "created": True} if fresh else None
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


#: An item the owner has not acted on. ``pending`` while the request is still
#: open, ``unanswered`` once it closed without this item being touched. Derived,
#: never stored: a whole-request answer must not fabricate an item answer.
ITEM_PENDING = "pending"
ITEM_UNANSWERED = "unanswered"


def _item_answers(conn: sqlite3.Connection, request_id: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        "SELECT item_id, status, answer_json, feedback, resolved_at "
        "FROM request_item_answers WHERE request_id = ?",
        (request_id,),
    ).fetchall()
    return {
        str(r[0]): {
            "status": str(r[1]),
            "answer": json.loads(r[2]) if r[2] else None,
            "feedback": r[3],
            "resolved_at": r[4],
        }
        for r in rows
    }


def _item_state(
    items: list[dict[str, Any]],
    answers: dict[str, dict[str, Any]],
    request_status: str,
) -> dict[str, dict[str, Any]]:
    """Per item, what came back -- kept SEPARATE from what was asked.

    ``items`` is projected verbatim because it is part of the tuple the dedupe
    key hashes and ``displayed_row_matches`` re-derives; folding answers into
    those objects would make the row stop reproducing what the owner was shown
    the moment they answered one item, and the request would refuse to execute.
    """
    untouched = ITEM_PENDING if request_status == "pending" else ITEM_UNANSWERED
    state = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or "")
        state[item_id] = answers.get(item_id) or {
            "status": untouched, "answer": None, "feedback": None,
            "resolved_at": None,
        }
    return state


def _project(row: Any, answers: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    items = json.loads(row[13] or "[]") if len(row) > 13 else []
    if not isinstance(items, list):
        items = []
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
        "origin": row[12] or ORIGIN_AGENT,
        "items": items,
        "item_answers": _item_state(items, answers or {}, str(row[6])),
    }


_SELECT = (
    "SELECT request_id, kind, title, body, fields_json, action_json, status, "
    "answer_json, created_at, resolved_at, feedback, dedupe_key, origin, "
    "items_json FROM pending_requests"
)


def _projected(conn: sqlite3.Connection, rows: list[Any]) -> list[dict[str, Any]]:
    """Project rows, reading item answers only for rows that have items.

    A request with no items -- which is almost all of them -- costs no extra
    query, so adding items charges nothing to the rail's existing reads.
    """
    out = []
    for row in rows:
        has_items = bool(row[13] and row[13] not in ("[]", "null"))
        out.append(_project(row, _item_answers(conn, str(row[0])) if has_items else None))
    return out


def get_request(universe_dir: Path, request_id: str) -> dict[str, Any] | None:
    try:
        with _db(universe_dir) as conn:
            row = conn.execute(
                f"{_SELECT} WHERE request_id = ?", (request_id,)
            ).fetchone()
            return _projected(conn, [row])[0] if row else None
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
            return _projected(conn, rows)
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
            # An itemised request reads back as ONE answer whichever way the
            # owner worked through it, so whatever items they already answered
            # ride into the closing answer. Items they never touched contribute
            # nothing -- the projection derives `unanswered` for those, rather
            # than this inventing a value for them.
            stored = _item_answers(conn, request_id)
            merged = dict(answer) if answer else {}
            if stored:
                merged["items"] = {
                    item_id: {"status": state["status"], "answer": state["answer"],
                              "feedback": state["feedback"]}
                    for item_id, state in stored.items()
                }
            cur = conn.execute(
                "UPDATE pending_requests SET status = ?, answer_json = ?, "
                "feedback = ?, resolved_at = ? "
                "WHERE request_id = ? AND status = 'pending'",
                (
                    status,
                    json.dumps(merged) if merged else None,
                    feedback or None,
                    time.time(),
                    request_id,
                ),
            )
            if cur.rowcount <= 0:
                return False
            row = conn.execute(
                "SELECT kind, title, dedupe_key FROM pending_requests "
                "WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if dont_ask_again:
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
    except Exception:  # noqa: BLE001
        logger.warning("pending_requests: resolve failed", exc_info=True)
        return False
    # Every surface answers through here, so one emit wakes a subscribed
    # branch whichever surface the owner used. Never raises.
    from tinyassets.automation_events import emit_pending_request_answered

    emit_pending_request_answered(
        universe_dir, request_id=request_id,
        kind=str(row[0]) if row else "", status=status,
    )
    # And take it off the owner's OTHER devices. Same seam as the emit, for the
    # same reason: every surface resolves through here, so one call covers them
    # all and there is one definition of when a notification is cleared.
    from tinyassets.owner_notifications import clear_for_universe_dir

    clear_for_universe_dir(universe_dir, request_id=request_id)
    return True


def resolve_item(
    universe_dir: Path,
    request_id: str,
    item_id: str,
    *,
    status: str,
    answer: dict[str, Any] | None = None,
    feedback: str = "",
) -> dict[str, Any]:
    """Resolve ONE item of a pending request. One answer per item, ever.

    The request stays ``pending`` unless this was its last unresolved item, in
    which case it closes as ``answered`` in the same transaction -- so there is
    no window where every item is answered and the tab is still up.

    Returns ``{"item_id", "status", "request_status", "remaining"}``, or an
    ``error`` envelope naming why nothing moved. A second answer for the same
    item reports ``item_already_resolved`` and does NOT overwrite the first:
    the PRIMARY KEY is the guarantee, not the check above it.
    """
    if status not in {"answered", "dismissed"}:
        return {"error": "item_status_invalid", "detail": "answered or dismissed"}
    closed = False
    try:
        with _db(universe_dir) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status, items_json, kind FROM pending_requests "
                "WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None:
                return {"error": "not_found", "resource": "pending_request"}
            if str(row[0]) != "pending":
                return {"error": "already_resolved", "status": str(row[0])}
            try:
                items = json.loads(row[1] or "[]")
            except (json.JSONDecodeError, TypeError):
                items = []
            ids = [
                str(i.get("item_id") or "") for i in items if isinstance(i, dict)
            ]
            if item_id not in ids:
                # Uniform with the request-level miss: an id that is not on this
                # request is simply not found, so probing ids learns nothing.
                return {"error": "not_found", "resource": "request_item"}
            cur = conn.execute(
                "INSERT OR IGNORE INTO request_item_answers "
                "(request_id, item_id, status, answer_json, feedback, resolved_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    request_id, item_id, status,
                    json.dumps(answer) if answer else None,
                    feedback or None, time.time(),
                ),
            )
            if cur.rowcount <= 0:
                return {"error": "item_already_resolved", "item_id": item_id}
            resolved = {
                str(r[0]) for r in conn.execute(
                    "SELECT item_id FROM request_item_answers WHERE request_id = ?",
                    (request_id,),
                )
            }
            remaining = [i for i in ids if i not in resolved]
            if not remaining:
                answers = _item_answers(conn, request_id)
                conn.execute(
                    "UPDATE pending_requests SET status = 'answered', "
                    "answer_json = ?, resolved_at = ? "
                    "WHERE request_id = ? AND status = 'pending'",
                    (
                        json.dumps({"items": {
                            k: {"status": v["status"], "answer": v["answer"],
                                "feedback": v["feedback"]}
                            for k, v in answers.items()
                        }}),
                        time.time(), request_id,
                    ),
                )
                closed = True
            kind = str(row[2] or "")
    except Exception as exc:  # noqa: BLE001 - report the reason, never break the turn
        logger.warning("pending_requests: resolve_item failed", exc_info=True)
        return {"error": "request_storage_unavailable", "detail": str(exc)}
    # ONE emit, carrying the item. A closing item would otherwise wake an
    # unfiltered subscription twice for a single act.
    from tinyassets.automation_events import emit_pending_request_answered

    emit_pending_request_answered(
        universe_dir, request_id=request_id, kind=kind,
        status="answered" if closed else "pending", item_id=item_id,
    )
    # Only a CLOSING item clears the notification. A notification is per
    # request, so answering one item of fifty changes nothing a device is
    # displaying, and pushing a silent clear per item made a 50-item note cost
    # 51 wakeups per device (gpt-6-astra, 2026-09-29). Per-item state is what
    # the rail shows when the app is opened.
    if closed:
        from tinyassets.owner_notifications import clear_for_universe_dir

        clear_for_universe_dir(universe_dir, request_id=request_id)
    return {
        "item_id": item_id,
        "status": status,
        "request_status": "answered" if closed else "pending",
        "remaining": len(remaining),
    }


def withdraw_request(
    universe_dir: Path, request_id: str, *, reason: str = ""
) -> dict[str, Any]:
    """The agent takes back an ask it raised and no longer needs.

    One guarded UPDATE: only a row that is still ``pending`` AND was raised by
    the agent moves, so a withdrawal racing the owner's answer cannot both win,
    and a platform-raised ask stays up. Writes no standing decision, so the
    agent may ask again later. On a miss, says why.
    """
    try:
        with _db(universe_dir) as conn:
            cur = conn.execute(
                "UPDATE pending_requests SET status = 'withdrawn', feedback = ?, "
                "resolved_at = ? WHERE request_id = ? AND status = 'pending' "
                "AND origin = ?",
                (reason or None, time.time(), request_id, ORIGIN_AGENT),
            )
            moved = cur.rowcount > 0
    except Exception as exc:  # noqa: BLE001 - report, never raise into the turn
        logger.warning("pending_requests: withdraw failed", exc_info=True)
        return {"error": "request_storage_unavailable", "detail": str(exc)}
    row = get_request(universe_dir, request_id)
    if moved and row is not None:
        return row
    if row is None:
        return {"error": "not_found", "resource": "pending_request"}
    if row["status"] != "pending":
        return {"error": "already_resolved", "status": row["status"]}
    return {"error": "not_withdrawable", "origin": row["origin"],
            "detail": "this ask was raised by the platform, not by you"}


def list_resolved(universe_dir: Path, limit: int = 20) -> list[dict[str, Any]]:
    """Recently answered requests — how the agent reads what it was told."""
    try:
        with _db(universe_dir) as conn:
            rows = conn.execute(
                f"{_SELECT} WHERE status != 'pending' "
                "ORDER BY resolved_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            return _projected(conn, rows)
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
    "ITEM_PENDING",
    "ITEM_UNANSWERED",
    "MAX_ITEMS",
    "MAX_PENDING",
    "create_request",
    "get_request",
    "list_pending",
    "list_resolved",
    "list_suppressions",
    "list_unmutes",
    "record_unmute",
    "resolve_item",
    "resolve_request",
    "unsuppress",
    "withdraw_request",
]
