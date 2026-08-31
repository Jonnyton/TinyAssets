"""Two storage classes back a workspace job: a universe's permanent space, whose
immutable generations are charged to its tier quota, and a shared scratch pool of
per-job leases that is never charged to any universe. Admission is one
``BEGIN IMMEDIATE`` transaction - the hourly ledger reservation, the pool total or
the universe quota, both job locks and the ``ACTIVE`` lease either all happen or
none of them do, so two concurrent checkouts can never oversubscribe the box.
Release is an outbox rather than a direct write because a crash between deleting
bytes and recording the deletion has to be repairable: a run's terminal status and
its outbox entries commit together, and one processor claims each entry
at-least-once, reconciles the filesystem against a deterministic quarantine name,
and only then marks the lease ``AVAILABLE`` or ``LOST``. This module never creates
directories and never reads an env var - it computes paths and routes every
filesystem step through an injected :class:`PoolFilesystem`, so the caller keeps
the no-follow directory handle that actually owns the bytes and the tests can
drive every crash window.

The tables live in the RUNS database so that a run's terminal row and its outbox
entries are one transaction. Every function that participates in a caller's
transaction therefore takes an OPEN ``sqlite3.Connection``; standalone functions
take ``db: Path`` and open their own ``BEGIN IMMEDIATE``.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

GIB = 1024**3

#: Defaults from design note ``workspace-node`` D4.
DEFAULT_POOL_BYTES_CAP = 20 * GIB
DEFAULT_LEASE_BYTES_CAP = 4 * GIB
DEFAULT_JOBS_PER_HOUR = 10
DEFAULT_BYTES_PER_HOUR = 20 * GIB
#: The rolling ledger window, in seconds.
WINDOW_S = 3600
#: One host-wide slot in this change; the runner sidecar is what lifts it.
HOST_SLOT = "slot-0"
DEFAULT_CLAIM_TTL_S = 300
#: A negative TTL steals every claim: used by the startup sweep, where nothing
#: else is running and a claim can only be a dead process's.
STEAL_ALL_TTL_S = -1.0

STORAGE_SCRATCH = "scratch"
STORAGE_UNIVERSE = "universe"
STORAGE_CLASSES = (STORAGE_SCRATCH, STORAGE_UNIVERSE)

STATE_RESERVED = "RESERVED"
STATE_ACTIVE = "ACTIVE"
STATE_QUARANTINED = "QUARANTINED"
STATE_WIPING = "WIPING"
STATE_AVAILABLE = "AVAILABLE"
STATE_LOST = "LOST"

ACTION_WIPE_SCRATCH = "wipe_scratch"
ACTION_DISCARD_PERMANENT = "discard_permanent_generation"
ACTION_RELEASE_LOCK_ONLY = "release_lock_only"

SCOPE_UNIVERSE = "universe"
SCOPE_HOST = "host"

KIND_JOBS = "jobs"
KIND_BYTES = "bytes"

#: Refusal codes (design note D6). One actionable class per refusal.
REFUSED_POOL_BUSY = "workspace_pool_busy"
REFUSED_BUSY = "workspace_busy"
REFUSED_QUOTA = "workspace_quota_exceeded"

#: Outcomes ``process_entry`` returns and records on the entry.
OUTCOME_WIPED = "wiped"
OUTCOME_RELEASED = "released"
OUTCOME_LOST = "lost"
OUTCOME_LOST_CLAIM = "lost_claim"
OUTCOME_ALREADY_DONE = "already_done"
#: The entry names a generation this module has no lease row for, so its bytes
#: cannot be located. Recorded, not silently dropped, and never retried forever -
#: a wedged entry would block every admission (see ``admission_open``).
OUTCOME_UNKNOWN_TARGET = "unknown_target"

QUARANTINE_DIR = ".quarantine"
WORKSPACES_DIR = "workspaces"


class WorkspacePoolRefused(Exception):
    """A refusal a caller can act on: ``code`` is one of the three D6 classes."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Lease:
    """One admitted workspace, scratch or permanent. ``path`` is computed, never
    created by this module; the caller creates it under a no-follow handle."""

    lease_id: str
    universe_id: str
    connection_id: str
    repo_key: str
    storage_class: str
    generation: int
    state: str
    reserved_bytes: int
    measured_bytes: int | None
    run_id: str | None
    path: Path
    quarantine_path: Path
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class OutboxEntry:
    """Work owed after a run's terminal transaction committed."""

    entry_id: int
    run_id: str
    action: str
    lease_id: str | None
    repo_key: str | None
    generation: int | None
    universe_id: str
    release_universe_lock: bool
    release_host_lock: bool
    claim_token: str | None
    claimed_at: float | None
    created_at: float


@dataclass(frozen=True)
class PoolUsage:
    """Scratch-pool totals. ``LOST`` leases keep their bytes charged forever."""

    reserved_bytes: int
    lost_bytes: int
    active_leases: int
    lost_leases: int


@dataclass(frozen=True)
class LedgerUsage:
    """A universe's rolling-hour ``workspace`` usage. ``clears_at`` is when the
    oldest in-window charge falls out, or None when nothing is charged."""

    jobs: int
    bytes: int
    clears_at: float | None


