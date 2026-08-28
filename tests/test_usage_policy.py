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


def test_the_settlement_key_matches_the_receipt_identity():
    key = settlement_key(sink="x:posting", effect_key="abc123")
    assert "x:posting" in key and "abc123" in key


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
