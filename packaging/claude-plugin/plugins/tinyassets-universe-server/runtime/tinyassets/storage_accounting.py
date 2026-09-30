"""One storage pool per account: measured everywhere, enforced on user-driven writes.

Founder directive 2026-09-30: an account's limits are storage GiB and concurrent
seats -- nothing else. Storage is ONE pool per person, shared across all of their
universes (`tinyassets.universe_owner`). At the quota a user-driven write is
refused visibly, with an inline Upgrade link; reads never break.

Design: `openspec/changes/account-storage-quota/design.md` (D3-D5, D7, D8).

The number
----------
``used(account) = sum(measurements) + sum(pending)``.

* A **measurement** is the cached size of one store for one scope -- a universe
  (for stores that live inside it) or an account (for stores keyed by person).
  Taken off the write path, outside any transaction.
* A **pending** row is a write admitted since. ``reserved`` while the write is in
  flight, ``committed`` once it has landed, stamped with a sequence number.
* A measurement clears only the committed rows whose sequence is at or below the
  sequence it READ BEFORE SCANNING. Those writes were on disk before the scan
  began, so the scan saw them. Anything later, or still reserved, stays pending.
  The worst case is a brief over-count; an under-count cannot happen. (This is
  what a reset-on-measure ledger gets wrong: a write landing mid-scan vanishes.)

Admission runs in ONE ``BEGIN IMMEDIATE`` transaction, so two concurrent writes
cannot both be admitted into the same headroom.

Never refuse on a stale number
------------------------------
Before refusing, the gate re-measures every one of the account's rows older than
`FRESH_BEFORE_REFUSE_S` and decides again. A delete is therefore credited on the
next write that needs the room, whether or not the delete path remembered to call
`touch` -- `touch` only makes the owner's displayed number catch up sooner. There
are no "freed" credits: bytes are free when a measurement stops seeing them.

What is gated, and what is only counted
---------------------------------------
Counted: every registered store. Gated: the write paths a user drives volume
through (files, pages, uploads, workspaces, branch/version writes, and the project
memory / daemon memory / UI library stores that lost their own caps). NOT gated:
the credential vault, sessions, chat history, run records -- refusing those would
lock the owner out of fixing it, or lose work already admitted.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.principals import named_principal

_log = logging.getLogger(__name__)

DB_FILENAME = ".storage_accounting.db"

#: A refusal is only ever decided on measurements at most this old.
FRESH_BEFORE_REFUSE_S = 60.0

#: A reserved row whose write never committed or released (a crashed process) is
#: dropped by a measurement that started this long after it was reserved. By then
#: the write has either landed -- and the measurement saw it -- or never will.
#: Gated writes on this path are single documents; none takes minutes.
RESERVED_TTL_S = 600.0

SCOPE_UNIVERSE = "universe"
SCOPE_ACCOUNT = "account"

FAILURE_QUOTA = "storage_quota_exceeded"
FAILURE_UNAVAILABLE = "storage_accounting_unavailable"

_GIB = 1024**3
_MIB = 1024**2


# --------------------------------------------------------------------------- #
# Stores
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Store:
    """One place user bytes live, and how to size one scope of it.

    ``measure(base, scope_id)`` returns logical bytes. It may raise; a failed
    measurement is reported, never replaced by a guess.
    """

    name: str
    scope: str
    measure: Callable[[Path, str], int]


def _walk_bytes(root: Path, *, exclude_top: frozenset[str] = frozenset()) -> int:
    """Logical bytes of regular files under ``root``. Symlinks are not followed
    and a hard-linked file is counted once. Missing root is 0 bytes."""
    try:
        info = os.lstat(root)
    except FileNotFoundError:
        return 0
    if not stat.S_ISDIR(info.st_mode):
        return 0
    total = 0
    seen: set[tuple[int, int]] = set()
    stack: list[tuple[Path, bool]] = [(root, True)]
    while stack:
        directory, top = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if top and entry.name in exclude_top:
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue  # removed mid-walk: it is not there to charge
                if stat.S_ISDIR(st.st_mode):
                    stack.append((Path(entry.path), False))
                elif stat.S_ISREG(st.st_mode):
                    if not st.st_ino:
                        # Windows DirEntry leaves inode/link count unset; ask.
                        try:
                            st = os.lstat(entry.path)
                        except FileNotFoundError:
                            continue
                    key = (st.st_dev, st.st_ino)
                    if st.st_nlink > 1:
                        if key in seen:
                            continue
                        seen.add(key)
                    total += st.st_size
    return total


def _universe_files(base: Path, universe_id: str) -> int:
    """Everything in the universe's own directory except what the user did not put
    there -- the platform's provider runtime (``.runtime``) and transient checkout
    staging (``.workspace-staging``, platform debris when a checkout fails:
    measured at 2.8 GiB in one production universe, concern
    2026-09-30-workspace-staging-leaks-on-failed-checkouts) -- and permanent
    workspaces, which are their own store."""
    if not universe_id or Path(universe_id).name != universe_id or universe_id.startswith("."):
        raise ValueError(f"not a universe id: {universe_id!r}")
    return _walk_bytes(base / universe_id, exclude_top=_NOT_USER_BYTES)


#: Top-level entries of a universe directory that are the PLATFORM's, not the
#: user's. Counted on the host line, never charged to an account.
_NOT_USER_BYTES = frozenset({".runtime", ".workspace-staging", "workspaces"})


def _account_actors(base: Path, account_id: str) -> list[str]:
    """Every actor string whose writes belong to this account: the person, and
    each of their universes acting as itself (``universe:<id>``)."""
    from tinyassets.universe_owner import owned_universes

    return [account_id, *(f"universe:{uid}" for uid in owned_universes(base, account_id))]


def _sum_sql(db: Path, sql: str, params: tuple) -> int:
    if not db.exists():
        return 0
    uri = f"file:{db.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            row = conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return 0
            raise
    finally:
        conn.close()
    return int(row[0] or 0) if row else 0


def _project_memory(base: Path, account_id: str) -> int:
    """Project memory lives at the data root, keyed by project, and records its
    WRITER on every row and every history row. Charged to the writer's account."""
    actors = _account_actors(base, account_id)
    marks = ",".join("?" * len(actors))
    db = base / ".project_memory.db"
    current = _sum_sql(
        db,
        "SELECT SUM(length(CAST(value AS BLOB)) + length(CAST(project_id AS BLOB)) "
        f"+ length(CAST(key AS BLOB))) FROM project_memory WHERE updated_by IN ({marks})",
        tuple(actors),
    )
    history = _sum_sql(
        db,
        "SELECT SUM(length(CAST(value AS BLOB)) + length(CAST(project_id AS BLOB)) "
        f"+ length(CAST(key AS BLOB))) FROM project_memory_history WHERE updated_by IN ({marks})",
        tuple(actors),
    )
    return current + history


