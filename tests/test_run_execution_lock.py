"""Cross-process run lifetime ownership, independent of file admission."""

from __future__ import annotations

import multiprocessing
import os
import sqlite3
import threading

import pytest

from tinyassets.runs import runs_db_path
from tinyassets.storage.run_execution_lock import RunExecutionGuard, try_run_execution_lock


def _child_lock(base, run_id, output):
    with try_run_execution_lock(base, run_id=run_id) as guard:
        output.put(guard is not None)


def _crash_with_lock(base):
    context = try_run_execution_lock(base, run_id="crashed")
    guard = context.__enter__()
    os._exit(0 if guard is not None else 2)


def test_guard_is_nonexpiring_cross_process_and_bound_to_database(tmp_path):
    database = runs_db_path(tmp_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    ctx = multiprocessing.get_context("spawn")
    with try_run_execution_lock(tmp_path, run_id="ordinary:run/identifier") as guard:
        guard.require_held(conn)
        with try_run_execution_lock(tmp_path, run_id=guard.run_id) as duplicate:
            assert duplicate is None
        queue = ctx.Queue()
        child = ctx.Process(target=_child_lock, args=(str(tmp_path), guard.run_id, queue))
        child.start()
        child.join(15)
        assert child.exitcode == 0
        assert queue.get(timeout=2) is False
        queue.close()
        other = sqlite3.connect(tmp_path / "other.db")
        with pytest.raises(RuntimeError, match="database"):
            guard.require_held(other)
        other.close()
    with pytest.raises(RuntimeError, match="held"):
        guard.require_held(conn)
    with try_run_execution_lock(tmp_path, run_id=guard.run_id) as fresh:
        fresh.require_held(conn)
    conn.close()


def test_guard_rejects_cross_thread_and_different_runs_are_independent(tmp_path):
    conn = sqlite3.connect(runs_db_path(tmp_path))
    errors = []
    with try_run_execution_lock(tmp_path, run_id="one") as guard:

        def other_thread():
            try:
                guard.require_held(conn)
            except RuntimeError as exc:
                errors.append(str(exc))

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join(2)
        assert errors and "held" in errors[0]
        with try_run_execution_lock(tmp_path, run_id="two") as independent:
            independent.require_held(conn)
    conn.close()


@pytest.mark.parametrize("run_id", [None, "", True, "x" * 257])
def test_bad_identity_never_becomes_a_path(tmp_path, run_id):
    with pytest.raises(ValueError):
        with try_run_execution_lock(tmp_path, run_id=run_id):
            pytest.fail("bad run identity accepted")


def test_crash_releases_ownership_without_replacing_sidecar(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    child = ctx.Process(target=_crash_with_lock, args=(str(tmp_path),))
    child.start()
    child.join(15)
    assert child.exitcode == 0
    sidecar = next((runs_db_path(tmp_path).parent / ".run-execution-locks").glob("*.lock"))
    before = sidecar.stat()
    with try_run_execution_lock(tmp_path, run_id="crashed") as guard:
        assert guard is not None
    after = sidecar.stat()
    assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)


def test_constructed_or_inherited_guard_cannot_fake_ownership(tmp_path, monkeypatch):
    database = runs_db_path(tmp_path)
    conn = sqlite3.connect(database)
    invented = RunExecutionGuard(database.resolve(), "run")
    with pytest.raises(RuntimeError, match="held"):
        invented.require_held(conn)
    with try_run_execution_lock(tmp_path, run_id="run") as guard:
        monkeypatch.setattr(os, "getpid", lambda: guard._pid + 1)
        with pytest.raises(RuntimeError, match="held"):
            guard.require_held(conn)
    conn.close()
