"""Tombstone-authorized exact file cleanup before account row erasure.

This is not a second deletion queue: existing operation inventory/debt survives
every failed physical step and existing maintenance can finish it independently.
"""

from pathlib import Path

from tinyassets import runs
from tinyassets.account_deletion import principal_digest
from tinyassets.run_file_cleanup import cleanup_file_operation
from tinyassets.scoped_reset import _assert_recovery_state_is_clean, acquire_maintenance_barrier
from tinyassets.storage import _connect as author_connection
from tinyassets.storage import run_files as store
from tinyassets.storage.run_file_lock import try_file_operation_lock


def _deleted(conn, owner):
    return (
        conn.execute(
            "SELECT 1 FROM deleted_principals WHERE founder_sub=?", (principal_digest(owner),)
        ).fetchone()
        is not None
    )


def _erase_operation(base, operation_id, owner):
    # An existing subset cleanup must finish before remaining siblings can be
    # revoked. At most two physical passes: existing subset, then full inventory.
    for _ in range(2):
        with try_file_operation_lock(base, operation_id=operation_id) as guard:
            if guard is None:
                raise store.FileCustodyRefused("file_erasure_pending")
            with author_connection(base) as author:
                author.execute("BEGIN IMMEDIATE")
                if not _deleted(author, owner):
                    raise store.FileCustodyRefused("file_erasure_requires_tombstone")
                with runs._connect(base) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    guard.require_held(conn)
                    row = conn.execute(
                        "SELECT * FROM run_file_operations WHERE operation_id=? AND owner_id=?",
                        (operation_id, owner),
                    ).fetchone()
                    if row is None or row["state"] == "released":
                        return
                    if row["state"] != "cleanup":
                        store.mark_cleanup_in_transaction(
                            conn,
                            operation_id=operation_id,
                            owner_id=owner,
                            universe_id=row["universe_id"],
                        )
        # Collector reacquires exclusion; no author or runs writer crosses IO.
        if not cleanup_file_operation(base, operation_id=operation_id):
            raise store.FileCustodyRefused("file_erasure_pending")
    with runs._connect(base) as conn:
        row = conn.execute(
            "SELECT state FROM run_file_operations WHERE operation_id=? AND owner_id=?",
            (operation_id, owner),
        ).fetchone()
        if row is not None and row[0] != "released":
            raise store.FileCustodyRefused("file_erasure_pending")


def erase_owner_files(base, *, owner_id):
    """Refuse row erasure until each independently owned operation is settled."""
    base = Path(base).absolute()
    if not runs.runs_db_path(base).is_file():
        return
    with acquire_maintenance_barrier(base, exclusive=False, timeout=5):
        _assert_recovery_state_is_clean(base)
        with runs._connect(base) as conn:
            if (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='run_file_operations' AND type='table'"
                ).fetchone()
                is None
            ):
                return
            operations = [
                row[0]
                for row in conn.execute(
                    "SELECT operation_id FROM run_file_operations WHERE owner_id=?",
                    (owner_id,),
                )
            ]
        for operation in operations:
            _erase_operation(base, operation, owner_id)


def reconcile_deleted_file_operation(base, operation_id):
    """Called within maintenance's shared reset barrier, without any DB writer."""
    with runs._connect(base) as conn:
        row = conn.execute(
            "SELECT owner_id FROM run_file_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
    if row is None:
        return False
    with author_connection(base) as conn:
        if not _deleted(conn, row[0]):
            return False
    _erase_operation(base, operation_id, row[0])
    return True


def settled_deletion_targets(conn, *, principal):
    """Same-transaction FK children/parents, independent of former home identity."""
    if (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='run_file_operations' AND type='table'"
        ).fetchone()
        is None
    ):
        return []
    unsettled = conn.execute(
        "SELECT 1 FROM run_file_operations o LEFT JOIN run_file_allocations a USING(operation_id) "
        "WHERE o.owner_id=? AND (o.state!='released' OR a.state IS NULL OR a.state!='released' "
        "OR a.amount!=0 OR EXISTS(SELECT 1 FROM run_file_cleanup c "
        "WHERE c.operation_id=o.operation_id) OR EXISTS(SELECT 1 FROM run_file_objects f "
        "WHERE f.operation_id=o.operation_id AND f.state!='released')) LIMIT 1",
        (principal,),
    ).fetchone()
    if unsettled:
        raise store.FileCustodyRefused("file_erasure_pending")
    operations = "SELECT operation_id FROM run_file_operations WHERE owner_id=?"
    files = "SELECT file_id FROM run_file_objects WHERE owner_id=?"
    return [
        ("run_file_bindings", f"file_id IN ({files})", (principal,)),
        ("run_file_objects", "owner_id=?", (principal,)),
        ("run_file_allocations", f"operation_id IN ({operations})", (principal,)),
        ("run_file_cleanup", f"operation_id IN ({operations})", (principal,)),
        ("run_file_operations", "owner_id=?", (principal,)),
    ]
