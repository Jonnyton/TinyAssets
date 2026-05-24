"""Trigger receipt / outbox primitive for wiki-filed bug investigations
(FEAT-004).

Per-request-id traceable record of what happened when a wiki page filing
attempted to auto-trigger the canonical investigation branch. Closes the
silent-enqueue-failure gap discovered after PR #176 wired the in-process
trigger call-site: the page write could succeed and the response could
look healthy while the trigger silently failed to enqueue, leaving an
opaque "filing succeeded, no run exists" state.

Storage: a tiny sqlite table at $WORKFLOW_DATA_DIR/wiki_trigger_attempts.db.
One row per filed-page trigger attempt. Append-only via this module's
helpers — the write is in the same logical commit as the page metadata
write so an enqueue failure cannot erase the fact that a trigger was
expected.

Status lifecycle:

    pending  -> queued (dispatcher returned a request_id)
    pending  -> failed (dispatcher raised; error_class/error_message recorded)
    pending  -> skipped (no canonical branch configured; recorded for audit)

Surface: the file_bug response payload includes a ``trigger`` block
containing the receipt fields. Operators and canaries can also query
the table directly via ``recent_attempts(limit)`` and
``orphan_attempts(stale_minutes)`` for periodic health checks.

Backward compatibility: the existing ``investigation`` block in the
file_bug response is preserved verbatim. The new ``trigger`` block is
additive.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status enum + dataclass
# ---------------------------------------------------------------------------

# Status values are stored as text in the sqlite table for forward-compat.
# Adding a new status (e.g. "rejected_by_policy") is a no-op on existing
# rows — older rows stay valid because the column has no enum constraint.
STATUS_PENDING = "pending"
STATUS_QUEUED = "queued"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


@dataclass
class TriggerReceipt:
    """One trigger attempt for a wiki-filed request.

    Mirrors the ``wiki_trigger_attempts`` table schema. Use ``to_response``
    to produce the dict that lands in the file_bug response payload's
    ``trigger`` block.
    """

    trigger_attempt_id: str
    request_id: str  # bug_id or feature request id, e.g. "BUG-047" / "FEAT-004"
    request_kind: str  # "bug" / "feature" / "design"
    request_page: str  # path within the wiki, e.g. pages/bugs/bug-047-...md
    status: str  # one of STATUS_*
    attempted_at: str  # ISO-8601 UTC
    goal_id: str | None = None
    branch_def_id: str | None = None
    queued_at: str | None = None
    run_id: str | None = None
    dispatcher_request_id: str | None = None
    error_class: str | None = None
    error_message: str | None = None

    def to_response(self) -> dict[str, Any]:
        """Build the ``trigger`` block for the file_bug response payload."""
        out: dict[str, Any] = {
            "attempted": True,
            "trigger_attempt_id": self.trigger_attempt_id,
            "status": self.status,
        }
        # Optional fields — omit when None to keep the payload compact.
        for key in (
            "goal_id", "branch_def_id", "queued_at",
            "run_id", "dispatcher_request_id",
        ):
            v = getattr(self, key)
            if v is not None:
                out[key] = v
        if self.error_class or self.error_message:
            out["error"] = {
                "class": self.error_class,
                "message": self.error_message,
            }
        return out

    def to_row(self) -> dict[str, Any]:
        """Full dict for sqlite write. Includes None for optional cols."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Sqlite store