def _ui_library(base: Path, account_id: str) -> int:
    """A person's app-UI library, per universe they saved one in."""
    from tinyassets import custom_agents

    return _sum_sql(
        custom_agents.db_path(base),
        "SELECT SUM(length(CAST(ui_library_json AS BLOB)) "
        "+ COALESCE(length(CAST(ui_selection_json AS BLOB)), 0)) "
        "FROM universe_app_ui WHERE owner_user_id = ?",
        (account_id,),
    )


def _owned_daemon_ids(base: Path, account_id: str) -> list[str]:
    from tinyassets.daemon_registry import list_daemons

    return sorted(
        str(d["daemon_id"])
        for d in list_daemons(base)
        if str(d.get("owner_user_id") or "") == account_id
    )


def _daemon_memory(base: Path, account_id: str) -> int:
    """A daemon's operational memory -- brain entries and its wiki directory --
    charged to the daemon's owner (its authenticated ``created_by``)."""
    from tinyassets.daemon_brain import daemon_brain_db_path
    from tinyassets.daemon_wiki import daemon_wiki_root

    daemons = _owned_daemon_ids(base, account_id)
    if not daemons:
        return 0
    marks = ",".join("?" * len(daemons))
    db = daemon_brain_db_path(base)

    def _col(name: str) -> str:
        return f"length(CAST({name} AS BLOB))"

    # EVERY variable-sized column a caller can fill, not just content: an
    # unmeasured column is a place to put bytes nobody counts (gpt-6-astra,
    # PR #4158: promotion metadata, temporal bounds, source paths).
    tables = {
        "daemon_brain_entries": (
            "content", "metadata_json", "temporal_bounds_json", "source_path",
            "source_hash", "source_id", "source_type", "reliability", "language_type",
        ),
        "daemon_memory_promotions": (
            "summary", "metadata_json", "entry_ids_json", "target_path",
        ),
        "daemon_memory_events": (
            "metadata_json", "entry_ids_json", "query_text", "source_id", "source_type",
        ),
    }
    total = 0
    for table, columns in tables.items():
        total += _sum_sql(
            db,
            f"SELECT SUM({' + '.join(_col(c) for c in columns)}) "
            f"FROM {table} WHERE daemon_id IN ({marks})",
            tuple(daemons),
        )
    wikis = sum(_walk_bytes(daemon_wiki_root(base, daemon_id)) for daemon_id in daemons)
    return total + wikis


