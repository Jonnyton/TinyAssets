"""Patch-loop S4: per-remix merge policy eligibility.

Proves the invariant "no policy merges a red PR" plus per-policy release rules
and founder-OAuth-per-merge gating. Pure-function tests (no IO)."""

from __future__ import annotations

import pytest

from tinyassets import merge_policy as mp


def test_normalize_policy_defaults_and_validates():
    assert mp.normalize_policy(None) == "manual"
    assert mp.normalize_policy("") == "manual"
    assert mp.normalize_policy("AUTO") == "auto"
    assert mp.normalize_policy("timer") == "timer"
    with pytest.raises(ValueError):
        mp.normalize_policy("yolo")


def test_verify_is_green_is_strict():
    assert mp.verify_is_green("pass") is True
    assert mp.verify_is_green("PASS") is True
    for red in ("fail", "unknown", "", None, "passing"):
        assert mp.verify_is_green(red) is False


# ── Universal red-PR guard: NO policy merges a red PR ───────────────────────


@pytest.mark.parametrize("policy", ["manual", "auto", "timer"])
@pytest.mark.parametrize("verdict", ["fail", "unknown", ""])
def test_no_policy_merges_a_red_pr(policy, verdict):
    decision = mp.evaluate_merge_eligibility(
        policy=policy,
        verify_verdict=verdict,
        item_status="approved",  # even owner-approved cannot release red
        created_at=0.0,
        now=10_000.0,
        timer_delay_s=0.0,
    )
    assert decision["eligible"] is False
    assert decision["reason"] == "verify_not_green"


# ── Manual policy holds until owner approval ────────────────────────────────


def test_manual_holds_until_approved():
    pending = mp.evaluate_merge_eligibility(
        policy="manual", verify_verdict="pass", item_status="pending"
    )
    assert pending["eligible"] is False
    assert pending["reason"] == "manual_policy_awaiting_owner_approval"

    approved = mp.evaluate_merge_eligibility(
        policy="manual", verify_verdict="pass", item_status="approved"
    )
    assert approved["eligible"] is True


# ── Auto policy: green verify releases ──────────────────────────────────────


def test_auto_releases_on_green_without_owner_action():
    decision = mp.evaluate_merge_eligibility(
        policy="auto", verify_verdict="pass", item_status="pending"
    )
    assert decision["eligible"] is True


def test_auto_held_when_owner_reshaped_or_rejected():
    for status in ("reshaped", "rejected"):
        decision = mp.evaluate_merge_eligibility(
            policy="auto", verify_verdict="pass", item_status=status
        )
        assert decision["eligible"] is False
        assert decision["reason"] == "auto_policy_held_by_owner"


# ── Timer policy: green verify + elapsed delay + not held ───────────────────


def test_timer_waits_for_delay_then_releases():
    not_yet = mp.evaluate_merge_eligibility(
        policy="timer",
        verify_verdict="pass",
        item_status="pending",
        created_at=1000.0,
        now=1000.0 + 30.0,
        timer_delay_s=3600.0,
    )
    assert not_yet["eligible"] is False
    assert not_yet["reason"] == "timer_policy_delay_not_elapsed"

    elapsed = mp.evaluate_merge_eligibility(
        policy="timer",
        verify_verdict="pass",
        item_status="pending",
        created_at=1000.0,
        now=1000.0 + 4000.0,
        timer_delay_s=3600.0,
    )
    assert elapsed["eligible"] is True


def test_timer_held_by_owner_blocks_even_after_delay():
    decision = mp.evaluate_merge_eligibility(
        policy="timer",
        verify_verdict="pass",
        item_status="reshaped",
        created_at=0.0,
        now=1_000_000.0,
        timer_delay_s=1.0,
    )
    assert decision["eligible"] is False
    assert decision["reason"] == "timer_policy_held_by_owner"


# ── Founder-OAuth-per-merge gate layered on any policy ──────────────────────


def test_founder_oauth_required_blocks_without_fresh_approval():
    blocked = mp.evaluate_merge_eligibility(
        policy="auto",
        verify_verdict="pass",
        item_status="pending",
        founder_oauth_required=True,
        fresh_approval_present=False,
    )
    assert blocked["eligible"] is False
    assert blocked["reason"] == "founder_oauth_required"

    ok = mp.evaluate_merge_eligibility(
        policy="auto",
        verify_verdict="pass",
        item_status="pending",
        founder_oauth_required=True,
        fresh_approval_present=True,
    )
    assert ok["eligible"] is True
    assert ok["founder_oauth_required"] is True
