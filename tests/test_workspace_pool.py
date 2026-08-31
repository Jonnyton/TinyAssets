"""The scratch lease pool, its hourly ledger, and the terminal outbox.

Every scenario of ``openspec/changes/workspace-node/specs/scratch-storage``,
plus the durable job lock (``graph-execution-substrate``) and the pre-wire
reservation (``engine-run-admissions``). The filesystem is injected: a fake
drives every crash window deterministically, and ``RealPoolFilesystem`` proves
the no-follow deletion against real bytes under ``tmp_path``.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest

from tinyassets import workspace_pool as wp
from tinyassets.workspace_fs import RealPoolFilesystem

GIB = wp.GIB


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Roots:
    pool: Path
    universe: Path


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "runs.db"


@pytest.fixture
def roots(tmp_path: Path) -> Roots:
    return Roots(pool=tmp_path / "scratch", universe=tmp_path / "universe")


class FakeFs:
    """A ``PoolFilesystem`` over a set of paths, with an ordered op log."""

    def __init__(self, present: tuple[Path | str, ...] = (), fail_remove: Path | str | None = None):
        self.present: set[str] = {str(p) for p in present}
        self.ops: list[tuple] = []
        self.fail_remove = None if fail_remove is None else str(fail_remove)

    def exists(self, path: Path) -> bool:
        return str(path) in self.present

    def rename(self, src: Path, dst: Path) -> None:
        if str(src) not in self.present:
            raise FileNotFoundError(str(src))
        self.present.discard(str(src))
        self.present.add(str(dst))
        self.ops.append(("rename", str(src), str(dst)))

    def remove_tree_no_follow(self, path: Path) -> None:
        if self.fail_remove is not None and str(path) == self.fail_remove:
            self.ops.append(("remove_failed", str(path)))
            raise OSError(13, "permission denied")
        self.ops.append(("remove", str(path)))
        self.present.discard(str(path))


def _ids(*names: str):
    """A deterministic ``lease_id_factory`` handing out ``names`` in order."""
    remaining = list(names)

    def factory() -> str:
        return remaining.pop(0)

    return factory


def admit_scratch(db: Path, roots: Roots, **kw):
    params: dict = dict(
        universe_id="u1",
        connection_id="c1",
        repo_key="repo",
        storage_class=wp.STORAGE_SCRATCH,
        run_id="run-1",
        max_bytes=GIB,
        pool_root=roots.pool,
        universe_root=roots.universe,
    )
    params.update(kw)
    return wp.admit(db, **params)


def admit_universe(db: Path, roots: Roots, **kw):
    params: dict = dict(
        universe_id="u1",
        connection_id="c1",
        repo_key="repo",
        storage_class=wp.STORAGE_UNIVERSE,
        run_id="run-1",
        max_bytes=GIB,
        pool_root=roots.pool,
        universe_root=roots.universe,
        universe_quota_bytes=10 * GIB,
        universe_used_bytes_fn=lambda _u: 0,
    )
    params.update(kw)
    return wp.admit(db, **params)


@contextlib.contextmanager
def terminal_txn(db: Path):
    """What ``runs.py`` will do: the run's terminal row and the outbox entries
    in ONE transaction the pool functions join."""
    conn = sqlite3.connect(str(db), timeout=30)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows(db: Path, sql: str, args: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(str(db), timeout=30)
    try:
        return list(conn.execute(sql, args))
    finally:
        conn.close()


def lock_rows(db: Path) -> list[tuple]:
    return rows(db, 'SELECT scope, "key", run_id FROM workspace_locks ORDER BY scope')


def lease_state(db: Path, lease_id: str) -> str:
    return rows(db, "SELECT state FROM workspace_leases WHERE lease_id = ?", (lease_id,))[0][0]


def make_dir_link(link: Path, target: Path) -> str | None:
    """A symlink, else a Windows junction (no privilege needed), else None."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and os.path.lexists(link):
            return "junction"
    return None


# --------------------------------------------------------------------------
# admission: shape, paths, and the two storage classes
# --------------------------------------------------------------------------