#: THE registry. A store not listed here is a place to put bytes that nobody
#: counts; `tests/test_storage_accounting.py` fails on one.
STORES: dict[str, Store] = {
    store.name: store
    for store in (
        Store("universe_files", SCOPE_UNIVERSE, _universe_files),
        Store("project_memory", SCOPE_ACCOUNT, _project_memory),
        Store("ui_library", SCOPE_ACCOUNT, _ui_library),
        Store("daemon_memory", SCOPE_ACCOUNT, _daemon_memory),
    )
}


# --------------------------------------------------------------------------- #
# The ledger
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    scope_id    TEXT NOT NULL,
    store       TEXT NOT NULL,
    bytes       INTEGER NOT NULL CHECK (bytes >= 0),
    start_seq   INTEGER NOT NULL,
    measured_at REAL NOT NULL,
    dirty       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (scope_id, store)
);
CREATE TABLE IF NOT EXISTS pending (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  TEXT NOT NULL,
    scope_id    TEXT NOT NULL,
    store       TEXT NOT NULL,
    bytes       INTEGER NOT NULL CHECK (bytes >= 0),
    state       TEXT NOT NULL CHECK (state IN ('reserved', 'committed')),
    commit_seq  INTEGER,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_account ON pending(account_id);
CREATE INDEX IF NOT EXISTS idx_pending_scope ON pending(scope_id, store);
CREATE TABLE IF NOT EXISTS counter (
    id  INTEGER PRIMARY KEY CHECK (id = 1),
    seq INTEGER NOT NULL
);
INSERT OR IGNORE INTO counter (id, seq) VALUES (1, 0);
"""


def ledger_path(base_path: str | Path) -> Path:
    return Path(base_path) / DB_FILENAME


def _connect(base_path: str | Path) -> sqlite3.Connection:
    path = ledger_path(base_path)
    if path.is_symlink():
        raise RuntimeError(f"refusing a symlinked storage ledger: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(_SCHEMA)
    return conn


@contextlib.contextmanager
def _txn(base_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = _connect(base_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


def _next_seq(conn: sqlite3.Connection) -> int:
    conn.execute("UPDATE counter SET seq = seq + 1 WHERE id = 1")
    return int(conn.execute("SELECT seq FROM counter WHERE id = 1").fetchone()[0])


def _scopes(base: Path, account_id: str) -> list[tuple[str, str]]:
    """Every (scope_id, store) pair that makes up this account's number."""
    from tinyassets.universe_owner import owned_universes

    universes = owned_universes(base, account_id)
    pairs: list[tuple[str, str]] = []
    for store in STORES.values():
        if store.scope == SCOPE_UNIVERSE:
            pairs.extend((uid, store.name) for uid in universes)
        else:
            pairs.append((account_id, store.name))
    return pairs


def measure(base_path: str | Path, scope_id: str, store: str, *, now: float | None = None) -> int:
    """Measure one store for one scope and retire the pending rows it covers.

    The sequence is read BEFORE scanning; only committed rows at or below it are
    retired, because only those were provably on disk when the scan began.
    """
    base = Path(base_path)
    spec = STORES[store]
    with _txn(base) as conn:
        start_seq = int(conn.execute("SELECT seq FROM counter WHERE id = 1").fetchone()[0])
    started = time.time() if now is None else float(now)
    size = int(spec.measure(base, scope_id))
    if size < 0:
        raise ValueError(f"{store} measured negative bytes for {scope_id}")
    with _txn(base) as conn:
        existing = conn.execute(
            "SELECT start_seq FROM measurements WHERE scope_id = ? AND store = ?",
            (scope_id, store),
        ).fetchone()
        if existing is not None and int(existing[0]) > start_seq:
            # A scan that STARTED later already landed. This one saw less: writing
            # it would replace a newer number with an older one after that newer
            # scan had already retired the pending rows it covered -- bytes
            # counted nowhere (gpt-6-astra, PR #4158). Discard it.
            return size
        conn.execute(
            "INSERT INTO measurements (scope_id, store, bytes, start_seq, measured_at, dirty) "
            "VALUES (?, ?, ?, ?, ?, 0) ON CONFLICT (scope_id, store) DO UPDATE SET "
            "bytes = excluded.bytes, start_seq = excluded.start_seq, "
            "measured_at = excluded.measured_at, dirty = 0",
            (scope_id, store, size, start_seq, started),
        )
        conn.execute(
            "DELETE FROM pending WHERE scope_id = ? AND store = ? AND state = 'committed' "
            "AND commit_seq <= ?",
            (scope_id, store, start_seq),
        )
        conn.execute(
            "DELETE FROM pending WHERE scope_id = ? AND store = ? AND state = 'reserved' "
            "AND created_at < ?",
            (scope_id, store, started - RESERVED_TTL_S),
        )
    return size


def touch(base_path: str | Path, scope_id: str, store: str) -> None:
    """Mark a store dirty after a delete, so the displayed number catches up.

    A latency aid only: a refusal re-measures stale rows regardless. Never raises
    -- a delete that succeeded must not fail on bookkeeping."""
    try:
        with _txn(base_path) as conn:
            conn.execute(
                "UPDATE measurements SET dirty = 1 WHERE scope_id = ? AND store = ?",
                (scope_id, store),
            )
    except Exception:  # noqa: BLE001 -- see docstring
        _log.warning("storage touch failed for %s/%s", scope_id, store, exc_info=True)


@dataclass(frozen=True)
class Usage:
    account_id: str
    used_bytes: int
    quota_bytes: int
    tier: str
    #: (scope_id, store, bytes), largest first -- the account's OWN consumers.
    breakdown: tuple[tuple[str, str, int], ...]
    #: Pairs that have never been measured successfully.
    unmeasured: tuple[tuple[str, str], ...]
    #: Oldest measurement's timestamp, or None when nothing is measured.
    oldest_measured_at: float | None


def _usage_in(conn: sqlite3.Connection, account_id: str, pairs, quota: int, tier: str) -> Usage:
    rows = {}
    for scope_id, store in pairs:
        row = conn.execute(
            "SELECT bytes, measured_at FROM measurements WHERE scope_id = ? AND store = ?",
            (scope_id, store),
        ).fetchone()
        if row is not None:
            rows[(scope_id, store)] = (int(row[0]), float(row[1]))
    pending = int(
        conn.execute(
            "SELECT COALESCE(SUM(bytes), 0) FROM pending WHERE account_id = ?", (account_id,)
        ).fetchone()[0]
    )
    measured = sum(size for size, _ in rows.values())
    breakdown = tuple(sorted(
        ((scope, store, size) for (scope, store), (size, _) in rows.items() if size),
        key=lambda item: -item[2],
    ))
    return Usage(
        account_id=account_id,
        used_bytes=measured + pending,
        quota_bytes=quota,
        tier=tier,
        breakdown=breakdown,
        unmeasured=tuple(pair for pair in pairs if pair not in rows),
        oldest_measured_at=min((at for _, at in rows.values()), default=None),
    )


def _quota(base: Path, account_id: str) -> tuple[int, str]:
    from tinyassets.universe_owner import tier_of
    from tinyassets.usage_policy import limits_for

    limits = limits_for(tier_of(base, account_id))
    return int(limits.storage_bytes), limits.name


def usage(base_path: str | Path, account_id: str) -> Usage:
    """The owner-facing number. Read-only against the ledger; never refuses."""
    base = Path(base_path)
    quota, tier = _quota(base, account_id)
    pairs = _scopes(base, account_id)
    conn = _connect(base)
    try:
        return _usage_in(conn, account_id, pairs, quota, tier)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


def _human(size: int | float) -> str:
    size = float(size)
    if size >= _GIB:
        return f"{size / _GIB:.1f} GiB"
    if size >= _MIB:
        return f"{size / _MIB:.0f} MiB"
    if size >= 1024:
        return f"{size / 1024:.0f} KiB"
    return f"{int(size)} bytes"


class StorageRefused(Exception):
    """A gated write that must not happen. ``record`` is the structured failure
    a surface returns; ``str(exc)`` is the owner-facing message."""

    def __init__(self, record: dict):
        self.record = record
        super().__init__(record["error"])


def refusal_record(usage_: Usage, requested: int, *, universes: int) -> dict:
    from tinyassets.usage_policy import upgrade_sentence

    across = f" across {universes} universes" if universes > 1 else ""
    message = (
        f"Your account is using {_human(usage_.used_bytes)} of its "
        f"{_human(usage_.quota_bytes)} of cloud storage{across}, and this write needs "
        f"{_human(requested)}. Delete files, pages, run outputs or workspaces to free "
        "space"
    )
    link = upgrade_sentence(usage_.tier, what="storage")
    message = f"{message}, or {link[0].lower()}{link[1:]}" if link else f"{message}."
    return {
        "error": message,
        "failure_class": FAILURE_QUOTA,
        "actionable_by": "user",
        "used_bytes": usage_.used_bytes,
        "quota_bytes": usage_.quota_bytes,
        "requested_bytes": requested,
        "tier": usage_.tier,
        "largest": [
            {"scope_id": scope, "store": store, "bytes": size}
            for scope, store, size in usage_.breakdown[:3]
        ],
    }


def _unavailable_record(requested: int) -> dict:
    return {
        "error": (
            "Cloud storage use for this account could not be measured just now, so "
            "this write was not accepted. Nothing was lost; try again shortly."
        ),
        "failure_class": FAILURE_UNAVAILABLE,
        "actionable_by": "host",
        "requested_bytes": requested,
    }


def _measure_many(base: Path, pairs) -> list[tuple[str, str]]:
    """Measure each pair; return the ones that failed (logged loudly)."""
    failed = []
    for scope_id, store in pairs:
        try:
            measure(base, scope_id, store)
        except Exception:  # noqa: BLE001 -- reported below, never guessed
            _log.exception("storage measurement failed for %s/%s", scope_id, store)
            failed.append((scope_id, store))
    return failed


@dataclass
class Reservation:
    """An admitted write. ``id`` is None for an unattributed universe: its bytes
    are counted by measurement, and nothing is refused until an owner is known."""

    base: Path
    id: int | None
    account_id: str | None
    bytes: int


def _try_admit(base, account_id, scope_id, store, nbytes, pairs, quota, tier):
    """One serialized decision. Unmeasured stores count as 0 here -- the bytes
    that ARE known (measurements plus every pending write) still bound it, so a
    store that cannot be measured never opens an unbounded path."""
    with _txn(base) as conn:
        current = _usage_in(conn, account_id, pairs, quota, tier)
        if current.used_bytes + nbytes > quota:
            return None, current
        cursor = conn.execute(
            "INSERT INTO pending (account_id, scope_id, store, bytes, state, created_at) "
            "VALUES (?, ?, ?, ?, 'reserved', ?)",
            (account_id, scope_id, store, nbytes, time.time()),
        )
        return int(cursor.lastrowid), current


def _stale_pairs(base: Path, pairs) -> list[tuple[str, str]]:
    cutoff = time.time() - FRESH_BEFORE_REFUSE_S
    conn = _connect(base)
    try:
        stale = []
        for scope_id, store in pairs:
            row = conn.execute(
                "SELECT measured_at, dirty FROM measurements WHERE scope_id = ? AND store = ?",
                (scope_id, store),
            ).fetchone()
            if row is None or float(row[0]) < cutoff or int(row[1]):
                stale.append((scope_id, store))
        return stale
    finally:
        conn.close()


def reserve(
    base_path: str | Path,
    *,
    account_id: str | None,
    scope_id: str,
    store: str,
    nbytes: int,
) -> Reservation:
    """Admit a write of ``nbytes`` into ``store`` for ``scope_id``, charged to
    ``account_id``, or raise `StorageRefused`.

    ``account_id`` None means an unattributed universe: admitted, counted by
    measurement, never refused (founder decision 2026-09-30).

    A refusal is always PROVEN: it is decided only after every stale or
    never-measured store of the account was re-measured, on known bytes that
    already exceed the quota. A store that still cannot be measured counts as 0
    and is logged loudly -- which can only under-refuse, never over-refuse. The
    only other refusal is a ledger that cannot be opened at all
    (`storage_accounting_unavailable`), which is the host's to fix.
    """
    if store not in STORES:
        raise KeyError(f"unregistered store {store!r}")
    nbytes = int(nbytes)
    if nbytes < 0:
        raise ValueError("nbytes must be >= 0")
    base = Path(base_path)
    account = named_principal(account_id or "")
    if not account:
        return Reservation(base, None, None, nbytes)
    quota, tier = _quota(base, account)
    pairs = _scopes(base, account)
    if (scope_id, store) not in pairs:
        raise ValueError(f"{store}/{scope_id} is not part of this account's storage")
    try:
        # First contact with an account's number: measure what never was.
        conn = _connect(base)
        try:
            missing = _usage_in(conn, account, pairs, quota, tier).unmeasured
        finally:
            conn.close()
        if missing:
            _measure_many(base, missing)
        rid, current = _try_admit(base, account, scope_id, store, nbytes, pairs, quota, tier)
        if rid is None:
            # Never refuse on a stale number.
            stale = _stale_pairs(base, pairs)
            if stale:
                _measure_many(base, stale)
                rid, current = _try_admit(
                    base, account, scope_id, store, nbytes, pairs, quota, tier,
                )
    except sqlite3.Error:
        _log.exception("storage ledger unavailable for an admission")
        raise StorageRefused(_unavailable_record(nbytes)) from None
    if current.unmeasured:
        _log.warning(
            "storage decided with unmeasured stores %s (counted as 0)",
            list(current.unmeasured),
        )
    if rid is None:
        universes = len({scope for scope, st in pairs if STORES[st].scope == SCOPE_UNIVERSE})
        raise StorageRefused(refusal_record(current, nbytes, universes=universes))
    return Reservation(base, rid, account, nbytes)


def commit(reservation: Reservation, actual_bytes: int | None = None) -> None:
    """The write landed. ``actual_bytes`` above the reservation is a bug in the
    caller and fails loudly -- it is never clamped into looking fine."""
    if reservation.id is None:
        return
    actual = reservation.bytes if actual_bytes is None else int(actual_bytes)
    if actual < 0 or actual > reservation.bytes:
        raise ValueError(
            f"wrote {actual} bytes against a reservation of {reservation.bytes}"
        )
    with _txn(reservation.base) as conn:
        seq = _next_seq(conn)
        conn.execute(
            "UPDATE pending SET state = 'committed', bytes = ?, commit_seq = ? "
            "WHERE id = ? AND state = 'reserved'",
            (actual, seq, reservation.id),
        )


def release(reservation: Reservation) -> None:
    """The write did not happen. Never raises: the caller is already failing."""
    if reservation.id is None:
        return
    try:
        with _txn(reservation.base) as conn:
            conn.execute(
                "DELETE FROM pending WHERE id = ? AND state = 'reserved'", (reservation.id,)
            )
    except Exception:  # noqa: BLE001 -- the reservation expires by RESERVED_TTL_S
        _log.warning("storage release failed for reservation %s", reservation.id, exc_info=True)


@contextlib.contextmanager
def admitted(
    base_path: str | Path,
    *,
    account_id: str | None,
    scope_id: str,
    store: str,
    nbytes: int,
) -> Iterator[Reservation]:
    """``with admitted(...):`` the write. Commits on success, releases on error;
    raises `StorageRefused` before the body runs when the write does not fit."""
    reservation = reserve(
        base_path, account_id=account_id, scope_id=scope_id, store=store, nbytes=nbytes,
    )
    try:
        yield reservation
    except BaseException:
        release(reservation)
        raise
    commit(reservation)


def account_for_actor(base_path: str | Path, actor: str) -> str | None:
    """The account a write by ``actor`` is charged to.

    A person is their own account; a universe acting as itself
    (``universe:<id>``) is charged to its owner. Anything else -- the host, an
    anonymous caller -- has no account and is not gated here.
    """
    from tinyassets.universe_owner import owner_of

    text = (actor or "").strip()
    if text.startswith("universe:"):
        return owner_of(base_path, text.split(":", 1)[1])
    person = named_principal(text)
    return person if person and is_account(base_path, person) else None


#: The platform's own principals: never a person, so never an account.
_PLATFORM_PRINCIPALS = frozenset({"host", "system"})


def is_account(base_path: str | Path, principal: str) -> bool:
    """Whether ``principal`` is an ACCOUNT storage is charged to.

    Every authenticated person is -- including a collaborator who owns no
    universe and has no home: they still have a pool (the free tier), or their
    writes into someone else's universe would escape every quota (gpt-6-astra,
    PR #4158). Only the platform's own principals are exempt.
    """
    del base_path  # kept for call-site symmetry; the answer needs no lookup
    person = named_principal(principal or "")
    return bool(person) and person.lower() not in _PLATFORM_PRINCIPALS


def account_for_daemon(base_path: str | Path, daemon_id: str) -> str | None:
    """The account a daemon's memory is charged to: its authenticated owner."""
    from tinyassets.daemon_registry import get_daemon

    try:
        daemon = get_daemon(base_path, daemon_id=daemon_id)
    except Exception:  # noqa: BLE001 -- unknown daemon: the write fails on its own
        return None
    owner = str(daemon.get("owner_user_id") or "")
    return owner if is_account(base_path, owner) else None


@contextlib.contextmanager
def charged(
    base_path: str | Path, *, account_id: str | None, store: str, nbytes: int,
) -> Iterator[Reservation]:
    """`admitted` for an ACCOUNT-scoped store (project memory, UI library,
    daemon memory): the scope is the account itself."""
    with admitted(
        base_path, account_id=account_id, scope_id=account_id or "", store=store,
        nbytes=nbytes,
    ) as reservation:
        yield reservation


__all__ = [
    "FAILURE_QUOTA",
    "FAILURE_UNAVAILABLE",
    "STORES",
    "Reservation",
    "StorageRefused",
    "Usage",
    "account_for_actor",
    "account_for_daemon",
    "charged",
    "is_account",
    "admitted",
    "commit",
    "measure",
    "refusal_record",
    "release",
    "reserve",
    "touch",
    "usage",
]
