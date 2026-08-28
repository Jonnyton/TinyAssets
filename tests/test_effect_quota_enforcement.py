"""Effect quota enforcement through the real outbound boundary.

The unit tests cover the ledger and the gate in isolation. These cover the property
that actually matters: when the budget is gone, **nothing leaves**.
"""

from __future__ import annotations

import itertools

import pytest

from tinyassets.effectors.outbound_boundary import execute_replay_safe_effect
from tinyassets.storage.external_write_receipts import STATUS_FAILED, STATUS_SUCCEEDED
from tinyassets.storage.subscription_state import apply_tier_event
from tinyassets.storage.usage_ledger import usage_summary

_EVENT_CLOCK = itertools.count(1_000)


def _next_event() -> float:
    """Monotonic event timestamps: apply_tier_event refuses a stale one, so a test
    that reuses a timestamp would silently not change the tier it thinks it set."""
    return float(next(_EVENT_CLOCK))


@pytest.fixture(autouse=True)
def _enforcement_on(monkeypatch):
    """These tests are ABOUT enforcement, so they opt in explicitly.

    Enforcement ships dark (default off) until settlement is exactly-once, so a
    test silently relying on the default would stop testing anything the day that
    default flips.
    """
    monkeypatch.setenv("TINYASSETS_USAGE_ENFORCEMENT", "1")



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

    apply_tier_event(universe, tier="paid", event_created=_next_event())

    assert _fire(universe, "e2", calls)["status"] == STATUS_SUCCEEDED


def test_cancelling_back_to_free_re_applies_the_free_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "1")
    monkeypatch.setenv("TINYASSETS_PAID_EFFECTS_PER_WINDOW", "50")
    universe = tmp_path / "universe"
    calls: list[str] = []

    apply_tier_event(universe, tier="paid", event_created=_next_event())
    for n in range(3):
        assert _fire(universe, f"p{n}", calls, run_id=f"r{n}")["status"] == (
            STATUS_SUCCEEDED
        )

    apply_tier_event(universe, tier="free", event_created=_next_event())

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
    apply_tier_event(universe, tier=tier, event_created=_next_event())

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


def test_every_invoke_path_is_gated_not_just_the_ordinary_one(tmp_path, monkeypatch):
    """The choke point, not the call site.

    `execute_capped_action`'s confirmed-hold branch reaches the destination via
    `_invoke_reserved_effect` WITHOUT passing through `execute_replay_safe_effect`,
    so a gate placed only in the latter never sees it — which is exactly how that
    path fired with no quota admission. Gating the shared helper closes the class.
    """
    from tinyassets.effectors.outbound_boundary import _invoke_reserved_effect
    from tinyassets.storage.external_write_receipts import try_reserve_receipt

    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "1")
    universe = tmp_path / "universe"
    calls: list[str] = []

    # Spend the single slot.
    _fire(universe, "first", calls)
    assert calls == ["first"]

    # Now drive the helper directly, as the confirmed-hold path does.
    try_reserve_receipt(
        universe, idempotency_hint="held-one", sink="test_sink", run_id="run-2"
    )
    result = _invoke_reserved_effect(
        universe_dir=universe,
        effect_key="held-one",
        sink="test_sink",
        run_id="run-2",
        invoke=lambda: calls.append("held-one") or {"ok": True},
        reconcile=None,
    )

    assert result["reason"] == "usage_limit_reached"
    assert calls == ["first"], "the held effect must not reach the destination"


def test_the_ordinary_path_does_not_double_consume_through_the_choke_point(
    tmp_path, monkeypatch
):
    """Reserve is idempotent per key, so gating both places costs nothing."""
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "2")
    universe = tmp_path / "universe"
    calls: list[str] = []

    assert _fire(universe, "a", calls)["status"] == STATUS_SUCCEEDED
    assert _fire(universe, "b", calls)["status"] == STATUS_SUCCEEDED

    summary = usage_summary(universe, window_seconds=86_400.0)
    assert summary["effects_committed"] == 2.0, "two effects, two charges"
