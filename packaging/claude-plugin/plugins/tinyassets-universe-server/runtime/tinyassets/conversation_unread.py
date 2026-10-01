"""How many of the owner's messages the universe has not read yet.

Founder, 2026-10-01: *"the background self should just have an indicator of how
many messages have been sent since it looked last."* Every JSON result a served
tool returns carries ``owner_unread`` (``engine_mcp_server.OwnerUnread``), so a
running agent -- a background wake or a chat turn -- notices new messages at its
next tool boundary and can read them. Nothing is aborted or restarted.

**Where the marker lives, and why.** One marker per conversation thread: the
universe's directory and the owner's own session (``principal:<owner>``), stored
beside the thread in ``.conversation_memory.db``. It belongs to the universe as
one reader, not to a run: a background self is a sequence of short wakes, so a
per-run marker would start every wake at "everything is unread", and the
universe has no other durable identity that its chat turns and its wakes share.
A run that reads a message through the tool marks it read for the universe.

**What advances it.** Only a message actually delivered by a read: a
``read_graph target="conversation"`` read that returned that message's text
through its end (``mark_delivered``, fed the ids parsed from the very payload
that was returned). A catalogue page returns ids, not text, so it marks nothing;
a message that arrives while a read is in flight is not in that payload, so it
stays unread. Reads are recorded per message rather than as a high-water mark,
because reading the newest message must not mark the older unread ones read.
A turn's own prompt is not a read here: the chat turn answering a message does
not take it away from the background self's count.

**What counts.** The owner's (``founder`` speaker) messages in the owner's own
thread, recorded at or after ``UNREAD_EPOCH``. History from before the counter
existed is not news; without the epoch every existing universe would open at
"340 unread". Another principal's thread in the same store is never counted:
the session id is the owner's own, and it is the only filter between threads.

**Cost.** The count is cached against the store's file signature (database and
WAL size + mtime), so a tool call that changes nothing costs two ``stat`` calls.
A changed store costs one indexed count over the rows since the compaction
floor. Never raises: a count that cannot be read is ``None`` and the field is
left off rather than reported as zero.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_NAME = ".conversation_memory.db"
OWNER_SPEAKER = "founder"

#: 2026-09-30T00:00:00Z. Owner messages recorded before the counter shipped are
#: treated as seen.
UNREAD_EPOCH = 1_790_726_400.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_unread_floor (
    session_id TEXT PRIMARY KEY,
    floor_id   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_unread_read (
    session_id TEXT    NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (session_id, message_id)
);
"""

_COUNT_SQL = (
    "SELECT COUNT(*) FROM conversation_turns t "
    "WHERE t.session_id = ? AND t.speaker = ? AND t.ts >= ? "
    "AND t.id > COALESCE((SELECT floor_id FROM conversation_unread_floor "
    "                     WHERE session_id = ?), 0) "
    "AND NOT EXISTS (SELECT 1 FROM conversation_unread_read r "
    "                WHERE r.session_id = t.session_id AND r.message_id = t.id)"
)
#: A store no tool has marked yet has neither table; nothing has been read.
_COUNT_UNMARKED_SQL = (
    "SELECT COUNT(*) FROM conversation_turns "
    "WHERE session_id = ? AND speaker = ? AND ts >= ?"
)

_cache_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[tuple, int]] = {}


def _store(universe_dir: str | Path) -> Path:
    return Path(universe_dir) / _DB_NAME


def _signature(path: Path) -> tuple | None:
    try:
        main = os.stat(path)
    except OSError:
        return None
    try:
        wal = os.stat(str(path) + "-wal")
        wal_sig = (wal.st_size, wal.st_mtime_ns)
    except OSError:
        wal_sig = None
    return (main.st_size, main.st_mtime_ns, wal_sig)


def owner_unread(
    universe_dir: str | Path, session_id: str, *, epoch: float = UNREAD_EPOCH,
) -> int | None:
    """Owner messages in ``session_id`` not yet delivered by a read, or None."""
    if not session_id:
        return None
    path = _store(universe_dir)
    signature = _signature(path)
    if signature is None:
        return 0  # no conversation yet: nothing was sent
    key = (str(path), session_id)
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None and cached[0] == (signature, epoch):
        return cached[1]
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
                                     timeout=5.0)) as conn:
            try:
                row = conn.execute(
                    _COUNT_SQL, (session_id, OWNER_SPEAKER, epoch, session_id),
                ).fetchone()
            except sqlite3.OperationalError as exc:
                if "no such table" not in str(exc).lower():
                    raise
                row = conn.execute(
                    _COUNT_UNMARKED_SQL, (session_id, OWNER_SPEAKER, epoch),
                ).fetchone()
    except Exception:  # noqa: BLE001 - a missing field, never a failed tool call
        logger.warning("owner_unread: count failed for %s", path, exc_info=True)
        return None
    count = int(row[0]) if row else 0
    with _cache_lock:
        _cache[key] = ((signature, epoch), count)
    return count


