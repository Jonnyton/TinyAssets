"""Tier resolution and refusal messages."""

from __future__ import annotations

import pytest

from tinyassets.usage_policy import (
    TIER_FREE,
    TIER_PAID,
    QuotaRefusal,
    limits_for,
    settlement_key,
)


@pytest.fixture(autouse=True)
def _enforcement_on(monkeypatch):
    """These tests are ABOUT enforcement, so they opt in explicitly.

    Enforcement ships dark (default off) until settlement is exactly-once, so a
    test silently relying on the default would stop testing anything the day that
    default flips.
    """
    monkeypatch.setenv("TINYASSETS_USAGE_ENFORCEMENT", "1")



@pytest.mark.parametrize(
    "value",
    ["", "   ", "unknown", "enterprise", "PAID_UNLIMITED", "admin", None],
)
def test_an_unresolvable_tier_falls_back_to_free_never_paid(value):
    """A lookup failure must not silently hand out the paid tier."""
    limits = limits_for(value)
    assert limits.name == TIER_FREE
    assert limits.is_paid is False
    assert limits.effects == limits_for(TIER_FREE).effects


@pytest.mark.parametrize("value", ["paid", "PAID", "  Paid  "])
def test_the_paid_tier_resolves_case_and_whitespace_insensitively(value):
    assert limits_for(value).name == TIER_PAID


def test_paid_is_strictly_more_generous_than_free():
    free, paid = limits_for(TIER_FREE), limits_for(TIER_PAID)
    assert paid.effects > free.effects
    assert paid.compute_seconds > free.compute_seconds
    assert paid.storage_bytes > free.storage_bytes


def test_limits_are_configurable(monkeypatch):
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "7")
    assert limits_for(TIER_FREE).effects == 7


@pytest.mark.parametrize("raw", ["0", "-5", "not-a-number", "nan", "inf"])
def test_an_unusable_limit_override_falls_back_loudly(monkeypatch, capsys, raw):
    """A misconfiguration must be announced, not silently swallowed."""
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", raw)
    limits = limits_for(TIER_FREE)
    assert limits.effects == 100
    assert "TINYASSETS_FREE_EFFECTS_PER_WINDOW" in capsys.readouterr().out


def test_the_settlement_key_cannot_be_forged_by_a_colliding_pair():
    """`a|bc` and `ab|c` must not produce the same ledger key."""
    assert settlement_key(sink="a", effect_key="bc") != settlement_key(
        sink="ab", effect_key="c"
    )


def test_the_settlement_key_is_injective_even_when_a_field_holds_the_separator():
    """Codex REJECT 2026-08-28 B: concatenation is not injective.

    ("a", "bc") and ("ab", "c") produced ONE key, and since reserve treats
    an existing row as "same effect, proceed", one tuple could ride another's
    reservation and write with no budget of its own.
    """
    assert settlement_key(sink="a", effect_key="bc") != settlement_key(
        sink="ab", effect_key="c"
    )


def test_the_settlement_key_is_stable_for_the_same_effect():
    """A retry must find its own reservation, not take a second slot."""
    assert settlement_key(sink="x:posting", effect_key="abc") == settlement_key(
        sink="x:posting", effect_key="abc"
    )


def test_a_refusal_names_the_dimension_and_when_it_refills():
    message = QuotaRefusal(
        dimension="effect", limit=100, tier="free", retry_after_seconds=7200
    ).message()
    assert "effect" in message
    assert "free" in message
    assert "100" in message
    # The specific failure of the old text: "try again shortly" with no reset time.
    assert "shortly" not in message
    assert any(unit in message for unit in ("h", "m"))


# --- the quota gate over the ledger -----------------------------------------


def test_the_gate_admits_until_the_tier_limit_then_refuses(tmp_path, monkeypatch):
    from tinyassets.usage_policy import reserve_effect_quota

    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "2")

    assert reserve_effect_quota(tmp_path, sink="s", effect_key="a") is None
    assert reserve_effect_quota(tmp_path, sink="s", effect_key="b") is None

    refusal = reserve_effect_quota(tmp_path, sink="s", effect_key="c")
    assert refusal is not None
    assert refusal.dimension == "effect"
    assert refusal.tier == TIER_FREE
    assert "effect" in refusal.message()


def test_a_released_effect_returns_its_budget(tmp_path, monkeypatch):
    from tinyassets.usage_policy import release_effect_quota, reserve_effect_quota

    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "1")

    assert reserve_effect_quota(tmp_path, sink="s", effect_key="a") is None
    assert reserve_effect_quota(tmp_path, sink="s", effect_key="b") is not None

    release_effect_quota(tmp_path, sink="s", effect_key="a")

    assert reserve_effect_quota(tmp_path, sink="s", effect_key="b") is None


def test_settling_the_same_effect_twice_charges_once(tmp_path, monkeypatch):
    """Every success path may call settle; only the transition counts."""
    from tinyassets.usage_policy import reserve_effect_quota, settle_effect_quota

    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "5")
    reserve_effect_quota(tmp_path, sink="s", effect_key="a")

    assert settle_effect_quota(tmp_path, sink="s", effect_key="a") is True
    # Reconciliation / replay / confirmed-hold arriving late must not re-charge.
    assert settle_effect_quota(tmp_path, sink="s", effect_key="a") is False


def test_the_paid_tier_admits_where_free_refuses(tmp_path, monkeypatch):
    from tinyassets.usage_policy import reserve_effect_quota

    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "1")
    monkeypatch.setenv("TINYASSETS_PAID_EFFECTS_PER_WINDOW", "10")

    assert reserve_effect_quota(tmp_path, sink="s", effect_key="a") is None
    assert reserve_effect_quota(tmp_path, sink="s", effect_key="b") is not None
    # Same universe, same ledger — the tier is what changes the answer.
    assert (
        reserve_effect_quota(tmp_path, sink="s", effect_key="b", tier=TIER_PAID) is None
    )
