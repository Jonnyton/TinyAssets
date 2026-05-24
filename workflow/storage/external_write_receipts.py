"""External-write idempotency receipts — PR-122 Phase 2.

Per-universe SQLite store recording every external-write attempt so
concurrent runs do not produce duplicate side-effects.

Design source: ``drafts/concepts/external-write-phase-2-authority.md``
§2 "Idempotency store". The store is one of three gates the
``github_pr`` effector consults before any real ``gh pr create`` fires
(capability env + consent grant + idempotency receipt).

Round-2 fix for Codex P1.1
--------------------------

Round-1 of this slice ran a lookup → invoke → write sequence that was
non-atomic; two concurrent run threads could both observe "no receipt"
and both invoke ``gh pr create``, producing duplicate PRs. SQLite
``database is locked`` errors were also silently treated as a miss,
which compounded the leak.

The fix is **atomic reservation**: a writer must call
:func:`try_reserve_receipt` BEFORE invoking the external side-effect.
The reservation uses ``INSERT … ON CONFLICT DO NOTHING`` so SQLite's
row-level lock makes the "is anyone else doing this right now?"
question answerable in one round-trip. The reservation lives in a
new ``status`` column with values:

* ``pending``    — reservation held; ``gh pr create`` is in flight.
* ``succeeded``  — receipt is final; future calls dedup-hit.
* ``failed``     — invocation failed; the row remains so the caller
                    can decide whether to retry under the same hint
                    or pick a new hint.

After the side-effect lands the writer calls
:func:`finalize_receipt` to update the row to ``succeeded`` with
final evidence. On failure the writer calls
:func:`release_reservation` so a retry can re-acquire the hint.

Stale ``pending`` reservations (writer died mid-flight, never
finalized) are auto-reclaimed by :func:`try_reserve_receipt` after
:data:`STALE_PENDING_THRESHOLD_SECONDS`. Default 600s (10 min) bounds
the worst-case "PR was created but receipt write crashed" window;
after that, any retry under the same hint can re-reserve and the
worst case is one duplicate PR (the prior PR exists because the
side-effect ran).

SQLite "database is locked" handling
------------------------------------

The connection sets ``busy_timeout=30000`` so SQLite blocks-and-retries
for up to 30 seconds before raising
:class:`sqlite3.OperationalError`. We never catch and silently swallow
that error class — it propagates to the effector, which surfaces a
structured ``error_kind="receipt_store_locked"`` evidence record
rather than firing a duplicate side-effect.

Schema (per-universe, file: ``${universe_dir}/.external_write_receipts.db``):

.. code-block:: sql

    CREATE TABLE IF NOT EXISTS external_write_receipts (
        idempotency_hint TEXT NOT NULL,
        sink             TEXT NOT NULL,
        evidence_json    TEXT NOT NULL DEFAULT '{}',
        run_id           TEXT NOT NULL,
        created_at       REAL NOT NULL,
        status           TEXT NOT NULL DEFAULT 'succeeded',
        PRIMARY KEY (idempotency_hint, sink)
    );

Migration safety: the ``status`` column was added in round-2. Existing
rows are upgraded with the default ``'succeeded'`` value during
:func:`initialize_receipts_db` so round-1 receipts continue to behave
as terminal-success rows.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

_DB_FILENAME = ".external_write_receipts.db"

# Receipt lifecycle states.
STATUS_PENDING = "pending"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

# After this many seconds a ``pending`` reservation is considered
# abandoned (the holding writer died mid-invocation without finalizing
# or releasing). Subsequent reservation attempts may steal it. The
# value is conservative — `gh pr create` typically settles in <10s,
# so 10min covers crashes/hangs without making concurrent retries wait
# forever on a phantom reservation.
STALE_PENDING_THRESHOLD_SECONDS = 600.0


def receipts_db_path(universe_dir: str | Path) -> Path:
    """Resolve the per-universe receipts DB path."""
    return Path(universe_dir) / _DB_FILENAME


def _connect(universe_dir: str | Path) -> sqlite3.Connection:
    """Open the receipts DB with WAL + 30s busy timeout (run-path-safe).

    Note: ``isolation_level=None`` deliberately NOT set. We use Python's
    implicit-transaction wrapper around every ``INSERT … ON CONFLICT``
    so the conflict-check + insert are atomic without needing explicit
    BEGIN IMMEDIATE/COMMIT. SQLite's row-level lock on the unique key
    serializes concurrent writers.
    """
    path = receipts_db_path(universe_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Base CREATE — never references columns added by later migrations so
# it stays compatible with round-1 DBs that pre-date the ``status``
# column. Migration steps run AFTER this base, in initialize_receipts_db.
_BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS external_write_receipts (
    idempotency_hint TEXT NOT NULL,
    sink             TEXT NOT NULL,
    evidence_json    TEXT NOT NULL DEFAULT '{}',
    run_id           TEXT NOT NULL,
    created_at       REAL NOT NULL,
    PRIMARY KEY (idempotency_hint, sink)
);

CREATE INDEX IF NOT EXISTS idx_receipts_sink_created
    ON external_write_receipts(sink, created_at DESC);
"""


