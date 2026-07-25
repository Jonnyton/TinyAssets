"""Host-operator-only safety primitives for exact-founder-home reset.

This module is intentionally not imported by the MCP or HTTP servers.  The
public lifecycle surface remains unchanged; scoped reset is an offline
maintenance operation with an explicit reviewed plan.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

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


class ScopedResetError(RuntimeError):
    """Base error for scoped-reset safety failures."""


class ScopedResetSchemaError(ScopedResetError):
    """The current store inventory differs from the reviewed inventory."""


class ScopedResetLeaseBusy(ScopedResetError):
    """A writer or reset operation currently owns the maintenance barrier."""


@dataclass(frozen=True)
class ScopeInventory:
    """Read-only, content-free inventory for one exact founder binding."""

    principal: str
    home_id: str | None
    home_path: Path | None
    schema_tables: frozenset[str]
    subject_grants: tuple[tuple[str, str], ...]
    blockers: tuple[str, ...]


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
    return blockers


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

    return ScopeInventory(
        principal=subject,
        home_id=home_id,
        home_path=home_path,
        schema_tables=tables,
        subject_grants=grants,
        blockers=tuple(sorted(set(blockers))),
    )


__all__ = [
    "FAULT_POINTS",
    "INVENTORY_REVISION",
    "MAIN_DB_TABLE_CLASSIFICATIONS",
    "MaintenanceBarrier",
    "ScopeInventory",
    "ScopedResetError",
    "ScopedResetLeaseBusy",
    "ScopedResetSchemaError",
    "acquire_maintenance_barrier",
    "inspect_reset_scope",
]
