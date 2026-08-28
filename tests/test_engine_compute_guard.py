"""The engine compute guard: separate buckets, fail-closed, configurable.

Regression cover for 2026-08-28, where one shared 20/hour pool meant the founder's
universe spent its budget authoring a branch repair and had none left to run it.
"""

from __future__ import annotations

import pytest

import tinyassets.engine_mcp_server as engine


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    yield


def test_authoring_does_not_starve_running(monkeypatch):
    """The exact 2026-08-28 failure: writes must not consume run capacity."""
    monkeypatch.setenv("TINYASSETS_ENGINE_WRITE_GUARD_PER_HOUR", "3")
    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GUARD_PER_HOUR", "2")

    # Exhaust the WRITE bucket entirely.
    for _ in range(3):
        assert engine._engine_run_admit(bucket=engine.BUCKET_WRITE) is True
    assert engine._engine_run_admit(bucket=engine.BUCKET_WRITE) is False

    # Runs are untouched — the repair can still execute.
    assert engine._engine_run_admit(bucket=engine.BUCKET_RUN) is True
    assert engine._engine_run_admit(bucket=engine.BUCKET_RUN) is True


def test_each_bucket_enforces_its_own_ceiling(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GUARD_PER_HOUR", "1")
    assert engine._engine_run_admit(bucket=engine.BUCKET_RUN) is True
    assert engine._engine_run_admit(bucket=engine.BUCKET_RUN) is False


def test_the_guard_fails_closed_when_its_ledger_cannot_be_evaluated(
    tmp_path, monkeypatch
):
    """Compute is this guard's only job now, so admitting on error defeats it.

    ThreadPoolExecutor.submit queues without bound, so concurrency is not itself a
    compute bound — an injected engine could otherwise queue unlimited durable runs
    during a ledger outage.
    """
    # A regular FILE where the data dir should be: the ledger cannot open.
    blocked = tmp_path / "blocked-root"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(blocked))
    assert engine._engine_run_admit(bucket=engine.BUCKET_RUN) is False


def test_the_default_posture_is_fail_closed():
    import inspect

    default = inspect.signature(engine._engine_run_admit).parameters[
        "fail_closed"
    ].default
    assert default is True, "compute guard must default to refusing on error"


def test_the_ceiling_is_configurable_and_generous_by_default(monkeypatch):
    monkeypatch.delenv("TINYASSETS_ENGINE_RUN_GUARD_PER_HOUR", raising=False)
    # The old shared limit was 20/hour, tight enough to catch honest debugging.
    assert engine._engine_guard_limit(engine.BUCKET_RUN) > 20

    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GUARD_PER_HOUR", "42")
    assert engine._engine_guard_limit(engine.BUCKET_RUN) == 42


@pytest.mark.parametrize("raw", ["0", "-1", "abc", ""])
def test_an_unusable_ceiling_override_falls_back(monkeypatch, raw):
    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GUARD_PER_HOUR", raw)
    assert engine._engine_guard_limit(engine.BUCKET_RUN) == 300
