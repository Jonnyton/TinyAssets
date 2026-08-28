"""Effect quota enforcement through the real outbound boundary.

The unit tests cover the ledger and the gate in isolation. These cover the property
that actually matters: when the budget is gone, **nothing leaves**.
"""

from __future__ import annotations

import pytest

from tinyassets.effectors.outbound_boundary import execute_replay_safe_effect
from tinyassets.storage.external_write_receipts import STATUS_FAILED, STATUS_SUCCEEDED
from tinyassets.storage.usage_ledger import set_tier, usage_summary


def _fire(universe, key, calls, *, run_id="run-1", fail=False):
    def invoke():
        calls.append(key)
        if fail:
            raise RuntimeError("destination rejected")
        return {"ok": True}

    return execute_replay_safe_effect(
        universe_dir=universe,
        effect_key=key,
        sink="test_sink",
        run_id=run_id,
        invoke=invoke,
    )


def test_an_exhausted_budget_prevents_the_outbound_call_entirely(
    tmp_path, monkeypatch
):
    """The load-bearing property: refusal happens BEFORE the write."""
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "2")
    universe = tmp_path / "universe"
    calls: list[str] = []

    assert _fire(universe, "e1", calls)["status"] == STATUS_SUCCEEDED
    assert _fire(universe, "e2", calls)["status"] == STATUS_SUCCEEDED

    refused = _fire(universe, "e3", calls)

    assert refused["status"] == STATUS_FAILED
    assert refused["reason"] == "usage_limit_reached"
    assert refused["terminal"] is True
    # The whole point: the destination was never contacted.
    assert calls == ["e1", "e2"], "a refused effect must not invoke the destination"


def test_the_refusal_tells_the_caller_what_ran_out_and_when(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "1")
    universe = tmp_path / "universe"
    calls: list[str] = []
    _fire(universe, "e1", calls)

    refused = _fire(universe, "e2", calls)

    assert refused["dimension"] == "effect"
    assert refused["tier"] == "free"
    detail = refused["detail"]
    assert "effect" in detail and "free" in detail
    assert "shortly" not in detail, "must state when capacity returns"


def test_failed_effects_do_not_consume_the_budget(tmp_path, monkeypatch):
    """The 2026-08-28 outage in miniature: 15 failures must not exhaust a budget."""
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "3")
    universe = tmp_path / "universe"
    calls: list[str] = []

    for n in range(15):
        result = _fire(universe, f"fail-{n}", calls, run_id=f"run-{n}", fail=True)
        assert result["status"] == STATUS_FAILED
        assert result.get("reason") == "destination_rejected"

    assert len(calls) == 15, "every failing attempt really did reach the destination"

    # Budget untouched, so honest work still proceeds.
    assert _fire(universe, "real", calls)["status"] == STATUS_SUCCEEDED
    summary = usage_summary(universe, window_seconds=86_400.0)
    assert summary["effects_committed"] == 1.0, "only the successful effect is billed"


def test_upgrading_the_tier_restores_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "1")
    monkeypatch.setenv("TINYASSETS_PAID_EFFECTS_PER_WINDOW", "50")
    universe = tmp_path / "universe"
    calls: list[str] = []

    assert _fire(universe, "e1", calls)["status"] == STATUS_SUCCEEDED
    assert _fire(universe, "e2", calls)["status"] == STATUS_FAILED

    set_tier(universe, tier="paid")

    assert _fire(universe, "e2", calls)["status"] == STATUS_SUCCEEDED


def test_cancelling_back_to_free_re_applies_the_free_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "1")
    monkeypatch.setenv("TINYASSETS_PAID_EFFECTS_PER_WINDOW", "50")
    universe = tmp_path / "universe"
    calls: list[str] = []

    set_tier(universe, tier="paid")
    for n in range(3):
        assert _fire(universe, f"p{n}", calls, run_id=f"r{n}")["status"] == (
            STATUS_SUCCEEDED
        )

    set_tier(universe, tier="free")

    # Already over the free ceiling, so the next effect is refused.
    assert _fire(universe, "after-cancel", calls)["status"] == STATUS_FAILED


def test_a_replayed_effect_is_billed_once(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "10")
    universe = tmp_path / "universe"
    calls: list[str] = []

    _fire(universe, "e1", calls, run_id="run-1")
    replay = _fire(universe, "e1", calls, run_id="run-2")

    assert replay["replay"] is True
    assert calls == ["e1"], "replay must not re-invoke the destination"
    summary = usage_summary(universe, window_seconds=86_400.0)
    assert summary["effects_committed"] == 1.0


@pytest.mark.parametrize("tier", ["free", "paid"])
def test_quota_never_widens_authority(tmp_path, monkeypatch, tier):
    """Available budget must not make an otherwise-refused effect succeed."""
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "100")
    universe = tmp_path / "universe"
    set_tier(universe, tier=tier)

    def invoke():
        raise PermissionError("not authorized for this destination")

    result = execute_replay_safe_effect(
        universe_dir=universe,
        effect_key="e1",
        sink="test_sink",
        run_id="run-1",
        invoke=invoke,
    )
    assert result["status"] == STATUS_FAILED
