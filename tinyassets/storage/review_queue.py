"""Owner review queue for loop-produced pull requests — patch-loop S4 (G3/G6).

A user's patch loop (``patch_loop_reference`` remix) produces **ready-to-merge
PRs** against the owner's bound GitHub repo. Those PRs do not merge on their
own: the project OWNER reviews them from any surface (phone included) whenever
they get around to it — **approve / reshape (send back with notes) / reject** —
and a per-remix merge policy governs *when* an eligible PR actually merges.

This module is the durable storage for that queue. It is per-universe (the
owner's universe directory), mirroring the ``effector_consents`` store shape so
the two authority surfaces compose rather than fork:

- ``effector_consents`` — a **standing** grant ("this universe may write to
  repo X via sink S"). Persists until revoked.
- ``review_queue`` (this module) — the **per-PR** owner decision surface, plus
  the **fresh-per-merge founder-OAuth approvals** that Jonathan's own remix
  requires. A standing consent deliberately does NOT satisfy a founder-OAuth
  approval — see :func:`consume_merge_approval`.

Schema (per-universe, file ``${universe_dir}/.review_queue.db``):

.. code-block:: sql

    CREATE TABLE review_queue (
        item_id        TEXT PRIMARY KEY,
        destination    TEXT NOT NULL,   -- owner/repo
        pr_number      INTEGER NOT NULL,
        pr_url         TEXT NOT NULL,
        head_sha       TEXT NOT NULL DEFAULT '',
        request_ref    TEXT NOT NULL DEFAULT '',  -- originating user-request id
        verify_verdict TEXT NOT NULL DEFAULT 'unknown',  -- pass|fail|unknown
        status         TEXT NOT NULL,   -- pending|approved|reshaped|rejected|merged
        notes          TEXT NOT NULL DEFAULT '',
        created_at     REAL NOT NULL,
        updated_at     REAL NOT NULL,
        decided_by     TEXT NOT NULL DEFAULT '',
        decided_at     REAL
    );

    CREATE TABLE merge_approvals (
        approval_id  TEXT PRIMARY KEY,
        item_id      TEXT NOT NULL,
        destination  TEXT NOT NULL,
        pr_number    INTEGER NOT NULL,
        head_sha     TEXT NOT NULL,     -- binds the approval to an exact commit
        approved_by  TEXT NOT NULL,
        approved_at  REAL NOT NULL,
        consumed_at  REAL               -- NULL until a merge consumes it (single-use)
    );

A ``merge_approvals`` row is the founder's *fresh authenticated approval action*
for one merge: it is single-use (``consumed_at`` set on merge) and bound to the
exact ``head_sha`` (a re-pushed PR head invalidates it, forcing re-approval).
That is the concrete difference from a standing consent grant.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_DB_FILENAME = ".review_queue.db"

#: Terminal + in-flight statuses a queue item may hold.
VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "approved", "reshaped", "rejected", "merged"}
)

#: Verify verdicts. Only ``"pass"`` is green; everything else blocks merge.
VERIFY_PASS = "pass"
VERIFY_FAIL = "fail"
VERIFY_UNKNOWN = "unknown"


def review_queue_db_path(universe_dir: str | Path) -> Path:
    """Resolve the per-universe review-queue DB path."""
    return Path(universe_dir) / _DB_FILENAME


def _connect(universe_dir: str | Path) -> sqlite3.Connection:
    """Open the review-queue DB with WAL + 30s busy timeout (hard rule 1/SQLite)."""
    path = review_queue_db_path(universe_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_queue (
    item_id        TEXT PRIMARY KEY,
    destination    TEXT NOT NULL,
    pr_number      INTEGER NOT NULL,
    pr_url         TEXT NOT NULL,
    head_sha       TEXT NOT NULL DEFAULT '',
    request_ref    TEXT NOT NULL DEFAULT '',
    verify_verdict TEXT NOT NULL DEFAULT 'unknown',
    status         TEXT NOT NULL,
    notes          TEXT NOT NULL DEFAULT '',
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL,
    decided_by     TEXT NOT NULL DEFAULT '',
    decided_at     REAL
);

CREATE INDEX IF NOT EXISTS idx_review_queue_status
    ON review_queue(status);

CREATE TABLE IF NOT EXISTS merge_approvals (
    approval_id  TEXT PRIMARY KEY,
    item_id      TEXT NOT NULL,
    destination  TEXT NOT NULL,
    pr_number    INTEGER NOT NULL,
    head_sha     TEXT NOT NULL,
    approved_by  TEXT NOT NULL,
    approved_at  REAL NOT NULL,
    consumed_at  REAL
);

CREATE INDEX IF NOT EXISTS idx_merge_approvals_fresh
    ON merge_approvals(destination, pr_number, head_sha)
    WHERE consumed_at IS NULL;
"""