def initialize_receipts_db(universe_dir: str | Path) -> Path:
    """Ensure the receipts DB exists and is migrated. Returns the DB path.

    Round-2 migration: probe for the ``status`` column and add it with
    a default of ``'succeeded'`` so round-1 receipts (which represent
    terminal-success rows) keep their semantics. The status-indexed
    secondary key is created only AFTER the column exists.
    """
    path = receipts_db_path(universe_dir)
    with _connect(universe_dir) as conn:
        conn.executescript(_BASE_SCHEMA)
        existing_cols = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(external_write_receipts)"
            )
        }
        if "status" not in existing_cols:
            # SQLite lacks ADD COLUMN IF NOT EXISTS.
            conn.execute(
                "ALTER TABLE external_write_receipts "
                "ADD COLUMN status TEXT NOT NULL DEFAULT 'succeeded'"
            )
        # Status-indexed key — safe to (re-)create after the column
        # exists; CREATE INDEX IF NOT EXISTS is a no-op on subsequent
        # initializations.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_receipts_status "
            "ON external_write_receipts(status, created_at)"
        )
        conn.commit()
    return path


def lookup_receipt(
    universe_dir: str | Path,
    *,
    idempotency_hint: str,
    sink: str,
) -> dict[str, Any] | None:
    """Return the receipt row for ``(idempotency_hint, sink)`` or None.

    Empty ``idempotency_hint`` returns ``None`` — the effector treats
    "no hint" as "always miss" so the caller can opt out of dedup by
    omitting the field.

    The returned dict now includes ``status`` so callers can distinguish
    succeeded (dedup-hit), pending (concurrent in-flight), and failed
    (retry-eligible) receipts.
    """
    if not idempotency_hint:
        return None
    initialize_receipts_db(universe_dir)
    with _connect(universe_dir) as conn:
        row = conn.execute(
            """
            SELECT idempotency_hint, sink, evidence_json, run_id,
                   created_at, status
              FROM external_write_receipts
             WHERE idempotency_hint = ? AND sink = ?
            """,
            (idempotency_hint, sink),
        ).fetchone()
    if row is None:
        return None
    try:
        evidence = json.loads(row["evidence_json"])
    except (TypeError, ValueError):
        evidence = {}
    return {
        "idempotency_hint": row["idempotency_hint"],
        "sink": row["sink"],
        "evidence": evidence,
        "run_id": row["run_id"],
        "created_at": row["created_at"],
        "status": row["status"],
    }


