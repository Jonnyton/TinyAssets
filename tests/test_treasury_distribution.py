"""Tests for tinyassets.treasury distribution math — pure functions, edge cases."""

from __future__ import annotations

import pytest

from tinyassets.treasury import (
    BOUNTY_POOL_SHARE_BP,
    PLATFORM_TAKE_BP,
    compute_bounty_allocation,
    compute_royalty_share,
    compute_take,
    compute_treasury_retained,
    net_after_take,
    split_take,
)

# ── compute_take ───────────────────────────────────────────────────────────────

class TestComputeTake:
    def test_one_percent_of_one_token(self):
        # 1_000_000 MicroTokens * 100 bp = 10_000
        assert compute_take(1_000_000, 100) == 10_000

    def test_default_rate(self):
        assert compute_take(1_000_000) == compute_take(1_000_000, PLATFORM_TAKE_BP)

    def test_zero_amount(self):
        assert compute_take(0) == 0

    def test_zero_rate(self):
        assert compute_take(1_000_000, 0) == 0

    def test_full_rate(self):
        # 100% take
        assert compute_take(1_000_000, 10_000) == 1_000_000

    def test_floor_division_small(self):
        # 1 MicroToken at 1% = 0 (floor)
        assert compute_take(1, 100) == 0

    def test_floor_division_99(self):
        # 99 MicroTokens at 1% = 0 (floor)
        assert compute_take(99, 100) == 0

    def test_floor_division_100(self):
        # 100 MicroTokens at 1% = 1
        assert compute_take(100, 100) == 1

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError, match="amount"):
            compute_take(-1)

    def test_negative_rate_raises(self):
        with pytest.raises(ValueError, match="rate_bp"):
            compute_take(1_000_000, -1)

    def test_large_amount(self):
        # 1 million tokens
        assert compute_take(1_000_000_000_000, 100) == 10_000_000_000


# ── net_after_take ─────────────────────────────────────────────────────────────

class TestNetAfterTake:
    def test_standard(self):
        assert net_after_take(1_000_000) == 990_000

    def test_invariant_sum(self):
        amount = 1_234_567
        assert compute_take(amount) + net_after_take(amount) == amount

    def test_zero(self):
        assert net_after_take(0) == 0

    def test_full_rate_leaves_nothing(self):
        assert net_after_take(1_000_000, 10_000) == 0


# ── compute_bounty_allocation ──────────────────────────────────────────────────

class TestComputeBountyAllocation:
    def test_fifty_percent_of_take(self):
        # take = 10_000; 50% = 5_000
        assert compute_bounty_allocation(10_000) == 5_000

    def test_default_pool_share(self):
        assert compute_bounty_allocation(10_000) == compute_bounty_allocation(
            10_000, BOUNTY_POOL_SHARE_BP
        )

    def test_zero_take(self):
        assert compute_bounty_allocation(0) == 0

    def test_zero_pool_share(self):
        assert compute_bounty_allocation(10_000, 0) == 0

    def test_full_pool_share(self):
        assert compute_bounty_allocation(10_000, 10_000) == 10_000

    def test_floor_division(self):
        # 1 MicroToken at 50% = 0 (floor)
        assert compute_bounty_allocation(1) == 0

    def test_negative_take_raises(self):
        with pytest.raises(ValueError, match="take_amount"):
            compute_bounty_allocation(-1)

    def test_pool_share_above_10000_raises(self):
        with pytest.raises(ValueError, match="pool_share_bp"):
            compute_bounty_allocation(10_000, 10_001)

    def test_pool_share_negative_raises(self):
        with pytest.raises(ValueError, match="pool_share_bp"):
            compute_bounty_allocation(10_000, -1)


# ── compute_treasury_retained ──────────────────────────────────────────────────

class TestComputeTreasuryRetained:
    def test_fifty_percent_retained(self):
        # take=10_000, 50% bounty → 5_000 retained
        assert compute_treasury_retained(10_000) == 5_000

    def test_invariant_bounty_plus_retained_eq_take(self):
        take = 10_000
        bounty = compute_bounty_allocation(take)
        retained = compute_treasury_retained(take)
        assert bounty + retained == take

    def test_zero_take(self):
        assert compute_treasury_retained(0) == 0


# ── compute_royalty_share ──────────────────────────────────────────────────────

class TestComputeRoyaltyShare:
    def test_ten_percent(self):
        assert compute_royalty_share(500_000, 0.10) == 50_000

    def test_zero_share(self):
        assert compute_royalty_share(500_000, 0.0) == 0

    def test_full_share(self):
        assert compute_royalty_share(500_000, 1.0) == 500_000

    def test_floor_division(self):
        # 1 MicroToken at 10% = 0 (int conversion floors)
        assert compute_royalty_share(1, 0.10) == 0

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError, match="gross_amount"):
            compute_royalty_share(-1, 0.10)

    def test_share_above_one_raises(self):
        with pytest.raises(ValueError, match="designer_share"):
            compute_royalty_share(500_000, 1.001)

    def test_share_negative_raises(self):
        with pytest.raises(ValueError, match="designer_share"):
            compute_royalty_share(500_000, -0.01)

    def test_sub_cent_settlement(self):
        # Very small settlement, non-zero royalty
        assert compute_royalty_share(10, 0.50) == 5

    def test_realistic_scenario(self):
        # 1 token settlement, designer gets 10%
        amount = 1_000_000
        royalty = compute_royalty_share(amount, 0.10)
        assert royalty == 100_000


# ── split_take ────────────────────────────────────────────────────────────────

class TestSplitTake:
    def test_invariant_sums_to_amount(self):
        amount = 1_000_000
        net, bounty, treasury = split_take(amount)
        assert net + bounty + treasury == amount

    def test_standard_split(self):
        # amount=1_000_000; take=10_000; bounty=5_000; treasury=5_000
        net, bounty, treasury = split_take(1_000_000)
        assert net == 990_000
        assert bounty == 5_000
        assert treasury == 5_000

    def test_zero_amount(self):
        net, bounty, treasury = split_take(0)
        assert (net, bounty, treasury) == (0, 0, 0)

    def test_all_values_nonnegative(self):
        for amount in (1, 99, 100, 999, 1_000_000, 1_000_000_000):
            net, bounty, treasury = split_take(amount)
            assert net >= 0
            assert bounty >= 0
            assert treasury >= 0

    def test_invariant_across_many_amounts(self):
        for amount in range(0, 10_001, 100):
            net, bounty, treasury = split_take(amount)
            assert net + bounty + treasury == amount, f"failed at amount={amount}"

    def test_custom_rates(self):
        # 2% take, 75% of that to bounty
        net, bounty, treasury = split_take(1_000_000, rate_bp=200, pool_share_bp=7_500)
        assert net == 980_000
        take = 20_000
        assert bounty == take * 7_500 // 10_000  # 15_000
        assert treasury == take - bounty  # 5_000
        assert net + bounty + treasury == 1_000_000