# ---------------------------------------------------------------------------

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS wiki_trigger_attempts (
    trigger_attempt_id    TEXT PRIMARY KEY,
    request_id            TEXT NOT NULL,
    request_kind          TEXT NOT NULL,
    request_page          TEXT NOT NULL,
    status                TEXT NOT NULL,
    attempted_at          TEXT NOT NULL,
    goal_id               TEXT,
    branch_def_id         TEXT,
    queued_at             TEXT,
    run_id                TEXT,
    dispatcher_request_id TEXT,
    error_class           TEXT,
    error_message         TEXT
)
"""

_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_wiki_trigger_request_id "
    "ON wiki_trigger_attempts(request_id)",
    "CREATE INDEX IF NOT EXISTS idx_wiki_trigger_status_attempted "
    "ON wiki_trigger_attempts(status, attempted_at)",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_db_path() -> Path:
    """Resolve the trigger receipts sqlite path.

    Honors ``WORKFLOW_TRIGGER_RECEIPTS_DB`` env override (test-friendly),
    otherwise places the file under ``WORKFLOW_DATA_DIR`` (resolved by
    ``workflow.storage.data_dir()`` when available, else env fallback).
    """
    override = os.environ.get("WORKFLOW_TRIGGER_RECEIPTS_DB", "").strip()
    if override:
        return Path(override)

    # Try the canonical resolver first; fall back to env if storage module
    # isn't importable (some test contexts).
    try:
        from workflow.storage import data_dir
        base = data_dir()
    except Exception:
        base = Path(os.environ.get("WORKFLOW_DATA_DIR", str(Path.home() / ".workflow")))

    base.mkdir(parents=True, exist_ok=True)
    return base / "wiki_trigger_attempts.db"


@contextmanager
def _conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a sqlite connection with the table ensured."""
    p = db_path or _resolve_db_path()
    conn = sqlite3.connect(str(p))
    try:
        conn.execute(_TABLE_DDL)
        for ddl in _INDEX_DDL:
            conn.execute(ddl)
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public API — called by workflow/api/wiki.py:_wiki_file_bug
# ---------------------------------------------------------------------------