def try_reserve_receipt(
    universe_dir: str | Path,
    *,
    idempotency_hint: str,
    sink: str,
    run_id: str,
    now: float | None = None,
    stale_after_seconds: float = STALE_PENDING_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    """Atomically reserve a receipt slot for ``(idempotency_hint, sink)``.

    Returns one of:

    * ``{"status": "reserved", "row": <receipt>}`` — caller acquired
      a fresh pending row; proceed with the side-effect and call
      :func:`finalize_receipt` or :func:`release_reservation` next.

    * ``{"status": "reserved_after_stale", "row": <receipt>,
       "displaced_run_id": "<id>"}`` — caller reclaimed a stale
      pending reservation; proceed.

    * ``{"status": "duplicate", "row": <existing receipt>}`` — a
      terminal ``succeeded`` row already exists; caller should return
      the dedup-hit evidence WITHOUT invoking the side-effect.

    * ``{"status": "in_flight", "row": <existing pending receipt>}``
      — another writer holds a non-stale ``pending`` reservation;
      caller should dry-run with a ``concurrent_in_flight`` reason
      rather than fire a duplicate side-effect.

    * ``{"status": "failed_prior", "row": <existing failed receipt>}``
      — the prior attempt under this hint failed and was released to
      ``failed``. Round-2 contract: a fresh retry under the same hint
      MAY re-reserve. We delete the failed row and acquire a new
      pending slot. Returned status is ``"reserved"`` (or
      ``"reserved_after_failed"``) so the caller flow stays uniform.

    Empty ``idempotency_hint`` returns ``{"status": "no_hint"}`` —
    callers that opt out of dedup must not pretend they reserved.

    Raises :class:`sqlite3.OperationalError` on lock timeout; the caller
    must surface this loudly, NOT swallow it as a miss.
    """
    if not idempotency_hint:
        return {"status": "no_hint"}
    initialize_receipts_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        # Atomic INSERT … ON CONFLICT DO NOTHING. If we win the race,
        # ``changes()`` returns 1. If we lose, 0.
        conn.execute(
            """
            INSERT INTO external_write_receipts (
                idempotency_hint, sink, evidence_json, run_id,
                created_at, status
            ) VALUES (?, ?, '{}', ?, ?, ?)
            ON CONFLICT(idempotency_hint, sink) DO NOTHING
            """,
            (idempotency_hint, sink, run_id, ts, STATUS_PENDING),
        )
        rowcount = conn.total_changes
        conn.commit()
        if rowcount > 0:
            # Won the race — fresh reservation.
            row = conn.execute(
                "SELECT idempotency_hint, sink, evidence_json, run_id, "
                "       created_at, status "
                "FROM external_write_receipts "
                "WHERE idempotency_hint = ? AND sink = ?",
                (idempotency_hint, sink),
            ).fetchone()
            return {"status": "reserved", "row": _row_to_dict(row)}

        # Lost the race — read the existing row to decide what kind of
        # collision this is. The decision is made in a second
        # transaction so SQLite's row-lock semantics on the conflict
        # check above don't leak into the lookup.
        row = conn.execute(
            "SELECT idempotency_hint, sink, evidence_json, run_id, "
            "       created_at, status "
            "FROM external_write_receipts "
            "WHERE idempotency_hint = ? AND sink = ?",
            (idempotency_hint, sink),
        ).fetchone()
        if row is None:
            # Extremely unlikely: someone deleted the row between our
            # INSERT and the SELECT. Retry once.
            conn.execute(
                """
                INSERT INTO external_write_receipts (
                    idempotency_hint, sink, evidence_json, run_id,
                    created_at, status
                ) VALUES (?, ?, '{}', ?, ?, ?)
                ON CONFLICT(idempotency_hint, sink) DO NOTHING
                """,
                (idempotency_hint, sink, run_id, ts, STATUS_PENDING),
            )
            conn.commit()
            row = conn.execute(
                "SELECT idempotency_hint, sink, evidence_json, run_id, "
                "       created_at, status "
                "FROM external_write_receipts "
                "WHERE idempotency_hint = ? AND sink = ?",
                (idempotency_hint, sink),
            ).fetchone()
            if row is None:
                # Give up; surface as lock-class error so the caller
                # treats it as fail-loud, not miss.
                raise sqlite3.OperationalError(
                    "receipt row vanished mid-reservation; refusing to "
                    "treat as miss"
                )
            return {"status": "reserved", "row": _row_to_dict(row)}

        existing = _row_to_dict(row)
        status = existing.get("status")
        if status == STATUS_SUCCEEDED:
            return {"status": "duplicate", "row": existing}
        if status == STATUS_PENDING:
            age = ts - float(existing.get("created_at") or 0.0)
            if age < stale_after_seconds:
                return {"status": "in_flight", "row": existing}
            # Stale pending — reclaim atomically. UPDATE WHERE
            # status='pending' AND run_id=<old_id> ensures we don't
            # clobber a concurrent retry that already reclaimed.
            displaced = existing.get("run_id") or ""
            cur = conn.execute(
                """
                UPDATE external_write_receipts
                   SET run_id = ?, created_at = ?, status = ?,
                       evidence_json = '{}'
                 WHERE idempotency_hint = ? AND sink = ?
                   AND status = ?
                   AND run_id = ?
                """,
                (
                    run_id, ts, STATUS_PENDING,
                    idempotency_hint, sink,
                    STATUS_PENDING, displaced,
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                # Another concurrent retry won the reclaim. Re-read and
                # report the resulting state.
                row = conn.execute(
                    "SELECT idempotency_hint, sink, evidence_json, "
                    "       run_id, created_at, status "
                    "FROM external_write_receipts "
                    "WHERE idempotency_hint = ? AND sink = ?",
                    (idempotency_hint, sink),
                ).fetchone()
                if row is None:
                    raise sqlite3.OperationalError(
                        "stale-reclaim race resolved by row deletion; "
                        "refusing to treat as miss"
                    )
                reclaim_row = _row_to_dict(row)
                if reclaim_row.get("status") == STATUS_PENDING:
                    return {"status": "in_flight", "row": reclaim_row}
                if reclaim_row.get("status") == STATUS_SUCCEEDED:
                    return {"status": "duplicate", "row": reclaim_row}
                return {"status": "in_flight", "row": reclaim_row}
            row = conn.execute(
                "SELECT idempotency_hint, sink, evidence_json, run_id, "
                "       created_at, status "
                "FROM external_write_receipts "
                "WHERE idempotency_hint = ? AND sink = ?",
                (idempotency_hint, sink),
            ).fetchone()
            return {
                "status": "reserved_after_stale",
                "row": _row_to_dict(row),
                "displaced_run_id": displaced,
            }
        if status == STATUS_FAILED:
            # Failed-prior policy: a retry under the same hint replaces
            # the failed row with a fresh reservation. UPDATE WHERE
            # status='failed' so we don't clobber a concurrent retry
            # that already moved the row to pending.
            cur = conn.execute(
                """
                UPDATE external_write_receipts
                   SET run_id = ?, created_at = ?, status = ?,
                       evidence_json = '{}'
                 WHERE idempotency_hint = ? AND sink = ?
                   AND status = ?
                """,
                (
                    run_id, ts, STATUS_PENDING,
                    idempotency_hint, sink, STATUS_FAILED,
                ),
            )
            conn.commit()
            if cur.rowcount == 0:
                row = conn.execute(
                    "SELECT idempotency_hint, sink, evidence_json, "
                    "       run_id, created_at, status "
                    "FROM external_write_receipts "
                    "WHERE idempotency_hint = ? AND sink = ?",
                    (idempotency_hint, sink),
                ).fetchone()
                if row is None:
                    raise sqlite3.OperationalError(
                        "failed-row replace race resolved by deletion"
                    )
                replaced = _row_to_dict(row)
                # Re-classify by current status.
                if replaced.get("status") == STATUS_SUCCEEDED:
                    return {"status": "duplicate", "row": replaced}
                if replaced.get("status") == STATUS_PENDING:
                    return {"status": "in_flight", "row": replaced}
                return {"status": "in_flight", "row": replaced}
            row = conn.execute(
                "SELECT idempotency_hint, sink, evidence_json, run_id, "
                "       created_at, status "
                "FROM external_write_receipts "
                "WHERE idempotency_hint = ? AND sink = ?",
                (idempotency_hint, sink),
            ).fetchone()
            return {
                "status": "reserved_after_failed",
                "row": _row_to_dict(row),
            }
        # Unknown status — treat conservatively as in_flight so the
        # caller dry-runs rather than firing a duplicate side-effect.
        return {"status": "in_flight", "row": existing}


def finalize_receipt(
    universe_dir: str | Path,
    *,
    idempotency_hint: str,
    sink: str,
    evidence: dict[str, Any],
    run_id: str,
    status: str = STATUS_SUCCEEDED,
    now: float | None = None,
) -> bool:
    """Mark a reservation terminal with final evidence.

    Returns True when the row was updated (the caller held the
    reservation). Returns False when no row matched the caller's
    ``run_id`` — that means another writer raced past us and the
    caller should not overwrite their evidence. The caller's invocation
    already succeeded; the worst case is a slightly stale evidence
    record under the canonical key.

    ``status`` defaults to :data:`STATUS_SUCCEEDED`. Pass
    :data:`STATUS_FAILED` from a release path to mark the row as
    "tried and failed" without deleting it.

    Empty ``idempotency_hint`` is a silent no-op (matches
    :func:`record_receipt`'s semantics).

    Raises :class:`sqlite3.OperationalError` on lock timeout.
    """
    if not idempotency_hint:
        return False
    initialize_receipts_db(universe_dir)
    payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        cur = conn.execute(
            """
            UPDATE external_write_receipts
               SET evidence_json = ?,
                   run_id = ?,
                   created_at = ?,
                   status = ?
             WHERE idempotency_hint = ? AND sink = ?
               AND run_id = ?
            """,
            (payload, run_id, ts, status, idempotency_hint, sink, run_id),
        )
        conn.commit()
        return cur.rowcount > 0


def release_reservation(
    universe_dir: str | Path,
    *,
    idempotency_hint: str,
    sink: str,
    run_id: str,
    mark_failed: bool = True,
    now: float | None = None,
) -> bool:
    """Release a pending reservation after a side-effect failure.

    With ``mark_failed=True`` (the default) the row is set to
    :data:`STATUS_FAILED` so a future retry under the same hint can
    re-reserve via :func:`try_reserve_receipt`. With
    ``mark_failed=False`` the row is deleted entirely.

    Only releases if the row is still ``pending`` AND owned by the
    caller's ``run_id`` — concurrent reclaim is safe.

    Returns True when the row was released.
    """
    if not idempotency_hint:
        return False
    initialize_receipts_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        if mark_failed:
            cur = conn.execute(
                """
                UPDATE external_write_receipts
                   SET status = ?, created_at = ?
                 WHERE idempotency_hint = ? AND sink = ?
                   AND status = ? AND run_id = ?
                """,
                (
                    STATUS_FAILED, ts,
                    idempotency_hint, sink,
                    STATUS_PENDING, run_id,
                ),
            )
        else:
            cur = conn.execute(
                """
                DELETE FROM external_write_receipts
                 WHERE idempotency_hint = ? AND sink = ?
                   AND status = ? AND run_id = ?
                """,
                (
                    idempotency_hint, sink,
                    STATUS_PENDING, run_id,
                ),
            )
        conn.commit()
        return cur.rowcount > 0


def record_receipt(
    universe_dir: str | Path,
    *,
    idempotency_hint: str,
    sink: str,
    evidence: dict[str, Any],
    run_id: str,
    created_at: float | None = None,
    status: str = STATUS_SUCCEEDED,
) -> None:
    """Idempotently upsert a terminal receipt (legacy/test path).

    The round-1 callers used this as a single-step "record success"
    helper. Round-2 effector code prefers
    :func:`try_reserve_receipt` + :func:`finalize_receipt` because
    that pair is race-safe. This function remains for callers that
    KNOW they hold the only writer (tests, replays, host scripts) and
    just want to upsert a terminal row.

    Last-write-wins on the same key — an existing row is replaced
    regardless of its prior status. Use the reservation pair instead
    when concurrent writers may exist.

    Empty ``idempotency_hint`` is a silent no-op.
    """
    if not idempotency_hint:
        return
    initialize_receipts_db(universe_dir)
    payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    ts = created_at if created_at is not None else time.time()
    with _connect(universe_dir) as conn:
        conn.execute(
            """
            INSERT INTO external_write_receipts (
                idempotency_hint, sink, evidence_json, run_id,
                created_at, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(idempotency_hint, sink) DO UPDATE SET
                evidence_json = excluded.evidence_json,
                run_id        = excluded.run_id,
                created_at    = excluded.created_at,
                status        = excluded.status
            """,
            (idempotency_hint, sink, payload, run_id, ts, status),
        )
        conn.commit()


def delete_receipt(
    universe_dir: str | Path,
    *,
    idempotency_hint: str,
    sink: str,
) -> bool:
    """Remove the receipt for ``(idempotency_hint, sink)``. Returns True on hit.

    Used by tests and host scripts to clear a stale row. Production
    callers should prefer :func:`release_reservation` for pending
    rows so they don't accidentally clobber a concurrent reservation.
    """
    if not idempotency_hint:
        return False
    initialize_receipts_db(universe_dir)
    with _connect(universe_dir) as conn:
        cur = conn.execute(
            "DELETE FROM external_write_receipts "
            "WHERE idempotency_hint = ? AND sink = ?",
            (idempotency_hint, sink),
        )
        conn.commit()
        return cur.rowcount > 0


def list_receipts(
    universe_dir: str | Path,
    *,
    sink: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return receipts, most-recent first. Optional sink + status filter.

    Diagnostic surface for the chatbot and tests. Bounded by ``limit``.
    """
    initialize_receipts_db(universe_dir)
    limit = max(1, min(int(limit), 1000))
    clauses: list[str] = []
    params: list[Any] = []
    if sink:
        clauses.append("sink = ?")
        params.append(sink)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _connect(universe_dir) as conn:
        rows = conn.execute(
            f"""
            SELECT idempotency_hint, sink, evidence_json, run_id,
                   created_at, status
              FROM external_write_receipts
              {where}
          ORDER BY created_at DESC
             LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    try:
        evidence = json.loads(row["evidence_json"])
    except (TypeError, ValueError):
        evidence = {}
    return {
        "idempotency_hint": row["idempotency_hint"],
        "sink": row["sink"],
        "evidence": evidence,
        "run_id": row["run_id"],
        "created_at": row["created_at"],
        "status": row["status"] if "status" in row.keys() else STATUS_SUCCEEDED,
    }


__all__ = [
    "STATUS_PENDING",
    "STATUS_SUCCEEDED",
    "STATUS_FAILED",
    "STALE_PENDING_THRESHOLD_SECONDS",
    "receipts_db_path",
    "initialize_receipts_db",
    "lookup_receipt",
    "try_reserve_receipt",
    "finalize_receipt",
    "release_reservation",
    "record_receipt",
    "delete_receipt",
    "list_receipts",
]
