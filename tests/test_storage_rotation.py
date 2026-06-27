"""Storage rotation + pruning tests (BUG-023 Phase 3).

Covers:
- rotate_activity_log: no rotation below soft cap.
- rotate_activity_log: rotation when at/above soft cap.
- rotate_activity_log: disabled when env var unset.
- rotate_activity_log: env var override is respected.
- prune_universe_outputs: no pruning when total <= hard cap.
- prune_universe_outputs: oldest files deleted when over hard cap.
- prune_universe_outputs: prunes until under soft cap (80% of hard).
- prune_universe_outputs: disabled when env var unset.
- prune_universe_outputs: env var override is respected.
- startup_storage_probe: returns activity_log_rotated + universe_outputs_pruned.
- startup_storage_probe: triggers rotation + pruning when over cap.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from tinyassets.storage.rotation import (
    prune_universe_outputs,
    rotate_activity_log,
    startup_storage_probe,
)


class TestRotateActivityLog:
    def test_no_rotation_below_soft_cap(self, tmp_path):
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 100)
        rotated = rotate_activity_log(log, soft_cap_bytes=1000)
        assert rotated is False
        assert log.exists()
        assert not (tmp_path / "activity.log.1").exists()

    def test_rotation_at_soft_cap(self, tmp_path):
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 1000)
        rotated = rotate_activity_log(log, soft_cap_bytes=1000)
        assert rotated is True
        assert not log.exists()
        assert (tmp_path / "activity.log.1").exists()

    def test_rotation_above_soft_cap(self, tmp_path):
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 2000)
        rotated = rotate_activity_log(log, soft_cap_bytes=500)
        assert rotated is True
        assert not log.exists()
        assert (tmp_path / "activity.log.1").exists()

    def test_disabled_when_cap_zero(self, tmp_path):
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 99999)
        rotated = rotate_activity_log(log, soft_cap_bytes=0)
        assert rotated is False
        assert log.exists()

    def test_disabled_when_env_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TINYASSETS_CAP_ACTIVITY_LOG_BYTES", raising=False)
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 99999)
        rotated = rotate_activity_log(log)
        assert rotated is False

    def test_env_var_override_respected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_ACTIVITY_LOG_BYTES", "500")
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 600)
        rotated = rotate_activity_log(log)
        assert rotated is True
        assert not log.exists()

    def test_no_error_when_log_missing(self, tmp_path):
        log = tmp_path / "nonexistent.log"
        rotated = rotate_activity_log(log, soft_cap_bytes=100)
        assert rotated is False

    def test_rotation_is_idempotent(self, tmp_path):
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 1000)
        rotate_activity_log(log, soft_cap_bytes=500)
        assert not log.exists()
        log.write_bytes(b"x" * 1000)
        rotate_activity_log(log, soft_cap_bytes=500)
        assert not log.exists()
        assert (tmp_path / "activity.log.1").exists()


class TestPruneUniverseOutputs:
    def _make_files(
        self,
        directory: Path,
        sizes: list[int],
        *,
        base_mtime: float | None = None,
    ) -> list[Path]:
        """Create files with controlled sizes and mtimes (oldest first)."""
        if base_mtime is None:
            base_mtime = time.time() - len(sizes) * 10
        files = []
        for i, size in enumerate(sizes):
            p = directory / f"file_{i:03d}.txt"
            p.write_bytes(b"x" * size)
            mtime = base_mtime + i * 10
            os.utime(p, (mtime, mtime))
            files.append(p)
        return files

    def test_no_pruning_below_hard_cap(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        self._make_files(d, [100, 200, 300])
        deleted = prune_universe_outputs(d, hard_cap_bytes=10_000)
        assert deleted == []
        assert len(list(d.iterdir())) == 3

    def test_no_pruning_at_hard_cap(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        self._make_files(d, [100, 200, 300])
        deleted = prune_universe_outputs(d, hard_cap_bytes=600)
        assert deleted == []

    def test_prunes_oldest_when_over_cap(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        files = self._make_files(d, [100, 200, 300])
        # Total=600, hard cap=400. soft=320. Must delete oldest until <=320.
        deleted = prune_universe_outputs(d, hard_cap_bytes=400)
        assert len(deleted) > 0
        # file_000 (oldest, 100 bytes) should be deleted first.
        assert str(files[0]) in deleted
        assert not files[0].exists()

    def test_prunes_until_under_soft_cap(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        self._make_files(d, [100, 100, 100, 100, 100])
        # Total=500, hard cap=400, soft=320.
        # After deleting 2 files (200 bytes removed) → 300 <= 320. Stop.
        prune_universe_outputs(d, hard_cap_bytes=400)
        remaining = list(d.rglob("*"))
        remaining_bytes = sum(f.stat().st_size for f in remaining if f.is_file())
        assert remaining_bytes <= 320

    def test_disabled_when_cap_zero(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        self._make_files(d, [100, 200, 300])
        deleted = prune_universe_outputs(d, hard_cap_bytes=0)
        assert deleted == []
        assert len(list(d.iterdir())) == 3

    def test_disabled_when_env_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TINYASSETS_CAP_UNIVERSE_OUTPUTS_BYTES", raising=False)
        d = tmp_path / "output"
        d.mkdir()
        self._make_files(d, [999_999])
        deleted = prune_universe_outputs(d)
        assert deleted == []

    def test_env_var_override_respected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_UNIVERSE_OUTPUTS_BYTES", "400")
        d = tmp_path / "output"
        d.mkdir()
        self._make_files(d, [100, 200, 300])
        deleted = prune_universe_outputs(d)
        assert len(deleted) > 0

    def test_no_error_when_dir_missing(self, tmp_path):
        d = tmp_path / "nonexistent_output"
        deleted = prune_universe_outputs(d, hard_cap_bytes=100)
        assert deleted == []

    def test_does_not_delete_outside_subsystem(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        outside = tmp_path / "important.txt"
        outside.write_bytes(b"x" * 1000)
        self._make_files(d, [500, 500, 500])
        prune_universe_outputs(d, hard_cap_bytes=800)
        assert outside.exists()


class TestStartupStorageProbe:
    def test_returns_expected_shape(self, tmp_path):
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 10)
        out = tmp_path / "output"
        out.mkdir()
        result = startup_storage_probe(log_path=log, outputs_dir=out)
        assert "activity_log_rotated" in result
        assert "universe_outputs_pruned" in result
        assert isinstance(result["activity_log_rotated"], bool)
        assert isinstance(result["universe_outputs_pruned"], list)

    def test_triggers_rotation_when_over_cap(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_ACTIVITY_LOG_BYTES", "100")
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 200)
        out = tmp_path / "output"
        out.mkdir()
        result = startup_storage_probe(log_path=log, outputs_dir=out)
        assert result["activity_log_rotated"] is True
        assert not log.exists()

    def test_triggers_pruning_when_over_cap(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_UNIVERSE_OUTPUTS_BYTES", "300")
        log = tmp_path / "activity.log"
        log.write_bytes(b"hello")
        out = tmp_path / "output"
        out.mkdir()
        base_mtime = time.time() - 100
        for i, size in enumerate([100, 200, 300]):
            p = out / f"f{i}.txt"
            p.write_bytes(b"x" * size)
            mtime = base_mtime + i
            os.utime(p, (mtime, mtime))
        result = startup_storage_probe(log_path=log, outputs_dir=out)
        assert len(result["universe_outputs_pruned"]) > 0

    def test_no_action_when_caps_not_set(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TINYASSETS_CAP_ACTIVITY_LOG_BYTES", raising=False)
        monkeypatch.delenv("TINYASSETS_CAP_UNIVERSE_OUTPUTS_BYTES", raising=False)
        log = tmp_path / "activity.log"
        log.write_bytes(b"x" * 999_999)
        out = tmp_path / "output"
        out.mkdir()
        (out / "big.txt").write_bytes(b"x" * 999_999)
        result = startup_storage_probe(log_path=log, outputs_dir=out)
        assert result["activity_log_rotated"] is False
        assert result["universe_outputs_pruned"] == []
