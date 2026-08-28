"""Compute metering settles worker-held time against the owning universe."""

from __future__ import annotations

import tinyassets.runs as runs
from tinyassets.storage.usage_ledger import usage_summary

WINDOW = 86_400.0


def test_metering_starts_at_worker_acquisition_not_enqueue(tmp_path, monkeypatch):
    """Queue delay is platform load and must not be billed to the user."""
    universe = tmp_path / "u1"
    universe.mkdir()
    monkeypatch.setattr(runs, "_resolve_effector_base", lambda *a, **k: universe)

    # A run that sat in the queue for an hour but held a worker for 5 seconds.
    acquired = runs._now() - 5.0
    runs._settle_run_compute(tmp_path, "run-1", acquired)

    metered = usage_summary(universe, window_seconds=WINDOW)["compute_seconds"]
    assert 4.0 <= metered <= 8.0, (
        "only worker-held time is metered, not time spent queued"
    )


def test_a_run_cannot_be_metered_beyond_the_ceiling(tmp_path, monkeypatch):
    universe = tmp_path / "u1"
    universe.mkdir()
    monkeypatch.setattr(runs, "_resolve_effector_base", lambda *a, **k: universe)
    monkeypatch.setenv("TINYASSETS_MAX_CHARGEABLE_RUN_S", "60")

    # A wedged run that has been "held" for a simulated week.
    runs._settle_run_compute(tmp_path, "wedged", runs._now() - 604_800.0)

    assert usage_summary(universe, window_seconds=WINDOW)["compute_seconds"] == 60.0


def test_settling_the_same_run_twice_meters_once(tmp_path, monkeypatch):
    universe = tmp_path / "u1"
    universe.mkdir()
    monkeypatch.setattr(runs, "_resolve_effector_base", lambda *a, **k: universe)

    acquired = runs._now() - 3.0
    runs._settle_run_compute(tmp_path, "run-1", acquired)
    runs._settle_run_compute(tmp_path, "run-1", acquired)

    metered = usage_summary(universe, window_seconds=WINDOW)["compute_seconds"]
    assert metered < 10.0, "a retried settlement must not double-charge"


def test_metering_bills_the_owning_universe_not_the_data_root(tmp_path, monkeypatch):
    """base_path is the flat data root; billing it would mis-bind like the
    effector-consent bug that _resolve_effector_base exists to prevent."""
    data_root = tmp_path
    universe = tmp_path / "u-owner"
    universe.mkdir()
    monkeypatch.setattr(runs, "_resolve_effector_base", lambda *a, **k: universe)

    runs._settle_run_compute(data_root, "run-1", runs._now() - 2.0)

    assert usage_summary(universe, window_seconds=WINDOW)["compute_seconds"] > 0
    assert usage_summary(data_root, window_seconds=WINDOW)["compute_seconds"] == 0.0


def test_metering_failure_never_breaks_the_run(tmp_path, monkeypatch):
    """Metering observes a run; it must never be able to fail one."""

    def _boom(*a, **k):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(runs, "_resolve_effector_base", _boom)

    # Must not raise.
    runs._settle_run_compute(tmp_path, "run-1", runs._now() - 1.0)
