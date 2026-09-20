"""Internal persisted memory-family authority; no public packet or kernel allocator.

Callers retain the family fence across their short authority/pool transactions
and kernel join/release barrier. These are two WALs, not an atomic database pair.
No legacy row is adopted and no normal run path enables guarded memory yet.
"""

from __future__ import annotations

import contextvars
import os
import re
import sqlite3
import stat
import threading
import time
import weakref
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tinyassets.storage.delivery_lock import _try_os_lock

_mutex_guard = threading.Lock()
_mutexes = weakref.WeakValueDictionary()
_TERMINAL = ("completed", "failed", "cancelled", "interrupted")
_REASONS = frozenset({"cancelled", "memory_limit", "interrupted", "failed", "drained"})
_MANAGED_RUNTIME_READY = contextvars.ContextVar("tinyassets_managed_runtime_ready", default=None)


class FamilyRefused(RuntimeError):
    """Unknown, stale or closed family authority; never permission to fall back."""


class _ManagedRuntimeReadiness:
    """Process-local enrollment readiness, never invocation or kernel authority.

    No production publisher ships yet: full startup/lifecycle integration must
    establish readiness outside database writers before installing this carrier.
    Actual admission/launch still requires its fresh authority and kernel checks.
    Teardown retires the same object so copied contexts cannot outlive it.
    """

    def __init__(self, database: Path):
        self.database = database.resolve()
        self.pid = os.getpid()
        self.active = True

    def retire(self):
        self.active = False

    def __reduce__(self):
        raise TypeError("managed runtime readiness is not serializable")

    def require(self, conn):
        database = next(row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main")
        if (not self.active or self.pid != os.getpid()
                or not database or Path(database).resolve() != self.database):
            raise FamilyRefused("managed runtime readiness is retired or belongs to another root")


def root_enrollment_enabled(conn) -> bool:
    readiness = _MANAGED_RUNTIME_READY.get()
    if readiness is None:
        return False
    if type(readiness) is not _ManagedRuntimeReadiness:
        raise FamilyRefused("unknown managed runtime readiness")
    readiness.require(conn)
    return True


@dataclass(frozen=True)
class UnmanagedParent:
    """Trusted legacy invocation marker: children stay unknown, not new roots."""


UNMANAGED_PARENT = UnmanagedParent()


@dataclass(frozen=True)
class FamilyMember:
    run_id: str
    root_run_id: str
    epoch: int
    owner_user_id: str
    universe_id: str
    actor: str
    runtime_instance_id: str = ""
    worker_id: str = ""


class FamilyFence:
    def __init__(self, database: Path, root_run_id: str):
        self.database = database
        self.root_run_id = root_run_id
        self._pid = os.getpid()
        self._thread = threading.get_ident()
        self._held = True

    def require(self, conn: sqlite3.Connection, *, write=False):
        if not self._held or self._pid != os.getpid() or self._thread != threading.get_ident():
            raise FamilyRefused("family fence is not held by this worker")
        database = next(row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main")
        if Path(database).resolve() != self.database:
            raise FamilyRefused("family fence belongs to another database")
        if write and not conn.in_transaction:
            raise FamilyRefused("family write requires caller-owned transaction")


@dataclass(frozen=True)
class FamilyAdmission:
    fence: FamilyFence
    member: FamilyMember

    def require(self, run_id: str, universe_id: str) -> None:
        from tinyassets.runs import _connect

        if (run_id, universe_id) != (self.member.run_id, self.member.universe_id):
            raise FamilyRefused("admission identity mismatch")
        with _connect(self.fence.database.parent) as conn:
            validate_in_transaction(conn, self.fence, self.member)


@dataclass(frozen=True)
class FamilyRelease:
    fence: FamilyFence
    universe_id: str
    epoch: int
    empty: Callable[[], bool]

    def require(self, root_run_id: str, universe_id: str, epoch: int) -> None:
        from tinyassets.runs import _connect

        if (root_run_id, universe_id, epoch) != (
            self.fence.root_run_id,
            self.universe_id,
            self.epoch,
        ):
            raise FamilyRefused("release identity or epoch mismatch")
        with _connect(self.fence.database.parent) as conn:
            self.fence.require(conn)
            root = _row(conn, root_run_id)
            if (
                root["workspace_budget_root_run_id"] != root_run_id
                or root["workspace_budget_epoch"] != epoch
                or root["queue_universe_id"] != universe_id
                or root["workspace_budget_closing_reason"] not in _REASONS
                or _active(conn, root_run_id, epoch)
            ):
                raise FamilyRefused("family release is not current and terminal")
            if self.empty() is not True:
                raise FamilyRefused("family release is not kernel-empty")


def _after_fork():
    global _mutex_guard, _mutexes
    _mutex_guard = threading.Lock()
    _mutexes = weakref.WeakValueDictionary()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


@contextmanager
def try_family_fence(base_path: str | Path, root_run_id: str):
    """Nonblocking interprocess exclusion. Sidecar inodes are never unlinked.

    This lock is not authority. The caller must revalidate current rows under it.
    No descriptor from this guard may be inherited by a job.
    """
    from tinyassets.runs import runs_db_path

    if (
        not isinstance(root_run_id, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", root_run_id) is None
    ):
        raise FamilyRefused("invalid server family identity")
    database = runs_db_path(base_path).resolve()
    directory = database.parent / ".workspace-family-locks"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not stat.S_ISDIR(directory.lstat().st_mode):
        raise FamilyRefused("family fence directory is not a real directory")
    path = directory / (root_run_id + ".lock")
    with _mutex_guard:
        mutex = _mutexes.setdefault(str(path), threading.Lock())
    if not mutex.acquire(blocking=False):
        yield None
        return
    fd = None
    guard = None
    try:
        if path.is_symlink():
            raise FamilyRefused("family fence cannot follow a link")
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.set_inheritable(fd, False)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise FamilyRefused("family fence must be a private regular file")
        if _try_os_lock(fd):
            guard = FamilyFence(database, root_run_id)
        yield guard
    finally:
        if guard is not None:
            guard._held = False
        try:
            if fd is not None:
                os.close(fd)
        finally:
            mutex.release()


def _row(conn, run_id):
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise FamilyRefused("unknown family member")
    return row


@contextmanager
def family_fence(base_path: str | Path, root_run_id: str, *, timeout_s: float = 5.0):
    """Bounded serialization for short concurrent admissions; never hold a DB write lock.

    Reconciliation may use try_family_fence to skip busy roots. Execution callers
    wait outside the fence so ordinary parallel child nodes don't fail on overlap.
    Nothing is dispatched/replayed while waiting, and authority is read afterwards.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        with try_family_fence(base_path, root_run_id) as fence:
            if fence is not None:
                yield fence
                return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FamilyRefused("workspace family busy")
        time.sleep(min(0.025, remaining))


def _member(row):
    root, epoch = row["workspace_budget_root_run_id"], row["workspace_budget_epoch"]
    if not root or type(epoch) is not int or epoch < 1:
        raise FamilyRefused("unknown family association")
    if not row["owner_user_id"] or not row["queue_universe_id"] or not row["actor"]:
        raise FamilyRefused("unknown family identity")
    return FamilyMember(
        row["run_id"],
        root,
        epoch,
        row["owner_user_id"],
        row["queue_universe_id"],
        row["actor"],
        row["runtime_instance_id"] or "",
        row["worker_id"] or "",
    )


def _cancelled(conn, *run_ids):
    return any(
        conn.execute("SELECT 1 FROM run_cancels WHERE run_id=?", (rid,)).fetchone() is not None
        for rid in run_ids
    )


def member_in_transaction(conn, fence: FamilyFence, run_id: str) -> FamilyMember:
    fence.require(conn)
    member = _member(_row(conn, run_id))
    return validate_in_transaction(conn, fence, member)


def execution_member(
    base_path: str | Path,
    run_id: str,
    *,
    for_compile: bool = False,
) -> FamilyMember | None:
    """Read current typed context; only wholly unassociated legacy rows return None.

    Called outside legacy actor-fallback handlers. An unreadable/partial/stale
    association is an error, never an invitation to mint a replacement root.
    """
    from tinyassets.runs import _connect

    with _connect(base_path) as conn:
        row = _row(conn, run_id)
        if all(
            row[key] is None
            for key in (
                "workspace_budget_root_run_id",
                "workspace_budget_epoch",
                "workspace_budget_closing_reason",
            )
        ):
            return None
        member = _member(row)
    with family_fence(base_path, member.root_run_id) as fence:
        with _connect(base_path) as conn:
            _validate_identity(conn, fence, member)
            allowed = ("queued", "running", "resumed") if for_compile else ("running",)
            if _row(conn, run_id)["status"] not in allowed:
                raise FamilyRefused("invoking family member is not running or preparing")
            return member


@contextmanager
def run_transaction(base_path: str | Path, run_id: str, *, expected: FamilyMember | None = None):
    """Short lifecycle transaction in the same fence order as child insertion.

    Missing/wholly legacy rows retain legacy behavior. Partially known identity
    is never converted to legacy. No pool/IO/kill wait belongs in this transaction.
    """
    from tinyassets.runs import _connect

    with _connect(base_path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        known = row is not None and any(
            row[key] is not None
            for key in (
                "workspace_budget_root_run_id",
                "workspace_budget_epoch",
                "workspace_budget_closing_reason",
            )
        )
        member = _member(row) if known else None
        if expected is not None and (type(expected) is not FamilyMember or member != expected):
            raise FamilyRefused("stale worker lifecycle family identity or epoch")
    scope = family_fence(base_path, member.root_run_id) if member else nullcontext()
    with scope as fence, _connect(base_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if member is not None:
            fence.require(conn, write=True)
            if (
                _member(_row(conn, run_id)) != member
                or _row(conn, member.root_run_id)["workspace_budget_epoch"] != member.epoch
            ):
                raise FamilyRefused("stale lifecycle family identity or epoch")
        yield conn, member, fence


@contextmanager
def status_transaction(
    base_path: str | Path,
    run_id: str,
    status: str | None,
    *,
    expected: FamilyMember | None = None,
    expected_statuses=None,
):
    with run_transaction(base_path, run_id, expected=expected) as (conn, member, fence):
        if member is not None and status in ("queued", "running", "resumed"):
            _validate_identity(conn, fence, member)
        from tinyassets.runs import _RUN_EXECUTION_GUARD, RunExecutionAuthorityLost

        guard = _RUN_EXECUTION_GUARD.get()
        owned = guard is not None and guard.run_id == run_id
        if owned:
            guard.require_held(conn)
        if status is not None and (member is not None or owned or expected_statuses is not None):

            allowed = expected_statuses
            if allowed is None:
                allowed = (
                    {"queued", "resumed"}
                    if status == "running"
                    else {"interrupted"}
                    if status == "resumed"
                    else {"queued", "running", "resumed", status}
                    if status in _TERMINAL
                    else {status}
                )
            if _row(conn, run_id)["status"] not in allowed:
                raise RunExecutionAuthorityLost("Run lost its expected prior status.")
        yield conn
        if member is not None and status in _TERMINAL:
            if member.run_id == member.root_run_id and status != "completed":
                close_in_transaction(conn, fence, member.epoch, status)
            elif not _active(conn, member.root_run_id, member.epoch):
                # This is closing INTENT only. Locks/reservations still require
                # exact kernel-empty and member cleanup proofs before release.
                close_in_transaction(conn, fence, member.epoch, "drained")


def validate_in_transaction(conn, fence: FamilyFence, member: FamilyMember) -> FamilyMember:
    _validate_identity(conn, fence, member)
    if _row(conn, member.run_id)["status"] != "running":
        raise FamilyRefused("invoking family member is not running")
    return member


def _validate_identity(conn, fence: FamilyFence, member: FamilyMember) -> None:
    fence.require(conn)
    if type(member) is not FamilyMember or member.root_run_id != fence.root_run_id:
        raise FamilyRefused("family fence identity mismatch")
    root = _row(conn, member.root_run_id)
    row = _row(conn, member.run_id)
    if (
        root["workspace_budget_epoch"] != member.epoch
        or row["workspace_budget_epoch"] != member.epoch
    ):
        raise FamilyRefused("stale family epoch")
    if root["workspace_budget_closing_reason"] != "":
        raise FamilyRefused("family is closed or unknown")
    if (
        _member(row) != member
        or root["workspace_budget_root_run_id"] != member.root_run_id
        or root["owner_user_id"] != member.owner_user_id
        or root["queue_universe_id"] != member.universe_id
    ):
        raise FamilyRefused("family identity mismatch")
    if _cancelled(conn, member.run_id, member.root_run_id):
        raise FamilyRefused("family cancellation requested")


def assign_in_transaction(
    conn, fence: FamilyFence, run_id: str, *, parent: FamilyMember | None = None
) -> FamilyMember:
    """Only the authenticated insert caller uses this before committing its row.

    Call after existing child/private-owner authorization, never from inputs or
    lineage. This seam does not itself authorize invoking a child definition.
    """
    fence.require(conn, write=True)
    row = _row(conn, run_id)
    if any(
        row[key] is not None
        for key in (
            "workspace_budget_root_run_id",
            "workspace_budget_epoch",
            "workspace_budget_closing_reason",
        )
    ):
        raise FamilyRefused("family association is already assigned")
    if not row["owner_user_id"] or not row["queue_universe_id"] or not row["actor"]:
        raise FamilyRefused("unknown authenticated family identity")
    if parent is None:
        if fence.root_run_id != run_id:
            raise FamilyRefused("new root must own its family fence")
        root, epoch, closing = run_id, 1, ""
    else:
        validate_in_transaction(conn, fence, parent)
        if (row["owner_user_id"], row["queue_universe_id"], row["actor"]) != (
            parent.owner_user_id,
            parent.universe_id,
            parent.actor,
        ):
            raise FamilyRefused("child family identity mismatch")
        root, epoch, closing = parent.root_run_id, parent.epoch, None
    conn.execute(
        "UPDATE runs SET workspace_budget_root_run_id=?,workspace_budget_epoch=?,"
        "workspace_budget_closing_reason=? WHERE run_id=?",
        (root, epoch, closing, run_id),
    )
    return _member(_row(conn, run_id))


def close_in_transaction(conn, fence: FamilyFence, epoch: int, reason: str) -> bool:
    fence.require(conn, write=True)
    if reason not in _REASONS:
        raise FamilyRefused("unknown family close reason")
    root = _row(conn, fence.root_run_id)
    if root["workspace_budget_epoch"] != epoch:
        return False
    if root["workspace_budget_closing_reason"] is None:
        raise FamilyRefused("unknown family closing state")
    conn.execute(
        "UPDATE runs SET workspace_budget_closing_reason=? WHERE run_id=? "
        "AND workspace_budget_epoch=? AND workspace_budget_closing_reason=''",
        (reason, fence.root_run_id, epoch),
    )
    return True


def _active(conn, root, epoch):
    return (
        conn.execute(
            "SELECT 1 FROM runs WHERE workspace_budget_root_run_id=? "
            "AND workspace_budget_epoch=? AND status NOT IN (?,?,?,?) LIMIT 1",
            (root, epoch, *_TERMINAL),
        ).fetchone()
        is not None
    )


def prepare_release_in_transaction(
    conn, fence: FamilyFence, epoch: int, *, empty: Callable[[], bool]
) -> bool:
    fence.require(conn, write=True)
    root = _row(conn, fence.root_run_id)
    if root["workspace_budget_epoch"] != epoch or _active(conn, fence.root_run_id, epoch):
        return False
    close_in_transaction(conn, fence, epoch, "drained")
    # Driver must verify exact owned kernel group/inode/populated0, never a PID.
    return empty() is True


def resume_in_transaction(
    conn, fence: FamilyFence, member: FamilyMember, *, empty: Callable[[], bool]
) -> FamilyMember:
    """Prepare a fresh incarnation for an already-authorized interrupted resume.

    Current owner/private-child authority is rechecked by the resume caller. Only
    this member and root metadata advance; old siblings and receipts stay old.
    Caller persists the existing resume transition before releasing the fence.
    """
    fence.require(conn, write=True)
    if type(member) is not FamilyMember or member.root_run_id != fence.root_run_id:
        raise FamilyRefused("resume family fence identity mismatch")
    row, root = _row(conn, member.run_id), _row(conn, member.root_run_id)
    if _member(row) != member or root["workspace_budget_epoch"] != member.epoch:
        raise FamilyRefused("stale resume epoch or identity")
    if row["status"] != "interrupted":
        raise FamilyRefused("only interrupted family members may resume")
    if _cancelled(conn, member.run_id, member.root_run_id):
        raise FamilyRefused("cancelled family cannot resume")
    if (
        root["owner_user_id"] != member.owner_user_id
        or root["queue_universe_id"] != member.universe_id
    ):
        raise FamilyRefused("resume family identity mismatch")
    if root["workspace_budget_closing_reason"] not in _REASONS:
        raise FamilyRefused("old family is not closed")
    if _active(conn, member.root_run_id, member.epoch) or empty() is not True:
        raise FamilyRefused("old family is not terminal and empty")
    epoch = member.epoch + 1
    conn.execute(
        "UPDATE runs SET workspace_budget_epoch=?,workspace_budget_closing_reason='' "
        "WHERE run_id=?",
        (epoch, member.root_run_id),
    )
    conn.execute("UPDATE runs SET workspace_budget_epoch=? WHERE run_id=?", (epoch, member.run_id))
    return _member(_row(conn, member.run_id))
