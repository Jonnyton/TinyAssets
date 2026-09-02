"""A workspace lock the sweep cannot see is held forever.

Live, 2026-09-01. The founder's universe could not check out a repository:

    workspace not admitted: universe lock
    'u-01kxm1vszd8hwp7em418asq8h9' is held by run '8f30bb9abf2b492f'

That run had FAILED 27 hours earlier -- it is the one that hit the old
`api.github.com` 403 that #2753 fixed. Read straight out of the production
databases: the lock (and the host slot) sat in the UNIVERSE's runs database,
whose `runs` table was empty; the run's row, status `failed`, sat in the ROOT
one. The terminal enqueue ran against the root, found no lock there, and wrote
nothing. The sweep found orphaned locks with an INNER JOIN against the local
`runs` table, so it could not see the lock either.

That is the live topology, not a corner case: EVERY workspace run leaves its
locks held. The sweep therefore consults the root, where runs are recorded.
"""
from __future__ import annotations

import sqlite3
import time

import pytest


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """A root data dir (where run rows live) and one universe dir under it
    (where the workspace effector keeps locks, leases and the outbox)."""
    from tinyassets import workspace_pool
    from tinyassets.runs import runs_db_path

    root = tmp_path / "data"
    universe = root / "u-1"
    universe.mkdir(parents=True)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    for base in (root, universe):
        db = runs_db_path(base)
        with sqlite3.connect(db) as conn:
            workspace_pool.ensure_schema(conn)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS runs ("
                "run_id TEXT PRIMARY KEY, status TEXT NOT NULL)"
            )
    return root, universe


def _lock(
    base, run_id: str, *, age_s: float, universe: str = "u-1", slot: str = "slot-0",
) -> None:
    """One universe lock and one host slot, both held by ``run_id``. The table
    is keyed by (scope, key), so two locks in one test need distinct keys or
    the second silently replaces the first (which is how a test here once
    passed without its subject existing)."""
    from tinyassets.runs import runs_db_path

    with sqlite3.connect(runs_db_path(base)) as conn:
        conn.execute(
            'INSERT INTO workspace_locks (scope, "key", run_id, '
            "lease_id, acquired_at) VALUES ('universe', ?, ?, NULL, ?)",
            (universe, run_id, time.time() - age_s),
        )
        conn.execute(
            'INSERT INTO workspace_locks (scope, "key", run_id, '
            "lease_id, acquired_at) VALUES ('host', ?, ?, NULL, ?)",
            (slot, run_id, time.time() - age_s),
        )


def _run_row(base, run_id: str, status: str) -> None:
    from tinyassets.runs import runs_db_path

    with sqlite3.connect(runs_db_path(base)) as conn:
        conn.execute("INSERT INTO runs (run_id, status) VALUES (?, ?)", (run_id, status))


def _queued(base) -> set[str]:
    from tinyassets.runs import runs_db_path

    with sqlite3.connect(runs_db_path(base)) as conn:
        return {row[0] for row in conn.execute("SELECT run_id FROM workspace_outbox")}


def _held(base) -> set[tuple[str, str]]:
    from tinyassets.runs import runs_db_path

    with sqlite3.connect(runs_db_path(base)) as conn:
        return {
            (row[0], row[1])
            for row in conn.execute('SELECT scope, "key" FROM workspace_locks')
        }


def _held_by(base) -> set[tuple[str, str]]:
    """``(scope, run_id)`` for every lock still in the table."""
    from tinyassets.runs import runs_db_path

    with sqlite3.connect(runs_db_path(base)) as conn:
        return {
            (row[0], row[1])
            for row in conn.execute("SELECT scope, run_id FROM workspace_locks")
        }


# ------------------------------------------------- the live production shape


def test_the_live_shape_a_run_that_FAILED_at_the_root_is_released_at_once(dirs):
    """THE regression, exactly as production had it: lock in the universe DB,
    run row at the root with a terminal status, nothing pending. Released on
    the very next sweep, however young -- this is what lets one workspace job
    follow another instead of waiting out the age bound."""
    from tinyassets.runs import _workspace_sweep_once

    root, universe = dirs
    _run_row(root, "8f30bb9abf2b492f", "failed")
    _lock(universe, "8f30bb9abf2b492f", age_s=5)

    _workspace_sweep_once(universe, claimant="test")

    assert "8f30bb9abf2b492f" in _queued(universe), (
        "a lock whose run finished at the root was left held"
    )
    assert _held(universe) == set(), (
        "the outbox entry did not release BOTH the universe lock and the host slot"
    )


def test_a_run_that_is_still_RUNNING_at_the_root_keeps_its_lock_however_old(dirs):
    """The hazard an age bound alone gets wrong: a long job (more than an hour)
    whose row lives at the root is live, not orphaned."""
    from tinyassets.runs import _workspace_sweep_once

    root, universe = dirs
    _run_row(root, "long-job", "running")
    _lock(universe, "long-job", age_s=86_400)

    _workspace_sweep_once(universe, claimant="test")

    assert "long-job" not in _queued(universe), (
        "a live run's lock was swept out from under it because it was old"
    )


# ------------------------------------------------ a run known nowhere at all


def test_a_lock_whose_run_is_known_nowhere_is_released_once_it_is_old(dirs):
    """No row here, no row at the root: nothing will ever transition it, so
    age is the only evidence left, and a day is far past any real start."""
    from tinyassets.runs import _workspace_sweep_once

    _root, universe = dirs
    _lock(universe, "vanished", age_s=86_400)

    _workspace_sweep_once(universe, claimant="test")

    assert "vanished" in _queued(universe)


def test_a_lock_taken_moments_ago_by_a_run_known_nowhere_is_left_alone(dirs):
    """A lock is written BEFORE its run row on a legitimate start. Sweeping
    unknown-run locks eagerly would reap live work inside that window."""
    from tinyassets.runs import _workspace_sweep_once

    _root, universe = dirs
    _lock(universe, "run-just-started", age_s=5)

    _workspace_sweep_once(universe, claimant="test")

    assert "run-just-started" not in _queued(universe), (
        "a lock from a run that may still be starting was swept"
    )


# --------------------------------------------- the local paths are unchanged


def test_a_lock_held_by_a_run_RUNNING_locally_is_left_alone(dirs):
    from tinyassets.runs import _workspace_sweep_once

    _root, universe = dirs
    _run_row(universe, "busy", "running")
    _lock(universe, "busy", age_s=86_400)

    _workspace_sweep_once(universe, claimant="test")

    assert "busy" not in _queued(universe)


def test_a_lock_held_by_a_run_FINISHED_locally_is_still_released(dirs):
    from tinyassets.runs import _workspace_sweep_once

    _root, universe = dirs
    _run_row(universe, "done", "failed")
    _lock(universe, "done", age_s=10)

    _workspace_sweep_once(universe, claimant="test")

    assert "done" in _queued(universe)


def test_sweeping_the_root_itself_does_not_consult_itself(dirs):
    """At the root there is no 'elsewhere': an unknown run there falls back to
    the age bound and nothing else."""
    from tinyassets.runs import _workspace_sweep_once

    root, _universe = dirs
    _lock(root, "root-young", age_s=5, universe="u-young", slot="slot-1")
    _lock(root, "root-old", age_s=86_400, universe="u-old", slot="slot-0")
    assert {r for _s, r in _held_by(root)} == {"root-young", "root-old"}, (
        "both subjects must exist before the sweep, or the test is vacuous"
    )

    _workspace_sweep_once(root, claimant="test")

    queued = _queued(root)
    assert "root-old" in queued
    assert "root-young" not in queued
