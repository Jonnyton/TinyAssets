"""Internal immutable-file custody transactions in the existing runs store.

Not an authentication, filesystem, deletion or public intake API. The service
must hold current owner authority and the operation's interprocess exclusion.
It inventories names before writing, publishes verified bodies without DB locks,
then commits visibility here under the author-store fence. No runtime adapter is
enabled by importing this module. Physical cleanup callers must prove deletion
before releasing allocations; transport settlement is separate and never zeroed
by these retained-storage transitions.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass

_MAX_INT = 2**63 - 1
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[0-9a-f]{32}\Z")
UNBOUND_LIFETIME_SECONDS = 3600

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS run_file_operations (
        operation_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL, universe_id TEXT NOT NULL,
        request_sha256 TEXT NOT NULL, max_bytes INTEGER NOT NULL CHECK(max_bytes >= 0),
        physical_root_id TEXT NOT NULL,
        created_at REAL NOT NULL DEFAULT 0,
        unbound_expires_at REAL NOT NULL DEFAULT 0,
        state TEXT NOT NULL CHECK(state IN ('pending','committed','cleanup','released')),
        inventory_json TEXT NOT NULL DEFAULT '[]',
        result_json TEXT NOT NULL DEFAULT '[]'
    )""",
    """CREATE TABLE IF NOT EXISTS run_file_allocations (
        operation_id TEXT PRIMARY KEY REFERENCES run_file_operations(operation_id),
        amount INTEGER NOT NULL CHECK(amount >= 0),
        state TEXT NOT NULL CHECK(state IN ('pending','retained','releasing','released'))
    )""",
    """CREATE TABLE IF NOT EXISTS run_file_objects (
        file_id TEXT PRIMARY KEY,
        operation_id TEXT NOT NULL REFERENCES run_file_operations(operation_id),
        owner_id TEXT NOT NULL, universe_id TEXT NOT NULL,
        storage_key TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        filename TEXT NOT NULL, media_type TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('ready','released'))
    )""",
    """CREATE TABLE IF NOT EXISTS run_file_bindings (
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        field_name TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
        file_id TEXT NOT NULL REFERENCES run_file_objects(file_id),
        PRIMARY KEY(run_id, field_name, ordinal)
    )""",
    """CREATE TABLE IF NOT EXISTS run_file_cleanup (
        operation_id TEXT PRIMARY KEY REFERENCES run_file_operations(operation_id),
        inventory_json TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS run_file_owner ON run_file_objects(owner_id, universe_id)",
)


class FileCustodyRefused(ValueError):
    """Stable refusal at the internal custody boundary."""


def _integer(value, *, positive=False):
    if type(value) is not int or not (int(positive) <= value <= _MAX_INT):
        raise FileCustodyRefused("file_capacity_invalid")
    return value


def _name(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise FileCustodyRefused("file_scope_invalid")
    return value


def capacity_limit() -> int:
    """Operational subsystem ceiling; never infer an entitlement from a tier."""
    raw = os.environ.get("TINYASSETS_RUN_FILE_CUSTODY_MAX_BYTES", "").strip()
    if not raw:
        raise FileCustodyRefused("file_custody_not_configured")
    if not raw.isascii() or not raw.isdecimal():
        raise FileCustodyRefused("file_capacity_invalid")
    try:
        return _integer(int(raw), positive=True)
    except ValueError as exc:
        raise FileCustodyRefused("file_capacity_invalid") from exc


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Additive schema only; execute never commits the caller's transaction."""
    for statement in _SCHEMA:
        conn.execute(statement)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(run_file_operations)")}
    for name in ("created_at", "unbound_expires_at"):
        if name not in columns:
            # Unknown legacy age is not permission to delete previously held data.
            conn.execute(
                f"ALTER TABLE run_file_operations ADD COLUMN {name} REAL NOT NULL DEFAULT 0"
            )


def _transaction(conn):
    if not conn.in_transaction:
        raise ValueError("file custody requires a caller-owned transaction")


def _owned_operation(conn, operation_id, owner_id, universe_id):
    _transaction(conn)
    row = conn.execute(
        "SELECT * FROM run_file_operations WHERE operation_id=? AND owner_id=? AND universe_id=?",
        (operation_id, owner_id, universe_id),
    ).fetchone()
    if row is None:
        raise FileCustodyRefused("run_file_not_found")
    return row


