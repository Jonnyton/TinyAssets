"""Exact physical settlement for already-revoked file-operation cleanup debt.

Internal maintenance primitive, not owner-release authorization or a TTL sweep.
Tombstoning/retention/release policy must first create the durable cleanup row.
This never erases a ready object, recursively scans, or guesses a missing path.
"""

import json
import os
import re
from pathlib import Path

from tinyassets import runs
from tinyassets.run_file_capture import _physical_store
from tinyassets.scoped_reset import _assert_recovery_state_is_clean, acquire_maintenance_barrier
from tinyassets.storage import run_files as store
from tinyassets.storage.run_file_lock import try_file_operation_lock


def cleanup_file_operation(base, *, operation_id):
    """Return False on live operation ownership; never wait while holding SQL."""
    base = Path(base).absolute()
    with acquire_maintenance_barrier(base, exclusive=False, timeout=5):
        _assert_recovery_state_is_clean(base)
        with try_file_operation_lock(base, operation_id=operation_id) as guard:
            if guard is None:
                return False
            with runs._connect(base) as conn:
                conn.execute("BEGIN")
                guard.require_held(conn)
                row = conn.execute(
                    "SELECT * FROM run_file_operations WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if row is None:
                    raise store.FileCustodyRefused("file_cleanup_not_found")
                if row["state"] == "released":
                    return True
                debt = conn.execute(
                    "SELECT inventory_json FROM run_file_cleanup WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if row["state"] != "cleanup" or debt is None:
                    raise store.FileCustodyRefused("file_cleanup_not_started")
                inventory = json.loads(debt[0])
                if (
                    not isinstance(inventory, list)
                    or any(
                        type(key) is not str or re.fullmatch(r"[0-9a-f]{32}", key) is None
                        for key in inventory
                    )
                    or len(set(inventory)) != len(inventory)
                ):
                    raise store.FileCustodyRefused("file_cleanup_inventory_invalid")
                original = json.loads(row["inventory_json"])
                if not isinstance(original, list) or not set(inventory) <= set(original):
                    raise store.FileCustodyRefused("file_cleanup_inventory_invalid")
                ready = {
                    item[0]
                    for item in conn.execute(
                        "SELECT storage_key FROM run_file_objects "
                        "WHERE operation_id=? AND state='ready'",
                        (operation_id,),
                    )
                }
                if ready & set(inventory):
                    raise store.FileCustodyRefused("file_cleanup_has_ready_objects")
                owned = dict(row)
                debt_json = debt[0]
            # No metadata transaction exists inside the physical coordinator.
            _, blobs = _physical_store(base, create=False)
            if ":".join(str(part) for part in blobs.root_identity) != owned["physical_root_id"]:
                raise store.FileCustodyRefused("run_file_root_changed")
            with blobs.coordinated():
                for key in inventory:
                    for suffix in (".part", ".body"):
                        with blobs._secure_parent(key + suffix, create_parents=False) as (
                            parent,
                            leaf,
                            _,
                        ):
                            parent.ensure_stable()
                            if parent.stat_leaf(leaf) is not None:
                                parent.unlink_leaf(leaf)
                            parent.ensure_stable()
                            if parent.stat_leaf(leaf) is not None:
                                raise store.FileCustodyRefused("file_cleanup_incomplete")
                            if parent.parent_fd is not None:
                                os.fsync(parent.parent_fd)
            with runs._connect(base) as conn:
                conn.execute("BEGIN IMMEDIATE")
                guard.require_held(conn)
                current = store._owned_operation(
                    conn, operation_id, owned["owner_id"], owned["universe_id"]
                )
                if (
                    current["state"] != "cleanup"
                    or current["inventory_json"] != owned["inventory_json"]
                    or current["physical_root_id"] != owned["physical_root_id"]
                ):
                    raise store.FileCustodyRefused("file_cleanup_changed")
                current_debt = conn.execute(
                    "SELECT inventory_json FROM run_file_cleanup WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if current_debt is None or current_debt[0] != debt_json:
                    raise store.FileCustodyRefused("file_cleanup_changed")
                store.finish_cleanup_in_transaction(
                    conn,
                    operation_id=operation_id,
                    owner_id=owned["owner_id"],
                    universe_id=owned["universe_id"],
                )
            return True
