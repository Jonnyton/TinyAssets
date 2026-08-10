from __future__ import annotations

import threading

import pytest


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
