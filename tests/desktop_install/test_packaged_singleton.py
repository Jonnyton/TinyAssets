from __future__ import annotations

from pathlib import Path

from tinyassets.singleton_lock import acquire_singleton_lock, release_singleton_lock


def test_packaged_double_launch_converges_on_one_control_process(
    tmp_path: Path,
) -> None:
    packaged_data_root = tmp_path / "TinyAssets"
    lock_path = packaged_data_root / "runtime" / "tray.lock"

    first = acquire_singleton_lock(lock_path)
    second = acquire_singleton_lock(lock_path)
    try:
        assert first.acquired is True
        assert second.acquired is False
        assert second.existing_pid is not None
    finally:
        release_singleton_lock(second)
        release_singleton_lock(first)
