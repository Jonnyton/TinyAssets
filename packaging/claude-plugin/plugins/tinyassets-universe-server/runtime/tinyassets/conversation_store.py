"""Durable, session-anchored conversation store for the stateless universe turn.

Why this exists
---------------
The universe turn is rebuilt from scratch every call (a fresh ``claude -p`` with
the persona system prompt + the current message only). The 2026-08-08 hotfix gave
the *Slack* path a sliding window pulled from ``conversations.history`` each turn,
but that left three gaps u-tiny named itself (Slack thread 1786225160):

* the MCP ``converse`` path had **no memory at all**;
* nothing was **durable** — the Slack pull re-fetches every turn and depends on
  bot-token scopes + rate limits, so the platform owned no copy of its own
  conversation;
* there was no **session-anchored** ``(session_id, turn, role, content)`` store,
  so nothing beyond the window survived and no summary layer could be built.

This is that layer — the Vercel ``ChatbotMessagePersistence`` shape applied here:
**thread identity → persistent message store → reconstruction at turn start.**
It is the pure storage half; the bounded, untrusted-fenced *rendering* stays in
:mod:`tinyassets.conversation_memory` (already Codex-reviewed 2026-08-08). Callers
load prior turns, run the turn, then record both sides.

Contract
--------
* Per-universe isolation: one SQLite file at ``<universe_dir>/.conversation_memory.db``.
* Keyed by ``session_id`` (``slack:<channel>`` / ``converse:<universe_id>:<actor>``);
  ``turn_no`` is per-session and monotonic. ``speaker`` is DISPLAY metadata only
  (Founder vs the universe's own voice) — it is never read as authentication.
* **Memory is never consent** — this only stores/loads text; the fenced
  not-consent formatter and the fresh-consent gate live elsewhere and are
  unchanged.
* **Best-effort, single boundary**: every function catches its own storage
  errors, logs, and degrades to "no memory this turn" (matching the hotfix
  contract) — it never raises, so callers do NOT re-wrap it (that would just
  double-log). This is the one place the fail-loud rule yields, because memory is
  a bonus layer and a blank window is strictly better than dropping the answer.

Not the custody store
---------------------
:mod:`tinyassets.conversation_custody` is a separate concern: user-controlled
privacy/export/delete behind one-use Ed25519-signed per-operation grants. Using
it for every-turn working memory would mean minting + consuming a signed grant
per turn — the wrong tool. Authorization for the turn is the founder gate on the
caller (``converse`` is founder-only; history injection is founder-gated), and
per-universe DB isolation inherits the universe dir's filesystem boundary. If a
future authenticated app-conversation authority owner ships, this store is where
it integrates; until then it stays deliberately lightweight.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

from tinyassets.conversation_memory import DEFAULT_LIMIT, Msg

logger = logging.getLogger(__name__)

#: One SQLite file per universe, alongside its vault/soul.
_DB_NAME = ".conversation_memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_turns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    turn_no    INTEGER NOT NULL,
    speaker    TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    ts         REAL    NOT NULL,
    UNIQUE(session_id, turn_no)
);
CREATE INDEX IF NOT EXISTS ix_turns_session
    ON conversation_turns(session_id, turn_no);
CREATE TABLE IF NOT EXISTS conversation_backfill (
    session_id TEXT PRIMARY KEY,
    ts         REAL NOT NULL
);
"""

#: Same-process writers (the daemon serves both the Slack ingress and the MCP
#: converse paths in one process) are serialized per db file for a clean
#: turn_no; the UNIQUE(session_id, turn_no) constraint + retry is the
#: cross-process backstop.
_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_for(db_path: Path) -> threading.Lock:
    key = str(db_path)
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def _db_path(universe_dir: "str | Path") -> Path:
    return Path(universe_dir) / _DB_NAME


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_SCHEMA)
    return conn


