"""Bounded owner/run-bound export. No public route or node authority inferred.

Public adapters supply authenticated identity. Sandbox adapters additionally
prove current running placement and declared incoming reference membership.
This service grants neither from a caller-authored run/file identifier.
"""

import base64
import logging
import uuid
from pathlib import Path

from tinyassets import runs, workspace_pool
from tinyassets.execution_authority.blob_proof import BlobRef
from tinyassets.execution_authority.blob_stream import CHUNK_BYTES
from tinyassets.run_file_capture import _authority, _physical_store
from tinyassets.run_file_contract import public_reference
from tinyassets.scoped_reset import _assert_recovery_state_is_clean, acquire_maintenance_barrier
from tinyassets.storage import run_files as store
from tinyassets.storage.run_file_lock import try_file_operation_lock

logger = logging.getLogger(__name__)


def _owned_row(base, owner, universe, run_id, file_id):
    with _authority(base, owner, universe):
        with runs._connect(base) as conn:
            conn.execute("BEGIN")
            row = store.bound_file_in_transaction(
                conn, run_id=run_id, owner_id=owner, universe_id=universe, file_id=file_id
            )
            operation = store.visible_operation_in_transaction(conn, row)
            row["physical_root_id"] = operation["physical_root_id"]
            return row


def read_bound_file(
    base, *, owner_id, universe_id, run_id, file_id, offset, count, should_cancel=None
):
    """Return one exact base64 chunk; no path or unbound custody read is exposed."""
    if (
        any(type(x) is not str or not x for x in (owner_id, universe_id, run_id, file_id))
        or type(offset) is not int
        or offset < 0
        or type(count) is not int
        or not 0 <= count <= CHUNK_BYTES
    ):
        raise store.FileCustodyRefused("file_read_request_invalid")
    base = Path(base).absolute()
    with acquire_maintenance_barrier(base, exclusive=False, timeout=5):
        _assert_recovery_state_is_clean(base)
        initial = _owned_row(base, owner_id, universe_id, run_id, file_id)
        with try_file_operation_lock(base, operation_id=initial["operation_id"]) as guard:
            if guard is None:
                raise store.FileCustodyRefused("file_operation_busy")
            row = _owned_row(base, owner_id, universe_id, run_id, file_id)
            if row != initial or offset > row["size_bytes"]:
                raise store.FileCustodyRefused("file_read_reference_changed")
            reference = public_reference(row)
            _, blobs = _physical_store(base, create=False)
            if ":".join(str(part) for part in blobs.root_identity) != row["physical_root_id"]:
                raise store.FileCustodyRefused("run_file_root_changed")
            maximum = min(count, row["size_bytes"] - offset)
            transfer = "file:read:" + uuid.uuid4().hex
            workspace_pool.reserve_transfer_bytes(
                runs.runs_db_path(base),
                universe_id=universe_id,
                run_id=run_id,
                operation_id=transfer,
                max_bytes=maximum,
            )
            consumed = None  # Unmeasured failed read keeps the bounded reservation.

            def cancelled():
                current = _owned_row(base, owner_id, universe_id, run_id, file_id)
                if current != row:
                    raise store.FileCustodyRefused("file_read_reference_changed")
                return should_cancel is not None and should_cancel()

            try:
                body = BlobRef(row["storage_key"] + ".body", row["sha256"], row["size_bytes"])
                with blobs.open_held_stream(body, should_cancel=cancelled) as held:
                    chunk = held.read_range(offset, count)
                    consumed = len(chunk)
                if cancelled():
                    raise store.FileCustodyRefused("file_read_cancelled")
                return {
                    "reference": reference,
                    "bytes_base64": base64.b64encode(chunk).decode("ascii"),
                    "offset": offset,
                    "next_offset": offset + len(chunk),
                    "eof": offset + len(chunk) == row["size_bytes"],
                }
            finally:
                if consumed is not None:
                    try:
                        workspace_pool.reconcile_operation_bytes(
                            runs.runs_db_path(base), transfer, consumed
                        )
                    except Exception:
                        logger.exception("Run-file read settlement debt: %s", transfer)
