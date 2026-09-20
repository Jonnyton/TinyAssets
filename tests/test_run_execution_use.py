"""Derived use pins real work; only the original thread owns the OS guard."""

import multiprocessing
import os
import pickle
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_run_execution_lock import _child_lock
from tinyassets import runs
from tinyassets.storage.run_execution_lock import try_run_execution_lock


def test_pool_thread_use_is_not_owner_authority(tmp_path):
    with sqlite3.connect(runs.runs_db_path(tmp_path)) as conn:
        with try_run_execution_lock(tmp_path, run_id="run") as guard:
            use = guard.issue_use(conn)
            assert guard.issue_use(conn) is use

            def worker():
                with sqlite3.connect(runs.runs_db_path(tmp_path)) as reader:
                    with pytest.raises(RuntimeError, match="held"):
                        guard.require_held(reader)
                    with pytest.raises(RuntimeError, match="held"):
                        guard.issue_use(reader)
                    with use.hold(reader):
                        use.require_in_use(reader)
                        with pytest.raises(runs.RunExecutionAuthorityLost):
                            runs.terminalize_unstarted_run(
                                tmp_path, run_id="run", execution_guard=use,
                                status="failed", error="not owner",
                            )
                    with pytest.raises(RuntimeError, match="use"):
                        use.require_in_use(reader)

            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(worker).result(timeout=3)
            with pytest.raises(TypeError):
                pickle.dumps(use)
        with pytest.raises(RuntimeError):
            with use.hold(conn):
                pytest.fail("retired use entered")


@pytest.mark.parametrize("interrupt_wait", [False, True])
def test_owner_unlock_waits_for_actual_use_and_rejects_late_work(tmp_path, interrupt_wait):
    sqlite3.connect(runs.runs_db_path(tmp_path)).close()
    entered, release, leaving, finished = (threading.Event() for _ in range(4))
    holders, errors = [], []

    def actual_worker(use):
        with sqlite3.connect(runs.runs_db_path(tmp_path)) as conn:
            with use.hold(conn):
                entered.set()
                assert release.wait(10)

    def owner():
        try:
            with try_run_execution_lock(tmp_path, run_id="run") as guard:
                with sqlite3.connect(runs.runs_db_path(tmp_path)) as conn:
                    use = guard.issue_use(conn)
                holders.extend((guard, use))
                worker = threading.Thread(target=actual_worker, args=(use,))
                worker.start()
                assert entered.wait(3)
                if interrupt_wait:
                    wait = guard._condition.wait
                    calls = []

                    def interrupted(*args, **kwargs):
                        if not calls:
                            calls.append(True)
                            raise RuntimeError("injected wait interruption")
                        return wait(*args, **kwargs)

                    guard._condition.wait = interrupted
                leaving.set()
            worker.join(3)
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=owner)
    thread.start()
    try:
        assert leaving.wait(3)
        guard, use = holders
        end = time.monotonic() + 3
        while not guard._closing and time.monotonic() < end:
            time.sleep(.01)
        assert guard._closing and not finished.is_set()
        with sqlite3.connect(runs.runs_db_path(tmp_path)) as conn:
            with pytest.raises(RuntimeError, match="closing"):
                with use.hold(conn):
                    pytest.fail("late work entered")
        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        child = ctx.Process(target=_child_lock, args=(str(tmp_path), "run", queue))
        child.start()
        child.join(10)
        assert child.exitcode == 0 and queue.get(timeout=2) is False
        queue.close()
        release.set()
        thread.join(5)
        assert finished.is_set()
        assert bool(errors) == interrupt_wait
        if errors:
            assert str(errors[0]) == "injected wait interruption"
        with try_run_execution_lock(tmp_path, run_id="run") as next_owner:
            assert next_owner is not None
    finally:
        release.set()
        thread.join(5)


def test_wrong_database_and_unissued_use_refuse(tmp_path):
    from tinyassets.storage.run_execution_lock import RunExecutionUse

    with sqlite3.connect(runs.runs_db_path(tmp_path)) as conn:
        with try_run_execution_lock(tmp_path, run_id="run") as guard:
            use = guard.issue_use(conn)
            with sqlite3.connect(tmp_path / "other.db") as wrong:
                with pytest.raises(RuntimeError, match="database"):
                    with use.hold(wrong):
                        pytest.fail("wrong DB")
            fake = RunExecutionUse(guard)
            with pytest.raises(RuntimeError, match="issued"):
                with fake.hold(conn):
                    pytest.fail("unissued receipt")


def test_callback_exception_does_not_release_sibling_pin(tmp_path):
    entered, release = threading.Event(), threading.Event()
    with sqlite3.connect(runs.runs_db_path(tmp_path)) as conn:
        with try_run_execution_lock(tmp_path, run_id="run") as guard:
            use = guard.issue_use(conn)

            def sibling():
                with sqlite3.connect(runs.runs_db_path(tmp_path)) as reader:
                    with use.hold(reader):
                        entered.set()
                        assert release.wait(5)

            with ThreadPoolExecutor(max_workers=1) as pool:
                worker = pool.submit(sibling)
                try:
                    assert entered.wait(2)
                    with pytest.raises(ValueError, match="callback"):
                        with use.hold(conn):
                            raise ValueError("callback failure")
                    assert len(guard._pins) == 1
                    with try_run_execution_lock(tmp_path, run_id="run") as competing:
                        assert competing is None
                finally:
                    release.set()
                worker.result(timeout=3)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="actual fork-inherited receipt")
def test_forked_use_refuses_before_touching_parent_condition(tmp_path):
    with sqlite3.connect(runs.runs_db_path(tmp_path)) as conn:
        with try_run_execution_lock(tmp_path, run_id="run") as guard:
            use = guard.issue_use(conn)
            guard._condition.acquire()
            try:
                pid = os.fork()
                if pid == 0:
                    try:
                        with use.hold(conn):
                            os._exit(2)
                    except RuntimeError:
                        os._exit(0)
                _, status = os.waitpid(pid, 0)
                assert os.waitstatus_to_exitcode(status) == 0
            finally:
                guard._condition.release()
