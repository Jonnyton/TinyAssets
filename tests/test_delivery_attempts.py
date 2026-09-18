"""Real attempt locks and conservative recovery; no public intake proof."""

import errno
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_delivery_reservations import (
    _accept,
    _counts,
    _read,
    delivery_env,  # noqa: F401
)
from tests.test_receiver_links import env as management_env  # noqa: F401
from tests.test_workspace_run_wiring import _admit, _pending
from tinyassets import runs
from tinyassets.storage import deliveries, delivery_lock


@pytest.fixture
def reserved(delivery_env):  # noqa: F811
    base, _, _, link = delivery_env
    with deliveries.transaction(base) as conn:
        receipt = _accept(conn, link)
        private = _read(conn, receipt, principal="receiver", universe="u-receiver")
    return base, receipt, private["run_id"]


def _lock(base, receipt):
    return delivery_lock.try_attempt_lock(base, delivery_id=receipt["delivery_id"], attempt=1)


def test_lock_excludes_same_thread_and_other_threads_without_unlinking(reserved):
    base, receipt, _ = reserved

    def contender():
        with _lock(base, receipt) as other:
            return other is None

    with _lock(base, receipt) as guard:
        assert guard is not None
        assert contender()
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert all(pool.map(lambda _: contender(), range(8)))
        path = base / ".delivery-locks" / f"{receipt['delivery_id']}-1.lock"
        inode = path.stat().st_ino
    assert path.exists()
    with _lock(base, receipt) as reacquired:
        assert reacquired is not None
        assert path.stat().st_ino == inode
    with deliveries.transaction(base) as conn:
        with pytest.raises(RuntimeError, match="not held"):
            deliveries.recover_attempt_in_transaction(conn, guard)


def test_lock_io_failure_never_becomes_acquisition(reserved, monkeypatch):
    base, receipt, _ = reserved

    def io_failure(fd):
        raise OSError(errno.EIO, "injected storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(delivery_lock, "_try_os_lock", io_failure)
        with pytest.raises(OSError, match="injected storage failure"):
            with _lock(base, receipt):
                pytest.fail("I/O error must not enter guarded code")
    with _lock(base, receipt) as guard:
        assert guard is not None  # Failed acquisition did not leak its thread lock.


@pytest.mark.parametrize(
    "identity, attempt", [("../../escape", 1), ("a" * 32, 0), ("a" * 32, True)]
)
def test_lock_names_are_server_generated(tmp_path, identity, attempt):
    with pytest.raises(ValueError):
        with delivery_lock.try_attempt_lock(tmp_path, delivery_id=identity, attempt=attempt):
            pytest.fail("invalid lock identity")


def test_guard_cannot_cross_database_or_thread(reserved, tmp_path):
    base, receipt, _ = reserved
    with _lock(base, receipt) as guard:
        with deliveries.transaction(tmp_path / "other") as conn:
            with pytest.raises(RuntimeError, match="another database"):
                guard.require_held(conn)

        def foreign_thread():
            with deliveries.transaction(base) as conn:
                with pytest.raises(RuntimeError, match="not held"):
                    guard.require_held(conn)

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(foreign_thread).result(timeout=10)


def test_proven_unstarted_run_survives_startup_interruption_without_new_reservation(reserved):
    base, receipt, run_id = reserved
    runs.update_run_status(base, run_id, status="interrupted", error="startup", finished_at=1)
    with _lock(base, receipt) as guard:
        with deliveries.transaction(base) as conn:
            recovered = deliveries.recover_attempt_in_transaction(conn, guard)
            assert recovered["state"] == "pending"
            assert recovered["execution_started_at"] is None
            token = deliveries.start_attempt_in_transaction(conn, guard)
            assert token
        with deliveries.transaction(base) as conn:
            attempt = conn.execute("SELECT * FROM graph_delivery_attempts").fetchone()
            run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            assert attempt["claim_token"] == token
            assert attempt["execution_started_at"] is not None
            assert run["status"] == "queued"
            assert run["error"] == ""
            assert run["finished_at"] is None
    assert _counts(base) == (1, 1, 1)


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "running"])
def test_nonpending_run_is_never_replayed_even_without_start_marker(reserved, status):
    base, receipt, run_id = reserved
    runs.update_run_status(base, run_id, status=status)
    with _lock(base, receipt) as guard:
        with deliveries.transaction(base) as conn:
            assert deliveries.start_attempt_in_transaction(conn, guard) is None
            observed = _read(conn, receipt)
            assert observed["status"] == ("interrupted" if status == "running" else status)
    assert _counts(base) == (1, 1, 1)


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "interrupted"])
def test_completion_uses_exact_claim_and_does_not_leak_receiver_error(reserved, status):
    base, receipt, run_id = reserved
    with _lock(base, receipt) as guard:
        with deliveries.transaction(base) as conn:
            token = deliveries.start_attempt_in_transaction(conn, guard)
        runs.update_run_status(base, run_id, status=status, error="private-secret-receiver-output")
        with deliveries.transaction(base) as conn:
            with pytest.raises(RuntimeError, match="claim lost"):
                deliveries.finish_attempt_in_transaction(conn, guard, claim_token="stale")
            deliveries.finish_attempt_in_transaction(conn, guard, claim_token=token)
            observed = _read(conn, receipt)
            assert observed["status"] == status
            assert observed["finished_at"] is not None
            assert "private-secret" not in str(observed)
            assert "run_id" not in observed
            assert deliveries.start_attempt_in_transaction(conn, guard) is None