def delivered_ids(payload: Any) -> list[int]:
    """The owner-message ids a conversation read's payload actually delivered.

    Only a message read whose returned chunk reached the end of the text
    (``next_offset`` is None). A catalogue page carries no text and delivers
    nothing; a middle chunk has not delivered the message yet.
    """
    if not isinstance(payload, dict) or payload.get("error"):
        return []
    if "chunk" not in payload or payload.get("next_offset") is not None:
        return []
    if payload.get("speaker") != OWNER_SPEAKER:
        return []
    raw = payload.get("field_name")
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
        return []
    return [int(raw)]


def mark_delivered(
    universe_dir: str | Path, session_id: str, message_ids: Iterable[int],
    *, epoch: float = UNREAD_EPOCH,
) -> None:
    """Record that these messages were delivered to the universe. Never raises.

    An id is recorded only when it is an owner message of THIS session, so a
    read can never mark another thread's message. The compaction floor then
    advances over the leading run of read messages and drops their rows.
    """
    ids = sorted({int(i) for i in message_ids if isinstance(i, int) and i > 0})
    if not session_id or not ids:
        return
    path = _store(universe_dir)
    if not path.is_file():
        return
    try:
        with closing(sqlite3.connect(str(path), timeout=5.0)) as conn:
            conn.executescript(_SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                "INSERT OR IGNORE INTO conversation_unread_read (session_id, message_id) "
                "SELECT session_id, id FROM conversation_turns "
                "WHERE session_id = ? AND id = ? AND speaker = ?",
                [(session_id, message_id, OWNER_SPEAKER) for message_id in ids],
            )
            _compact(conn, session_id, epoch)
            conn.commit()
    except Exception:  # noqa: BLE001 - the read already succeeded
        logger.warning("owner_unread: mark failed for %s", path, exc_info=True)


def _compact(conn: sqlite3.Connection, session_id: str, epoch: float) -> None:
    row = conn.execute(
        "SELECT floor_id FROM conversation_unread_floor WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    floor = int(row[0]) if row else 0
    new_floor = floor
    for message_id, read in conn.execute(
        "SELECT t.id, r.message_id IS NOT NULL FROM conversation_turns t "
        "LEFT JOIN conversation_unread_read r "
        "  ON r.session_id = t.session_id AND r.message_id = t.id "
        "WHERE t.session_id = ? AND t.speaker = ? AND t.ts >= ? AND t.id > ? "
        "ORDER BY t.id",
        (session_id, OWNER_SPEAKER, epoch, floor),
    ):
        if not read:
            break
        new_floor = int(message_id)
    if new_floor == floor:
        return
    conn.execute(
        "INSERT INTO conversation_unread_floor (session_id, floor_id) VALUES (?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET floor_id = excluded.floor_id",
        (session_id, new_floor),
    )
    conn.execute(
        "DELETE FROM conversation_unread_read WHERE session_id = ? AND message_id <= ?",
        (session_id, new_floor),
    )


def with_owner_unread(text: Any, count: int | None) -> str | None:
    """``text`` (a JSON object) with ``owner_unread`` as its first key, or None.

    None means leave the text alone: not a JSON object, already carrying the
    key, or no count. The insertion is textual, so the rest of the document is
    passed through byte-for-byte.
    """
    import json

    if count is None or not isinstance(text, str):
        return None
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        document = json.loads(stripped)
    except (ValueError, RecursionError):
        return None
    if not isinstance(document, dict) or "owner_unread" in document:
        return None
    head = '{"owner_unread": %d' % int(count)
    if not document:
        return head + "}"
    return head + ", " + stripped[1:].lstrip()


__all__ = [
    "UNREAD_EPOCH",
    "delivered_ids",
    "mark_delivered",
    "owner_unread",
    "with_owner_unread",
]
