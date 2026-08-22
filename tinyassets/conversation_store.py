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
The user-controlled privacy/export/delete custody store (behind one-use
Ed25519-signed per-operation grants) is a SEPARATE concern, and this module is
deliberately NOT a consumer of it. Using that store for every-turn working
memory would mean minting + consuming a signed grant per turn — the wrong tool.
Authorization for the turn is the founder gate on the
caller (``converse`` is founder-only; history injection is founder-gated), and
per-universe DB isolation inherits the universe dir's filesystem boundary. If a
future authenticated app-conversation authority owner ships, this store is where
it integrates; until then it stays deliberately lightweight.
"""

from __future__ import annotations

import logging
import math
import sqlite3
import threading
import time
from collections import Counter
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
    ext_id     TEXT    NOT NULL DEFAULT '',
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
    # Migrate a pre-ext_id table (older DB that predates the stable-id column).
    # Idempotent: a DB that already has the column raises "duplicate column name",
    # which we swallow QUIETLY. Any OTHER OperationalError (a locked/corrupt DB)
    # must be VISIBLE — swallowing it silently would disable ext_id reconciliation
    # forever with no diagnostic (Codex 2026-08-10). `ext_id` is the raw Slack
    # message ts — the STABLE identity sync_tail dedups on.
    try:
        conn.execute("ALTER TABLE conversation_turns ADD COLUMN ext_id TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError as exc:
        if "duplicate column" not in str(exc).lower():
            logger.warning("conversation_store: ext_id migration failed: %s", exc)
    # Stable-id uniqueness — the DB-level guarantee that no ext_id is ever stored
    # twice per session, so a re-synced/raced timeline cannot duplicate a turn
    # regardless of the dedup logic above it (Codex FIX2/NEW1 2026-08-10). PARTIAL
    # so the many id-less ('') rows (live-recorded founder turns) never collide.
    # Tolerated if a pre-existing DB already holds a dup: log, don't break the store.
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_turns_extid "
            "ON conversation_turns(session_id, ext_id) WHERE ext_id != ''"
        )
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
        logger.warning(
            "conversation_store: ext_id uniqueness index not created: %s", exc
        )
    return conn


def record_turn(
    universe_dir: "str | Path",
    session_id: str,
    speaker: str,
    text: str,
    *,
    ts: float | None = None,
    ext_id: str = "",
) -> int:
    """Append one turn; return its per-session ``turn_no`` (0 if not recorded).

    Blank text is a no-op (returns 0). Best-effort: any storage failure logs and
    returns 0 rather than raising, so a memory hiccup never breaks the reply. A
    malformed ``ts`` degrades to "now" rather than raising (a bad ts must never
    cost the turn). ``ext_id`` is a stable external identity (the Slack message
    ts) used for dedup; "" when unknown.
    """
    if not isinstance(text, str) or not text.strip():
        return 0
    if not session_id:
        return 0
    # Setup can raise too (a custom ext_id with a raising __str__, a bad-type
    # universe_dir in _db_path), and this runs OUTSIDE the retry try below, so
    # guard it — record_turn's contract is NEVER to raise into the turn
    # (Codex 2026-08-10).
    try:
        when = _when(ts)
        ext_id = str(ext_id or "")
        db_path = _db_path(universe_dir)
        lock = _lock_for(db_path)
    except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
        logger.warning("conversation_store: record setup failed", exc_info=True)
        return 0
    for attempt in range(6):
        try:
            with lock:
                conn = _connect(db_path)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    # Stable-id idempotency: if this ext_id is already stored for
                    # the session, it's a re-sync / concurrent-sync repeat, NOT a
                    # new turn. BEGIN IMMEDIATE serialises writers (in- AND cross-
                    # process), so this check + insert is atomic — closing the
                    # read-before-write window that let two syncs both persist the
                    # same reply (Codex FIX2/NEW1 2026-08-10). Return 0 QUIETLY:
                    # nothing was appended, but nothing was dropped either.
                    if ext_id:
                        dup = conn.execute(
                            "SELECT 1 FROM conversation_turns "
                            "WHERE session_id = ? AND ext_id = ? LIMIT 1",
                            (session_id, ext_id),
                        ).fetchone()
                        if dup is not None:
                            conn.commit()
                            return 0
                    row = conn.execute(
                        "SELECT COALESCE(MAX(turn_no), 0) + 1 "
                        "FROM conversation_turns WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
                    turn_no = int(row[0])
                    conn.execute(
                        "INSERT INTO conversation_turns "
                        "(session_id, turn_no, speaker, content, ts, ext_id) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (session_id, turn_no, str(speaker or ""), text, when, ext_id),
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
        except sqlite3.IntegrityError as exc:  # turn_no race → retry; ext_id → stored
            # The partial UNIQUE(session_id, ext_id) index is the cross-process
            # backstop to the in-transaction check above: if it fires, the turn is
            # already stored — return 0 QUIETLY, never burn retries or warn (Codex
            # FIX2/NEW1 2026-08-10). Only a turn_no collision is a real race.
            if "ext_id" in str(exc).lower():
                return 0
            if attempt < 5:
                time.sleep(0.02 * (attempt + 1))
                continue
            # Retries exhausted on the turn_no race. Best-effort still means the
            # reply survives, but a DROPPED record is exactly what silently
            # drifts the store behind the live thread — so it must be VISIBLE
            # (WARNING), never a silent return, or a future regression hides here.
            logger.warning(
                "conversation_store: record dropped after %d turn_no races "
                "for session %s (store may drift behind the live thread)",
                attempt + 1,
                session_id,
            )
            return 0
        except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
            logger.warning("conversation_store: record failed", exc_info=True)
            return 0
    # Only reached if every attempt was a transient retry that never resolved.
    logger.warning(
        "conversation_store: record failed after %d attempts for session %s",
        6,
        session_id,
    )
    return 0


#: Per-session retention ceiling for the verbatim transcript at rest. Rendering
#: is already bounded (DEFAULT_LIMIT turns / character budget); this bounds the
#: store itself so a long-lived thread cannot grow without limit. Oldest turns
#: beyond it are deleted on every exchange (Codex 2026-08-22 #3). User-driven
#: deletion/export of the transcript is a separate, tracked follow-up.
RETENTION_TURNS = 400


def record_exchange(
    universe_dir: "str | Path",
    session_id: str,
    founder_text: str,
    universe_text: str,
    *,
    ts: float | None = None,
) -> bool:
    """Append a founder turn AND the universe's reply in ONE transaction.

    Two independent ``record_turn`` calls can leave a founder-only half-turn
    when the second write fails (Codex 2026-08-22 #2); here both rows commit
    together or not at all. Also applies ``RETENTION_TURNS``. Best-effort by
    contract: returns False and logs on any failure, never raises.
    """
    if not session_id or not isinstance(founder_text, str) or not founder_text.strip():
        return False
    if not isinstance(universe_text, str) or not universe_text.strip():
        return False
    try:
        when = _when(ts)
        db_path = _db_path(universe_dir)
        lock = _lock_for(db_path)
    except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
        logger.warning("conversation_store: exchange setup failed", exc_info=True)
        return False
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
                    conn.executemany(
                        "INSERT INTO conversation_turns "
                        "(session_id, turn_no, speaker, content, ts, ext_id) "
                        "VALUES (?, ?, ?, ?, ?, '')",
                        [
                            (session_id, turn_no, "founder", founder_text, when),
                            (session_id, turn_no + 1, "universe", universe_text, when),
                        ],
                    )
                    conn.execute(
                        "DELETE FROM conversation_turns WHERE session_id = ? AND turn_no <= "
                        "(SELECT COALESCE(MAX(turn_no), 0) FROM conversation_turns "
                        "WHERE session_id = ?) - ?",
                        (session_id, session_id, RETENTION_TURNS),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except (sqlite3.OperationalError, sqlite3.IntegrityError) as exc:
            msg = str(exc).lower()
            if ("lock" in msg or "busy" in msg or "unique" in msg) and attempt < 5:
                time.sleep(0.02 * (attempt + 1))
                continue
            logger.warning("conversation_store: exchange failed: %s", exc)
            return False
        except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
            logger.warning("conversation_store: exchange failed", exc_info=True)
            return False
    logger.warning("conversation_store: exchange failed after 6 attempts for %s", session_id)
    return False


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
    try:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                "SELECT speaker, content, ts FROM conversation_turns "
                "WHERE session_id = ? ORDER BY ts DESC, turn_no DESC LIMIT ?",
                (session_id, max(1, int(limit))),
            ).fetchall()
        finally:
            conn.close()
        # Order by the real Slack ts (CHRONOLOGY), turn_no only as a tiebreaker.
        # sync_tail can back-fill a missed MIDDLE turn, which gets turn_no=max+1
        # (appended last); ordering by turn_no alone would then render it out of
        # order (stored 1,3 + synced 2 -> "1,3,2"). Ordering by ts renders 1,2,3
        # (Codex 2026-08-10). Every row has a positive ts (_when falls back to now).
        # DESC from SQL → reverse to oldest-first for the formatter. Carry ts so
        # the turn knows WHEN each message was sent (SDK createdAt metadata). The
        # ts coercion stays INSIDE the try so malformed stored data degrades to
        # "no memory", never a raise (fail-open contract).
        return [
            Msg(speaker=str(sp or ""), text=str(ct or ""), ts=_coerce_ts(t))
            for sp, ct, t in reversed(rows)
        ]
    except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
        logger.warning("conversation_store: load failed", exc_info=True)
        return []


def sync_tail(
    universe_dir: "str | Path",
    session_id: str,
    live_messages: "list[dict]",
    *,
    limit: int = DEFAULT_LIMIT,
) -> int:
    """Reconcile the store's tail against the live timeline; append what's missing.

    Why this exists
    ---------------
    ``backfill_once`` runs EXACTLY ONCE per session (a marker row claims it). It
    imports the timeline the first time and never again. So if any later
    ``record_turn`` is dropped — a transient turn_no race that exhausts its
    retries, a crash between the founder-record and the reply-record, a turn
    taken by a path that forgot to record — the store silently drifts BEHIND the
    live thread and, because backfill is spent, never re-syncs. The universe
    keeps losing the most recent context and nothing surfaces it. That is the
    exact class of silent regression that froze u-tiny's memory at turn 130.

    This makes the LOAD path self-healing: before a turn builds its history
    block, reconcile the durable tail against the live timeline and append only
    the missing trailing turns, so a missed record can never cost recent context.

    Contract
    --------
    * ``live_messages`` is the ``[{"speaker","text","ts"}]`` shape the Slack
      timeline loader returns, oldest-first, ALREADY excluding the current
      prompt (the loader does this).
    * Bounded: only reconciles against the recent window (``limit``), never the
      whole history.
    * De-duped by the stable Slack ``ts``. A legacy id-less row may match by
      ``(speaker, text)``, but each stored row is consumed at most once.
    * Reconciled oldest-first. A failed append stops the pass immediately, so a
      later success cannot become an anchor that permanently strands the gap.
      A window with no overlap does nothing; cold import is ``backfill_once``'s
      job.
    * Best-effort: NEVER raises (the whole body is guarded) and never
      double-counts — ``appended`` only advances when ``record_turn`` actually
      persisted (returned a turn_no), so a dropped write is not logged as a sync.
    """
    try:
        return _sync_tail_impl(universe_dir, session_id, live_messages, limit=limit)
    except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
        logger.warning("conversation_store: sync_tail failed", exc_info=True)
        return 0


def _sync_tail_impl(
    universe_dir: "str | Path",
    session_id: str,
    live_messages: "list[dict]",
    *,
    limit: int,
) -> int:
    if not session_id:
        return 0
    rows = [
        (str(m.get("speaker") or ""), str(m.get("text") or "").strip(), str(m.get("ts") or ""))
        for m in (live_messages or [])
        if isinstance(m, dict) and str(m.get("text") or "").strip()
    ]
    if not rows:
        return 0
    stored = _recent_identities(
        universe_dir, session_id, limit=max(int(limit), len(rows) + 5)
    )
    if not stored:
        # Cold store: that is backfill_once's job. Appending a whole live window
        # here would both duplicate what backfill imports and race it.
        return 0
    stored_ids = {ext for _sp, _tx, ext in stored if ext}
    # Text fallback exists only for pre-stable-id rows. A Counter makes the
    # fallback a one-for-one legacy migration seam rather than a text set that
    # shadows every later message with the same words.
    legacy_pairs = Counter(
        (speaker, text)
        for speaker, text, ext in stored
        if text and not ext
    )
    # The newest stored STABLE id (a Slack ts). A legacy id-less row can only
    # stand in for an OLD live message (<= this); a live row NEWER than every
    # stored id is genuinely new and must never be swallowed by a stale text
    # match whose original has rolled out of the window (Codex FIX2 2026-08-10).
    _id_ts = [t for t in (_coerce_ts(e) for e in stored_ids) if t is not None]
    newest_id_ts = max(_id_ts) if _id_ts else None

    def _known(speaker: str, text: str, ext: str) -> bool:
        # Exact stable-id match first; consume one legacy id-less row only when
        # necessary. New daemon-side founder and universe writes both have ids.
        if ext and ext in stored_ids:
            return True
        pair = (speaker, text)
        if legacy_pairs[pair]:
            live_ts = _coerce_ts(ext)
            # Only when this live row is not newer than the newest stored id
            # (or there are no id rows yet — the pure-legacy transition start).
            if newest_id_ts is None or (live_ts is not None and live_ts <= newest_id_ts):
                legacy_pairs[pair] -= 1
                return True
        return False

    # Require some overlap so sync_tail never races cold backfill. Once overlap
    # exists, walk the entire window oldest-first; this also repairs a gap that
    # appears before a later already-stored row.
    if not any(
        (ext and ext in stored_ids) or legacy_pairs[(speaker, text)]
        for speaker, text, ext in rows
    ):
        return 0
    appended = 0
    for speaker, text, ext in rows:
        if _known(speaker, text, ext):
            continue  # already stored (id or text) — never duplicate
        if not ext:
            # Slack timeline rows always carry ts. Without one there is no safe
            # durable identity, so do not store or advance beyond this gap.
            break
        turn_no = record_turn(
            universe_dir, session_id, speaker, text, ts=_coerce_ts(ext), ext_id=ext
        )
        if not turn_no:
            # Do not count or advance beyond an unpersisted gap. The next turn
            # starts from the same row and retries it before any later message.
            break
        stored_ids.add(ext)
        appended += 1
    if appended:
        logger.info(
            "conversation_store: re-synced %d missing tail turn(s) for session %s",
            appended,
            session_id,
        )
    return appended


def _recent_identities(
    universe_dir: "str | Path", session_id: str, *, limit: int
) -> "list[tuple[str, str, str]]":
    """Recent stored turns as ``(speaker, text, ext_id)`` for sync_tail dedup.

    Separate from :func:`load_recent` because that returns render-ready ``Msg``
    objects with no ``ext_id``. Empty on any trouble (fail-open).
    """
    if not session_id:
        return []
    db_path = _db_path(universe_dir)
    if not db_path.exists():
        return []
    try:
        conn = _connect(db_path)
        try:
            fetched = conn.execute(
                "SELECT speaker, content, ext_id FROM conversation_turns "
                "WHERE session_id = ? ORDER BY ts DESC, turn_no DESC LIMIT ?",
                (session_id, max(1, int(limit))),
            ).fetchall()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - memory is a bonus, never a blocker
        # Fail-open, but NOT silent: an empty identity set disables sync_tail
        # reconciliation, so a persistently locked/failed read would let the store
        # drift behind the live thread forever with no diagnostic (Codex NEW2
        # 2026-08-10). Make it visible.
        logger.warning(
            "conversation_store: identity read failed for session %s "
            "(sync reconciliation degraded this turn)",
            session_id,
            exc_info=True,
        )
        return []
    return [
        (str(sp or ""), str(ct or "").strip(), str(ext or ""))
        for sp, ct, ext in fetched
    ]


def _coerce_ts(value: object) -> "float | None":
    """A Slack/epoch ts (str or number) as float seconds, or None.

    Catches EVERY conversion failure, not just TypeError/ValueError: e.g.
    ``float(10**10000)`` raises OverflowError, and a ts must NEVER cost the turn
    (Codex FIX1 2026-08-10). NaN/inf are rejected too (``f > 0`` is False for
    both), so a poisoned ts degrades to "now" upstream rather than storing junk.
    """
    try:
        f = float(value)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - a bad ts must never raise into the turn
        return None
    # Finite AND positive. `float("inf") > 0` is True, so without isfinite an
    # "inf" ts would be STORED and — now that load_recent orders by ts — sort
    # above every real turn, crowding valid history out of the bounded window
    # (Codex 2026-08-10). NaN is already rejected (`nan > 0` is False).
    return f if (math.isfinite(f) and f > 0) else None


def _when(ts: object) -> float:
    """A valid epoch-seconds "when" for storage — never raises, falls back to now."""
    coerced = _coerce_ts(ts)
    return coerced if coerced is not None else time.time()


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
        (
            str(m.get("speaker") or ""),
            str(m.get("text") or ""),
            _ts(m),
            str(m.get("ts") or ""),  # ext_id: the stable Slack message id
        )
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
                    for i, (speaker, content, ts_val, ext) in enumerate(rows, start=1):
                        conn.execute(
                            "INSERT INTO conversation_turns "
                            "(session_id, turn_no, speaker, content, ts, ext_id) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (session_id, base + i, speaker, content, ts_val, ext),
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
    "sync_tail",
]