class PoolFilesystem(Protocol):
    """The only filesystem this module touches, injected so the caller owns the
    no-follow handle. ``exists`` must NOT follow links (a dangling symlink is
    present); ``remove_tree_no_follow`` must never descend into a symlinked
    directory."""

    def exists(self, path: Path) -> bool: ...

    def rename(self, src: Path, dst: Path) -> None: ...

    def remove_tree_no_follow(self, path: Path) -> None: ...


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the five pool tables. Call INSIDE the caller's transaction, as
    ``engine_admissions`` does: two first touches must not race the create."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS workspace_leases ("
        "lease_id TEXT PRIMARY KEY, universe_id TEXT NOT NULL, "
        "connection_id TEXT NOT NULL, repo_key TEXT NOT NULL, "
        "storage_class TEXT NOT NULL CHECK (storage_class IN ('scratch','universe')), "
        "generation INTEGER NOT NULL, "
        "state TEXT NOT NULL CHECK (state IN "
        "('RESERVED','ACTIVE','QUARANTINED','WIPING','AVAILABLE','LOST')), "
        "reserved_bytes INTEGER NOT NULL, measured_bytes INTEGER, run_id TEXT, "
        "path TEXT NOT NULL, quarantine_path TEXT NOT NULL, "
        "created_at REAL NOT NULL, updated_at REAL NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS workspace_leases_repo "
        "ON workspace_leases(universe_id, repo_key, generation)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS workspace_locks ("
        'scope TEXT NOT NULL CHECK (scope IN (\'universe\',\'host\')), "key" TEXT NOT NULL, '
        "run_id TEXT NOT NULL, lease_id TEXT, acquired_at REAL NOT NULL, "
        'PRIMARY KEY (scope, "key"))'
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS workspace_outbox ("
        "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, "
        "action TEXT NOT NULL CHECK (action IN "
        "('wipe_scratch','discard_permanent_generation','release_lock_only')), "
        "lease_id TEXT, repo_key TEXT, generation INTEGER, universe_id TEXT NOT NULL, "
        "release_universe_lock INTEGER NOT NULL, release_host_lock INTEGER NOT NULL, "
        "claim_token TEXT, claimed_at REAL, done_at REAL, outcome TEXT, "
        "created_at REAL NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS workspace_outbox_pending "
        "ON workspace_outbox(done_at, entry_id)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS workspace_generations ("
        "repo_key TEXT NOT NULL, universe_id TEXT NOT NULL, generation INTEGER NOT NULL, "
        "path TEXT NOT NULL, PRIMARY KEY (universe_id, repo_key))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS workspace_ledger ("
        "universe_id TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('jobs','bytes')), "
        "amount INTEGER NOT NULL, reserved INTEGER NOT NULL, run_id TEXT NOT NULL, "
        "lease_id TEXT, created_at REAL NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS workspace_ledger_window "
        "ON workspace_ledger(universe_id, kind, created_at)"
    )


def _connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


# --------------------------------------------------------------------------
# validation and paths
# --------------------------------------------------------------------------


def _require_path_key(field: str, value: str) -> str:
    """A value that becomes a path component must not be able to escape one.

    ``repo_key`` and ``lease_id`` end up in both a directory name and the
    deterministic quarantine name, so a separator or a dot-segment is a
    traversal. Fail loudly rather than sanitise: a sanitised key collides.
    """
    if not isinstance(value, str) or not re.fullmatch("[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError(
            f"{field} must match [A-Za-z0-9][A-Za-z0-9._-]* (no separators), got {value!r}"
        )
    return value


def _require_storage_class(storage_class: str) -> str:
    if storage_class not in STORAGE_CLASSES:
        raise ValueError(f"storage_class must be one of {STORAGE_CLASSES}, got {storage_class!r}")
    return storage_class


def scratch_paths(pool_root: Path, lease_id: str, generation: int) -> tuple[Path, Path]:
    """``(<pool_root>/<lease_id>, <pool_root>/.quarantine/<lease_id>.<generation>)``."""
    return (
        Path(pool_root) / lease_id,
        Path(pool_root) / QUARANTINE_DIR / f"{lease_id}.{generation}",
    )


def universe_paths(universe_root: Path, repo_key: str, generation: int) -> tuple[Path, Path]:
    """``(<root>/workspaces/<repo>/<gen>, <root>/workspaces/.quarantine/<repo>.<gen>)``."""
    workspaces = Path(universe_root) / WORKSPACES_DIR
    return (
        workspaces / repo_key / str(generation),
        workspaces / QUARANTINE_DIR / f"{repo_key}.{generation}",
    )


def _lease_from_row(row: sqlite3.Row | tuple) -> Lease:
    return Lease(
        lease_id=row[0],
        universe_id=row[1],
        connection_id=row[2],
        repo_key=row[3],
        storage_class=row[4],
        generation=int(row[5]),
        state=row[6],
        reserved_bytes=int(row[7]),
        measured_bytes=None if row[8] is None else int(row[8]),
        run_id=row[9],
        path=Path(row[10]),
        quarantine_path=Path(row[11]),
        created_at=float(row[12]),
        updated_at=float(row[13]),
    )