def test_unfinished_run_cannot_publish_success(reserved):
    base, receipt, _ = reserved
    with _lock(base, receipt) as guard:
        with deliveries.transaction(base) as conn:
            token = deliveries.start_attempt_in_transaction(conn, guard)
        with deliveries.transaction(base) as conn:
            with pytest.raises(RuntimeError, match="not reached a terminal"):
                deliveries.finish_attempt_in_transaction(conn, guard, claim_token=token)
            assert _read(conn, receipt)["status"] == "running"


def test_recovery_owes_workspace_cleanup_atomically(reserved, tmp_path, monkeypatch):
    base, receipt, run_id = reserved
    with _lock(base, receipt) as guard:
        with deliveries.transaction(base) as conn:
            assert deliveries.start_attempt_in_transaction(conn, guard)
    lease = _admit(base, tmp_path, run_id)
    with _lock(base, receipt) as guard:
        with pytest.raises(RuntimeError, match="before commit"):
            with deliveries.transaction(base) as conn:
                deliveries.recover_attempt_in_transaction(conn, guard)
                raise RuntimeError("before commit")
        assert _pending(base, run_id) == []
        with deliveries.transaction(base) as conn:
            assert (
                conn.execute("SELECT state FROM graph_delivery_attempts").fetchone()[0]
                == "executing"
            )
        kicks = []
        monkeypatch.setattr(runs, "_kick_workspace_sweep", lambda p: kicks.append(p))
        assert deliveries.reconcile_attempt(base, guard)["state"] == "interrupted"
        assert _pending(base, run_id) == [("wipe_scratch", lease.lease_id)]
        assert kicks == [base]
        assert deliveries.reconcile_attempt(base, guard)["state"] == "interrupted"
        assert _pending(base, run_id) == [("wipe_scratch", lease.lease_id)]


def _process_hold_and_crash(base, receipt, mark_started, ready, stop):
    with _lock(base, receipt) as guard:
        assert guard is not None
        if mark_started:
            with deliveries.transaction(base) as conn:
                assert deliveries.start_attempt_in_transaction(conn, guard)
                if mark_started == "terminal":
                    run_id = conn.execute("SELECT run_id FROM graph_delivery_attempts").fetchone()[
                        0
                    ]
            if mark_started == "terminal":
                runs.update_run_status(base, run_id, status="completed")
        ready.send(True)
        if not stop.wait(20):
            raise RuntimeError("test did not release child")
        os._exit(74)  # No finally cleanup: only the kernel can release this lock.


@pytest.mark.parametrize("mark_started", [False, True, "terminal"])
def test_process_death_resumes_only_proven_unstarted_attempt(reserved, mark_started):
    base, receipt, run_id = reserved
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    stop = context.Event()
    child = context.Process(
        target=_process_hold_and_crash, args=(base, receipt, mark_started, send, stop)
    )
    try:
        child.start()
        assert receive.poll(20)
        assert receive.recv()
        with _lock(base, receipt) as blocked:
            assert blocked is None
        stop.set()
        child.join(timeout=10)
        assert child.exitcode == 74
        with _lock(base, receipt) as guard:
            assert guard is not None
            with deliveries.transaction(base) as conn:
                recovered = deliveries.recover_attempt_in_transaction(conn, guard)
                expected = (
                    "completed"
                    if mark_started == "terminal"
                    else ("interrupted" if mark_started else "pending")
                )
                assert recovered["state"] == expected
                token = deliveries.start_attempt_in_transaction(conn, guard)
                assert bool(token) is not bool(mark_started)
                assert recovered["run_id"] == run_id
        assert _counts(base) == (1, 1, 1)
    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)
        receive.close()
        send.close()
