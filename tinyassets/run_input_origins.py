"""Static admitted-origin dispatch for initial calls and restart nomination.

No registry is writable by workflows. The existing executor, run guard and
start CAS remain the only execution path; the scan is not another work queue.
"""

import logging
from pathlib import Path

from tinyassets import runs
from tinyassets.run_input_origin import OriginHeld, decode_origin

logger = logging.getLogger(__name__)


def _adapter(envelope):
    decode_origin(envelope)
    try:
        if envelope["origin_kind"] == "direct":
            from tinyassets.run_input_direct import prepare_admitted_direct

            return prepare_admitted_direct, None
        if envelope["origin_kind"] == "canonical_consumer":
            from tinyassets.consumer_runtime import (
                prepare_admitted_consumer,
                settle_admitted_consumer,
            )

            return prepare_admitted_consumer, settle_admitted_consumer
    except ImportError as exc:
        raise OriginHeld("run_input_origin_unavailable") from exc
    raise OriginHeld("run_input_origin_unknown")


def _correlation(conn, envelope):
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_run_admissions'"
    ).fetchone()
    row = (conn.execute("SELECT * FROM conversation_run_admissions WHERE run_id=?",
                        (envelope["run_id"],)).fetchone() if exists else None)
    if envelope["origin_kind"] == "direct" and row is not None:
        raise OriginHeld("run_input_origin_correlation_conflict")
    if envelope["origin_kind"] == "canonical_consumer" and row is None:
        raise OriginHeld("run_input_origin_correlation_missing")
    # Consumer's static preparer owns the exact correlation/source-context
    # comparison. Do not invent a second interpretation of its schema here.


def _prepare(base, envelope, *, author_conn, runs_conn):
    adapter, _ = _adapter(envelope)
    _correlation(runs_conn, envelope)
    return adapter(base, envelope, author_conn=author_conn, runs_conn=runs_conn)


def _settled(base, run_id):
    with runs._connect(base) as conn:
        row = conn.execute(
            "SELECT * FROM run_input_admissions WHERE run_id=?", (run_id,),
        ).fetchone()
    if row is None:
        return
    _, observer = _adapter(dict(row))
    if observer is not None:
        observer(base, run_id)


def dispatch_initial_run(base, *, run_id):
    """Only dispatch entry for known-origin intake, same-key replay and recovery."""
    from tinyassets.run_input_runtime import dispatch_admitted_run

    with runs._connect(base) as conn:
        row = conn.execute(
            "SELECT * FROM run_input_admissions WHERE run_id=?", (run_id,),
        ).fetchone()
    if row is None:
        raise OriginHeld("run_input_origin_missing")
    _adapter(dict(row))  # Legacy/unknown/partial runtime refuses before submission.
    return dispatch_admitted_run(base, run_id=run_id, prepare=_prepare, on_settled=_settled)


def reconcile_admitted_runs(base, *, after_run_id="", limit=32):
    """Bounded separate admission scan, including runs with no file operation."""
    from tinyassets.scoped_reset import _assert_recovery_state_is_clean, acquire_maintenance_barrier

    if type(after_run_id) is not str or type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError("invalid admitted run scan")
    base = Path(base).absolute()
    if not runs.runs_db_path(base).is_file():
        return ""
    with acquire_maintenance_barrier(base, exclusive=False, timeout=5):
        _assert_recovery_state_is_clean(base)
        with runs._connect(base) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(run_input_admissions)")}
            if not {"origin_kind", "origin_version", "origin_options_json"} <= columns:
                return ""  # Normal schema initialization upgrades; scans never guess.
            ids = [row[0] for row in conn.execute(
                "SELECT a.run_id FROM run_input_admissions a JOIN runs r ON r.run_id=a.run_id "
                "WHERE a.run_id>? AND a.origin_kind IN ('direct','canonical_consumer') "
                "AND a.origin_version=1 AND a.execution_started_at IS NULL "
                "AND a.claim_token IS NULL AND r.status='queued' ORDER BY a.run_id LIMIT ?",
                (after_run_id, limit),
            )]
        for run_id in ids:
            try:
                dispatch_initial_run(base, run_id=run_id)
            except Exception:
                logger.exception("Admitted initial dispatch remains held: %s", run_id)
        return ids[-1] if len(ids) == limit else ""
