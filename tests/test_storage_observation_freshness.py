"""Additive freshness/scope evidence, without more filesystem or private reads."""
from datetime import datetime

import pytest

from tinyassets import storage


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TINYASSETS_STORAGE_SNAPSHOT_TTL_S", raising=False)
    storage.reset_storage_snapshot_cache()
    yield
    storage.reset_storage_snapshot_cache()


def test_cached_capture_time_is_retained_and_age_advances(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(storage.time, "monotonic", lambda: clock[0])
    first = storage.inspect_storage_utilization()
    clock[0] += 12
    second = storage.inspect_storage_utilization()
    assert second["observed_at"] == first["observed_at"]
    assert datetime.fromisoformat(second["observed_at"].replace("Z", "+00:00")).tzinfo
    assert first["observation_age_seconds"] == 0
    assert second["observation_age_seconds"] == 12
    assert second["cache_ttl_seconds"] == 60
    assert "_observed_monotonic" not in first
    assert "_observed_monotonic" not in second


def test_expired_sample_reports_new_measurement(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(storage.time, "monotonic", lambda: clock[0])
    storage.inspect_storage_utilization()
    clock[0] += 61
    fresh = storage.inspect_storage_utilization()
    assert fresh["observation_age_seconds"] == 0


@pytest.mark.parametrize("setting,expected", [("0", 0), ("-1", 0), ("7", 7), ("inf", 60)])
def test_reports_actual_cache_reuse_setting(monkeypatch, setting, expected):
    monkeypatch.setenv("TINYASSETS_STORAGE_SNAPSHOT_TTL_S", setting)
    assert storage.inspect_storage_utilization()["cache_ttl_seconds"] == expected


def test_scope_is_partial_without_new_private_fields(tmp_path):
    result = storage.inspect_storage_utilization()
    assert result["volume_scope"] == "filesystem_containing_data_root"
    assert result["subsystem_scope"] == "partial_enumerated_daemon_paths"
    assert result["volume_percent_formula"] == "1 - volume_bytes_free / volume_bytes_total"
    caveats = " ".join(result["accounting_caveats"])
    for phrase in ("largest listed", "Docker images", "owner-attributed", "not an atomic"):
        assert phrase in caveats
    assert str(tmp_path) not in caveats
    assert result["volume_availability"] == "available"


def test_failed_probe_is_explicitly_unavailable(monkeypatch):
    def fail(_):
        raise OSError("private path must not escape")
    monkeypatch.setattr("shutil.disk_usage", fail)
    result = storage.inspect_storage_utilization()
    assert result["volume_availability"] == "unavailable"
    assert result["volume_bytes_total"] == result["volume_bytes_free"] == 0
    assert "private path must not escape" not in str(result)


def test_zero_capacity_is_not_available(monkeypatch):
    from collections import namedtuple
    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr("shutil.disk_usage", lambda _: usage(0, 0, 0))
    assert storage.inspect_storage_utilization()["volume_availability"] == "unavailable"
