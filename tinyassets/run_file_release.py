"""Owner-authorized per-file revocation, followed by exact physical cleanup."""

import logging
from pathlib import Path

from tinyassets import runs
from tinyassets.run_file_capture import _authority
from tinyassets.run_file_cleanup import cleanup_file_operation
from tinyassets.scoped_reset import _assert_recovery_state_is_clean, acquire_maintenance_barrier
from tinyassets.storage import run_files as store
from tinyassets.storage.run_file_lock import try_file_operation_lock

logger = logging.getLogger(__name__)


def _owned(conn, owner, universe, file_id):
    row = conn.execute(
        "SELECT o.*,p.state AS operation_state FROM run_file_objects o "
        "JOIN run_file_operations p USING(operation_id) "
        "WHERE o.file_id=? AND o.owner_id=? AND o.universe_id=?",
        (file_id, owner, universe),
    ).fetchone()
    if row is None:
        raise store.FileCustodyRefused("run_file_not_found")
    return row


def release_owned_file(base, *, owner_id, universe_id, file_id):
    """No sibling release; active bindings refuse and cleanup debt stays visible."""
    if any(type(x) is not str or not x for x in (owner_id, universe_id, file_id)):
        raise store.FileCustodyRefused("file_release_request_invalid")
    base = Path(base).absolute()
    with acquire_maintenance_barrier(base, exclusive=False, timeout=5):
        _assert_recovery_state_is_clean(base)
        with _authority(base, owner_id, universe_id):
            with runs._connect(base) as conn:
                operation_id = _owned(conn, owner_id, universe_id, file_id)["operation_id"]
        with try_file_operation_lock(base, operation_id=operation_id) as guard:
            if guard is None:
                raise store.FileCustodyRefused("file_operation_busy")
            with _authority(base, owner_id, universe_id, write=True):
                with runs._connect(base) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    guard.require_held(conn)
                    row = _owned(conn, owner_id, universe_id, file_id)
                    if row["operation_id"] != operation_id:
                        raise store.FileCustodyRefused("file_release_reference_changed")
                    if row["state"] == "released" and row["operation_state"] != "cleanup":
                        return {"file_id": file_id, "state": "released"}
                    if row["state"] == "ready":
                        # Bindings and ready-state change serialize on this same
                        # runs writer. A new admission cannot race this decision.
                        has_runs = conn.execute(
                            "SELECT 1 FROM sqlite_master WHERE name='runs' AND type='table'"
                        ).fetchone()
                        if (
                            has_runs
                            and conn.execute(
                                "SELECT 1 FROM run_file_bindings b JOIN runs r USING(run_id) "
                            "WHERE b.file_id=? "
                            "AND r.status IN ('queued','running','resumed') LIMIT 1",
                                (file_id,),
                            ).fetchone()
                        ):
                            raise store.FileCustodyRefused("run_file_in_active_use")
                        store.mark_cleanup_in_transaction(
                            conn,
                            operation_id=operation_id,
                            owner_id=owner_id,
                            universe_id=universe_id,
                            file_ids=[file_id],
                        )
        # Collector reacquires the same operation guard, never the physical root
        # while metadata locks are held. Another release sees explicit debt.
        try:
            cleaned = cleanup_file_operation(base, operation_id=operation_id)
        except Exception:
            logger.exception("Run-file release cleanup remains pending: %s", operation_id)
            cleaned = False
        return {"file_id": file_id, "state": "released" if cleaned else "cleanup_pending"}
