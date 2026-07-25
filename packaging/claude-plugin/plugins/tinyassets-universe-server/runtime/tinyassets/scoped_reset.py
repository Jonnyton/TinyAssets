"""Host-operator-only safety primitives for exact-founder-home reset.

This module is intentionally not imported by the MCP or HTTP servers.  The
public lifecycle surface remains unchanged; scoped reset is an offline
maintenance operation with an explicit reviewed plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import AbstractSet, Callable, Mapping

from tinyassets.storage import DB_FILENAME

INVENTORY_REVISION = "scoped-reset-inventory-v1-2026-07-25"

# Classification is location-specific: these are the only reviewed tables
# allowed in the root .tinyassets.db.  A migration adding any other table must
# update this inventory before scoped planning can resume.
MAIN_DB_TABLE_CLASSIFICATIONS = MappingProxyType({
    # Exact candidate-home mutable state.
    "universes": "reset_home",
    "universe_rules": "reset_home",
    "universe_notes": "reset_home",
    "universe_work_targets": "reset_home",
    "universe_hard_priorities": "reset_home",
    "universe_snapshots": "reset_home",
    "branches": "reset_home",
    "branch_heads": "reset_home",
    "user_requests": "reset_home_or_block",
    "vote_windows": "reset_home_or_block",
    "vote_ballots": "reset_home_or_block",
    # Ownership and access are distinct.
    "founder_home": "reset_binding",
    "universe_acl": "reset_subject_grants",
    # Global identity/auth/commons/audit records are preserved.
    "user_accounts": "preserve",
    "user_sessions": "preserve",
    "capability_grants": "preserve",
    "author_definitions": "preserve",
    "author_forks": "preserve",
    "author_runtime_instances": "preserve_or_block",
    "action_records": "preserve",
    "branch_definitions": "preserve",
    "goals": "preserve",
    "gate_claims": "preserve",
    "canonical_bindings": "preserve",
    "unreconciled_writes": "block_matching",
    # Queue Epoch 2 is authority/audit-bearing.  Terminal rows are preserved;
    # active or ambiguous rows block instead of being cascaded away.
    "request_admissions": "preserve",
    "request_admission_events": "preserve",
    "branch_tasks_v2": "preserve_or_block",
    "branch_tasks_v2_quarantine": "block_matching",
    "branch_tasks_v2_maintenance_state": "preserve",
    "request_admission_rollouts": "preserve_or_block",
    # Financial stores are immutable/shared and never reset.
    "escrow_locks": "preserve_or_block",
    "staker_escrow_budget": "preserve_or_block",
    "payout_wallet": "preserve",
    "escrow_balance": "preserve",
    "pending_settlement": "preserve_or_block",
    "settlement_batch": "preserve_or_block",
    "transaction_log": "preserve",
    "treasury_balance": "preserve",
    "bounty_pool_balance": "preserve_or_block",
    "royalty_payout": "preserve_or_block",
    "take_rate_log": "preserve",
    # Scoped reset's content-free coordination state.
    "scoped_reset_leases": "preserve",
    "scoped_reset_operations": "preserve",
})

FAULT_POINTS = (
    "before_rename",
    "after_rename",
    "before_commit",
    "after_commit",
    "before_cleanup",
    "after_cleanup",
)

_ACTIVE_DAEMON_STATES = frozenset({
    "active",
    "claimed",
    "pending",
    "queued",
    "running",
    "starting",
})
_ACTIVE_REQUEST_STATES = frozenset({
    "active",
    "claimed",
    "open",
    "pending",
    "queued",
    "running",
})
_ACTIVE_TASK_STATES = frozenset({
    "cancel_requested",
    "pending",
    "running",
})
_ACTIVE_ROLLOUT_STATES = frozenset({"canary", "enabled", "readers_only"})
_CREDENTIAL_NAMES = frozenset({
    ".credential-vault.json",
    ".credentials",
    "auth.json",
})
_HOME_AUDIT_PREFIXES = (
    ".external_write_receipts.db",
    ".idempotency.db",
    ".runs.db",
    "auto_ship_attempts.jsonl",
    "bid_execution_log.json",
)
_KNOWN_ROOT_DATABASES = frozenset({
    ".auth.db",
    ".external_write_receipts.db",
    ".idempotency.db",
    ".langgraph_runs.db",
    ".node_eval.db",
    ".project_memory.db",
    ".runs.db",
    DB_FILENAME,
    "checkpoints.db",
    "daemon_brain.db",
    "knowledge.db",
    "story.db",
    "wiki_trigger_attempts.db",
})

_CONTROL_SCHEMA = """
CREATE TABLE IF NOT EXISTS scoped_reset_leases (
    principal_fingerprint TEXT PRIMARY KEY,
    fence INTEGER NOT NULL CHECK (fence >= 1),
    plan_id TEXT NOT NULL,
    home_id TEXT,
    state TEXT NOT NULL CHECK (state IN ('active', 'released')),
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scoped_reset_operations (
    plan_id TEXT PRIMARY KEY,
    principal_fingerprint TEXT NOT NULL,
    roster_revision TEXT NOT NULL,
    inventory_revision TEXT NOT NULL,
    home_id TEXT,
    fence INTEGER NOT NULL CHECK (fence >= 1),
    state TEXT NOT NULL CHECK (
        state IN (
            'prepared', 'staged', 'committed', 'completed', 'rolled_back'
        )
    ),
    source_path TEXT NOT NULL,
    staging_path TEXT NOT NULL,
    journal_path TEXT NOT NULL,
    commit_witness INTEGER NOT NULL DEFAULT 0 CHECK (commit_witness IN (0, 1)),
    receipt_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


class ScopedResetError(RuntimeError):
    """Base error for scoped-reset safety failures."""


class ScopedResetSchemaError(ScopedResetError):
    """The current store inventory differs from the reviewed inventory."""


class ScopedResetLeaseBusy(ScopedResetError):
    """A writer or reset operation currently owns the maintenance barrier."""


class ScopedResetBlocked(ScopedResetError):
    """Reviewed scope contains state that must close through its normal lifecycle."""


class ScopedResetPlanChanged(ScopedResetError):
    """Apply no longer matches the exact plan reviewed by the operator."""


class ScopedResetRecoveryError(ScopedResetError):
    """Journal, witness, and filesystem state cannot be reconciled safely."""


@dataclass(frozen=True)
class ScopeInventory:
    """Read-only, content-free inventory for one exact founder binding."""

    principal: str
    home_id: str | None
    home_path: Path | None
    schema_tables: frozenset[str]
    subject_grants: tuple[tuple[str, str], ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class TestIdentityRoster:
    """Restricted operator input; aliases are safe to emit, subjects are not."""

    revision: str
    aliases: Mapping[str, str]
    allowlisted_subjects: AbstractSet[str]

    def __post_init__(self) -> None:
        revision = self.revision.strip()
        if not revision:
            raise ValueError("roster revision must be non-empty")
        normalized: dict[str, str] = {}
        for raw_alias, raw_subject in self.aliases.items():
            alias = str(raw_alias).strip()
            subject = str(raw_subject).strip()
            if not alias or not subject:
                raise ValueError("roster aliases and subjects must be non-empty")
            if subject == "anonymous":
                raise ValueError("anonymous cannot be a test identity")
            if alias in normalized:
                raise ValueError(f"duplicate test identity alias: {alias}")
            normalized[alias] = subject
        if len(set(normalized.values())) != len(normalized):
            raise ValueError("test identity subjects must be unique")
        allowed = frozenset(
            str(value).strip()
            for value in self.allowlisted_subjects
            if str(value).strip()
        )
        object.__setattr__(self, "revision", revision)
        object.__setattr__(self, "aliases", MappingProxyType(normalized))
        object.__setattr__(self, "allowlisted_subjects", allowed)


@dataclass
class MaintenanceBarrier:
    """Cross-process shared/exclusive byte-range lock."""

    fd: int
    path: Path
    exclusive: bool
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        _unlock_fd(self.fd)
        os.close(self.fd)
        self._released = True

    def __enter__(self) -> MaintenanceBarrier:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _lock_fd(fd: int, *, exclusive: bool) -> bool:
    os.lseek(fd, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        mode = msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK
        try:
            msvcrt.locking(fd, mode, 1)
        except OSError:
            return False
        return True

    import fcntl

    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    try:
        fcntl.flock(fd, mode | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_fd(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return

    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def acquire_maintenance_barrier(
    data_dir: Path,
    *,
    exclusive: bool,
    timeout: float = 0.0,
) -> MaintenanceBarrier:
    """Acquire the process-shared writer/reset barrier.

    Normal service writers hold a shared lease; scoped apply/recovery requires
    exclusive ownership.  Contention is explicit and never treated as success.
    """

    root = Path(data_dir).resolve(strict=True)
    path = root / ".scoped-reset.barrier"
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    if os.fstat(fd).st_size == 0:
        os.write(fd, b"\0")
    deadline = time.monotonic() + max(0.0, timeout)
    while not _lock_fd(fd, exclusive=exclusive):
        if time.monotonic() >= deadline:
            os.close(fd)
            mode = "exclusive reset" if exclusive else "shared writer"
            raise ScopedResetLeaseBusy(f"{mode} maintenance barrier is busy")
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    return MaintenanceBarrier(fd=fd, path=path, exclusive=exclusive)


def _table_names(conn: sqlite3.Connection) -> frozenset[str]:
    return frozenset(
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    )


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        info = path.lstat()
    except OSError:
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def _walk_home_without_following(home: Path) -> tuple[str, ...]:
    blockers: list[str] = []
    pending = [home]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            blockers.append(f"home path cannot be inspected: {exc.__class__.__name__}")
            continue
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink() or _is_link_or_reparse(path):
                blockers.append(
                    f"home contains link or reparse point: {path.relative_to(home)}"
                )
                continue
            if entry.name in _CREDENTIAL_NAMES:
                blockers.append(
                    f"home contains credential artifact: {path.relative_to(home)}"
                )
                continue
            if entry.name.startswith(_HOME_AUDIT_PREFIXES):
                blockers.append(
                    f"home-local audit or receipt store requires archival: "
                    f"{path.relative_to(home)}"
                )
                continue
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
    return tuple(blockers)


def _matching_count(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[object, ...],
) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def _inspect_database(
    conn: sqlite3.Connection,
    *,
    principal: str,
    home_id: str | None,
) -> list[str]:
    if home_id is None:
        return []
    blockers: list[str] = []
    foreign_bindings = _matching_count(
        conn,
        "SELECT COUNT(*) FROM founder_home "
        "WHERE universe_id = ? AND founder_sub <> ?",
        (home_id, principal),
    )
    if foreign_bindings:
        blockers.append(f"foreign binding references exact home ({foreign_bindings})")

    foreign_grants = _matching_count(
        conn,
        "SELECT COUNT(*) FROM universe_acl "
        "WHERE universe_id = ? AND actor_id <> ?",
        (home_id, principal),
    )
    if foreign_grants:
        blockers.append(f"foreign grant references exact home ({foreign_grants})")

    active_checks: tuple[
        tuple[str, str, tuple[object, ...]],
        ...,
    ] = (
        (
            "daemon",
            "SELECT COUNT(*) FROM author_runtime_instances "
            f"WHERE universe_id = ? AND lower(status) IN "
            f"({','.join('?' for _ in _ACTIVE_DAEMON_STATES)})",
            (home_id, *sorted(_ACTIVE_DAEMON_STATES)),
        ),
        (
            "request",
            "SELECT COUNT(*) FROM user_requests "
            f"WHERE universe_id = ? AND lower(status) IN "
            f"({','.join('?' for _ in _ACTIVE_REQUEST_STATES)})",
            (home_id, *sorted(_ACTIVE_REQUEST_STATES)),
        ),
        (
            "vote",
            "SELECT COUNT(*) FROM vote_windows "
            "WHERE universe_id = ? AND lower(status) = 'open'",
            (home_id,),
        ),
        (
            "epoch2",
            "SELECT COUNT(*) FROM branch_tasks_v2 "
            f"WHERE universe_id = ? AND lower(status) IN "
            f"({','.join('?' for _ in _ACTIVE_TASK_STATES)})",
            (home_id, *sorted(_ACTIVE_TASK_STATES)),
        ),
        (
            "epoch2 quarantine",
            "SELECT COUNT(*) FROM branch_tasks_v2_quarantine "
            "WHERE universe_id = ?",
            (home_id,),
        ),
        (
            "epoch2 rollout",
            "SELECT COUNT(*) FROM request_admission_rollouts "
            f"WHERE universe_id = ? AND lower(state) IN "
            f"({','.join('?' for _ in _ACTIVE_ROLLOUT_STATES)})",
            (home_id, *sorted(_ACTIVE_ROLLOUT_STATES)),
        ),
    )
    tables = _table_names(conn)
    for label, sql, params in active_checks:
        table = sql.split("FROM ", 1)[1].split(" ", 1)[0]
        if table in tables and _matching_count(conn, sql, params):
            blockers.append(f"active {label} state references exact home")

    market_checks: tuple[tuple[str, str, tuple[object, ...]], ...] = (
        (
            "escrow_locks",
            "SELECT COUNT(*) FROM escrow_locks "
            "WHERE lower(status) = 'locked' "
            "AND (staker_id = ? OR recipient_id = ?)",
            (principal, principal),
        ),
        (
            "staker_escrow_budget",
            "SELECT COUNT(*) FROM staker_escrow_budget "
            "WHERE staker_id = ? AND reserved_amount > 0",
            (principal,),
        ),
        (
            "escrow_balance",
            "SELECT COUNT(*) FROM escrow_balance "
            "WHERE staker_id = ? AND lower(status) IN ('locked', 'partial')",
            (principal,),
        ),
        (
            "pending_settlement",
            "SELECT COUNT(*) FROM pending_settlement "
            "WHERE recipient_id = ? AND lower(status) IN ('pending', 'batched')",
            (principal,),
        ),
        (
            "settlement_batch",
            "SELECT COUNT(*) FROM settlement_batch "
            "WHERE recipient_id = ? "
            "AND lower(status) IN ('open', 'submitted', 'in_doubt')",
            (principal,),
        ),
        (
            "royalty_payout",
            "SELECT COUNT(*) FROM royalty_payout "
            "WHERE designer_id = ? AND lower(status) = 'pending'",
            (principal,),
        ),
    )
    for table, sql, params in market_checks:
        if table in tables and _matching_count(conn, sql, params):
            blockers.append(f"active market obligation references test principal: {table}")
    return blockers


def _inspect_root_runs(
    root: Path,
    *,
    principal: str,
) -> tuple[str, ...]:
    runs_path = root / ".runs.db"
    if not runs_path.is_file():
        return ()
    try:
        conn = sqlite3.connect(f"file:{runs_path}?mode=ro", uri=True)
        tables = _table_names(conn)
        blockers: list[str] = []
        if "runs" in tables and _matching_count(
            conn,
            "SELECT COUNT(*) FROM runs "
            "WHERE lower(status) IN ('queued', 'running') "
            "AND (actor = ? OR owner_user_id = ?)",
            (principal, principal),
        ):
            blockers.append("active root run references test principal")
        if "branch_schedules" in tables and _matching_count(
            conn,
            "SELECT COUNT(*) FROM branch_schedules "
            "WHERE owner_actor = ? AND active = 1 AND paused = 0",
            (principal,),
        ):
            blockers.append("active schedule references test principal")
        if "branch_subscriptions" in tables and _matching_count(
            conn,
            "SELECT COUNT(*) FROM branch_subscriptions "
            "WHERE owner_actor = ? AND active = 1",
            (principal,),
        ):
            blockers.append("active subscription references test principal")
        return tuple(blockers)
    except sqlite3.DatabaseError as exc:
        return (f"root run history cannot be classified: {exc.__class__.__name__}",)
    finally:
        if "conn" in locals():
            conn.close()


def _inspect_root_operational_files(root: Path) -> tuple[str, ...]:
    blockers: list[str] = []
    for entry in root.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        base_name = name
        for suffix in ("-journal", "-shm", "-wal"):
            if base_name.endswith(suffix):
                base_name = base_name.removesuffix(suffix)
                break
        if (
            name == ".scoped-reset.barrier"
            or base_name in _KNOWN_ROOT_DATABASES
            or not (base_name.startswith(".") or base_name.endswith(".db"))
        ):
            continue
        blockers.append(f"unclassified root operational store: {name}")
    return tuple(blockers)


def inspect_reset_scope(data_dir: Path, *, principal: str) -> ScopeInventory:
    """Freeze the read-only reviewed scope for one exact founder binding."""

    subject = principal.strip()
    if not subject:
        raise ValueError("principal must be non-empty")
    root = Path(data_dir).resolve(strict=True)
    db_file = root / DB_FILENAME
    if not db_file.is_file():
        return ScopeInventory(
            principal=subject,
            home_id=None,
            home_path=None,
            schema_tables=frozenset(),
            subject_grants=(),
            blockers=(),
        )

    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        tables = _table_names(conn)
        unknown = sorted(tables - MAIN_DB_TABLE_CLASSIFICATIONS.keys())
        if unknown:
            raise ScopedResetSchemaError(
                "unclassified tables block scoped reset: " + ", ".join(unknown)
            )
        row = conn.execute(
            "SELECT universe_id FROM founder_home WHERE founder_sub = ?",
            (subject,),
        ).fetchone()
        home_id = str(row[0]) if row and row[0] else None
        grants = tuple(
            (str(grant[0]), str(grant[1]))
            for grant in conn.execute(
                "SELECT universe_id, permission FROM universe_acl "
                "WHERE actor_id = ? ORDER BY universe_id",
                (subject,),
            )
        )
        blockers = _inspect_database(
            conn,
            principal=subject,
            home_id=home_id,
        )
        if home_id is not None:
            registered = conn.execute(
                "SELECT host_path FROM universes WHERE universe_id = ?",
                (home_id,),
            ).fetchone()
            home_path = root / home_id
            expected = home_path.resolve(strict=False)
            if expected.parent != root:
                blockers.append("founder-home path escapes the data root")
            if registered is None:
                blockers.append("founder-home binding has no universe row")
            else:
                registered_path = Path(str(registered[0])).resolve(strict=False)
                if registered_path != expected:
                    blockers.append("founder-home path disagrees with universe index")
            if not home_path.is_dir():
                blockers.append("founder-home directory is missing")
            elif _is_link_or_reparse(home_path):
                blockers.append("founder-home path is a link or reparse point")
            else:
                blockers.extend(_walk_home_without_following(home_path))
        else:
            home_path = None
    finally:
        conn.close()

    marker = root / ".active_universe"
    if home_id is not None and marker.is_file():
        if marker.read_text(encoding="utf-8").strip() == home_id:
            blockers.append("active universe marker targets exact home")
    offer = root / "founder_offers" / f"{subject}.json"
    if offer.exists():
        blockers.append("enabled founder market offer must be disabled normally")
    blockers.extend(_inspect_root_runs(root, principal=subject))
    blockers.extend(_inspect_root_operational_files(root))

    return ScopeInventory(
        principal=subject,
        home_id=home_id,
        home_path=home_path,
        schema_tables=tables,
        subject_grants=grants,
        blockers=tuple(sorted(set(blockers))),
    )


def _principal_digest(principal: str) -> str:
    payload = f"tinyassets-scoped-reset-principal-v1\0{principal}".encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_value(value: object) -> object:
    if isinstance(value, bytes):
        return {
            "blob_sha256": hashlib.sha256(value).hexdigest(),
            "bytes": len(value),
        }
    return value


def _row_digest(row: sqlite3.Row) -> str:
    payload = {
        key: _json_value(row[key])
        for key in row.keys()
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _primary_key_columns(
    conn: sqlite3.Connection,
    table: str,
) -> tuple[str, ...]:
    columns = [
        (int(row[5]), str(row[1]))
        for row in conn.execute(f'PRAGMA table_info("{table}")')
        if int(row[5]) > 0
    ]
    return tuple(name for _, name in sorted(columns))


def _row_action(
    conn: sqlite3.Connection,
    *,
    table: str,
    row: sqlite3.Row,
    alias: str,
) -> dict[str, object]:
    keys = _primary_key_columns(conn, table)
    if not keys:
        raise ScopedResetSchemaError(
            f"resettable table {table!r} has no primary key"
        )
    safe_keys: dict[str, object] = {}
    for key in keys:
        if table == "founder_home" and key == "founder_sub":
            safe_keys["identity_alias"] = alias
        elif table == "universe_acl" and key == "actor_id":
            safe_keys["identity_alias"] = alias
        else:
            safe_keys[key] = _json_value(row[key])
    return {
        "table": table,
        "action": "delete_exact_row",
        "keys": safe_keys,
        "row_digest": _row_digest(row),
    }


def _select_rows(
    conn: sqlite3.Connection,
    *,
    table: str,
    where: str,
    params: tuple[object, ...],
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            f'SELECT * FROM "{table}" WHERE {where} ORDER BY rowid',
            params,
        )
    )


def _database_actions(
    conn: sqlite3.Connection,
    *,
    principal: str,
    alias: str,
    home_id: str | None,
) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    if home_id is not None:
        for row in _select_rows(
            conn,
            table="founder_home",
            where="founder_sub = ? AND universe_id = ?",
            params=(principal, home_id),
        ):
            actions.append(
                _row_action(
                    conn,
                    table="founder_home",
                    row=row,
                    alias=alias,
                )
            )
    for row in _select_rows(
        conn,
        table="universe_acl",
        where="actor_id = ?",
        params=(principal,),
    ):
        actions.append(
            _row_action(conn, table="universe_acl", row=row, alias=alias)
        )
    if home_id is None:
        return actions

    home_tables = (
        "universe_hard_priorities",
        "universe_notes",
        "universe_rules",
        "universe_snapshots",
        "universe_work_targets",
        "user_requests",
        "universes",
    )
    for table in home_tables:
        for row in _select_rows(
            conn,
            table=table,
            where="universe_id = ?",
            params=(home_id,),
        ):
            actions.append(
                _row_action(conn, table=table, row=row, alias=alias)
            )

    branch_rows = _select_rows(
        conn,
        table="branches",
        where="universe_id = ?",
        params=(home_id,),
    )
    branch_ids = [str(row["branch_id"]) for row in branch_rows]
    for branch_id in branch_ids:
        for row in _select_rows(
            conn,
            table="branch_heads",
            where="branch_id = ?",
            params=(branch_id,),
        ):
            actions.append(
                _row_action(conn, table="branch_heads", row=row, alias=alias)
            )
    for row in branch_rows:
        actions.append(_row_action(conn, table="branches", row=row, alias=alias))

    vote_rows = _select_rows(
        conn,
        table="vote_windows",
        where="universe_id = ?",
        params=(home_id,),
    )
    for vote in vote_rows:
        for row in _select_rows(
            conn,
            table="vote_ballots",
            where="vote_id = ?",
            params=(vote["vote_id"],),
        ):
            actions.append(
                _row_action(conn, table="vote_ballots", row=row, alias=alias)
            )
    for row in vote_rows:
        actions.append(
            _row_action(conn, table="vote_windows", row=row, alias=alias)
        )
    return sorted(
        actions,
        key=lambda action: (
            str(action["table"]),
            json.dumps(action["keys"], sort_keys=True),
        ),
    )


def plan_test_identity_reset(
    data_dir: Path,
    *,
    alias: str,
    roster: TestIdentityRoster,
) -> dict[str, object]:
    """Return a stable, content-free, read-only plan for one allowlisted alias."""

    identity_alias = alias.strip()
    principal = roster.aliases.get(identity_alias)
    if principal is None:
        raise PermissionError(f"unknown test identity alias: {identity_alias!r}")
    if principal not in roster.allowlisted_subjects:
        raise PermissionError(
            f"subject for alias {identity_alias!r} is not allowlisted"
        )

    scope = inspect_reset_scope(data_dir, principal=principal)
    root = Path(data_dir).resolve(strict=True)
    db_file = root / DB_FILENAME
    actions: list[dict[str, object]] = []
    if db_file.is_file():
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            conn.row_factory = sqlite3.Row
            actions = _database_actions(
                conn,
                principal=principal,
                alias=identity_alias,
                home_id=scope.home_id,
            )
        finally:
            conn.close()

    filesystem_actions: list[dict[str, str]] = []
    if scope.home_path is not None:
        filesystem_actions.append({
            "action": "stage_then_remove_home",
            "path": str(scope.home_path.resolve(strict=False)),
        })

    state_payload = {
        "database_actions": actions,
        "filesystem_actions": filesystem_actions,
    }
    state_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            state_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    plan_inputs = {
        "inventory_revision": INVENTORY_REVISION,
        "roster_revision": roster.revision,
        "principal_fingerprint": _principal_digest(principal),
        "home_id": scope.home_id,
        "resolved_data_dir": str(root),
        "state_digest": state_digest,
        "blockers": list(scope.blockers),
    }
    plan_id = "sha256:" + hashlib.sha256(
        json.dumps(
            plan_inputs,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        "plan_id": plan_id,
        **plan_inputs,
        "identity_alias": identity_alias,
        "database_actions": actions,
        "filesystem_actions": filesystem_actions,
        "preserved": [
            "all other founder homes and universe content",
            "commons, wiki, root run history, audit, market, and billing state",
            "global daemon identities and all credentials",
        ],
        "noop": not actions and not filesystem_actions,
    }


def load_test_identity_roster(path: Path) -> TestIdentityRoster:
    """Load the credential-free operator roster from an explicit local file."""

    roster_path = Path(path).resolve(strict=True)
    if not roster_path.is_file():
        raise ValueError("test identity roster must be a regular file")
    if sys.platform != "win32":
        permissions = stat.S_IMODE(roster_path.stat().st_mode)
        if permissions & 0o077:
            raise PermissionError(
                "test identity roster must not be group/world accessible"
            )
    payload = json.loads(roster_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("test identity roster must be a JSON object")
    allowed_fields = {"aliases", "allowlisted_subjects", "revision"}
    unexpected = sorted(set(payload) - allowed_fields)
    if unexpected:
        raise ValueError(
            "unexpected roster fields: " + ", ".join(unexpected)
        )
    aliases = payload.get("aliases")
    allowlisted = payload.get("allowlisted_subjects")
    if not isinstance(aliases, dict):
        raise ValueError("roster aliases must be a JSON object")
    if not isinstance(allowlisted, list):
        raise ValueError("roster allowlisted_subjects must be a JSON array")
    return TestIdentityRoster(
        revision=str(payload.get("revision") or ""),
        aliases={
            str(alias): str(subject)
            for alias, subject in aliases.items()
        },
        allowlisted_subjects=frozenset(str(value) for value in allowlisted),
    )


def read_completed_plan_receipt(
    data_dir: Path,
    *,
    plan_id: str,
) -> dict[str, object] | None:
    """Return the immutable receipt for a witnessed completed plan, if any."""

    root = Path(data_dir).resolve(strict=True)
    db_file = root / DB_FILENAME
    if not db_file.is_file():
        return None
    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        if "scoped_reset_operations" not in _table_names(conn):
            return None
        row = conn.execute(
            "SELECT receipt_json FROM scoped_reset_operations "
            "WHERE plan_id = ? AND state = 'completed' AND commit_witness = 1",
            (plan_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    receipt = json.loads(str(row[0]))
    if not isinstance(receipt, dict):
        raise ScopedResetSchemaError(
            "completed scoped-reset receipt must be a JSON object"
        )
    return {str(key): value for key, value in receipt.items()}


def _connect_control(data_dir: Path) -> sqlite3.Connection:
    db_file = Path(data_dir) / DB_FILENAME
    conn = sqlite3.connect(str(db_file), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _ensure_control_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_CONTROL_SCHEMA)


def _resolve_roster_principal(
    *,
    alias: str,
    roster: TestIdentityRoster,
) -> tuple[str, str]:
    identity_alias = alias.strip()
    principal = roster.aliases.get(identity_alias)
    if principal is None:
        raise PermissionError(f"unknown test identity alias: {identity_alias!r}")
    if principal not in roster.allowlisted_subjects:
        raise PermissionError(
            f"subject for alias {identity_alias!r} is not allowlisted"
        )
    return identity_alias, principal


def _completed_receipt_for_principal(
    conn: sqlite3.Connection,
    *,
    plan_id: str,
    principal_fingerprint: str,
) -> dict[str, object] | None:
    row = conn.execute(
        "SELECT receipt_json FROM scoped_reset_operations "
        "WHERE plan_id = ? AND principal_fingerprint = ? "
        "AND state = 'completed' AND commit_witness = 1",
        (plan_id, principal_fingerprint),
    ).fetchone()
    if row is None:
        return None
    receipt = json.loads(str(row[0]))
    if not isinstance(receipt, dict):
        raise ScopedResetRecoveryError("completed receipt is not a JSON object")
    return {str(key): value for key, value in receipt.items()}


def _safe_operation_paths(
    root: Path,
    *,
    plan_id: str,
    home_path: Path | None,
) -> tuple[Path | None, Path | None, Path]:
    operation_id = plan_id.removeprefix("sha256:")
    journal_root = root / ".scoped-reset-journal"
    staging_root = root / ".scoped-reset-staging" / operation_id
    for path in (journal_root, staging_root.parent):
        if path.exists() and _is_link_or_reparse(path):
            raise ScopedResetBlocked(
                f"scoped-reset operational path is a link or reparse point: {path}"
            )
        path.mkdir(parents=True, exist_ok=True)
    journal_path = journal_root / f"{operation_id}.json"
    if home_path is None:
        return None, None, journal_path
    source = home_path.resolve(strict=True)
    if source.parent != root or _is_link_or_reparse(source):
        raise ScopedResetBlocked("candidate home is outside the approved data root")
    staging_root.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse(staging_root):
        raise ScopedResetBlocked("reset staging path is a link or reparse point")
    if source.stat().st_dev != staging_root.stat().st_dev:
        raise ScopedResetBlocked("candidate home and staging are not on one filesystem")
    staging = staging_root / "home"
    if staging.exists():
        raise ScopedResetRecoveryError(
            f"reset staging already exists for reviewed plan: {plan_id}"
        )
    return source, staging, journal_path


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    if sys.platform == "win32":
        return
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_journal(
    path: Path,
    *,
    plan_id: str,
    home_id: str | None,
    fence: int,
    source_path: Path | None,
    staging_path: Path | None,
) -> None:
    payload = {
        "version": 1,
        "plan_id": plan_id,
        "inventory_revision": INVENTORY_REVISION,
        "home_id": home_id,
        "fence": fence,
        "source_path": str(source_path) if source_path else "",
        "staging_path": str(staging_path) if staging_path else "",
    }
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_file(path)
    _fsync_directory(path.parent)


def _remove_journal(path: Path) -> None:
    if path.is_file():
        path.unlink()
        _fsync_directory(path.parent)


def _acquire_durable_fence(
    conn: sqlite3.Connection,
    *,
    plan_id: str,
    principal_fingerprint: str,
    home_id: str | None,
) -> int:
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT fence FROM scoped_reset_leases "
            "WHERE principal_fingerprint = ?",
            (principal_fingerprint,),
        ).fetchone()
        fence = (int(row[0]) if row else 0) + 1
        conn.execute(
            """
            INSERT INTO scoped_reset_leases (
                principal_fingerprint, fence, plan_id, home_id, state, updated_at
            ) VALUES (?, ?, ?, ?, 'active', ?)
            ON CONFLICT(principal_fingerprint) DO UPDATE SET
                fence = excluded.fence,
                plan_id = excluded.plan_id,
                home_id = excluded.home_id,
                state = 'active',
                updated_at = excluded.updated_at
            """,
            (
                principal_fingerprint,
                fence,
                plan_id,
                home_id,
                time.time(),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return fence


def _prepare_operation(
    conn: sqlite3.Connection,
    *,
    plan: Mapping[str, object],
    fence: int,
    source_path: Path | None,
    staging_path: Path | None,
    journal_path: Path,
) -> None:
    now = time.time()
    conn.execute(
        """
        INSERT INTO scoped_reset_operations (
            plan_id, principal_fingerprint, roster_revision,
            inventory_revision, home_id, fence, state, source_path,
            staging_path, journal_path, commit_witness, receipt_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'prepared', ?, ?, ?, 0, '{}', ?, ?)
        ON CONFLICT(plan_id) DO UPDATE SET
            principal_fingerprint = excluded.principal_fingerprint,
            roster_revision = excluded.roster_revision,
            inventory_revision = excluded.inventory_revision,
            home_id = excluded.home_id,
            fence = excluded.fence,
            state = 'prepared',
            source_path = excluded.source_path,
            staging_path = excluded.staging_path,
            journal_path = excluded.journal_path,
            commit_witness = 0,
            receipt_json = '{}',
            updated_at = excluded.updated_at
        """,
        (
            plan["plan_id"],
            plan["principal_fingerprint"],
            plan["roster_revision"],
            plan["inventory_revision"],
            plan["home_id"],
            fence,
            str(source_path) if source_path else "",
            str(staging_path) if staging_path else "",
            str(journal_path),
            now,
            now,
        ),
    )
    conn.commit()


def _action_key_values(
    action: Mapping[str, object],
    *,
    principal: str,
) -> dict[str, object]:
    raw_keys = action["keys"]
    if not isinstance(raw_keys, dict):
        raise ScopedResetPlanChanged("planned row keys are invalid")
    table = str(action["table"])
    keys = dict(raw_keys)
    if table == "founder_home":
        keys = {"founder_sub": principal}
    elif table == "universe_acl":
        keys.pop("identity_alias", None)
        keys["actor_id"] = principal
    return keys


def _delete_planned_rows(
    conn: sqlite3.Connection,
    *,
    plan: Mapping[str, object],
    principal: str,
) -> None:
    raw_actions = plan["database_actions"]
    if not isinstance(raw_actions, list):
        raise ScopedResetPlanChanged("planned database actions are invalid")
    priority = {
        "branch_heads": 0,
        "vote_ballots": 0,
        "universe_hard_priorities": 1,
        "universe_notes": 1,
        "universe_snapshots": 1,
        "universe_work_targets": 1,
        "user_requests": 1,
        "branches": 2,
        "vote_windows": 2,
        "founder_home": 3,
        "universe_acl": 3,
        "universe_rules": 4,
        "universes": 5,
    }
    actions = sorted(
        raw_actions,
        key=lambda action: priority.get(str(action["table"]), 99),
    )
    for action in actions:
        table = str(action["table"])
        if MAIN_DB_TABLE_CLASSIFICATIONS.get(table) not in {
            "reset_binding",
            "reset_home",
            "reset_home_or_block",
            "reset_subject_grants",
        }:
            raise ScopedResetPlanChanged(
                f"plan attempts an unapproved table action: {table}"
            )
        keys = _action_key_values(action, principal=principal)
        where = " AND ".join(f'"{key}" = ?' for key in keys)
        values = tuple(keys.values())
        row = conn.execute(
            f'SELECT * FROM "{table}" WHERE {where}',
            values,
        ).fetchone()
        if row is None or _row_digest(row) != action["row_digest"]:
            raise ScopedResetPlanChanged(
                f"planned row changed before apply: {table}"
            )
        conn.execute(f'DELETE FROM "{table}" WHERE {where}', values)


def _safe_cleanup_staging(root: Path, staging: Path | None) -> None:
    if staging is None or not staging.exists():
        return
    resolved = staging.resolve(strict=True)
    expected_parent = root / ".scoped-reset-staging"
    if expected_parent not in resolved.parents or _is_link_or_reparse(resolved):
        raise ScopedResetRecoveryError("refusing unsafe reset staging cleanup")
    shutil.rmtree(resolved)
    operation_dir = resolved.parent
    if operation_dir.is_dir() and not any(operation_dir.iterdir()):
        operation_dir.rmdir()
    _fsync_directory(expected_parent)


def _complete_operation(
    conn: sqlite3.Connection,
    *,
    plan_id: str,
    principal_fingerprint: str,
) -> None:
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE scoped_reset_operations "
            "SET state = 'completed', updated_at = ? WHERE plan_id = ?",
            (now, plan_id),
        )
        conn.execute(
            "UPDATE scoped_reset_leases "
            "SET state = 'released', updated_at = ? "
            "WHERE principal_fingerprint = ?",
            (now, principal_fingerprint),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _fault(
    fault_injector: Callable[[str], None] | None,
    point: str,
) -> None:
    if fault_injector is not None:
        fault_injector(point)


def apply_test_identity_reset(
    data_dir: Path,
    *,
    alias: str,
    roster: TestIdentityRoster,
    plan_id: str,
    fault_injector: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Apply one exact reviewed plan under the exclusive maintenance barrier."""

    identity_alias, principal = _resolve_roster_principal(
        alias=alias,
        roster=roster,
    )
    principal_fingerprint = _principal_digest(principal)
    root = Path(data_dir).resolve(strict=True)
    with acquire_maintenance_barrier(root, exclusive=True, timeout=0.0):
        conn = _connect_control(root)
        try:
            _ensure_control_schema(conn)
            existing = _completed_receipt_for_principal(
                conn,
                plan_id=plan_id,
                principal_fingerprint=principal_fingerprint,
            )
            if existing is not None:
                return existing
            _recover_locked(root, conn)
            existing = _completed_receipt_for_principal(
                conn,
                plan_id=plan_id,
                principal_fingerprint=principal_fingerprint,
            )
            if existing is not None:
                return existing
            plan = plan_test_identity_reset(
                root,
                alias=identity_alias,
                roster=roster,
            )
            if plan["blockers"]:
                raise ScopedResetBlocked("; ".join(plan["blockers"]))
            if plan["plan_id"] != plan_id:
                raise ScopedResetPlanChanged(
                    "current state does not match the reviewed plan"
                )
            source, staging, journal = _safe_operation_paths(
                root,
                plan_id=plan_id,
                home_path=(
                    Path(str(plan["filesystem_actions"][0]["path"]))
                    if plan["filesystem_actions"]
                    else None
                ),
            )
            fence = _acquire_durable_fence(
                conn,
                plan_id=plan_id,
                principal_fingerprint=principal_fingerprint,
                home_id=plan["home_id"],
            )
            _prepare_operation(
                conn,
                plan=plan,
                fence=fence,
                source_path=source,
                staging_path=staging,
                journal_path=journal,
            )
            _write_journal(
                journal,
                plan_id=plan_id,
                home_id=plan["home_id"],
                fence=fence,
                source_path=source,
                staging_path=staging,
            )
            _fault(fault_injector, "before_rename")
            if source is not None and staging is not None:
                os.replace(source, staging)
                _fsync_directory(root)
                _fsync_directory(staging.parent)
            conn.execute(
                "UPDATE scoped_reset_operations "
                "SET state = 'staged', updated_at = ? WHERE plan_id = ?",
                (time.time(), plan_id),
            )
            conn.commit()
            _fault(fault_injector, "after_rename")
            _fault(fault_injector, "before_commit")

            receipt = {
                "plan_id": plan_id,
                "status": "completed",
                "identity_alias": identity_alias,
                "home_id": plan["home_id"],
                "fence": fence,
                "inventory_revision": INVENTORY_REVISION,
            }
            conn.execute("BEGIN IMMEDIATE")
            try:
                _delete_planned_rows(
                    conn,
                    plan=plan,
                    principal=principal,
                )
                conn.execute(
                    "UPDATE scoped_reset_operations "
                    "SET state = 'committed', commit_witness = 1, "
                    "receipt_json = ?, updated_at = ? WHERE plan_id = ?",
                    (
                        json.dumps(
                            receipt,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        time.time(),
                        plan_id,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            _fault(fault_injector, "after_commit")
            _fault(fault_injector, "before_cleanup")
            _safe_cleanup_staging(root, staging)
            _remove_journal(journal)
            _complete_operation(
                conn,
                plan_id=plan_id,
                principal_fingerprint=principal_fingerprint,
            )
            _fault(fault_injector, "after_cleanup")
            return receipt
        finally:
            conn.close()


def _recover_locked(root: Path, conn: sqlite3.Connection) -> None:
    _ensure_control_schema(conn)
    rows = conn.execute(
        "SELECT * FROM scoped_reset_operations "
        "WHERE state NOT IN ('completed', 'rolled_back') ORDER BY created_at"
    ).fetchall()
    for row in rows:
        plan_id = str(row["plan_id"])
        source = Path(str(row["source_path"])) if row["source_path"] else None
        staging = Path(str(row["staging_path"])) if row["staging_path"] else None
        journal = Path(str(row["journal_path"]))
        witness = bool(row["commit_witness"])
        if not journal.is_file():
            raise ScopedResetRecoveryError(
                f"incomplete reset is missing its journal: {plan_id}"
            )
        if witness:
            _safe_cleanup_staging(root, staging)
            _remove_journal(journal)
            _complete_operation(
                conn,
                plan_id=plan_id,
                principal_fingerprint=str(row["principal_fingerprint"]),
            )
            continue
        if staging is not None and staging.exists():
            if source is None:
                raise ScopedResetRecoveryError(
                    f"staged reset has no source path: {plan_id}"
                )
            if source.exists():
                raise ScopedResetRecoveryError(
                    f"rollback would overwrite replacement state: {plan_id}"
                )
            os.replace(staging, source)
            _fsync_directory(root)
        if staging is not None:
            operation_dir = staging.parent
            if operation_dir.is_dir() and not any(operation_dir.iterdir()):
                operation_dir.rmdir()
        _remove_journal(journal)
        now = time.time()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE scoped_reset_operations "
                "SET state = 'rolled_back', updated_at = ? WHERE plan_id = ?",
                (now, plan_id),
            )
            conn.execute(
                "UPDATE scoped_reset_leases "
                "SET state = 'released', updated_at = ? "
                "WHERE principal_fingerprint = ?",
                (now, row["principal_fingerprint"]),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def recover_scoped_resets(data_dir: Path) -> None:
    """Converge every incomplete operation before affected writers resume."""

    root = Path(data_dir).resolve(strict=True)
    with acquire_maintenance_barrier(root, exclusive=True, timeout=0.0):
        conn = _connect_control(root)
        try:
            _recover_locked(root, conn)
        finally:
            conn.close()


def prepare_service_writer_barrier(
    data_dir: Path,
    *,
    timeout: float = 30.0,
) -> MaintenanceBarrier:
    """Recover interrupted reset state, then admit one service writer process."""

    root = Path(data_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    recover_scoped_resets(root)
    return acquire_maintenance_barrier(
        root,
        exclusive=False,
        timeout=timeout,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tinyassets.scoped_reset",
        description="Operator-only exact test-identity reset maintenance",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="print a read-only reset plan")
    plan.add_argument("--data-dir", required=True, type=Path)
    plan.add_argument("--roster", required=True, type=Path)
    plan.add_argument("--identity", required=True)
    apply = commands.add_parser("apply", help="apply an exact reviewed plan")
    apply.add_argument("--data-dir", required=True, type=Path)
    apply.add_argument("--roster", required=True, type=Path)
    apply.add_argument("--identity", required=True)
    apply.add_argument("--plan-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the operator-only maintenance CLI."""

    args = _build_parser().parse_args(argv)
    if args.command == "plan":
        roster = load_test_identity_roster(args.roster)
        plan = plan_test_identity_reset(
            args.data_dir,
            alias=args.identity,
            roster=roster,
        )
        print(json.dumps(plan, sort_keys=True, separators=(",", ":")))
        return 0
    if args.command == "apply":
        roster = load_test_identity_roster(args.roster)
        receipt = apply_test_identity_reset(
            args.data_dir,
            alias=args.identity,
            roster=roster,
            plan_id=args.plan_id,
        )
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 0
    raise AssertionError(f"unhandled scoped reset command: {args.command}")


__all__ = [
    "FAULT_POINTS",
    "INVENTORY_REVISION",
    "MAIN_DB_TABLE_CLASSIFICATIONS",
    "MaintenanceBarrier",
    "ScopeInventory",
    "ScopedResetError",
    "ScopedResetBlocked",
    "ScopedResetLeaseBusy",
    "ScopedResetPlanChanged",
    "ScopedResetRecoveryError",
    "ScopedResetSchemaError",
    "TestIdentityRoster",
    "acquire_maintenance_barrier",
    "apply_test_identity_reset",
    "inspect_reset_scope",
    "load_test_identity_roster",
    "main",
    "plan_test_identity_reset",
    "prepare_service_writer_barrier",
    "read_completed_plan_receipt",
    "recover_scoped_resets",
]


if __name__ == "__main__":
    raise SystemExit(main())
