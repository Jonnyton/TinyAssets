"""Tests for tinyassets.singleton_lock — host-wide one-instance lock."""

from __future__ import annotations

import os
from pathlib import Path

from tinyassets import singleton_lock
from tinyassets.singleton_lock import (
    acquire_singleton_lock,
    release_singleton_lock,
)


def test_clean_acquire_writes_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / "tray.lock"
    pid_path = lock_path.with_suffix(lock_path.suffix + ".pid")
    acq = acquire_singleton_lock(lock_path)
    try:
        assert acq.acquired is True
        assert acq.fd is not None
        assert acq.existing_pid is None
        assert lock_path.exists()
        assert pid_path.exists()
        recorded = pid_path.read_text(encoding="utf-8").strip()
        assert recorded == str(os.getpid())
    finally:
        release_singleton_lock(acq)


def test_second_acquire_fails_while_first_holds(tmp_path: Path) -> None:
    lock_path = tmp_path / "tray.lock"
    first = acquire_singleton_lock(lock_path)
    try:
        assert first.acquired is True
        second = acquire_singleton_lock(lock_path)
        assert second.acquired is False
        assert second.fd is None
        assert second.existing_pid == os.getpid()
    finally:
        release_singleton_lock(first)


def test_release_lets_next_acquire_succeed(tmp_path: Path) -> None:
    lock_path = tmp_path / "tray.lock"
    first = acquire_singleton_lock(lock_path)
    assert first.acquired is True
    release_singleton_lock(first)

    second = acquire_singleton_lock(lock_path)
    try:
        assert second.acquired is True
    finally:
        release_singleton_lock(second)


def test_stale_lock_file_reclaims_when_os_lock_free(
    tmp_path: Path,
) -> None:
    """A PID sidecar containing a dead PID but no OS-level lock held is
    stale — acquire must succeed and overwrite the PID sidecar.
    """
    lock_path = tmp_path / "tray.lock"
    pid_path = lock_path.with_suffix(lock_path.suffix + ".pid")
    # Simulate a dead previous tray: PID sidecar exists, but no OS lock.
    lock_path.touch()
    pid_path.write_text("999999\n", encoding="utf-8")

    acq = acquire_singleton_lock(lock_path)
    try:
        assert acq.acquired is True
        assert pid_path.read_text(encoding="utf-8").strip() == str(os.getpid())
    finally:
        release_singleton_lock(acq)


def test_release_on_unacquired_is_safe() -> None:
    """release_singleton_lock must be a no-op on a failed acquisition —
    the tray's finally-block calls it unconditionally.
    """
    from tinyassets.singleton_lock import LockAcquisition

    release_singleton_lock(
        LockAcquisition(
            acquired=False, fd=None, path=Path("/nonexistent"),
            existing_pid=None,
        )
    )


def test_existing_pid_none_on_missing_pid_sidecar(
    tmp_path: Path,
) -> None:
    """If the PID sidecar is missing / unreadable while the OS lock is
    held, a blocked acquire returns ``existing_pid=None`` without
    crashing. Exercises the diagnostic fallback path.
    """
    lock_path = tmp_path / "tray.lock"
    pid_path = lock_path.with_suffix(lock_path.suffix + ".pid")
    first = acquire_singleton_lock(lock_path)
    try:
        assert first.acquired is True
        # Nuke the sidecar the first acquire wrote.
        pid_path.unlink()

        second = acquire_singleton_lock(lock_path)
        assert second.acquired is False
        assert second.existing_pid is None
    finally:
        release_singleton_lock(first)


def test_pid_alive_on_self() -> None:
    """Liveness probe must recognize the current process as alive."""
    assert singleton_lock._pid_alive(os.getpid()) is True


def test_pid_alive_on_dead_pid() -> None:
    """An obviously-dead PID (very large, never assigned) must report
    not alive on both platforms. Use 0x7FFFFFFE as a 'probably dead'
    PID — Windows will refuse to OpenProcess, POSIX will raise
    ProcessLookupError.
    """
    assert singleton_lock._pid_alive(0x7FFFFFFE) is False


def test_pid_alive_rejects_zero_and_negative() -> None:
    assert singleton_lock._pid_alive(0) is False
    assert singleton_lock._pid_alive(-1) is False