_LEASE_COLUMNS = (
    "lease_id, universe_id, connection_id, repo_key, storage_class, generation, state, "
    "reserved_bytes, measured_bytes, run_id, path, quarantine_path, created_at, updated_at"
)


def get_lease(db: Path, lease_id: str) -> Lease | None:
    """The lease row, or None. Read-only; no transaction."""
    conn = _connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        row = conn.execute(
            f"SELECT {_LEASE_COLUMNS} FROM workspace_leases WHERE lease_id = ?", (lease_id,)
        ).fetchone()
        conn.commit()
        return None if row is None else _lease_from_row(row)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# admission
# --------------------------------------------------------------------------


def _window_clears_at(
    conn: sqlite3.Connection, universe_id: str, kind: str, cutoff: float
) -> float | None:
    row = conn.execute(
        "SELECT MIN(created_at) FROM workspace_ledger "
        "WHERE universe_id = ? AND kind = ? AND created_at >= ?",
        (universe_id, kind, cutoff),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0]) + WINDOW_S


def _ledger_sum(conn: sqlite3.Connection, universe_id: str, kind: str, cutoff: float) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM workspace_ledger "
        "WHERE universe_id = ? AND kind = ? AND created_at >= ?",
        (universe_id, kind, cutoff),
    ).fetchone()
    return int(row[0])