def create_pending(
    *,
    request_id: str,
    request_kind: str,
    request_page: str,
    goal_id: str | None = None,
    branch_def_id: str | None = None,
    db_path: Path | None = None,
) -> TriggerReceipt:
    """Insert a new pending receipt and return it.

    Called BEFORE the trigger helper runs so the attempt is durable even
    if the helper crashes before reporting. The returned object carries
    the freshly-minted ``trigger_attempt_id`` which the caller threads
    into ``mark_queued`` / ``mark_failed`` / ``mark_skipped``.
    """
    receipt = TriggerReceipt(
        trigger_attempt_id=str(uuid.uuid4()),
        request_id=request_id,
        request_kind=request_kind,
        request_page=request_page,
        status=STATUS_PENDING,
        attempted_at=_utc_now_iso(),
        goal_id=goal_id,
        branch_def_id=branch_def_id,
    )
    with _conn(db_path) as c:
        c.execute(
            """INSERT INTO wiki_trigger_attempts (
                trigger_attempt_id, request_id, request_kind, request_page,
                status, attempted_at, goal_id, branch_def_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.trigger_attempt_id, receipt.request_id,
                receipt.request_kind, receipt.request_page,
                receipt.status, receipt.attempted_at,
                receipt.goal_id, receipt.branch_def_id,
            ),
        )
    logger.info(
        "trigger_receipt | pending | %s | %s",
        receipt.trigger_attempt_id, receipt.request_id,
    )
    return receipt


def mark_queued(
    receipt: TriggerReceipt,
    *,
    dispatcher_request_id: str | None = None,
    run_id: str | None = None,
    db_path: Path | None = None,
) -> TriggerReceipt:
    """Update an existing receipt to status=queued. Returns the updated obj."""
    receipt.status = STATUS_QUEUED
    receipt.queued_at = _utc_now_iso()
    receipt.dispatcher_request_id = dispatcher_request_id
    receipt.run_id = run_id
    with _conn(db_path) as c:
        c.execute(
            """UPDATE wiki_trigger_attempts
               SET status=?, queued_at=?, dispatcher_request_id=?, run_id=?
               WHERE trigger_attempt_id=?""",
            (
                receipt.status, receipt.queued_at,
                receipt.dispatcher_request_id, receipt.run_id,
                receipt.trigger_attempt_id,
            ),
        )
    logger.info(
        "trigger_receipt | queued | %s | dispatcher=%s run=%s",
        receipt.trigger_attempt_id, dispatcher_request_id, run_id,
    )
    return receipt


def mark_failed(
    receipt: TriggerReceipt,
    *,
    error: BaseException | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    db_path: Path | None = None,
) -> TriggerReceipt:
    """Update an existing receipt to status=failed. Returns the updated obj.

    Pass either ``error`` (auto-derives class+message) OR explicit
    ``error_class`` and ``error_message``.
    """
    receipt.status = STATUS_FAILED
    if error is not None:
        receipt.error_class = type(error).__name__
        receipt.error_message = str(error)[:500]
    if error_class is not None:
        receipt.error_class = error_class
    if error_message is not None:
        receipt.error_message = error_message[:500]
    with _conn(db_path) as c:
        c.execute(
            """UPDATE wiki_trigger_attempts
               SET status=?, error_class=?, error_message=?
               WHERE trigger_attempt_id=?""",
            (
                receipt.status,
                receipt.error_class, receipt.error_message,
                receipt.trigger_attempt_id,
            ),
        )
    logger.warning(
        "trigger_receipt | failed | %s | %s: %s",
        receipt.trigger_attempt_id, receipt.error_class, receipt.error_message,
    )
    return receipt


def mark_skipped(
    receipt: TriggerReceipt,
    *,
    reason: str = "no_canonical_branch",
    db_path: Path | None = None,
) -> TriggerReceipt:
    """Update an existing receipt to status=skipped. Returns the updated obj.

    Use when a trigger was deliberately not attempted (e.g. no canonical
    branch configured for this universe). Records ``reason`` in the
    error_message column for audit; this is intentional dual-use of the
    column to keep the schema narrow.
    """
    receipt.status = STATUS_SKIPPED
    receipt.error_class = "skip"
    receipt.error_message = reason
    with _conn(db_path) as c:
        c.execute(
            """UPDATE wiki_trigger_attempts
               SET status=?, error_class=?, error_message=?
               WHERE trigger_attempt_id=?""",
            (
                receipt.status, receipt.error_class, receipt.error_message,
                receipt.trigger_attempt_id,
            ),
        )
    return receipt


# ---------------------------------------------------------------------------
# Read API — called by canaries / get_status / operators
# ---------------------------------------------------------------------------


def get_receipt(
    trigger_attempt_id: str,
    *,
    db_path: Path | None = None,
) -> TriggerReceipt | None:
    """Read a single receipt by id. Returns None if not found."""
    with _conn(db_path) as c:
        row = c.execute(
            "SELECT * FROM wiki_trigger_attempts WHERE trigger_attempt_id=?",
            (trigger_attempt_id,),
        ).fetchone()
    if row is None:
        return None
    return TriggerReceipt(**dict(row))


def receipts_for_request(
    request_id: str,
    *,
    db_path: Path | None = None,
) -> list[TriggerReceipt]:
    """All receipts for a given request_id (e.g. all retries of BUG-047)."""
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT * FROM wiki_trigger_attempts WHERE request_id=? "
            "ORDER BY attempted_at",
            (request_id,),
        ).fetchall()
    return [TriggerReceipt(**dict(r)) for r in rows]


def recent_attempts(
    limit: int = 50,
    *,
    db_path: Path | None = None,
) -> list[TriggerReceipt]:
    """Most-recently-attempted receipts. For dashboards / get_status."""
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT * FROM wiki_trigger_attempts "
            "ORDER BY attempted_at DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [TriggerReceipt(**dict(r)) for r in rows]


def orphan_attempts(
    stale_minutes: int = 30,
    *,
    db_path: Path | None = None,
) -> list[TriggerReceipt]:
    """Receipts stuck in pending/queued past ``stale_minutes``.

    Orphan = `pending` for too long (trigger helper crashed without
    update) OR `queued` for too long with no observed run completion.
    Canaries call this periodically to detect silent failures.

    NOTE: SQLite text-column timestamp comparison only works because
    we always write ISO-8601 UTC strings (lex order = chrono order).
    Don't write local-tz strings into this column.
    """
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT * FROM wiki_trigger_attempts "
            "WHERE status IN (?, ?) AND attempted_at < ? "
            "ORDER BY attempted_at",
            (STATUS_PENDING, STATUS_QUEUED, cutoff),
        ).fetchall()
    return [TriggerReceipt(**dict(r)) for r in rows]


def health_summary(
    *,
    db_path: Path | None = None,
    last_n: int = 100,
) -> dict[str, Any]:
    """Compact snapshot suitable for embedding in get_status.

    Counts the most recent ``last_n`` attempts by status and surfaces
    the latest seen timestamps. Cheap query — no large scans.
    """
    with _conn(db_path) as c:
        rows = c.execute(
            "SELECT status, attempted_at FROM wiki_trigger_attempts "
            "ORDER BY attempted_at DESC LIMIT ?",
            (max(1, int(last_n)),),
        ).fetchall()
    counts: dict[str, int] = {}
    last_ts: dict[str, str] = {}
    for r in rows:
        s = r["status"]
        counts[s] = counts.get(s, 0) + 1
        if s not in last_ts:
            last_ts[s] = r["attempted_at"]
    return {
        "window_size": len(rows),
        "by_status": counts,
        "last_seen_at": last_ts,
    }