def test_scratch_admission_is_active_with_computed_paths(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    assert lease.lease_id == "lease1"
    assert lease.state == wp.STATE_ACTIVE
    assert lease.generation == 1
    assert lease.reserved_bytes == wp.DEFAULT_LEASE_BYTES_CAP
    assert lease.path == roots.pool / "lease1"
    assert lease.quarantine_path == roots.pool / ".quarantine" / "lease1.1"
    # The module computes the path; the caller creates it under a held handle.
    assert not lease.path.exists()
    assert not roots.pool.exists()


def test_universe_admission_paths_are_the_generation_and_its_quarantine(
    db: Path, roots: Roots
) -> None:
    lease = admit_universe(db, roots, lease_id_factory=_ids("lease1"))
    assert lease.storage_class == wp.STORAGE_UNIVERSE
    assert lease.path == roots.universe / "workspaces" / "repo" / "1"
    assert lease.quarantine_path == roots.universe / "workspaces" / ".quarantine" / "repo.1"
    assert lease.reserved_bytes == GIB


def test_a_large_checkout_does_not_enlarge_the_universe(db: Path, roots: Roots) -> None:
    """scratch-storage: a 3 GiB scratch checkout raises the POOL's reserved
    bytes by the lease bound and touches no universe quota."""
    calls: list[str] = []
    lease = admit_scratch(
        db,
        roots,
        max_bytes=3 * GIB,
        universe_quota_bytes=1,
        universe_used_bytes_fn=lambda u: calls.append(u) or 0,
    )
    assert calls == []  # the universe's quota is never consulted for scratch
    usage = wp.pool_usage(db)
    assert usage.reserved_bytes == wp.DEFAULT_LEASE_BYTES_CAP
    assert usage.active_leases == 1
    assert lease.storage_class == wp.STORAGE_SCRATCH


def test_a_permanent_generation_does_not_consume_the_scratch_pool(
    db: Path, roots: Roots
) -> None:
    admit_universe(db, roots, max_bytes=3 * GIB)
    assert wp.pool_usage(db).reserved_bytes == 0


def test_a_repo_key_that_could_escape_its_directory_is_refused(db: Path, roots: Roots) -> None:
    with pytest.raises(ValueError, match="repo_key"):
        admit_scratch(db, roots, repo_key="../../etc")


def test_a_lease_larger_than_the_lease_bound_is_refused(db: Path, roots: Roots) -> None:
    with pytest.raises(wp.WorkspacePoolRefused) as exc:
        admit_scratch(db, roots, max_bytes=5 * GIB, lease_bytes_cap=4 * GIB)
    assert exc.value.code == wp.REFUSED_QUOTA
    assert "lease bound" in exc.value.detail


# --------------------------------------------------------------------------
# the pool bound
# --------------------------------------------------------------------------


def test_two_admissions_cannot_oversubscribe_the_pool(db: Path, roots: Roots) -> None:
    """scratch-storage: 5 GiB left, two 4 GiB leases, exactly one admitted."""
    barrier = threading.Barrier(2)
    results: dict[str, object] = {}
    lock = threading.Lock()

    def attempt(name: str) -> None:
        barrier.wait(timeout=30)
        try:
            outcome: object = wp.admit(
                db,
                universe_id=f"u-{name}",
                connection_id="c1",
                repo_key="repo",
                storage_class=wp.STORAGE_SCRATCH,
                run_id=f"run-{name}",
                max_bytes=4 * GIB,
                pool_root=roots.pool,
                universe_root=roots.universe,
                pool_bytes_cap=5 * GIB,
                lease_bytes_cap=4 * GIB,
                lease_id_factory=_ids(f"lease{name}"),
            )
        except wp.WorkspacePoolRefused as exc:
            outcome = exc
        with lock:
            results[name] = outcome

    threads = [threading.Thread(target=attempt, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    admitted = [r for r in results.values() if isinstance(r, wp.Lease)]
    refused = [r for r in results.values() if isinstance(r, wp.WorkspacePoolRefused)]
    assert len(admitted) == 1, results
    assert len(refused) == 1, results
    assert refused[0].code == wp.REFUSED_POOL_BUSY
    assert wp.pool_usage(db).reserved_bytes == 4 * GIB


def test_lost_bytes_still_count_against_the_pool(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"), max_bytes=4 * GIB)
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    fs = FakeFs(present=(lease.path,), fail_remove=lease.quarantine_path)
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    assert wp.process_entry(db, entry, fs=fs) == wp.OUTCOME_LOST

    usage = wp.pool_usage(db)
    assert usage.lost_leases == 1
    assert usage.lost_bytes == wp.DEFAULT_LEASE_BYTES_CAP
    assert usage.reserved_bytes == wp.DEFAULT_LEASE_BYTES_CAP  # charged forever

    with pytest.raises(wp.WorkspacePoolRefused) as exc:
        admit_scratch(
            db,
            roots,
            run_id="run-2",
            pool_bytes_cap=5 * GIB,
            lease_bytes_cap=4 * GIB,
            max_bytes=4 * GIB,
            lease_id_factory=_ids("lease2"),
        )
    assert exc.value.code == wp.REFUSED_POOL_BUSY


def test_a_released_lease_frees_its_pool_bytes(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    assert wp.process_entry(db, entry, fs=FakeFs(present=(lease.path,))) == wp.OUTCOME_WIPED
    assert lease_state(db, "lease1") == wp.STATE_AVAILABLE
    assert wp.pool_usage(db).reserved_bytes == 0


# --------------------------------------------------------------------------
# the universe quota
# --------------------------------------------------------------------------


def test_a_quota_refusal_destroys_nothing(db: Path, roots: Roots) -> None:
    """scratch-storage: the existing generation is untouched by a refusal."""
    first = admit_universe(db, roots, lease_id_factory=_ids("lease1"), max_bytes=GIB)
    with terminal_txn(db) as conn:
        previous = wp.publish_generation(
            conn,
            universe_id="u1",
            repo_key="repo",
            generation=first.generation,
            path=first.path,
        )
    assert previous is None
    published_before = rows(db, "SELECT generation, path FROM workspace_generations")

    with pytest.raises(wp.WorkspacePoolRefused) as exc:
        admit_universe(
            db,
            roots,
            run_id="run-2",
            max_bytes=2 * GIB,
            universe_quota_bytes=10 * GIB,
            universe_used_bytes_fn=lambda _u: 9 * GIB,
            lease_id_factory=_ids("lease2"),
        )
    assert exc.value.code == wp.REFUSED_QUOTA
    assert rows(db, "SELECT generation, path FROM workspace_generations") == published_before
    assert rows(db, "SELECT lease_id FROM workspace_leases") == [("lease1",)]
    assert lease_state(db, "lease1") == wp.STATE_ACTIVE


def test_publish_generation_returns_the_previous_one(db: Path, roots: Roots) -> None:
    first = admit_universe(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        assert wp.publish_generation(
            conn, universe_id="u1", repo_key="repo", generation=1, path=first.path
        ) is None
    second = admit_universe(db, roots, lease_id_factory=_ids("lease2"))
    assert second.generation == 2
    with terminal_txn(db) as conn:
        assert (
            wp.publish_generation(
                conn, universe_id="u1", repo_key="repo", generation=2, path=second.path
            )
            == 1
        )
    assert rows(db, "SELECT generation, path FROM workspace_generations") == [
        (2, str(second.path))
    ]


def test_publishing_a_generation_backwards_is_a_loud_error(db: Path, roots: Roots) -> None:
    with terminal_txn(db) as conn:
        wp.publish_generation(
            conn, universe_id="u1", repo_key="repo", generation=4, path=roots.universe / "g4"
        )
    with pytest.raises(ValueError, match="does not follow"):
        with terminal_txn(db) as conn:
            wp.publish_generation(
                conn, universe_id="u1", repo_key="repo", generation=3, path=roots.universe / "g3"
            )


# --------------------------------------------------------------------------
# the durable job locks
# --------------------------------------------------------------------------


def test_the_lock_is_reentrant_for_the_same_run(db: Path, roots: Roots) -> None:
    """graph-execution-substrate: checkout, then a later node, then the push."""
    admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    admit_scratch(db, roots, lease_id_factory=_ids("lease2"))
    assert lock_rows(db) == [("host", "slot-0", "run-1"), ("universe", "u1", "run-1")]


def test_another_run_in_the_same_universe_is_workspace_busy(db: Path, roots: Roots) -> None:
    admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with pytest.raises(wp.WorkspacePoolRefused) as exc:
        admit_scratch(db, roots, run_id="run-2", lease_id_factory=_ids("lease2"))
    assert exc.value.code == wp.REFUSED_BUSY
    assert "universe lock" in exc.value.detail
    assert rows(db, "SELECT lease_id FROM workspace_leases") == [("lease1",)]


def test_the_host_slot_holds_off_another_universe_and_rolls_its_lock_back(
    db: Path, roots: Roots
) -> None:
    admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with pytest.raises(wp.WorkspacePoolRefused) as exc:
        admit_scratch(
            db, roots, universe_id="u2", run_id="run-2", lease_id_factory=_ids("lease2")
        )
    assert exc.value.code == wp.REFUSED_BUSY
    assert "host lock" in exc.value.detail
    # The universe lock u2 acquired a moment earlier rolled back with everything else.
    assert lock_rows(db) == [("host", "slot-0", "run-1"), ("universe", "u1", "run-1")]


def test_processing_the_terminal_entry_releases_both_locks(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    assert len(lock_rows(db)) == 2
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    wp.process_entry(db, entry, fs=FakeFs(present=(lease.path,)))
    assert lock_rows(db) == []
    # And the next universe's run is admitted where it was refused before.
    admit_scratch(db, roots, universe_id="u2", run_id="run-2", lease_id_factory=_ids("lease2"))


def test_a_lock_held_by_another_run_is_not_released_by_this_entry(
    db: Path, roots: Roots
) -> None:
    admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-other", universe_id="u1", lease=None)
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    assert wp.process_entry(db, entry, fs=FakeFs()) == wp.OUTCOME_RELEASED
    assert lock_rows(db) == [("host", "slot-0", "run-1"), ("universe", "u1", "run-1")]


# --------------------------------------------------------------------------
# the rolling-hour ledger (engine-run-admissions)
# --------------------------------------------------------------------------


def test_the_hourly_jobs_bound_is_named_in_the_refusal(db: Path, roots: Roots) -> None:
    clock = [1_000_000.0]
    for index in range(2):
        admit_scratch(
            db,
            roots,
            jobs_per_hour=2,
            lease_id_factory=_ids(f"lease{index}"),
            now=lambda: clock[0],
        )
    with pytest.raises(wp.WorkspacePoolRefused) as exc:
        admit_scratch(
            db,
            roots,
            jobs_per_hour=2,
            lease_id_factory=_ids("lease9"),
            now=lambda: clock[0],
        )
    assert exc.value.code == wp.REFUSED_QUOTA
    assert "jobs per hour (2)" in exc.value.detail
    assert f"clears_at={clock[0] + wp.WINDOW_S}" in exc.value.detail

    usage = wp.ledger_usage(db, "u1", now=lambda: clock[0])
    assert usage.jobs == 2
    assert usage.clears_at == clock[0] + wp.WINDOW_S


def test_charges_outside_the_window_do_not_count(db: Path, roots: Roots) -> None:
    clock = [1_000_000.0]
    admit_scratch(db, roots, jobs_per_hour=1, lease_id_factory=_ids("lease1"), now=lambda: clock[0])
    later = clock[0] + wp.WINDOW_S + 1
    admit_scratch(db, roots, jobs_per_hour=1, lease_id_factory=_ids("lease2"), now=lambda: later)
    assert wp.ledger_usage(db, "u1", now=lambda: later).jobs == 1


def test_two_concurrent_checkouts_cannot_cross_the_hourly_bytes_bound(
    db: Path, roots: Roots
) -> None:
    """engine-run-admissions: 5 GiB of the hour left, two 4 GiB reservations."""
    barrier = threading.Barrier(2)
    results: dict[str, object] = {}
    lock = threading.Lock()

    def attempt(name: str) -> None:
        barrier.wait(timeout=30)
        try:
            outcome: object = admit_scratch(
                db,
                roots,
                run_id="run-1",  # same run: the lock is reentrant, the ledger is not
                max_bytes=4 * GIB,
                bytes_per_hour=5 * GIB,
                lease_id_factory=_ids(f"lease{name}"),
            )
        except wp.WorkspacePoolRefused as exc:
            outcome = exc
        with lock:
            results[name] = outcome

    threads = [threading.Thread(target=attempt, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    admitted = [r for r in results.values() if isinstance(r, wp.Lease)]
    refused = [r for r in results.values() if isinstance(r, wp.WorkspacePoolRefused)]
    assert len(admitted) == 1, results
    assert len(refused) == 1, results
    assert refused[0].code == wp.REFUSED_QUOTA
    assert "bytes per hour" in refused[0].detail
    assert wp.ledger_usage(db, "u1").bytes == 4 * GIB


def test_the_reservation_reconciles_downward_only(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, max_bytes=4 * GIB, lease_id_factory=_ids("lease1"))
    assert wp.ledger_usage(db, "u1").bytes == 4 * GIB
    assert wp.reconcile_bytes(db, lease.lease_id, GIB) == GIB
    assert wp.ledger_usage(db, "u1").bytes == GIB
    stored = wp.get_lease(db, "lease1")
    assert stored is not None
    assert stored.measured_bytes == GIB
    # The POOL reservation stands until release, whatever the transfer measured.
    assert stored.reserved_bytes == wp.DEFAULT_LEASE_BYTES_CAP
    # A measurement above the reservation is clamped, never charged upward.
    assert wp.reconcile_bytes(db, lease.lease_id, 9 * GIB) == GIB
    assert wp.ledger_usage(db, "u1").bytes == GIB


def test_an_interrupted_transfer_keeps_the_maximum_charged(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, max_bytes=4 * GIB, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:  # the run dies; reconcile_bytes is never called
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    wp.process_entry(db, entry, fs=FakeFs(present=(lease.path,)))
    assert wp.ledger_usage(db, "u1").bytes == 4 * GIB
    assert rows(db, "SELECT reserved FROM workspace_ledger WHERE kind = 'bytes'") == [(1,)]


def test_reconciling_an_unknown_lease_is_a_loud_error(db: Path, roots: Roots) -> None:
    admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with pytest.raises(ValueError, match="unknown lease"):
        wp.reconcile_bytes(db, "nope", 1)


def test_a_refused_admission_writes_nothing(db: Path, roots: Roots) -> None:
    admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    before = (
        rows(db, "SELECT lease_id FROM workspace_leases"),
        lock_rows(db),
        rows(db, "SELECT rowid FROM workspace_ledger"),
    )
    with pytest.raises(wp.WorkspacePoolRefused):
        admit_scratch(db, roots, jobs_per_hour=1, lease_id_factory=_ids("lease2"))
    after = (
        rows(db, "SELECT lease_id FROM workspace_leases"),
        lock_rows(db),
        rows(db, "SELECT rowid FROM workspace_ledger"),
    )
    assert after == before


# --------------------------------------------------------------------------
# the outbox processor
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src_present,quarantine_present",
    [(True, False), (False, True), (False, False), (True, True)],
)
def test_every_crash_window_reconciles_on_retry(
    db: Path, roots: Roots, src_present: bool, quarantine_present: bool
) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    present: list[Path] = []
    if src_present:
        present.append(lease.path)
    if quarantine_present:
        present.append(lease.quarantine_path)
    fs = FakeFs(present=tuple(present))
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None

    assert wp.process_entry(db, entry, fs=fs) == wp.OUTCOME_WIPED
    assert fs.present == set()
    assert lease_state(db, "lease1") == wp.STATE_AVAILABLE
    if src_present and quarantine_present:
        # The stale quarantine goes FIRST, or the rename would fail on it.
        assert fs.ops == [
            ("remove", str(lease.quarantine_path)),
            ("rename", str(lease.path), str(lease.quarantine_path)),
            ("remove", str(lease.quarantine_path)),
        ]
    elif src_present:
        assert fs.ops[0] == ("rename", str(lease.path), str(lease.quarantine_path))
    elif quarantine_present:
        assert fs.ops == [("remove", str(lease.quarantine_path))]
    else:
        assert fs.ops == []


def test_a_failed_wipe_is_lost_reported_and_still_releases_the_locks(
    db: Path, roots: Roots
) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    fs = FakeFs(present=(lease.path,), fail_remove=lease.quarantine_path)
    assert wp.process_entry(db, entry, fs=fs) == wp.OUTCOME_LOST
    assert lease_state(db, "lease1") == wp.STATE_LOST
    assert lock_rows(db) == []
    outcome = rows(db, "SELECT outcome, done_at FROM workspace_outbox")[0]
    assert outcome[0].startswith("lost: ")
    assert "permission denied" in outcome[0]
    assert outcome[1] is not None


def test_a_lost_claim_changes_nothing(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    stale = wp.claim_next(db, claimant="slow")
    assert stale is not None
    stolen = wp.claim_next(db, claimant="sweeper", claim_ttl_s=wp.STEAL_ALL_TTL_S)
    assert stolen is not None
    assert stolen.entry_id == stale.entry_id
    assert stolen.claim_token != stale.claim_token

    assert wp.process_entry(db, stale, fs=FakeFs(present=(lease.path,))) == wp.OUTCOME_LOST_CLAIM
    assert lease_state(db, "lease1") == wp.STATE_ACTIVE
    assert len(lock_rows(db)) == 2
    assert rows(db, "SELECT done_at, outcome FROM workspace_outbox") == [(None, None)]

    assert wp.process_entry(db, stolen, fs=FakeFs(present=(lease.path,))) == wp.OUTCOME_WIPED
    assert lease_state(db, "lease1") == wp.STATE_AVAILABLE


def test_processing_an_entry_twice_is_a_no_op(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    assert wp.process_entry(db, entry, fs=FakeFs(present=(lease.path,))) == wp.OUTCOME_WIPED
    assert wp.process_entry(db, entry, fs=FakeFs()) == wp.OUTCOME_ALREADY_DONE
    assert len(rows(db, "SELECT entry_id FROM workspace_outbox WHERE done_at IS NOT NULL")) == 1


def test_the_claim_token_names_its_claimant(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    entry = wp.claim_next(db, claimant="processor-7")
    assert entry is not None
    assert entry.claim_token is not None
    assert entry.claim_token.startswith("processor-7:")
    assert wp.claim_next(db, claimant="other") is None  # a fresh claim is respected


def test_a_permanent_discard_quarantines_by_repo_key_and_generation(
    db: Path, roots: Roots
) -> None:
    first = admit_universe(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.publish_generation(
            conn, universe_id="u1", repo_key="repo", generation=1, path=first.path
        )
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=first)
    assert wp.startup_sweep(db, fs=FakeFs(), claimant="startup") == 1

    second = admit_universe(db, roots, run_id="run-2", lease_id_factory=_ids("lease2"))
    with terminal_txn(db) as conn:
        previous = wp.publish_generation(
            conn, universe_id="u1", repo_key="repo", generation=2, path=second.path
        )
        assert previous == 1
        wp.enqueue_discard(
            conn,
            run_id="run-2",
            universe_id="u1",
            storage_class=wp.STORAGE_UNIVERSE,
            repo_key="repo",
            generation=previous,
        )
    fs = FakeFs(present=(first.path,))
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    assert entry.action == wp.ACTION_DISCARD_PERMANENT
    assert wp.process_entry(db, entry, fs=fs) == wp.OUTCOME_WIPED
    assert fs.ops == [
        ("rename", str(first.path), str(roots.universe / "workspaces" / ".quarantine" / "repo.1")),
        ("remove", str(roots.universe / "workspaces" / ".quarantine" / "repo.1")),
    ]
    # The discarded generation's lease is finished; the published one is not.
    assert lease_state(db, "lease1") == wp.STATE_AVAILABLE
    assert lease_state(db, "lease2") == wp.STATE_ACTIVE
    # The discard released no lock: the run that owns it is still running.
    assert len(lock_rows(db)) == 2


def test_a_run_with_no_lease_only_releases_its_locks(db: Path, roots: Roots) -> None:
    admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        entry_id = wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=None)
    assert entry_id > 0
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    assert entry.action == wp.ACTION_RELEASE_LOCK_ONLY
    assert wp.process_entry(db, entry, fs=FakeFs()) == wp.OUTCOME_RELEASED
    assert lock_rows(db) == []


def test_a_still_authoritative_permanent_lease_is_release_lock_only(
    db: Path, roots: Roots
) -> None:
    lease = admit_universe(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.publish_generation(
            conn, universe_id="u1", repo_key="repo", generation=1, path=lease.path
        )
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    assert entry.action == wp.ACTION_RELEASE_LOCK_ONLY
    fs = FakeFs(present=(lease.path,))
    assert wp.process_entry(db, entry, fs=fs) == wp.OUTCOME_RELEASED
    assert fs.present == {str(lease.path)}  # the universe keeps its workspace
    assert lease_state(db, "lease1") == wp.STATE_ACTIVE
    assert lock_rows(db) == []


# --------------------------------------------------------------------------
# the admission barrier and the sweepers
# --------------------------------------------------------------------------


def test_pending_entries_block_admission_until_the_startup_sweep(
    db: Path, roots: Roots
) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    assert wp.admission_open(db) is False
    with pytest.raises(wp.WorkspacePoolRefused) as exc:
        admit_scratch(db, roots, universe_id="u2", run_id="run-2", lease_id_factory=_ids("x"))
    assert exc.value.code == wp.REFUSED_POOL_BUSY
    assert "startup reconciliation pending" in exc.value.detail

    assert wp.startup_sweep(db, fs=FakeFs(present=(lease.path,)), claimant="startup") == 1
    assert wp.admission_open(db) is True
    admitted = admit_scratch(
        db, roots, universe_id="u2", run_id="run-2", lease_id_factory=_ids("lease2")
    )
    assert admitted.state == wp.STATE_ACTIVE


def test_the_startup_sweep_takes_over_a_dead_processors_claim(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    wp.claim_next(db, claimant="died-mid-wipe")
    assert wp.startup_sweep(db, fs=FakeFs(present=(lease.path,)), claimant="startup") == 1
    assert wp.admission_open(db) is True
    assert rows(db, "SELECT claim_token FROM workspace_outbox")[0][0].startswith("startup:")


def test_the_periodic_sweep_respects_a_live_claim_and_reclaims_an_expired_one(
    db: Path, roots: Roots
) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    clock = [1_000_000.0]
    wp.claim_next(db, claimant="live", now=lambda: clock[0])
    fs = FakeFs(present=(lease.path,))
    assert wp.periodic_sweep(db, fs=fs, claimant="sweeper", now=lambda: clock[0]) == 0
    assert fs.ops == []
    clock[0] += wp.DEFAULT_CLAIM_TTL_S + 1
    assert wp.periodic_sweep(db, fs=fs, claimant="sweeper", now=lambda: clock[0]) == 1
    assert lease_state(db, "lease1") == wp.STATE_AVAILABLE


def test_the_sweeps_are_empty_when_nothing_is_owed(db: Path) -> None:
    assert wp.startup_sweep(db, fs=FakeFs(), claimant="startup") == 0
    assert wp.periodic_sweep(db, fs=FakeFs(), claimant="sweeper") == 0
    assert wp.admission_open(db) is True


def test_claims_are_taken_oldest_first(db: Path, roots: Roots) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    with terminal_txn(db) as conn:
        first = wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
        second = wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=None)
    claimed = wp.claim_next(db, claimant="test")
    assert claimed is not None and claimed.entry_id == first
    assert second > first


# --------------------------------------------------------------------------
# the real filesystem
# --------------------------------------------------------------------------


def test_the_real_processor_wipes_a_lease_and_the_next_one_is_a_new_directory(
    db: Path, roots: Roots
) -> None:
    """scratch-storage: the next run's lease is a NEW directory and nothing of
    the old lease survives under the pool."""
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    (lease.path / "repo" / ".git").mkdir(parents=True)
    (lease.path / "repo" / ".git" / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    assert wp.process_entry(db, entry, fs=RealPoolFilesystem()) == wp.OUTCOME_WIPED
    assert not lease.path.exists()
    assert not lease.quarantine_path.exists()

    nxt = admit_scratch(db, roots, universe_id="u2", run_id="run-2", lease_id_factory=_ids("l2"))
    assert nxt.path != lease.path
    survivors = [p for p in roots.pool.rglob("*") if p.name != ".quarantine"]
    assert survivors == []


def test_a_crash_after_the_rename_is_repaired_on_the_next_claim(
    db: Path, roots: Roots
) -> None:
    """scratch-storage: source absent, deterministic quarantine present."""
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    lease.quarantine_path.mkdir(parents=True)
    (lease.quarantine_path / "leftover.pack").write_bytes(b"0123456789")
    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    assert wp.startup_sweep(db, fs=RealPoolFilesystem(), claimant="startup") == 1
    assert not lease.quarantine_path.exists()
    assert lease_state(db, "lease1") == wp.STATE_AVAILABLE
    assert wp.admission_open(db) is True


def test_a_link_inside_a_lease_never_leaks_the_wipe_outside_it(
    db: Path, roots: Roots, tmp_path: Path
) -> None:
    lease = admit_scratch(db, roots, lease_id_factory=_ids("lease1"))
    (lease.path / "repo").mkdir(parents=True)
    (lease.path / "repo" / "file.txt").write_text("scratch", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    precious = outside / "keep.txt"
    precious.write_text("the host's data", encoding="utf-8")
    kind = make_dir_link(lease.path / "repo" / "escape", outside)
    if kind is None:
        pytest.skip("this host allows neither a symlink nor a junction")

    with terminal_txn(db) as conn:
        wp.enqueue_terminal(conn, run_id="run-1", universe_id="u1", lease=lease)
    entry = wp.claim_next(db, claimant="test")
    assert entry is not None
    assert wp.process_entry(db, entry, fs=RealPoolFilesystem()) == wp.OUTCOME_WIPED

    assert not lease.path.exists()
    assert outside.is_dir()
    assert precious.read_text(encoding="utf-8") == "the host's data"


def test_the_real_filesystem_sees_a_dangling_link_as_present(tmp_path: Path) -> None:
    fs = RealPoolFilesystem()
    target = tmp_path / "gone"
    link = tmp_path / "link"
    kind = make_dir_link(link, target)
    if kind is None:
        pytest.skip("this host allows neither a symlink nor a junction")
    assert fs.exists(link) is True
    fs.remove_tree_no_follow(link)
    assert fs.exists(link) is False


def test_removing_a_path_that_is_already_gone_is_a_no_op(tmp_path: Path) -> None:
    RealPoolFilesystem().remove_tree_no_follow(tmp_path / "never-existed")


# --------------------------------------------------------------------------
# the module's own discipline
# --------------------------------------------------------------------------


def test_the_module_creates_no_directories_and_reads_no_env_vars() -> None:
    """The pool computes paths only. Directory creation belongs to the caller,
    which holds a handle resolved without following links, and configuration is
    a parameter - never a switch read out of the process's env vars."""
    source = Path(wp.__file__).read_text(encoding="utf-8")
    for forbidden in ("environ", "mkdir", "makedirs", "getenv"):
        assert forbidden not in source, forbidden
    assert "import os" not in source
