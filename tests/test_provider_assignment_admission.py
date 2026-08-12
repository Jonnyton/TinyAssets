from __future__ import annotations

import multiprocessing
import queue
import threading

import pytest


def _enter_exclusive_in_child(universe: str, events) -> None:
    from tinyassets.provider_assignment import ProviderAssignmentAdmission

    events.put("attempting")
    with ProviderAssignmentAdmission().exclusive(universe):
        events.put("entered")


def test_shared_launch_fence_blocks_assignment_writer_until_release(tmp_path):
    from tinyassets.provider_assignment import ProviderAssignmentAdmission

    admission = ProviderAssignmentAdmission()
    universe = tmp_path / "u-fenced"
    writer_started = threading.Event()
    writer_entered = threading.Event()

    def _writer() -> None:
        writer_started.set()
        with admission.exclusive(universe):
            writer_entered.set()

    with admission.shared(universe):
        thread = threading.Thread(target=_writer)
        thread.start()
        assert writer_started.wait(timeout=1)
        assert not writer_entered.wait(timeout=0.05)

    thread.join(timeout=1)
    assert not thread.is_alive()
    assert writer_entered.is_set()


def test_assignment_admission_refuses_reentrant_and_reverse_order(tmp_path):
    from tinyassets.provider_assignment import ProviderAssignmentAdmission

    admission = ProviderAssignmentAdmission()
    universe = tmp_path / "u-fenced"
    with admission.shared(universe):
        with pytest.raises(RuntimeError, match="not reentrant"):
            with admission.shared(universe):
                pass
        with pytest.raises(RuntimeError, match="not reentrant"):
            with admission.exclusive(universe):
                pass


def test_shared_launch_fence_blocks_writer_in_another_process(tmp_path):
    from tinyassets.provider_assignment import ProviderAssignmentAdmission

    universe = tmp_path / "u-fenced"
    universe.mkdir()
    context = multiprocessing.get_context("spawn")
    events = context.Queue()
    process = context.Process(
        target=_enter_exclusive_in_child,
        args=(str(universe), events),
    )
    admission = ProviderAssignmentAdmission()
    with admission.shared(universe):
        process.start()
        assert events.get(timeout=5) == "attempting"
        with pytest.raises(queue.Empty):
            events.get(timeout=0.25)
    assert events.get(timeout=5) == "entered"
    process.join(timeout=5)
    assert process.exitcode == 0


def test_windows_file_lock_retry_is_bounded_and_fails_closed():
    from tinyassets.provider_assignment import _acquire_windows_file_lock

    attempts = 0

    class _Handle:
        @staticmethod
        def seek(_offset):
            return 0

        @staticmethod
        def fileno():
            return 17

    def _always_contended(_fileno, _mode, _count):
        nonlocal attempts
        attempts += 1
        raise OSError("contended")

    with pytest.raises(TimeoutError, match="admission lock"):
        _acquire_windows_file_lock(
            _Handle(),
            locking=_always_contended,
            sleep=lambda _seconds: None,
            max_attempts=3,
        )

    assert attempts == 3


def test_shared_admission_tolerates_read_only_data_mount(tmp_path, monkeypatch):
    # The Slack ingress agent mounts /data read-only. A SHARED (reader) lock —
    # used by list_serving_universes on every serving-enrollment cycle — must
    # still work; only EXCLUSIVE writers need write access. Regression: the
    # slack agent crashed each cycle on OSError [Errno 30] Read-only file system
    # and never served any universe (u-tiny went silent for days).
    from pathlib import Path

    from tinyassets.provider_assignment import ProviderAssignmentAdmission

    universe = tmp_path / "u-ro"
    universe.mkdir()
    # A read-write writer elsewhere already created the lock file.
    (universe / ".provider-assignment-admission.lock").write_bytes(b"\0")

    real_open = Path.open

    def read_only_open(self, mode="r", *args, **kwargs):
        # Simulate a read-only mount: any write-capable open fails.
        if "a" in mode or "w" in mode or "+" in mode:
            raise OSError(30, "Read-only file system")
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", read_only_open)
    admission = ProviderAssignmentAdmission()

    # Shared lock must succeed via the read-only fallback.
    with admission.shared(universe):
        pass

    # Exclusive (writer) lock must still fail loudly — it genuinely needs write.
    with pytest.raises(OSError):
        with admission.exclusive(universe):
            pass
