"""Tests for tinyassets/singleton_lock.py.

Host singleton — one tray / MCP / tunnel per host. The OS-level file
lock is the ground-truth exclusion mechanism; the PID sidecar is
diagnostic. These tests pin the race, stale-lock, and crash-recovery
contracts that #19 tray integration will rely on.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys

import pytest

from tinyassets.singleton_lock import (
    LockAcquisition,
    _pid_alive,
    _pid_path,
    acquire_singleton_lock,
    release_singleton_lock,
)

# -------------------------------------------------------------------
# Basic acquire + release
# -------------------------------------------------------------------


def test_fresh_acquire_succeeds_and_writes_pid_sidecar(tmp_path):
    lock_path = tmp_path / "test.lock"

    acq = acquire_singleton_lock(lock_path)
    try:
        assert acq.acquired is True
        assert acq.fd is not None
        assert acq.path == lock_path
        assert acq.existing_pid is None
        assert lock_path.exists()

        pid_file = _pid_path(lock_path)
        assert pid_file.exists()
        assert int(pid_file.read_text(encoding="utf-8").strip()) == os.getpid()
    finally:
        release_singleton_lock(acq)


def test_second_acquire_fails_while_first_held(tmp_path):
    """In the same process, a second acquire returns acquired=False with
    existing_pid populated from the sidecar. No crash, no block."""
    lock_path = tmp_path / "test.lock"

    first = acquire_singleton_lock(lock_path)
    try:
        assert first.acquired is True

        second = acquire_singleton_lock(lock_path)
        assert second.acquired is False
        assert second.fd is None
        assert second.existing_pid == os.getpid()
    finally:
        release_singleton_lock(first)


def test_release_allows_reacquire(tmp_path):
    """After clean release, next acquire succeeds."""
    lock_path = tmp_path / "test.lock"

    first = acquire_singleton_lock(lock_path)
    assert first.acquired is True
    release_singleton_lock(first)

    second = acquire_singleton_lock(lock_path)
    try:
        assert second.acquired is True
    finally:
        release_singleton_lock(second)


def test_release_is_idempotent_on_unacquired(tmp_path):
    """release_singleton_lock on a failed acquisition is a no-op, not a crash."""
    lock_path = tmp_path / "test.lock"

    first = acquire_singleton_lock(lock_path)
    try:
        second = acquire_singleton_lock(lock_path)
        assert second.acquired is False

        # Should NOT raise.
        release_singleton_lock(second)
    finally:
        release_singleton_lock(first)


def test_release_cleans_up_sidecar_files(tmp_path):
    lock_path = tmp_path / "test.lock"

    acq = acquire_singleton_lock(lock_path)
    assert lock_path.exists()
    assert _pid_path(lock_path).exists()

    release_singleton_lock(acq)

    # Best-effort cleanup — after release the sidecars should be gone.
    assert not _pid_path(lock_path).exists()
    assert not lock_path.exists()


# -------------------------------------------------------------------
# Stale-lock recovery
# -------------------------------------------------------------------


def test_stale_pid_sidecar_alone_does_not_block_acquire(tmp_path):
    """A leftover .pid file without an OS lock is stale — new acquire succeeds."""
    lock_path = tmp_path / "test.lock"
    pid_file = _pid_path(lock_path)

    # Simulate crash-recovery state: a .pid file exists but no process
    # holds the OS lock on the companion file.
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text("999999\n", encoding="utf-8")
    # Note: no lock file — acquire_singleton_lock creates it.

    acq = acquire_singleton_lock(lock_path)
    try:
        assert acq.acquired is True, (
            "A stale PID sidecar without an active OS lock must not block "
            "acquisition — the OS lock is ground truth."
        )
        # The acquire overwrites the PID sidecar with our own PID.
        assert int(pid_file.read_text(encoding="utf-8").strip()) == os.getpid()
    finally:
        release_singleton_lock(acq)


def test_unreadable_pid_sidecar_does_not_crash(tmp_path):
    """An empty or non-integer .pid sidecar on a conflict returns existing_pid=None."""
    lock_path = tmp_path / "test.lock"

    first = acquire_singleton_lock(lock_path)
    try:
        assert first.acquired is True
        # Corrupt the sidecar.
        pid_file = _pid_path(lock_path)
        pid_file.write_text("not-a-number\n", encoding="utf-8")

        # Second acquire should still fail (OS lock held) but report
        # existing_pid=None rather than crashing on the bad sidecar.
        second = acquire_singleton_lock(lock_path)
        assert second.acquired is False
        assert second.existing_pid is None
    finally:
        release_singleton_lock(first)


def test_empty_pid_sidecar_returns_none(tmp_path):
    lock_path = tmp_path / "test.lock"

    first = acquire_singleton_lock(lock_path)
    try:
        _pid_path(lock_path).write_text("", encoding="utf-8")

        second = acquire_singleton_lock(lock_path)
        assert second.acquired is False
        assert second.existing_pid is None
    finally:
        release_singleton_lock(first)


# -------------------------------------------------------------------
# _pid_alive liveness probe
# -------------------------------------------------------------------


def test_pid_alive_returns_true_for_current_process():
    assert _pid_alive(os.getpid()) is True


def test_pid_alive_returns_false_for_zero_or_negative():
    assert _pid_alive(0) is False
    assert _pid_alive(-1) is False


def test_pid_alive_returns_false_for_dead_pid():
    """A PID that's almost certainly dead (very large or unassigned) → False.

    On both Windows and POSIX, PID 999_999_999 is essentially guaranteed
    not to map to an active process.
    """
    assert _pid_alive(999_999_999) is False


# -------------------------------------------------------------------
# Race: two subprocesses attempt to acquire simultaneously
# -------------------------------------------------------------------


def _race_worker(lock_path_str: str, barrier: mp.Barrier, results_queue: mp.Queue) -> None:
    """Top-level worker so mp.spawn (Windows) can pickle it."""
    from pathlib import Path

    from tinyassets.singleton_lock import (
        acquire_singleton_lock as _acquire,
    )
    from tinyassets.singleton_lock import (
        release_singleton_lock as _release,
    )

    barrier.wait(timeout=10)  # synchronize start
    acq = _acquire(Path(lock_path_str))
    results_queue.put((os.getpid(), acq.acquired))
    if acq.acquired:
        # Hold briefly so the other worker has its chance to contend.
        import time
        time.sleep(0.5)
        _release(acq)


@pytest.mark.skipif(
    sys.platform == "win32" and os.environ.get("CI") == "true",
    reason="multiprocessing on Windows CI can hit spawn-path issues; "
    "race semantics already covered by in-process second-acquire test.",
)
def test_concurrent_acquire_exactly_one_wins(tmp_path):
    """Two subprocesses race on the same lock path. Exactly one wins."""
    lock_path = tmp_path / "race.lock"
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    results_queue = ctx.Queue()

    p1 = ctx.Process(target=_race_worker, args=(str(lock_path), barrier, results_queue))
    p2 = ctx.Process(target=_race_worker, args=(str(lock_path), barrier, results_queue))
    p1.start()
    p2.start()
    p1.join(timeout=15)
    p2.join(timeout=15)

    assert p1.exitcode == 0, f"worker 1 failed with exitcode {p1.exitcode}"
    assert p2.exitcode == 0, f"worker 2 failed with exitcode {p2.exitcode}"

    r1 = results_queue.get(timeout=5)
    r2 = results_queue.get(timeout=5)
    acquired_count = sum(1 for (_, ok) in (r1, r2) if ok)

    assert acquired_count == 1, (
        f"Exactly one worker must acquire; got r1={r1}, r2={r2} "
        f"(acquired_count={acquired_count})"
    )


# -------------------------------------------------------------------
# Crash recovery: lock released when holder process exits
# -------------------------------------------------------------------


def _crash_holder(lock_path_str: str, ready_event: mp.Event) -> None:
    """Top-level worker: acquire the lock, signal the parent, then exit
    without calling release_singleton_lock (simulates ungraceful exit)."""
    from pathlib import Path

    from tinyassets.singleton_lock import acquire_singleton_lock as _acquire

    acq = _acquire(Path(lock_path_str))
    assert acq.acquired, "crash-holder could not acquire its own fresh lock"
    ready_event.set()
    # Exit without releasing. The OS should release the lock when the
    # process dies even though release_singleton_lock wasn't called.


@pytest.mark.skipif(
    sys.platform == "win32" and os.environ.get("CI") == "true",
    reason="multiprocessing on Windows CI can hit spawn-path issues.",
)
def test_lock_released_when_holder_process_exits(tmp_path):
    """Holder process exits without explicit release; OS drops the lock;
    subsequent acquire succeeds (stale-sidecar path)."""
    lock_path = tmp_path / "crash.lock"
    ctx = mp.get_context("spawn")
    ready = ctx.Event()

    holder = ctx.Process(target=_crash_holder, args=(str(lock_path), ready))
    holder.start()
    try:
        assert ready.wait(timeout=10), "crash-holder never signaled ready"
    finally:
        holder.join(timeout=10)

    assert holder.exitcode == 0, f"holder exited with {holder.exitcode}"

    # Parent should now be able to acquire — OS-level lock is gone with
    # the dead process; the stale .pid sidecar does not block.
    acq = acquire_singleton_lock(lock_path)
    try:
        assert acq.acquired is True, (
            "Acquire must succeed after holder process died; OS lock is "
            "released with the holder's process."
        )
    finally:
        release_singleton_lock(acq)


# -------------------------------------------------------------------
# LockAcquisition dataclass surface
# -------------------------------------------------------------------


def test_lock_acquisition_is_dataclass_shaped():
    from pathlib import Path

    acq = LockAcquisition(
        acquired=True, fd=42, path=Path("/tmp/test"), existing_pid=None,
    )
    assert acq.acquired is True
    assert acq.fd == 42
    assert acq.path == Path("/tmp/test")
    assert acq.existing_pid is None