def reserve_in_transaction(
    conn,
    *,
    operation_id,
    owner_id,
    universe_id,
    request_sha256,
    max_bytes,
    physical_root_id,
    ceiling_bytes,
    free_bytes,
    headroom_bytes,
):
    """Reserve one copy's temp/final allocation; rename does not double it.

    Free bytes must be a fresh measurement of the already verified physical
    destination supplied by the trusted service, never request payload telemetry.
    This transaction serializes this subsystem, not unrelated host disk writers.
    """
    _transaction(conn)
    for value in (operation_id, owner_id, universe_id, physical_root_id):
        _name(value)
    if not isinstance(request_sha256, str) or not _SHA.fullmatch(request_sha256):
        raise FileCustodyRefused("file_request_digest_invalid")
    _integer(max_bytes)
    _integer(ceiling_bytes, positive=True)
    _integer(free_bytes)
    _integer(headroom_bytes)
    prior = conn.execute(
        "SELECT * FROM run_file_operations WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if prior is not None:
        expected = (owner_id, universe_id, request_sha256, max_bytes, physical_root_id)
        observed = tuple(
            prior[key]
            for key in (
                "owner_id",
                "universe_id",
                "request_sha256",
                "max_bytes",
                "physical_root_id",
            )
        )
        if observed != expected:
            raise FileCustodyRefused("file_operation_conflict")
        if prior["state"] in {"cleanup", "released"}:
            raise FileCustodyRefused("file_operation_cleanup")
        return dict(prior)
    allocated = conn.execute("SELECT COALESCE(SUM(amount),0) FROM run_file_allocations").fetchone()[
        0
    ]
    pending = conn.execute(
        "SELECT COALESCE(SUM(a.amount),0) FROM run_file_allocations a "
        "JOIN run_file_operations o USING(operation_id) "
        "WHERE o.physical_root_id=? AND a.state IN ('pending','releasing')",
        (physical_root_id,),
    ).fetchone()[0]
    if allocated + max_bytes > ceiling_bytes:
        raise FileCustodyRefused("file_custody_capacity_exhausted")
    if free_bytes - pending - headroom_bytes < max_bytes:
        raise FileCustodyRefused("file_physical_capacity_exhausted")
    now = time.time()
    conn.execute(
        "INSERT INTO run_file_operations(operation_id,owner_id,universe_id,request_sha256,"
        "max_bytes,physical_root_id,created_at,unbound_expires_at,state) "
        "VALUES(?,?,?,?,?,?,?,?,'pending')",
        (
            operation_id,
            owner_id,
            universe_id,
            request_sha256,
            max_bytes,
            physical_root_id,
            now,
            now + UNBOUND_LIFETIME_SECONDS,
        ),
    )
    conn.execute(
        "INSERT INTO run_file_allocations VALUES(?,?,'pending')", (operation_id, max_bytes)
    )
    return dict(_owned_operation(conn, operation_id, owner_id, universe_id))


def inventory_in_transaction(conn, *, operation_id, owner_id, universe_id, storage_keys):
    """Journal exact server-generated names BEFORE physical staging begins."""
    row = _owned_operation(conn, operation_id, owner_id, universe_id)
    if row["state"] != "pending":
        raise FileCustodyRefused("file_operation_not_pending")
    if not isinstance(storage_keys, list) or len(storage_keys) != len(set(storage_keys)):
        raise FileCustodyRefused("file_inventory_invalid")
    if any(not isinstance(key, str) or not _ID.fullmatch(key) for key in storage_keys):
        raise FileCustodyRefused("file_inventory_invalid")
    encoded = json.dumps(storage_keys)
    if row["inventory_json"] != "[]" and row["inventory_json"] != encoded:
        raise FileCustodyRefused("file_operation_conflict")
    conn.execute(
        "UPDATE run_file_operations SET inventory_json=? WHERE operation_id=?",
        (encoded, operation_id),
    )


@dataclass(frozen=True)
class CapturedFile:
    file_id: str
    filename: str
    media_type: str
    size_bytes: int
    sha256: str

    def __post_init__(self):
        if not isinstance(self.file_id, str) or not _ID.fullmatch(self.file_id):
            raise FileCustodyRefused("file_id_invalid")
        if not isinstance(self.sha256, str) or not _SHA.fullmatch(self.sha256):
            raise FileCustodyRefused("file_digest_invalid")
        _integer(self.size_bytes)
        if not isinstance(self.filename, str) or not isinstance(self.media_type, str):
            raise FileCustodyRefused("file_metadata_invalid")

    @classmethod
    def new(cls, *, filename, media_type, size_bytes, sha256):
        return cls(uuid.uuid4().hex, filename, media_type, size_bytes, sha256)


def commit_objects_in_transaction(conn, *, operation_id, owner_id, universe_id, objects):
    """Commit visibility only AFTER held-operation verified body publication.

    Internal metadata seam, not a function that itself writes/verifies bytes.
    Bundle validation precedes every insert, including errors caught by callers.
    """
    row = _owned_operation(conn, operation_id, owner_id, universe_id)
    if (
        not isinstance(objects, list)
        or not objects
        or any(not isinstance(item, CapturedFile) for item in objects)
    ):
        raise FileCustodyRefused("file_bundle_invalid")
    ids = [item.file_id for item in objects]
    if len(set(ids)) != len(ids):
        raise FileCustodyRefused("file_bundle_invalid")
    encoded = json.dumps([asdict(item) for item in objects], sort_keys=True, ensure_ascii=False)
    if row["state"] == "committed":
        if encoded != row["result_json"]:
            raise FileCustodyRefused("file_operation_conflict")
        return ids
    if row["state"] != "pending":
        raise FileCustodyRefused("file_operation_cleanup")
    total = sum(item.size_bytes for item in objects)
    if total > row["max_bytes"]:
        raise FileCustodyRefused("file_bundle_limit_exceeded")
    if json.loads(row["inventory_json"]) != ids:
        raise FileCustodyRefused("file_inventory_mismatch")
    if any(
        conn.execute("SELECT 1 FROM run_file_objects WHERE file_id=?", (file_id,)).fetchone()
        for file_id in ids
    ):
        raise FileCustodyRefused("file_operation_conflict")
    conn.executemany(
        "INSERT INTO run_file_objects VALUES(?,?,?,?,?,?,?,?,?,'ready')",
        [
            (
                item.file_id,
                operation_id,
                owner_id,
                universe_id,
                item.file_id,
                item.sha256,
                item.size_bytes,
                item.filename,
                item.media_type,
            )
            for item in objects
        ],
    )
    conn.execute(
        "UPDATE run_file_operations SET state='committed',result_json=?,unbound_expires_at=? "
        "WHERE operation_id=?",
        (encoded, time.time() + UNBOUND_LIFETIME_SECONDS, operation_id),
    )
    conn.execute(
        "UPDATE run_file_allocations SET state='retained',amount=? WHERE operation_id=?",
        (total, operation_id),
    )
    return ids


def _owned_run(conn, run_id, owner_id, universe_id):
    _transaction(conn)
    if (
        not owner_id
        or not universe_id
        or conn.execute(
            "SELECT 1 FROM runs WHERE run_id=? AND owner_user_id=? AND queue_universe_id=?",
            (run_id, owner_id, universe_id),
        ).fetchone()
        is None
    ):
        raise FileCustodyRefused("run_file_not_found")


def bind_in_transaction(conn, *, run_id, owner_id, universe_id, field_name, file_ids):
    """Bind only after service-side manifest/dataflow and execution admission."""
    _owned_run(conn, run_id, owner_id, universe_id)
    _name(field_name)
    if not isinstance(file_ids, list) or not file_ids:
        raise FileCustodyRefused("file_bundle_invalid")
    for file_id in file_ids:
        row = conn.execute(
            "SELECT o.* FROM run_file_objects o JOIN run_file_operations p USING(operation_id) "
            "WHERE o.file_id=? AND o.owner_id=? AND o.universe_id=? AND o.state='ready' "
            "AND (p.unbound_expires_at>? OR EXISTS "
            "(SELECT 1 FROM run_file_bindings b WHERE b.file_id=o.file_id))",
            (file_id, owner_id, universe_id, time.time()),
        ).fetchone()
        if row is None:
            raise FileCustodyRefused("run_file_not_found")
        visible_operation_in_transaction(conn, row)
    existing = [
        row[0]
        for row in conn.execute(
            "SELECT file_id FROM run_file_bindings WHERE run_id=? AND field_name=? "
            "ORDER BY ordinal",
            (run_id, field_name),
        )
    ]
    if existing:
        if existing != file_ids:
            raise FileCustodyRefused("file_binding_conflict")
        return
    conn.executemany(
        "INSERT INTO run_file_bindings VALUES(?,?,?,?)",
        [(run_id, field_name, index, file_id) for index, file_id in enumerate(file_ids)],
    )


def bound_file_in_transaction(conn, *, run_id, owner_id, universe_id, file_id):
    """Private storage row; service must not return its storage key to clients."""
    _owned_run(conn, run_id, owner_id, universe_id)
    row = conn.execute(
        "SELECT o.* FROM run_file_objects o JOIN run_file_bindings b USING(file_id) "
        "WHERE b.run_id=? AND o.file_id=? AND o.owner_id=? AND o.universe_id=? AND o.state='ready'",
        (run_id, file_id, owner_id, universe_id),
    ).fetchone()
    if row is None:
        raise FileCustodyRefused("run_file_not_found")
    visible_operation_in_transaction(conn, row)
    return dict(row)


def visible_operation_in_transaction(conn, row):
    """A sibling's cleanup debt never grants or revokes this object's visibility."""
    operation = _owned_operation(conn, row["operation_id"], row["owner_id"], row["universe_id"])
    if row["state"] != "ready" or operation["state"] not in {"committed", "cleanup"}:
        raise FileCustodyRefused("run_file_not_found")
    if operation["state"] == "cleanup":
        debt = conn.execute(
            "SELECT inventory_json FROM run_file_cleanup WHERE operation_id=?",
            (row["operation_id"],),
        ).fetchone()
        try:
            selected = json.loads(debt[0]) if debt is not None else None
            original = json.loads(operation["inventory_json"])
            valid = (
                isinstance(selected, list)
                and isinstance(original, list)
                and all(type(key) is str and _ID.fullmatch(key) for key in selected + original)
                and len(set(selected)) == len(selected)
                and len(set(original)) == len(original)
                and set(selected) <= set(original)
                and row["storage_key"] in original
                and row["storage_key"] not in selected
            )
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise FileCustodyRefused("run_file_not_found")
    return operation


def mark_cleanup_in_transaction(conn, *, operation_id, owner_id, universe_id, file_ids=None):
    """Revoke visibility, retain inventory/debt; caller checks active-run release policy."""
    row = _owned_operation(conn, operation_id, owner_id, universe_id)
    if row["state"] == "released":
        return
    inventory = json.loads(row["inventory_json"])
    if file_ids is None:
        selected = inventory
    else:
        if (
            not isinstance(file_ids, list)
            or not file_ids
            or any(type(value) is not str for value in file_ids)
            or len(set(file_ids)) != len(file_ids)
        ):
            raise FileCustodyRefused("file_cleanup_inventory_invalid")
        owned_ids = {
            item[0]
            for item in conn.execute(
                "SELECT file_id FROM run_file_objects "
                "WHERE operation_id=? AND owner_id=? AND universe_id=?",
                (operation_id, owner_id, universe_id),
            )
        }
        if not set(file_ids) <= owned_ids or not set(file_ids) <= set(inventory):
            raise FileCustodyRefused("run_file_not_found")
        selected = [key for key in inventory if key in file_ids]
    encoded = json.dumps(selected)
    if row["state"] == "cleanup":
        debt = conn.execute(
            "SELECT inventory_json FROM run_file_cleanup WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if debt is None or debt[0] != encoded:
            raise FileCustodyRefused("file_cleanup_pending")
        return
    conn.executemany(
        "UPDATE run_file_objects SET state='released' WHERE operation_id=? AND file_id=?",
        [(operation_id, key) for key in selected],
    )
    conn.execute(
        "UPDATE run_file_operations SET state='cleanup' WHERE operation_id=?", (operation_id,)
    )
    conn.execute(
        "UPDATE run_file_allocations SET state='releasing' WHERE operation_id=?", (operation_id,)
    )
    conn.execute("INSERT INTO run_file_cleanup VALUES(?,?)", (operation_id, encoded))


def finish_cleanup_in_transaction(conn, *, operation_id, owner_id, universe_id):
    """Internal collector settlement AFTER held-operation physical deletion proof."""
    row = _owned_operation(conn, operation_id, owner_id, universe_id)
    if row["state"] == "released":
        return
    if row["state"] != "cleanup":
        raise FileCustodyRefused("file_cleanup_not_started")
    # Retain every surviving sibling; refund the retired subset ONLY after the
    # caller proves those exact physical names absent under operation exclusion.
    remaining = conn.execute(
        "SELECT COUNT(*),COALESCE(SUM(size_bytes),0) FROM run_file_objects "
        "WHERE operation_id=? AND state='ready'",
        (operation_id,),
    ).fetchone()
    state = "committed" if remaining[0] else "released"
    conn.execute(
        "UPDATE run_file_operations SET state=? WHERE operation_id=?", (state, operation_id)
    )
    conn.execute(
        "UPDATE run_file_allocations SET state=?,amount=? WHERE operation_id=?",
        ("retained" if remaining[0] else "released", remaining[1], operation_id),
    )
    conn.execute("DELETE FROM run_file_cleanup WHERE operation_id=?", (operation_id,))
