"""A workspace lock the sweep cannot see is held forever.

Live, 2026-09-01. The founder's universe could not check out a repository:

    workspace not admitted: universe lock
    'u-01kxm1vszd8hwp7em418asq8h9' is held by run '8f30bb9abf2b492f'

That run FAILED the previous day — it is the one that hit the old
`api.github.com` 403 that #2753 fixed. Its lock outlived it by a day and blocked
every workspace operation for that universe, including the code-first workaround
the universe built to get around a separate problem.

The sweep exists for exactly this and could not see it: orphaned locks were
found with an INNER JOIN against `runs`, so a lock whose `run_id` has no row in
THAT database is dropped by the join. Nothing else releases it, because nothing
will ever transition a run this database has never heard of. Runs are recorded
per-universe as well as at the root, so a lock and its run can live in different
files — and then the lock is permanent.
"""
from __future__ import annotations

import sqlite3
import time

import pytest


@pytest.fixture
def base(tmp_path):
    from tinyassets import workspace_pool
    from tinyassets.runs import runs_db_path

    db = runs_db_path(tmp_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        workspace_pool.ensure_schema(conn)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runs ("
            "run_id TEXT PRIMARY KEY, status TEXT NOT NULL)"
        )
    return tmp_path


def _lock(base, run_id: str, *, age_s: float, universe: str = "u-1") -> None:
    from tinyassets.runs import runs_db_path

    with sqlite3.connect(runs_db_path(base)) as conn:
        conn.execute(
            'INSERT OR REPLACE INTO workspace_locks (scope, "key", run_id, '
            "lease_id, acquired_at) VALUES ('universe', ?, ?, NULL, ?)",
            (universe, run_id, time.time() - age_s),
        )


def _outbox_rows(base) -> list[tuple]:
    from tinyassets.runs import runs_db_path

    with sqlite3.connect(runs_db_path(base)) as conn:
        return conn.execute(
            "SELECT run_id, release_universe_lock FROM workspace_outbox"
        ).fetchall()


def test_a_lock_whose_run_is_unknown_gets_released(base):
    """THE regression. The run has no row here at all, so the INNER JOIN drops
    it and it is never swept — which is how a day-old lock survived."""
    from tinyassets.runs import _workspace_sweep_once

    _lock(base, "8f30bb9abf2b492f", age_s=86_400)

    _workspace_sweep_once(base, claimant="test")

    queued = {row[0] for row in _outbox_rows(base)}
    assert "8f30bb9abf2b492f" in queued, (
        "a lock whose run this database does not know was left held forever"
    )


def test_a_lock_taken_moments_ago_is_left_alone(base):
    """A lock is written BEFORE its run row on a legitimate start. Sweeping
    unknown-run locks eagerly would reap live work inside that window."""
    from tinyassets.runs import _workspace_sweep_once

    _lock(base, "run-just-started", age_s=5)

    _workspace_sweep_once(base, claimant="test")

    queued = {row[0] for row in _outbox_rows(base)}
    assert "run-just-started" not in queued, (
        "a lock from a run that may still be starting was swept"
    )


def test_a_lock_held_by_a_RUNNING_run_is_left_alone(base):
    """The known-run path must be unchanged: an active run keeps its lock
    however old it is."""
    from tinyassets.runs import _workspace_sweep_once, runs_db_path

    with sqlite3.connect(runs_db_path(base)) as conn:
        conn.execute("INSERT INTO runs (run_id, status) VALUES ('busy', 'running')")
    _lock(base, "busy", age_s=86_400)

    _workspace_sweep_once(base, claimant="test")

    queued = {row[0] for row in _outbox_rows(base)}
    assert "busy" not in queued, "a live run's lock was swept out from under it"


def test_a_lock_held_by_a_FINISHED_run_is_still_released(base):
    """The behaviour that already worked, pinned so the new clause did not
    replace it."""
    from tinyassets.runs import _workspace_sweep_once, runs_db_path

    with sqlite3.connect(runs_db_path(base)) as conn:
        conn.execute("INSERT INTO runs (run_id, status) VALUES ('done', 'failed')")
    _lock(base, "done", age_s=10)

    _workspace_sweep_once(base, claimant="test")

    queued = {row[0] for row in _outbox_rows(base)}
    assert "done" in queued