def record_turn(
    universe_dir: "str | Path",
    session_id: str,
    speaker: str,
    text: str,
    *,
    ts: float | None = None,
) -> int:
    """Append one turn; return its per-session ``turn_no`` (0 if not recorded).

    Blank text is a no-op (returns 0). Best-effort: any storage failure logs and
    returns 0 rather than raising, so a memory hiccup never breaks the reply.
    """
    if not isinstance(text, str) or not text.strip():
        return 0
    if not session_id:
        return 0
    when = time.time() if ts is None else float(ts)
    db_path = _db_path(universe_dir)
    lock = _lock_for(db_path)
    for attempt in range(6):
        try:
            with lock:
                conn = _connect(db_path)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute(
                        "SELECT COALESCE(MAX(turn_no), 0) + 1 "
                        "FROM conversation_turns WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
                    turn_no = int(row[0])
                    conn.execute(
                        "INSERT INTO conversation_turns "
                        "(session_id, turn_no, speaker, content, ts) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (session_id, turn_no, str(speaker or ""), text, when),
                    )
                    conn.commit()
                    return turn_no
                finally:
                    conn.close()
        except sqlite3.OperationalError as exc:  # locked/busy across processes
            msg = str(exc).lower()
            transient = "lock" in msg or "busy" in msg
            if transient and attempt < 5:
                time.sleep(0.02 * (attempt + 1))
                continue
            # A non-transient OperationalError (e.g. a missing universe dir in a
            # test) is permanent — fail fast rather than burning the retry budget.
            logger.warning("conversation_store: record failed: %s", exc)
            return 0
        except sqlite3.IntegrityError:  # cross-process turn_no race → retry
            if attempt < 5:
                time.sleep(0.02 * (attempt + 1))
                continue
            return 0
        except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
            logger.warning("conversation_store: record failed", exc_info=True)
            return 0
    return 0


def load_recent(
    universe_dir: "str | Path",
    session_id: str,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[Msg]:
    """Return the last ``limit`` turns for ``session_id``, oldest-first.

    Empty on any trouble (no store yet, missing dir, read error) — the caller
    treats ``[]`` as "no memory this turn".
    """
    if not session_id:
        return []
    db_path = _db_path(universe_dir)
    if not db_path.exists():
        return []
    def _ts(value: object) -> "float | None":
        try:
            f = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return f if f > 0 else None

    try:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                "SELECT speaker, content, ts FROM conversation_turns "
                "WHERE session_id = ? ORDER BY turn_no DESC LIMIT ?",
                (session_id, max(1, int(limit))),
            ).fetchall()
        finally:
            conn.close()
        # DESC from SQL → reverse to oldest-first for the formatter. Carry ts so
        # the turn knows WHEN each message was sent (SDK createdAt metadata). The
        # ts coercion stays INSIDE the try so malformed stored data degrades to
        # "no memory", never a raise (fail-open contract).
        return [
            Msg(speaker=str(sp or ""), text=str(ct or ""), ts=_ts(t))
            for sp, ct, t in reversed(rows)
        ]
    except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
        logger.warning("conversation_store: load failed", exc_info=True)
        return []


def is_backfilled(universe_dir: "str | Path", session_id: str) -> bool:
    """True if this session's one-time Slack-timeline import has been claimed.

    Distinct from :func:`has_prior_turns`: a session with an empty timeline is
    still marked backfilled so we do not re-hit the Slack API every turn.
    """
    if not session_id:
        return False
    db_path = _db_path(universe_dir)
    if not db_path.exists():
        return False
    try:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM conversation_backfill WHERE session_id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return False
    return row is not None


def backfill_once(
    universe_dir: "str | Path",
    session_id: str,
    messages: "list[dict]",
) -> int:
    """Import a session's prior messages ONCE, atomically. Return count imported.

    The marker claim + the message inserts happen in a single transaction, so:

    * **Concurrent** cold turns cannot both import — the ``conversation_backfill``
      PRIMARY KEY makes exactly one worker win; the loser returns 0 without
      importing (fixes the duplicate-every-message race).
    * A crash mid-import rolls back the whole transaction, leaving the session
      un-backfilled and RETRYABLE rather than half-populated (fixes partial
      backfill permanently suppressing retry).

    Returns 0 if already backfilled, nothing to import, or on any storage error
    (best-effort — a missed backfill just means less memory, never a lost reply).
    ``messages`` is ``[{"speaker","text"}]`` from the Slack timeline loader.
    """
    if not session_id:
        return 0
    when = time.time()

    def _ts(m: dict) -> float:
        # Preserve the message's real send time so backfilled history carries
        # accurate "when"; fall back to now only if the loader gave none.
        try:
            v = float(m.get("ts") or 0)
        except (TypeError, ValueError):
            v = 0.0
        return v if v > 0 else when

    rows = [
        (str(m.get("speaker") or ""), str(m.get("text") or ""), _ts(m))
        for m in (messages or [])
        if isinstance(m, dict) and str(m.get("text") or "").strip()
    ]
    db_path = _db_path(universe_dir)
    lock = _lock_for(db_path)
    for attempt in range(6):
        try:
            with lock:
                conn = _connect(db_path)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        conn.execute(
                            "INSERT INTO conversation_backfill (session_id, ts) "
                            "VALUES (?, ?)",
                            (session_id, when),
                        )
                    except sqlite3.IntegrityError:
                        conn.rollback()
                        return 0  # another worker already backfilled this session
                    base = int(
                        conn.execute(
                            "SELECT COALESCE(MAX(turn_no), 0) "
                            "FROM conversation_turns WHERE session_id = ?",
                            (session_id,),
                        ).fetchone()[0]
                    )
                    for i, (speaker, content, ts_val) in enumerate(rows, start=1):
                        conn.execute(
                            "INSERT INTO conversation_turns "
                            "(session_id, turn_no, speaker, content, ts) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (session_id, base + i, speaker, content, ts_val),
                        )
                    conn.commit()
                    return len(rows)
                finally:
                    conn.close()
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if ("lock" in msg or "busy" in msg) and attempt < 5:
                time.sleep(0.02 * (attempt + 1))
                continue
            logger.warning("conversation_store: backfill failed: %s", exc)
            return 0
        except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
            logger.warning("conversation_store: backfill failed", exc_info=True)
            return 0
    return 0


def has_prior_turns(universe_dir: "str | Path", session_id: str) -> bool:
    """True if this session already has durable history.

    Drives the Slack cold-store backfill: an empty store means "backfill from the
    Slack API once", a populated one means "the store is the source of truth".
    """
    if not session_id:
        return False
    db_path = _db_path(universe_dir)
    if not db_path.exists():
        return False
    try:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM conversation_turns WHERE session_id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return False
    return row is not None


__all__ = [
    "backfill_once",
    "has_prior_turns",
    "is_backfilled",
    "load_recent",
    "record_turn",
]