def initialize_review_queue_db(universe_dir: str | Path) -> Path:
    """Ensure the review-queue DB exists and is migrated. Returns the DB path."""
    path = review_queue_db_path(universe_dir)
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    return path


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "item_id": row["item_id"],
        "destination": row["destination"],
        "pr_number": row["pr_number"],
        "pr_url": row["pr_url"],
        "head_sha": row["head_sha"],
        "request_ref": row["request_ref"],
        "verify_verdict": row["verify_verdict"],
        "status": row["status"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "decided_by": row["decided_by"],
        "decided_at": row["decided_at"],
    }


def enqueue_pr(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    pr_url: str,
    head_sha: str = "",
    request_ref: str = "",
    verify_verdict: str = VERIFY_UNKNOWN,
    now: float | None = None,
) -> dict[str, Any]:
    """Record a loop-produced PR as ``pending`` on the owner's review queue.

    Called by the loop's ``present`` node once it has opened a ready-to-merge
    PR. Idempotent on ``(destination, pr_number)``: re-presenting the same PR
    (e.g. after a re-push) refreshes ``head_sha`` / ``verify_verdict`` and
    resets the item to ``pending`` so the owner re-reviews the new head, but
    keeps the original ``item_id`` + ``created_at``.

    Raises ``ValueError`` on missing required fields (contract violation, not a
    recoverable state — fail loud per hard rule 8).
    """
    dest = (destination or "").strip()
    if not dest:
        raise ValueError("enqueue_pr requires non-empty destination")
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise ValueError("enqueue_pr requires a positive integer pr_number")
    url = (pr_url or "").strip()
    if not url:
        raise ValueError("enqueue_pr requires non-empty pr_url")
    verdict = (verify_verdict or VERIFY_UNKNOWN).strip() or VERIFY_UNKNOWN

    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        existing = conn.execute(
            "SELECT item_id, created_at FROM review_queue "
            "WHERE destination = ? AND pr_number = ?",
            (dest, pr_number),
        ).fetchone()
        if existing is not None:
            item_id = existing["item_id"]
            conn.execute(
                """
                UPDATE review_queue
                   SET pr_url = ?, head_sha = ?, request_ref = ?,
                       verify_verdict = ?, status = 'pending',
                       notes = '', updated_at = ?,
                       decided_by = '', decided_at = NULL
                 WHERE item_id = ?
                """,
                (url, head_sha, request_ref, verdict, ts, item_id),
            )
        else:
            item_id = f"rq-{uuid.uuid4().hex[:16]}"
            conn.execute(
                """
                INSERT INTO review_queue (
                    item_id, destination, pr_number, pr_url, head_sha,
                    request_ref, verify_verdict, status, notes,
                    created_at, updated_at, decided_by, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', ?, ?, '', NULL)
                """,
                (
                    item_id, dest, pr_number, url, head_sha,
                    request_ref, verdict, ts, ts,
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
        ).fetchone()
    return _row_to_item(row)


def get_item(universe_dir: str | Path, *, item_id: str) -> dict[str, Any] | None:
    """Return a single queue item by id, or None if absent."""
    if not item_id:
        return None
    initialize_review_queue_db(universe_dir)
    with _connect(universe_dir) as conn:
        row = conn.execute(
            "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
        ).fetchone()
    return _row_to_item(row) if row is not None else None


def list_queue(
    universe_dir: str | Path,
    *,
    status: str | None = None,
    destination: str | None = None,
) -> list[dict[str, Any]]:
    """Return queue items, newest first. Optional ``status`` / ``destination``
    filters. With no filters, returns the whole queue (all statuses)."""
    initialize_review_queue_db(universe_dir)
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if destination:
        clauses.append("destination = ?")
        params.append(destination)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _connect(universe_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM review_queue {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def _decide(
    universe_dir: str | Path,
    *,
    item_id: str,
    new_status: str,
    decided_by: str,
    notes: str,
    now: float | None,
) -> dict[str, Any] | None:
    """Transition an item's status + stamp the decider. Returns the updated
    item, or None if the item does not exist."""
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        row = conn.execute(
            "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """
            UPDATE review_queue
               SET status = ?, notes = ?, decided_by = ?,
                   decided_at = ?, updated_at = ?
             WHERE item_id = ?
            """,
            (new_status, notes, decided_by, ts, ts, item_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
        ).fetchone()
    return _row_to_item(updated)


def approve_item(
    universe_dir: str | Path,
    *,
    item_id: str,
    approved_by: str,
    notes: str = "",
    now: float | None = None,
) -> dict[str, Any] | None:
    """Owner approves a queued PR. Sets status ``approved`` and mints a **fresh,
    single-use founder-OAuth approval** bound to the item's current
    ``head_sha`` + ``pr_number``.

    The minted approval is what a founder-OAuth-per-merge policy consumes at
    merge time (see :func:`consume_merge_approval`). For a manual policy WITHOUT
    founder-OAuth the token is simply unused — the ``approved`` status alone
    releases the merge.

    Returns the updated item (with an ``approval_id`` key), or None when the
    item does not exist.
    """
    if not approved_by:
        raise ValueError("approve_item requires non-empty approved_by")
    item = get_item(universe_dir, item_id=item_id)
    if item is None:
        return None
    ts = now if now is not None else time.time()
    approval_id = f"ap-{uuid.uuid4().hex[:16]}"
    with _connect(universe_dir) as conn:
        conn.execute(
            """
            INSERT INTO merge_approvals (
                approval_id, item_id, destination, pr_number, head_sha,
                approved_by, approved_at, consumed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                approval_id, item_id, item["destination"], item["pr_number"],
                item["head_sha"], approved_by, ts,
            ),
        )
        conn.commit()
    updated = _decide(
        universe_dir,
        item_id=item_id,
        new_status="approved",
        decided_by=approved_by,
        notes=notes,
        now=ts,
    )
    if updated is not None:
        updated["approval_id"] = approval_id
    return updated


def reshape_item(
    universe_dir: str | Path,
    *,
    item_id: str,
    reshaped_by: str,
    notes: str,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Owner sends a PR back to the loop with notes. Sets status ``reshaped``
    and returns the item plus a ``route_back`` payload the loop's
    ``draft_patch`` node consumes to produce a revised patch.

    ``notes`` is required — a reshape with no guidance is meaningless; the
    owner must say what to change. Any outstanding fresh approvals for the item
    are invalidated (consumed) so a stale approval can't merge the pre-reshape
    head.
    """
    reshaped_by = (reshaped_by or "").strip()
    if not reshaped_by:
        raise ValueError("reshape_item requires non-empty reshaped_by")
    if not (notes or "").strip():
        raise ValueError(
            "reshape_item requires non-empty notes — a reshape must tell the "
            "loop what to change"
        )
    item = get_item(universe_dir, item_id=item_id)
    if item is None:
        return None
    ts = now if now is not None else time.time()
    # Invalidate any outstanding approvals — the head we approved is being sent
    # back for rework, so no stale token may merge it.
    with _connect(universe_dir) as conn:
        conn.execute(
            "UPDATE merge_approvals SET consumed_at = ? "
            "WHERE item_id = ? AND consumed_at IS NULL",
            (ts, item_id),
        )
        conn.commit()
    updated = _decide(
        universe_dir,
        item_id=item_id,
        new_status="reshaped",
        decided_by=reshaped_by,
        notes=notes,
        now=ts,
    )
    if updated is None:
        return None
    updated["route_back"] = {
        "target_node": "draft_patch",
        "item_id": item_id,
        "destination": item["destination"],
        "pr_number": item["pr_number"],
        "request_ref": item["request_ref"],
        "owner_notes": notes,
    }
    return updated


def reject_item(
    universe_dir: str | Path,
    *,
    item_id: str,
    rejected_by: str,
    notes: str = "",
    now: float | None = None,
) -> dict[str, Any] | None:
    """Owner rejects a queued PR (terminal). Invalidates outstanding approvals."""
    rejected_by = (rejected_by or "").strip()
    if not rejected_by:
        raise ValueError("reject_item requires non-empty rejected_by")
    item = get_item(universe_dir, item_id=item_id)
    if item is None:
        return None
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        conn.execute(
            "UPDATE merge_approvals SET consumed_at = ? "
            "WHERE item_id = ? AND consumed_at IS NULL",
            (ts, item_id),
        )
        conn.commit()
    return _decide(
        universe_dir,
        item_id=item_id,
        new_status="rejected",
        decided_by=rejected_by,
        notes=notes,
        now=ts,
    )


def has_fresh_merge_approval(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    head_sha: str,
) -> bool:
    """Return True iff an unconsumed founder-OAuth approval exists bound to the
    exact ``(destination, pr_number, head_sha)``. Read-only — does NOT consume.

    A standing effector consent is intentionally invisible here: this queries
    only the ``merge_approvals`` fresh-token table, never ``effector_consents``.
    """
    if not destination or not head_sha or not isinstance(pr_number, int):
        return False
    initialize_review_queue_db(universe_dir)
    with _connect(universe_dir) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM merge_approvals
             WHERE destination = ? AND pr_number = ? AND head_sha = ?
               AND consumed_at IS NULL
             LIMIT 1
            """,
            (destination, pr_number, head_sha),
        ).fetchone()
    return row is not None


def consume_merge_approval(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    head_sha: str,
    now: float | None = None,
) -> str | None:
    """Consume (single-use) a fresh founder-OAuth approval for an exact
    ``(destination, pr_number, head_sha)`` and return its ``approval_id``.

    Returns None when no fresh approval exists — the founder has not performed a
    fresh authenticated approval for *this* PR head. A standing effector consent
    can NEVER satisfy this (different table), and a token already consumed by a
    prior merge attempt can never satisfy a second (``consumed_at`` is set on
    first use). This is the concrete "fresh per merge, not a standing consent"
    security property from the reference design §7.
    """
    if not destination or not head_sha or not isinstance(pr_number, int):
        return None
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        row = conn.execute(
            """
            SELECT approval_id FROM merge_approvals
             WHERE destination = ? AND pr_number = ? AND head_sha = ?
               AND consumed_at IS NULL
          ORDER BY approved_at ASC
             LIMIT 1
            """,
            (destination, pr_number, head_sha),
        ).fetchone()
        if row is None:
            return None
        approval_id = row["approval_id"]
        conn.execute(
            "UPDATE merge_approvals SET consumed_at = ? WHERE approval_id = ?",
            (ts, approval_id),
        )
        conn.commit()
    return approval_id


__all__ = [
    "review_queue_db_path",
    "initialize_review_queue_db",
    "VALID_STATUSES",
    "VERIFY_PASS",
    "VERIFY_FAIL",
    "VERIFY_UNKNOWN",
    "enqueue_pr",
    "get_item",
    "list_queue",
    "approve_item",
    "reshape_item",
    "reject_item",
    "has_fresh_merge_approval",
    "consume_merge_approval",
]