def _scratch_pool_reserved(conn: sqlite3.Connection) -> int:
    """Reserved bytes of every scratch lease that is not ``AVAILABLE``.

    ``LOST`` leases are included forever - that is the point of the state: bytes
    we failed to delete are still bytes on the box. Permanent generations are NOT
    in this sum; they are charged to the universe's own quota.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(reserved_bytes), 0) FROM workspace_leases "
        "WHERE storage_class = ? AND state != ?",
        (STORAGE_SCRATCH, STATE_AVAILABLE),
    ).fetchone()
    return int(row[0])


def _next_generation(conn: sqlite3.Connection, universe_id: str, repo_key: str) -> int:
    lease_max = conn.execute(
        "SELECT COALESCE(MAX(generation), 0) FROM workspace_leases "
        "WHERE universe_id = ? AND repo_key = ?",
        (universe_id, repo_key),
    ).fetchone()[0]
    published = conn.execute(
        "SELECT COALESCE(MAX(generation), 0) FROM workspace_generations "
        "WHERE universe_id = ? AND repo_key = ?",
        (universe_id, repo_key),
    ).fetchone()[0]
    return int(max(int(lease_max), int(published))) + 1


def _acquire_lock(
    conn: sqlite3.Connection,
    *,
    scope: str,
    key: str,
    run_id: str,
    lease_id: str,
    ts: float,
) -> None:
    """Reentrant for the run that holds it, ``workspace_busy`` for anyone else.

    The lock belongs to the RUN, not to the lease: a run's later workspace nodes
    and its push reuse it, and only the run's terminal outbox entry releases it.
    A reentrant acquisition leaves ``lease_id``/``acquired_at`` as the first
    holder wrote them.
    """
    row = conn.execute(
        'SELECT run_id FROM workspace_locks WHERE scope = ? AND "key" = ?', (scope, key)
    ).fetchone()
    if row is not None:
        if row[0] == run_id:
            return
        raise WorkspacePoolRefused(
            REFUSED_BUSY, f"{scope} lock {key!r} is held by run {row[0]!r}"
        )
    conn.execute(
        'INSERT INTO workspace_locks (scope, "key", run_id, lease_id, acquired_at) '
        "VALUES (?, ?, ?, ?, ?)",
        (scope, key, run_id, lease_id, ts),
    )


def _no_universe_bytes(_universe_id: str) -> int:
    """Scratch never asks a universe what it is using: the placeholder that
    makes that explicit instead of leaving the callable None."""
    return 0


def admit(
    db: Path,
    *,
    universe_id: str,
    connection_id: str,
    repo_key: str,
    storage_class: str,
    run_id: str,
    max_bytes: int,
    pool_root: Path,
    universe_root: Path,
    universe_quota_bytes: int | None = None,
    universe_used_bytes_fn: Callable[[str], int] | None = None,
    pool_bytes_cap: int = DEFAULT_POOL_BYTES_CAP,
    lease_bytes_cap: int = DEFAULT_LEASE_BYTES_CAP,
    jobs_per_hour: int = DEFAULT_JOBS_PER_HOUR,
    bytes_per_hour: int = DEFAULT_BYTES_PER_HOUR,
    host_slot: str = HOST_SLOT,
    now: Callable[[], float] = time.time,
    lease_id_factory: Callable[[], str] = secrets.token_hex,
) -> Lease:
    """Admit one workspace job in ONE ``BEGIN IMMEDIATE`` transaction.

    In order: the startup barrier, the rolling-hour ledger (jobs then bytes), the
    pool total (scratch) or the universe quota (permanent), the universe lock and
    the host slot, the ledger reservation of ``max_bytes``, and the ``ACTIVE``
    lease. Any refusal or error rolls the whole transaction back, so a refused
    admission moves no bytes and leaves an existing generation untouched.

    ``universe_used_bytes_fn`` is called inside the transaction and MUST NOT open
    this database. The returned lease's ``path`` does not exist yet: the caller
    creates it under a directory handle resolved without following links.
    """
    _require_storage_class(storage_class)
    _require_path_key("repo_key", repo_key)
    if not run_id:
        raise ValueError("run_id is required")
    if not universe_id:
        raise ValueError("universe_id is required")
    if int(max_bytes) < 0:
        raise ValueError(f"max_bytes must be >= 0, got {max_bytes}")
    max_bytes = int(max_bytes)
    quota_bytes = 0
    used_fn: Callable[[str], int] = _no_universe_bytes
    if storage_class == STORAGE_UNIVERSE:
        if universe_quota_bytes is None:
            raise ValueError("universe storage needs universe_quota_bytes")
        if universe_used_bytes_fn is None:
            raise ValueError("universe storage needs universe_used_bytes_fn")
        quota_bytes = int(universe_quota_bytes)
        used_fn = universe_used_bytes_fn

    ts = float(now())
    cutoff = ts - WINDOW_S
    lease_id = _require_path_key("lease_id", lease_id_factory())

    conn = _connect(db)
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
            ensure_schema(conn)

            # The startup barrier. "No new workspace job is admitted until every
            # old entry reached AVAILABLE or LOST" - a directory is never
            # recycled in place and there is no grace-window reuse.
            pending = int(
                conn.execute(
                    "SELECT COUNT(*) FROM workspace_outbox WHERE done_at IS NULL"
                ).fetchone()[0]
            )
            if pending:
                raise WorkspacePoolRefused(
                    REFUSED_POOL_BUSY,
                    f"startup reconciliation pending: {pending} outbox entr"
                    f"{'y' if pending == 1 else 'ies'} not yet AVAILABLE or LOST",
                )

            # (a) the rolling-hour workspace ledger.
            jobs = _ledger_sum(conn, universe_id, KIND_JOBS, cutoff)
            if jobs + 1 > jobs_per_hour:
                clears = _window_clears_at(conn, universe_id, KIND_JOBS, cutoff)
                raise WorkspacePoolRefused(
                    REFUSED_QUOTA,
                    f"workspace jobs per hour ({jobs_per_hour}) exhausted for "
                    f"{universe_id}: {jobs} charged, clears_at={clears}",
                )
            charged = _ledger_sum(conn, universe_id, KIND_BYTES, cutoff)
            if charged + max_bytes > bytes_per_hour:
                clears = _window_clears_at(conn, universe_id, KIND_BYTES, cutoff)
                raise WorkspacePoolRefused(
                    REFUSED_QUOTA,
                    f"workspace bytes per hour ({bytes_per_hour}) exhausted for "
                    f"{universe_id}: {charged} charged + {max_bytes} requested, "
                    f"clears_at={clears}",
                )

            # (b) the storage bound: the shared pool, or the universe's quota.
            if storage_class == STORAGE_SCRATCH:
                if max_bytes > lease_bytes_cap:
                    raise WorkspacePoolRefused(
                        REFUSED_QUOTA,
                        f"lease bound ({lease_bytes_cap}) is smaller than the "
                        f"requested {max_bytes}",
                    )
                reserved_bytes = int(lease_bytes_cap)
                pool_reserved = _scratch_pool_reserved(conn)
                if pool_reserved + reserved_bytes > pool_bytes_cap:
                    raise WorkspacePoolRefused(
                        REFUSED_POOL_BUSY,
                        f"scratch pool ({pool_bytes_cap}) has {pool_reserved} reserved; "
                        f"a {reserved_bytes} lease does not fit",
                    )
            else:
                reserved_bytes = max_bytes
                used = int(used_fn(universe_id))
                if used + max_bytes > quota_bytes:
                    raise WorkspacePoolRefused(
                        REFUSED_QUOTA,
                        f"universe quota ({quota_bytes}) exhausted for "
                        f"{universe_id}: {used} used + {max_bytes} requested",
                    )

            # (c) the durable job locks: one per universe, one host-wide slot.
            _acquire_lock(
                conn,
                scope=SCOPE_UNIVERSE,
                key=universe_id,
                run_id=run_id,
                lease_id=lease_id,
                ts=ts,
            )
            _acquire_lock(
                conn, scope=SCOPE_HOST, key=host_slot, run_id=run_id, lease_id=lease_id, ts=ts
            )

            # (d) reserve the maximum charge BEFORE any bytes move.
            conn.execute(
                "INSERT INTO workspace_ledger "
                "(universe_id, kind, amount, reserved, run_id, lease_id, created_at) "
                "VALUES (?, ?, 1, 0, ?, ?, ?)",
                (universe_id, KIND_JOBS, run_id, lease_id, ts),
            )
            conn.execute(
                "INSERT INTO workspace_ledger "
                "(universe_id, kind, amount, reserved, run_id, lease_id, created_at) "
                "VALUES (?, ?, ?, 1, ?, ?, ?)",
                (universe_id, KIND_BYTES, max_bytes, run_id, lease_id, ts),
            )

            # (e) the lease itself.
            generation = _next_generation(conn, universe_id, repo_key)
            if storage_class == STORAGE_SCRATCH:
                path, quarantine_path = scratch_paths(Path(pool_root), lease_id, generation)
            else:
                path, quarantine_path = universe_paths(
                    Path(universe_root), repo_key, generation
                )
            conn.execute(
                "INSERT INTO workspace_leases "
                "(lease_id, universe_id, connection_id, repo_key, storage_class, generation, "
                "state, reserved_bytes, measured_bytes, run_id, path, quarantine_path, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)",
                (
                    lease_id,
                    universe_id,
                    connection_id,
                    repo_key,
                    storage_class,
                    generation,
                    STATE_ACTIVE,
                    reserved_bytes,
                    run_id,
                    str(path),
                    str(quarantine_path),
                    ts,
                    ts,
                ),
            )
            conn.commit()
        except BaseException:
            # Everything rolls back together, the schema creation included: it is
            # a CREATE TABLE IF NOT EXISTS, not a migration, so redoing it costs
            # nothing and a half-applied admission would cost a leaked bound.
            conn.rollback()
            raise
    finally:
        conn.close()

    return Lease(
        lease_id=lease_id,
        universe_id=universe_id,
        connection_id=connection_id,
        repo_key=repo_key,
        storage_class=storage_class,
        generation=generation,
        state=STATE_ACTIVE,
        reserved_bytes=reserved_bytes,
        measured_bytes=None,
        run_id=run_id,
        path=path,
        quarantine_path=quarantine_path,
        created_at=ts,
        updated_at=ts,
    )


def reconcile_bytes(
    db: Path, lease_id: str, measured_bytes: int, *, now: Callable[[], float] = time.time
) -> int:
    """Reconcile the ledger reservation DOWNWARD to what actually moved.

    Never upward past the reservation: the admission is what bounded the
    transfer, so a measurement above it is clamped rather than charged. An
    interrupted or unknown transfer never calls this at all, and the maximum
    stays charged for the rest of the hour. The lease's ``reserved_bytes`` is
    left at the lease bound - the POOL reservation stands until release.
    Returns the bytes now charged for the hour.
    """
    if int(measured_bytes) < 0:
        raise ValueError(f"measured_bytes must be >= 0, got {measured_bytes}")
    measured_bytes = int(measured_bytes)
    ts = float(now())
    conn = _connect(db)
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
            ensure_schema(conn)
            lease = conn.execute(
                "SELECT lease_id FROM workspace_leases WHERE lease_id = ?", (lease_id,)
            ).fetchone()
            if lease is None:
                raise ValueError(f"unknown lease {lease_id!r}")
            row = conn.execute(
                "SELECT rowid, amount FROM workspace_ledger "
                "WHERE lease_id = ? AND kind = ? ORDER BY rowid LIMIT 1",
                (lease_id, KIND_BYTES),
            ).fetchone()
            if row is None:
                raise ValueError(f"lease {lease_id!r} has no bytes reservation to reconcile")
            rowid, amount = int(row[0]), int(row[1])
            charged = min(amount, measured_bytes)
            conn.execute(
                "UPDATE workspace_ledger SET amount = ?, reserved = 0 WHERE rowid = ?",
                (charged, rowid),
            )
            conn.execute(
                "UPDATE workspace_leases SET measured_bytes = ?, updated_at = ? "
                "WHERE lease_id = ?",
                (measured_bytes, ts, lease_id),
            )
            conn.commit()
            return charged
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# publication and the terminal outbox (inside the caller's transaction)
# --------------------------------------------------------------------------


def publish_generation(
    conn: sqlite3.Connection,
    *,
    universe_id: str,
    repo_key: str,
    generation: int,
    path: Path | str,
) -> int | None:
    """Switch a repo key's authoritative generation atomically.

    Runs inside the CALLER's transaction. Returns the generation it replaced, or
    None if this is the first - the caller enqueues
    ``discard_permanent_generation`` for the returned number. Publishing
    backwards is a bug, not a rollback: generations are immutable-by-host and
    only ever move forward.
    """
    _require_path_key("repo_key", repo_key)
    ensure_schema(conn)
    row = conn.execute(
        "SELECT generation FROM workspace_generations WHERE universe_id = ? AND repo_key = ?",
        (universe_id, repo_key),
    ).fetchone()
    previous = None if row is None else int(row[0])
    if previous is not None and int(generation) <= previous:
        raise ValueError(
            f"generation {generation} does not follow the published {previous} "
            f"for {universe_id}/{repo_key}"
        )
    conn.execute(
        "INSERT INTO workspace_generations (repo_key, universe_id, generation, path) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (universe_id, repo_key) DO UPDATE SET "
        "generation = excluded.generation, path = excluded.path",
        (repo_key, universe_id, int(generation), str(path)),
    )
    return previous


def _insert_entry(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    universe_id: str,
    action: str,
    lease_id: str | None,
    repo_key: str | None,
    generation: int | None,
    release_universe_lock: bool,
    release_host_lock: bool,
    created_at: float,
) -> int:
    cur = conn.execute(
        "INSERT INTO workspace_outbox "
        "(run_id, action, lease_id, repo_key, generation, universe_id, "
        "release_universe_lock, release_host_lock, claim_token, claimed_at, done_at, "
        "outcome, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?)",
        (
            run_id,
            action,
            lease_id,
            repo_key,
            None if generation is None else int(generation),
            universe_id,
            1 if release_universe_lock else 0,
            1 if release_host_lock else 0,
            created_at,
        ),
    )
    return int(cur.lastrowid or 0)


def enqueue_terminal(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    universe_id: str,
    lease: Lease | None,
    storage_class: str | None = None,
    release_locks: bool = True,
    now: Callable[[], float] = time.time,
) -> int:
    """Write the work a finished run owes, INSIDE its terminal transaction.

    A scratch lease becomes ``wipe_scratch``; a run with no lease, or one whose
    permanent generation is still the authoritative one, becomes
    ``release_lock_only``. The lease stays ``ACTIVE`` until the processor moves
    it: the ENTRY is what says work is owed, and it committed with the run's
    terminal status. Returns the entry id.
    """
    ensure_schema(conn)
    ts = float(now())
    if storage_class is not None:
        _require_storage_class(storage_class)
    effective = storage_class if lease is None else lease.storage_class
    if lease is not None and effective == STORAGE_SCRATCH:
        return _insert_entry(
            conn,
            run_id=run_id,
            universe_id=universe_id,
            action=ACTION_WIPE_SCRATCH,
            lease_id=lease.lease_id,
            repo_key=lease.repo_key,
            generation=lease.generation,
            release_universe_lock=release_locks,
            release_host_lock=release_locks,
            created_at=ts,
        )
    return _insert_entry(
        conn,
        run_id=run_id,
        universe_id=universe_id,
        action=ACTION_RELEASE_LOCK_ONLY,
        lease_id=None,
        repo_key=None if lease is None else lease.repo_key,
        generation=None if lease is None else lease.generation,
        release_universe_lock=release_locks,
        release_host_lock=release_locks,
        created_at=ts,
    )


def enqueue_discard(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    universe_id: str,
    storage_class: str,
    lease: Lease | None = None,
    repo_key: str | None = None,
    generation: int | None = None,
    release_locks: bool = False,
    now: Callable[[], float] = time.time,
) -> int:
    """An explicit ``discard``: scratch wipes its lease, permanent discards a
    generation by ``(repo_key, generation)``. INSIDE the caller's transaction.

    Revocation of any capability over the discarded workspace is the caller's:
    this records the bytes that are owed, nothing else. Returns the entry id.
    """
    _require_storage_class(storage_class)
    ensure_schema(conn)
    ts = float(now())
    if storage_class == STORAGE_SCRATCH:
        if lease is None:
            raise ValueError("a scratch discard needs the lease")
        return _insert_entry(
            conn,
            run_id=run_id,
            universe_id=universe_id,
            action=ACTION_WIPE_SCRATCH,
            lease_id=lease.lease_id,
            repo_key=lease.repo_key,
            generation=lease.generation,
            release_universe_lock=release_locks,
            release_host_lock=release_locks,
            created_at=ts,
        )
    key = repo_key if repo_key is not None else (lease.repo_key if lease else None)
    gen = generation if generation is not None else (lease.generation if lease else None)
    if key is None or gen is None:
        raise ValueError("a permanent discard needs repo_key and generation")
    _require_path_key("repo_key", key)
    lease_id = lease.lease_id if lease is not None else None
    if lease_id is None:
        # The generation being discarded is usually the one publish_generation
        # just replaced, and its lease row is what carries the paths and the
        # state the processor has to move. Find it inside the same transaction.
        row = conn.execute(
            "SELECT lease_id FROM workspace_leases "
            "WHERE universe_id = ? AND repo_key = ? AND generation = ? "
            "ORDER BY created_at LIMIT 1",
            (universe_id, key, int(gen)),
        ).fetchone()
        lease_id = None if row is None else row[0]
    return _insert_entry(
        conn,
        run_id=run_id,
        universe_id=universe_id,
        action=ACTION_DISCARD_PERMANENT,
        lease_id=lease_id,
        repo_key=key,
        generation=int(gen),
        release_universe_lock=release_locks,
        release_host_lock=release_locks,
        created_at=ts,
    )


# --------------------------------------------------------------------------
# the processor
# --------------------------------------------------------------------------


_ENTRY_COLUMNS = (
    "entry_id, run_id, action, lease_id, repo_key, generation, universe_id, "
    "release_universe_lock, release_host_lock, claim_token, claimed_at, created_at"
)


def _entry_from_row(row: sqlite3.Row | tuple) -> OutboxEntry:
    return OutboxEntry(
        entry_id=int(row[0]),
        run_id=row[1],
        action=row[2],
        lease_id=row[3],
        repo_key=row[4],
        generation=None if row[5] is None else int(row[5]),
        universe_id=row[6],
        release_universe_lock=bool(row[7]),
        release_host_lock=bool(row[8]),
        claim_token=row[9],
        claimed_at=None if row[10] is None else float(row[10]),
        created_at=float(row[11]),
    )


def admission_open(db: Path) -> bool:
    """False while any outbox entry is unfinished. ``admit`` refuses then."""
    conn = _connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        pending = int(
            conn.execute(
                "SELECT COUNT(*) FROM workspace_outbox WHERE done_at IS NULL"
            ).fetchone()[0]
        )
        conn.commit()
        return pending == 0
    finally:
        conn.close()


def claim_next(
    db: Path,
    *,
    claimant: str,
    claim_ttl_s: float = DEFAULT_CLAIM_TTL_S,
    now: Callable[[], float] = time.time,
    token_factory: Callable[[], str] = secrets.token_hex,
) -> OutboxEntry | None:
    """Claim the oldest unfinished entry at-least-once, or None.

    Claimable: never claimed, or claimed longer than ``claim_ttl_s`` ago (a dead
    processor). The token carries the claimant so a claim names its holder
    without a column, and the final transaction compares it exactly: a processor
    whose claim expired underneath it changes nothing.
    """
    ts = float(now())
    expiry = ts - claim_ttl_s
    token = f"{claimant}:{token_factory()}"
    conn = _connect(db)
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
            ensure_schema(conn)
            row = conn.execute(
                f"SELECT {_ENTRY_COLUMNS} FROM workspace_outbox "
                "WHERE done_at IS NULL AND (claim_token IS NULL OR claimed_at < ?) "
                "ORDER BY entry_id LIMIT 1",
                (expiry,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            entry = _entry_from_row(row)
            conn.execute(
                "UPDATE workspace_outbox SET claim_token = ?, claimed_at = ? WHERE entry_id = ?",
                (token, ts, entry.entry_id),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()
    return OutboxEntry(
        entry_id=entry.entry_id,
        run_id=entry.run_id,
        action=entry.action,
        lease_id=entry.lease_id,
        repo_key=entry.repo_key,
        generation=entry.generation,
        universe_id=entry.universe_id,
        release_universe_lock=entry.release_universe_lock,
        release_host_lock=entry.release_host_lock,
        claim_token=token,
        claimed_at=ts,
        created_at=entry.created_at,
    )


def _target_paths(db: Path, entry: OutboxEntry) -> tuple[Path, Path] | None:
    """The (source, quarantine) pair for an entry, from the lease that owns it.

    Both permanent and scratch workspaces get a lease row at admission, and the
    row keeps its computed paths, so the outbox needs no path column. None means
    no lease row exists for the named generation.
    """
    conn = _connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        if entry.lease_id:
            row = conn.execute(
                "SELECT path, quarantine_path FROM workspace_leases WHERE lease_id = ?",
                (entry.lease_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT path, quarantine_path FROM workspace_leases "
                "WHERE universe_id = ? AND repo_key = ? AND generation = ? "
                "ORDER BY created_at LIMIT 1",
                (entry.universe_id, entry.repo_key, entry.generation),
            ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if row is None:
        return None
    return Path(row[0]), Path(row[1])


def _reconcile_filesystem(fs: PoolFilesystem, src: Path, quarantine: Path) -> None:
    """Every crash window, on retry, ends with both names gone.

    present/absent -> rename then delete; absent/present -> delete; absent/absent
    -> done; present/present -> delete the stale quarantine first, then rename
    and delete. Deletion never follows links.
    """
    src_present = fs.exists(src)
    quarantine_present = fs.exists(quarantine)
    if quarantine_present:
        fs.remove_tree_no_follow(quarantine)
    if src_present:
        fs.rename(src, quarantine)
        fs.remove_tree_no_follow(quarantine)


def process_entry(
    db: Path,
    entry: OutboxEntry,
    *,
    fs: PoolFilesystem,
    now: Callable[[], float] = time.time,
) -> str:
    """Do the filesystem work, then acknowledge it in ONE transaction.

    The final transaction verifies the claim token still matches (else
    ``lost_claim`` and nothing changes), marks the lease ``AVAILABLE`` - or
    ``LOST`` with the failure recorded, keeping its bytes charged - releases the
    locks the entry names when the run still holds them, and sets
    ``done_at``/``outcome``. Returns the outcome.
    """
    outcome = OUTCOME_RELEASED
    failure: str | None = None
    if entry.action in (ACTION_WIPE_SCRATCH, ACTION_DISCARD_PERMANENT):
        targets = _target_paths(db, entry)
        if targets is None:
            outcome = OUTCOME_UNKNOWN_TARGET
            failure = (
                f"no lease row for {entry.universe_id}/{entry.repo_key}"
                f"@{entry.generation}; nothing located to delete"
            )
        else:
            src, quarantine = targets
            try:
                _reconcile_filesystem(fs, src, quarantine)
                outcome = OUTCOME_WIPED
            except OSError as exc:
                outcome = OUTCOME_LOST
                failure = f"{type(exc).__name__}: {exc}"

    ts = float(now())
    conn = _connect(db)
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
            ensure_schema(conn)
            row = conn.execute(
                "SELECT claim_token, done_at FROM workspace_outbox WHERE entry_id = ?",
                (entry.entry_id,),
            ).fetchone()
            if row is None or row[0] != entry.claim_token:
                conn.commit()
                return OUTCOME_LOST_CLAIM
            if row[1] is not None:
                conn.commit()
                return OUTCOME_ALREADY_DONE
            if entry.lease_id and outcome in (OUTCOME_WIPED, OUTCOME_LOST):
                conn.execute(
                    "UPDATE workspace_leases SET state = ?, updated_at = ? WHERE lease_id = ?",
                    (
                        STATE_AVAILABLE if outcome == OUTCOME_WIPED else STATE_LOST,
                        ts,
                        entry.lease_id,
                    ),
                )
            if entry.release_universe_lock:
                conn.execute(
                    'DELETE FROM workspace_locks WHERE scope = ? AND "key" = ? AND run_id = ?',
                    (SCOPE_UNIVERSE, entry.universe_id, entry.run_id),
                )
            if entry.release_host_lock:
                conn.execute(
                    "DELETE FROM workspace_locks WHERE scope = ? AND run_id = ?",
                    (SCOPE_HOST, entry.run_id),
                )
            recorded = outcome if failure is None else f"{outcome}: {failure}"
            conn.execute(
                "UPDATE workspace_outbox SET done_at = ?, outcome = ? "
                "WHERE entry_id = ? AND claim_token = ?",
                (ts, recorded, entry.entry_id, entry.claim_token),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()
    return outcome


def startup_sweep(
    db: Path,
    *,
    fs: PoolFilesystem,
    claimant: str,
    now: Callable[[], float] = time.time,
) -> int:
    """Process every pending entry to completion before admission reopens.

    Nothing else runs at startup, so this steals every claim: one left behind is
    a dead process's. Returns the number of entries finished. Raises rather than
    spin if an entry will not finish - a silent loop here would hold the
    admission barrier closed forever.
    """
    finished = 0
    budget = 0
    conn = _connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        budget = int(
            conn.execute(
                "SELECT COUNT(*) FROM workspace_outbox WHERE done_at IS NULL"
            ).fetchone()[0]
        )
        conn.commit()
    finally:
        conn.close()
    attempts = 0
    limit = budget * 2 + 8
    while True:
        entry = claim_next(db, claimant=claimant, claim_ttl_s=STEAL_ALL_TTL_S, now=now)
        if entry is None:
            return finished
        process_entry(db, entry, fs=fs, now=now)
        finished += 1
        attempts += 1
        if attempts > limit:
            raise RuntimeError(
                f"startup sweep did not converge after {attempts} entries "
                f"(started with {budget} pending)"
            )


def periodic_sweep(
    db: Path,
    *,
    fs: PoolFilesystem,
    claimant: str,
    claim_ttl_s: float = DEFAULT_CLAIM_TTL_S,
    now: Callable[[], float] = time.time,
) -> int:
    """Reclaim unclaimed and expired-claim entries, one at a time, until none.

    Unlike the startup sweep this respects a live claim: another processor's
    fresh claim is left alone. Returns the number processed.
    """
    processed = 0
    while True:
        entry = claim_next(db, claimant=claimant, claim_ttl_s=claim_ttl_s, now=now)
        if entry is None:
            return processed
        process_entry(db, entry, fs=fs, now=now)
        processed += 1


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def pool_usage(db: Path) -> PoolUsage:
    """What the shared scratch pool is currently holding, ``LOST`` included."""
    conn = _connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        reserved = _scratch_pool_reserved(conn)
        lost_bytes, lost_leases = conn.execute(
            "SELECT COALESCE(SUM(reserved_bytes), 0), COUNT(*) FROM workspace_leases "
            "WHERE storage_class = ? AND state = ?",
            (STORAGE_SCRATCH, STATE_LOST),
        ).fetchone()
        active = conn.execute(
            "SELECT COUNT(*) FROM workspace_leases WHERE storage_class = ? AND state = ?",
            (STORAGE_SCRATCH, STATE_ACTIVE),
        ).fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return PoolUsage(
        reserved_bytes=int(reserved),
        lost_bytes=int(lost_bytes),
        active_leases=int(active),
        lost_leases=int(lost_leases),
    )


def ledger_usage(
    db: Path, universe_id: str, *, now: Callable[[], float] = time.time
) -> LedgerUsage:
    """A universe's rolling-hour ``workspace`` jobs and bytes, and when the
    oldest charge falls out of the window."""
    ts = float(now())
    cutoff = ts - WINDOW_S
    conn = _connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        jobs = _ledger_sum(conn, universe_id, KIND_JOBS, cutoff)
        charged = _ledger_sum(conn, universe_id, KIND_BYTES, cutoff)
        row = conn.execute(
            "SELECT MIN(created_at) FROM workspace_ledger "
            "WHERE universe_id = ? AND created_at >= ?",
            (universe_id, cutoff),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    clears_at = None if row is None or row[0] is None else float(row[0]) + WINDOW_S
    return LedgerUsage(jobs=jobs, bytes=charged, clears_at=clears_at)
