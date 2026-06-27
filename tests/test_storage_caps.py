"""Storage cap tests (BUG-023 Phase 3).

Covers:
- `check_subsystem_cap` status classification: unbounded / ok / warn / exceeded.
- Soft-threshold math (SOFT_RATIO = 0.80 of hard).
- `enforce_write_cap` raises StorageCapExceeded at hard cap.
- `enforce_write_cap` emits WARNING at soft cap but does not raise.
- `enforce_write_cap` is a no-op when cap is unconfigured.
- `subsystem_cap_snapshot` reports all three cap-configurable subsystems.
- Env var invalid / zero / negative → cap disabled.
"""
from __future__ import annotations

import logging

import pytest

from tinyassets.exceptions import StorageCapExceeded
from tinyassets.storage.caps import (
    SOFT_RATIO,
    check_subsystem_cap,
    enforce_write_cap,
    subsystem_cap_snapshot,
)


class TestCheckSubsystemCap:
    def test_unbounded_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", raising=False)
        assert check_subsystem_cap("checkpoints", 999_999_999) == "unbounded"

    def test_ok_below_soft(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", "1000")
        # Soft = 800; below → ok.
        assert check_subsystem_cap("checkpoints", 500) == "ok"

    def test_warn_at_soft_threshold(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", "1000")
        # Soft = int(1000 * 0.80) = 800.
        assert check_subsystem_cap("checkpoints", 800) == "warn"
        assert check_subsystem_cap("checkpoints", 999) == "warn"

    def test_exceeded_at_hard_threshold(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", "1000")
        assert check_subsystem_cap("checkpoints", 1000) == "exceeded"
        assert check_subsystem_cap("checkpoints", 10_000) == "exceeded"

    @pytest.mark.parametrize("bad_value", ["abc", ""])
    def test_invalid_env_treated_as_unbounded(self, monkeypatch, bad_value):
        monkeypatch.setenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", bad_value)
        assert check_subsystem_cap("checkpoints", 10_000) == "unbounded"

    @pytest.mark.parametrize("zero_value", ["0", "-1", "-100"])
    def test_zero_or_negative_treated_as_unbounded(
        self, monkeypatch, zero_value,
    ):
        monkeypatch.setenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", zero_value)
        assert check_subsystem_cap("checkpoints", 10_000) == "unbounded"

    def test_unknown_subsystem_is_unbounded(self):
        assert check_subsystem_cap("ghost_subsystem", 999) == "unbounded"


class TestSoftRatio:
    def test_soft_ratio_is_80_percent(self):
        assert SOFT_RATIO == 0.80


class TestEnforceWriteCap:
    def test_raises_at_hard_cap(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", "1000")
        with pytest.raises(StorageCapExceeded) as exc_info:
            enforce_write_cap("checkpoints", current_bytes=1000)
        msg = str(exc_info.value)
        assert "checkpoints" in msg
        assert "TINYASSETS_CAP_CHECKPOINTS_BYTES" in msg

    def test_raises_on_projected_overage(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_LOGS_BYTES", "1000")
        # Current 950, adding 100 → 1050 >= 1000 → exceeded.
        with pytest.raises(StorageCapExceeded):
            enforce_write_cap(
                "logs",
                current_bytes=950,
                additional_bytes=100,
            )

    def test_warn_emits_warning_does_not_raise(
        self, monkeypatch, caplog,
    ):
        monkeypatch.setenv("TINYASSETS_CAP_RUN_ARTIFACTS_BYTES", "1000")
        with caplog.at_level(logging.WARNING, logger="tinyassets.storage.caps"):
            enforce_write_cap("run_artifacts", current_bytes=850)
        assert any(
            "soft-threshold" in rec.getMessage()
            for rec in caplog.records
        )

    def test_ok_does_not_warn_or_raise(self, monkeypatch, caplog):
        monkeypatch.setenv("TINYASSETS_CAP_RUN_ARTIFACTS_BYTES", "1000")
        with caplog.at_level(logging.WARNING, logger="tinyassets.storage.caps"):
            enforce_write_cap("run_artifacts", current_bytes=100)
        assert not any("soft-threshold" in r.getMessage() for r in caplog.records)

    def test_unbounded_is_noop(self, monkeypatch, caplog):
        monkeypatch.delenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", raising=False)
        with caplog.at_level(logging.WARNING, logger="tinyassets.storage.caps"):
            enforce_write_cap("checkpoints", current_bytes=999_999_999)
        assert not caplog.records


class TestSubsystemCapSnapshot:
    def test_snapshot_covers_all_configurable_subsystems(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", "1000")
        monkeypatch.setenv("TINYASSETS_CAP_LOGS_BYTES", "2000")
        monkeypatch.delenv("TINYASSETS_CAP_RUN_ARTIFACTS_BYTES", raising=False)

        snap = subsystem_cap_snapshot({
            "checkpoints": 900,
            "logs": 500,
            "run_artifacts": 5_000_000,
        })

        assert set(snap.keys()) == {"checkpoints", "logs", "run_artifacts"}
        assert snap["checkpoints"]["status"] == "warn"
        assert snap["checkpoints"]["hard_cap_bytes"] == 1000
        assert snap["checkpoints"]["soft_cap_bytes"] == 800
        assert snap["checkpoints"]["current_bytes"] == 900

        assert snap["logs"]["status"] == "ok"
        assert snap["logs"]["hard_cap_bytes"] == 2000

        assert snap["run_artifacts"]["status"] == "unbounded"
        assert snap["run_artifacts"]["hard_cap_bytes"] == 0

    def test_missing_input_defaults_current_to_zero(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_CAP_CHECKPOINTS_BYTES", "1000")
        snap = subsystem_cap_snapshot({})
        assert snap["checkpoints"]["current_bytes"] == 0
        assert snap["checkpoints"]["status"] == "ok"
