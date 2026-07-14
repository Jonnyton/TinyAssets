"""Paid-market pure-logic tests (Track E Waves 3-4).

Coverage:
- SettledTrade validation (5)
- capped_pair_weights water-filling (6)
- compute_vwap incl. wash-trade caps (6)
- compute_spot_quote windows/ceiling/staleness (8)
- buckets alignment/horizon/enumeration (9)
- forwards state machine (4)
- settle_forward demand-model math + rounding policy (12)
- adversarial regressions A-2 / B-1 (3)
- conservation property sweep, 20k randomized cases (2)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from fractions import Fraction

import pytest

from tinyassets.paid_market.buckets import (
    BucketError,
    bucket_end,
    enumerate_buckets,
    is_aligned,
    next_bucket_start,
    validate_bucket_start,
)
from tinyassets.paid_market.forwards import (
    ForwardError,
    ForwardState,
    assert_transition,
    collateral_micros,
    settle_forward,
)
from tinyassets.paid_market.index import (
    PPM,
    IndexError_,
    SettledTrade,
    capped_pair_weights,
    compute_spot_quote,
    compute_vwap,
)

NOW = 1_780_000_000  # fixed unix anchor for index tests
UTC = timezone.utc


def _trade(price, tokens, buyer="b", seller="s", age=0, cap="llama-405b:batch"):
    return SettledTrade(
        capability_id=cap,
        price_micros_per_mtok=price,
        tokens_out=tokens,
        buyer_id=buyer,
        seller_id=seller,
        settled_at=NOW - age,
    )


# ---------------------------------------------------------------- trades


class TestSettledTradeValidation:
    def test_valid_trade_passes(self):
        _trade(5_000_000, 10_000).validate()

    @pytest.mark.parametrize("price", [0, -1, 1.5, True])
    def test_bad_price_rejected(self, price):
        with pytest.raises(IndexError_):
            _trade(price, 10_000).validate()

    @pytest.mark.parametrize("tokens", [0, -5, 2.0, False])
    def test_bad_tokens_rejected(self, tokens):
        with pytest.raises(IndexError_):
            _trade(5_000_000, tokens).validate()

    def test_missing_ids_rejected(self):
        with pytest.raises(IndexError_):
            _trade(1, 1, buyer="").validate()

    def test_pair_key_direction_insensitive(self):
        assert _trade(1, 1, "a", "z").pair_key == _trade(1, 1, "z", "a").pair_key


# ------------------------------------------------------- weight capping


class TestCappedPairWeights:
    def test_no_cap_needed_returns_raw(self):
        vols = {("a", "b"): 100, ("c", "d"): 100, ("e", "f"): 100, ("g", "h"): 100, ("i", "j"): 100}
        w = capped_pair_weights(vols, 250_000)
        assert all(w[k] == Fraction(v) for k, v in vols.items())

    def test_whale_capped_to_share(self):
        vols = {
            ("w", "w2"): 10_000, ("a", "b"): 100, ("c", "d"): 100,
            ("e", "f"): 100, ("g", "h"): 100,
        }
        w = capped_pair_weights(vols, 250_000)  # 25%
        total = sum(w.values())
        assert w[("w", "w2")] / total == Fraction(1, 4)
        # Others keep raw volume
        assert w[("a", "b")] == 100

    def test_infeasible_cap_equal_weights(self):
        # 3 pairs at 25% cap: n*c = 0.75 <= 1 → equal weights (A-2 fix):
        # volume must not buy influence in thin markets
        vols = {("a", "b"): 1000, ("c", "d"): 1, ("e", "f"): 1}
        w = capped_pair_weights(vols, 250_000)
        assert w[("a", "b")] == w[("c", "d")] == w[("e", "f")] == Fraction(1)

    def test_multiple_whales_all_capped(self):
        vols = {("w1", "x"): 10_000, ("w2", "x"): 9_000}
        vols.update({(f"u{i}", "y"): 10 for i in range(8)})  # 10 pairs total
        w = capped_pair_weights(vols, 250_000)
        total = sum(w.values())
        assert w[("w1", "x")] / total == Fraction(1, 4)
        assert w[("w2", "x")] / total == Fraction(1, 4)

    def test_empty_input(self):
        assert capped_pair_weights({}, 250_000) == {}

    @pytest.mark.parametrize("cap", [0, -1, PPM + 1])
    def test_bad_cap_rejected(self, cap):
        with pytest.raises(IndexError_):
            capped_pair_weights({("a", "b"): 1}, cap)


# --------------------------------------------------------------- vwap


class TestComputeVwap:
    def test_single_pair_simple_average(self):
        trades = [_trade(4_000_000, 100), _trade(6_000_000, 100)]
        vwap, n_pairs = compute_vwap(trades)
        assert vwap == 5_000_000
        assert n_pairs == 1

    def test_volume_weighting(self):
        trades = [_trade(4_000_000, 300), _trade(8_000_000, 100)]
        vwap, _ = compute_vwap(trades)
        assert vwap == 5_000_000  # (4*3 + 8*1)/4

    def test_wash_pair_cannot_dominate(self):
        # Honest market at ~5.0 across 5 diverse pairs; attacker washes
        # huge volume at 50.0 through one pair.
        honest = [
            _trade(5_000_000, 1_000, f"b{i}", f"s{i}") for i in range(5)
        ]
        wash = [_trade(50_000_000, 1_000_000, "attacker", "attacker2")]
        vwap, n_pairs = compute_vwap(honest + wash)
        # Attacker capped at 25% of weight: vwap = 0.75*5 + 0.25*50 = 16.25
        assert vwap == 16_250_000
        assert n_pairs == 6
        # Without the cap it would have been ~49.78 — verify cap engaged
        uncapped, _ = compute_vwap(honest + wash, share_cap_ppm=PPM)
        assert uncapped > 45_000_000

    def test_wash_both_directions_share_one_cap(self):
        honest = [_trade(5_000_000, 1_000, f"b{i}", f"s{i}") for i in range(5)]
        wash = [
            _trade(50_000_000, 500_000, "att1", "att2"),
            _trade(50_000_000, 500_000, "att2", "att1"),  # reversed direction
        ]
        vwap, n_pairs = compute_vwap(honest + wash)
        assert n_pairs == 6  # both wash trades share one pair key
        assert vwap == 16_250_000

    def test_mixed_capability_rejected(self):
        with pytest.raises(IndexError_):
            compute_vwap([_trade(1, 1), _trade(1, 1, cap="other:batch")])

    def test_empty_rejected(self):
        with pytest.raises(IndexError_):
            compute_vwap([])


# --------------------------------------------------------------- quote


class TestComputeSpotQuote:
    def _quote(self, trades, **kw):
        args = dict(
            capability_id="llama-405b:batch",
            trades=trades,
            now=NOW,
            best_ask_micros=None,
            ceiling_micros=None,
        )
        args.update(kw)
        return compute_spot_quote(**args)

    def test_primary_window(self):
        trades = [_trade(5_000_000, 100, f"b{i}", f"s{i}", age=3600) for i in range(3)]
        q = self._quote(trades)
        assert q.vwap_window == "24h"
        assert q.vwap_micros == 5_000_000
        assert q.n_trades == 3

    def test_widens_to_7d_when_thin(self):
        trades = [
            _trade(5_000_000, 100, "b1", "s1", age=3600),
            _trade(5_000_000, 100, "b2", "s2", age=3 * 86400),
            _trade(5_000_000, 100, "b3", "s3", age=5 * 86400),
        ]
        q = self._quote(trades)
        assert q.vwap_window == "7d"
        assert q.n_trades == 3

    def test_null_vwap_when_too_thin(self):
        q = self._quote([_trade(5_000_000, 100, age=3600)])
        assert q.vwap_micros is None
        assert q.vwap_window is None
        assert q.n_trades == 0  # nothing selected

    def test_quote_never_null_with_ceiling(self):
        q = self._quote([], ceiling_micros=9_000_000, best_ask_micros=7_000_000)
        assert q.vwap_micros is None
        assert q.ceiling_micros == 9_000_000
        assert q.best_ask_micros == 7_000_000  # quotable at zero volume

    def test_ceiling_clamp_flags_and_retains_raw(self):
        trades = [_trade(50_000_000, 100, f"b{i}", f"s{i}", age=60) for i in range(3)]
        q = self._quote(trades, ceiling_micros=9_000_000)
        assert q.vwap_micros == 9_000_000
        assert q.raw_vwap_micros == 50_000_000
        assert q.above_ceiling is True

    def test_no_clamp_below_ceiling(self):
        trades = [_trade(5_000_000, 100, f"b{i}", f"s{i}", age=60) for i in range(3)]
        q = self._quote(trades, ceiling_micros=9_000_000)
        assert q.vwap_micros == 5_000_000 and not q.above_ceiling

    def test_future_trade_rejected(self):
        with pytest.raises(IndexError_):
            self._quote([_trade(1_000_000, 1, age=-10)])

    def test_capability_mismatch_rejected(self):
        with pytest.raises(IndexError_):
            self._quote([_trade(1_000_000, 1, cap="other:batch")])


# ------------------------------------------------------------- buckets


class TestBuckets:
    def test_8h_alignment(self):
        assert is_aligned(datetime(2026, 7, 10, 8, tzinfo=UTC), 8)
        assert not is_aligned(datetime(2026, 7, 10, 9, tzinfo=UTC), 8)
        assert not is_aligned(datetime(2026, 7, 10, 8, 0, 1, tzinfo=UTC), 8)

    def test_day_alignment(self):
        assert is_aligned(datetime(2026, 7, 10, tzinfo=UTC), 24)
        assert not is_aligned(datetime(2026, 7, 10, 8, tzinfo=UTC), 24)

    def test_week_alignment_monday(self):
        assert is_aligned(datetime(2026, 7, 6, tzinfo=UTC), 168)  # a Monday
        assert not is_aligned(datetime(2026, 7, 10, tzinfo=UTC), 168)  # Friday

    def test_naive_datetime_rejected(self):
        with pytest.raises(BucketError):
            is_aligned(datetime(2026, 7, 10), 8)

    def test_nonstandard_hours_rejected(self):
        with pytest.raises(BucketError):
            is_aligned(datetime(2026, 7, 10, tzinfo=UTC), 12)

    def test_validate_rejects_past_and_current_bucket(self):
        now = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)
        with pytest.raises(BucketError):
            validate_bucket_start(datetime(2026, 7, 10, 8, tzinfo=UTC), 8, now=now)
        validate_bucket_start(datetime(2026, 7, 10, 16, tzinfo=UTC), 8, now=now)

    def test_validate_rejects_beyond_horizon(self):
        now = datetime(2026, 7, 10, tzinfo=UTC)
        with pytest.raises(BucketError):
            validate_bucket_start(
                datetime(2026, 8, 10, tzinfo=UTC), 24, now=now, horizon_days=28
            )

    def test_next_bucket_start(self):
        now = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)
        assert next_bucket_start(now, 8) == datetime(2026, 7, 10, 16, tzinfo=UTC)
        assert next_bucket_start(now, 24) == datetime(2026, 7, 11, tzinfo=UTC)
        assert next_bucket_start(now, 168) == datetime(2026, 7, 13, tzinfo=UTC)
        # Exactly on a boundary → next bucket, not this one (strictly after)
        on_boundary = datetime(2026, 7, 10, 16, tzinfo=UTC)
        assert next_bucket_start(on_boundary, 8) == datetime(2026, 7, 11, 0, tzinfo=UTC)

    def test_enumerate_buckets_contiguous_and_within_horizon(self):
        now = datetime(2026, 7, 10, 9, 30, tzinfo=UTC)
        buckets = enumerate_buckets(now, 8, horizon_days=2)
        assert buckets[0] == datetime(2026, 7, 10, 16, tzinfo=UTC)
        assert all(
            (b2 - b1) == timedelta(hours=8) for b1, b2 in zip(buckets, buckets[1:])
        )
        assert buckets[-1] <= now + timedelta(days=2)
        assert bucket_end(buckets[0], 8) == buckets[1]


# -------------------------------------------------------- state machine


class TestStateMachine:
    def test_happy_path(self):
        assert_transition(ForwardState.OPEN, ForwardState.SOLD)
        assert_transition(ForwardState.SOLD, ForwardState.DELIVERING)
        assert_transition(ForwardState.DELIVERING, ForwardState.SETTLED)

    def test_expiry_path(self):
        assert_transition(ForwardState.OPEN, ForwardState.EXPIRED)

    @pytest.mark.parametrize(
        "cur,new",
        [
            (ForwardState.OPEN, ForwardState.SETTLED),
            (ForwardState.SOLD, ForwardState.EXPIRED),
            (ForwardState.SETTLED, ForwardState.OPEN),
            (ForwardState.EXPIRED, ForwardState.SOLD),
            (ForwardState.DELIVERING, ForwardState.OPEN),
        ],
    )
    def test_illegal_transitions(self, cur, new):
        with pytest.raises(ForwardError):
            assert_transition(cur, new)

    def test_unknown_state(self):
        with pytest.raises(ForwardError):
            assert_transition("open", "banana")


# ---------------------------------------------------------- settlement


class TestSettleForward:
    def test_full_demand_full_delivery(self):
        s = settle_forward(
            size_mtok=10,
            price_micros_per_mtok=5_000_000,
            tokens_requested=10_000_000,
            tokens_delivered=10_000_000,
            collateral_pct=20,
        )
        assert s.buyer_paid_total == 50_000_000
        assert s.seller_gross == 50_000_000
        assert s.treasury_fee == 500_000  # exactly 1%
        assert s.seller_net == 49_500_000
        assert s.buyer_refund == 0
        assert s.collateral_locked == 10_000_000
        assert s.collateral_released == 10_000_000
        assert s.slash_to_buyer == 0
        assert not s.defaulted

    def test_buyer_noshow_pays_seller_in_full(self):
        # B-1: demand == 0 → capacity was reserved; use-it-or-lose-it
        s = settle_forward(
            size_mtok=100,
            price_micros_per_mtok=5_000_000,
            tokens_requested=0,
            tokens_delivered=0,
            collateral_pct=20,
        )
        assert s.seller_gross == s.buyer_paid_total
        assert s.buyer_refund == 0
        assert s.slash_to_buyer == 0
        assert not s.defaulted

    def test_partial_demand_fully_served_pays_in_full(self):
        # Buyer used 40% of the reservation; seller served all of it
        s = settle_forward(
            size_mtok=10,
            price_micros_per_mtok=1_000_000,
            tokens_requested=4_000_000,
            tokens_delivered=4_000_000,
            collateral_pct=20,
        )
        assert s.seller_gross == s.buyer_paid_total
        assert s.slash_to_buyer == 0 and not s.defaulted

    def test_unserved_demand_refunded_prorata(self):
        # Demand 4M, served 3M → unserved 1M of a 10M contract → 10% refund
        s = settle_forward(
            size_mtok=10,
            price_micros_per_mtok=1_000_000,
            tokens_requested=4_000_000,
            tokens_delivered=3_000_000,
            collateral_pct=20,
        )
        assert s.buyer_refund == 1_000_000
        assert s.seller_gross == 9_000_000
        assert s.defaulted  # 3/4 = 75% of demand < 95% threshold
        # slash = collateral * unserved // size = 2_000_000 * 1M // 10M
        assert s.slash_to_buyer == 200_000
        assert s.collateral_released == 1_800_000

    def test_over_request_capped_at_size(self):
        s = settle_forward(
            size_mtok=1,
            price_micros_per_mtok=1_000_000,
            tokens_requested=5_000_000,  # buyer asks 5x the contract
            tokens_delivered=1_000_000,
            collateral_pct=20,
        )
        assert s.tokens_demand == 1_000_000
        assert s.seller_gross == s.buyer_paid_total and not s.defaulted

    def test_over_delivery_beyond_demand_unpaid(self):
        s = settle_forward(
            size_mtok=1,
            price_micros_per_mtok=1_000_000,
            tokens_requested=500_000,
            tokens_delivered=900_000,
            collateral_pct=20,
        )
        assert s.tokens_served == 500_000
        assert s.seller_gross == s.buyer_paid_total  # unserved == 0

    def test_at_threshold_no_slash_but_prorata_payment(self):
        # Exactly 95% of demand: no slash, but payment still pro-rata (A-1)
        s = settle_forward(
            size_mtok=1,
            price_micros_per_mtok=1_000_000,
            tokens_requested=1_000_000,
            tokens_delivered=950_000,
            collateral_pct=20,
        )
        assert not s.defaulted
        assert s.slash_to_buyer == 0
        assert s.seller_gross == 950_000  # threshold gates slash only
        assert s.buyer_refund == 50_000

    def test_just_below_threshold_slashes(self):
        s = settle_forward(
            size_mtok=1,
            price_micros_per_mtok=1_000_000,
            tokens_requested=1_000_000,
            tokens_delivered=949_999,
            collateral_pct=20,
        )
        assert s.defaulted
        # slash = 200_000 * 50_001 // 1_000_000 = 10_000
        assert s.slash_to_buyer == 10_000
        assert s.collateral_released == 190_000

    def test_zero_delivery_with_full_demand(self):
        s = settle_forward(
            size_mtok=10,
            price_micros_per_mtok=3_000_000,
            tokens_requested=10_000_000,
            tokens_delivered=0,
            collateral_pct=20,
        )
        assert s.seller_gross == 0 and s.seller_net == 0 and s.treasury_fee == 0
        assert s.buyer_refund == s.buyer_paid_total == 30_000_000
        assert s.slash_to_buyer == s.collateral_locked == 6_000_000
        assert s.collateral_released == 0

    def test_rounding_dust_conservation(self):
        s = settle_forward(
            size_mtok=1,
            price_micros_per_mtok=999_983,
            tokens_requested=777_781,
            tokens_delivered=333_337,
            collateral_pct=7,
        )
        assert s.seller_net + s.treasury_fee + s.buyer_refund == s.buyer_paid_total
        assert s.collateral_released + s.slash_to_buyer == s.collateral_locked

    @pytest.mark.parametrize("size", [0, 2, 5, 50, -1])
    def test_nonstandard_size_rejected(self, size):
        with pytest.raises(ForwardError):
            settle_forward(
                size_mtok=size,
                price_micros_per_mtok=1_000_000,
                tokens_requested=0,
                tokens_delivered=0,
                collateral_pct=20,
            )

    @pytest.mark.parametrize("pct", [0, 4, 101, -5])
    def test_collateral_bounds(self, pct):
        with pytest.raises(ForwardError):
            collateral_micros(1_000_000, pct)

    def test_negative_inputs_rejected(self):
        for kw in ({"tokens_requested": -1}, {"tokens_delivered": -1}):
            args = dict(
                size_mtok=1,
                price_micros_per_mtok=1_000_000,
                tokens_requested=0,
                tokens_delivered=0,
                collateral_pct=20,
            )
            args.update(kw)
            with pytest.raises(ForwardError):
                settle_forward(**args)


class TestAdversarialRegressions:
    def test_B1_noshow_griefing_unprofitable(self):
        # Attacker buys competitor's forward, submits nothing.
        s = settle_forward(
            size_mtok=100,
            price_micros_per_mtok=5_000_000,
            tokens_requested=0,
            tokens_delivered=0,
            collateral_pct=20,
        )
        attacker_recovers = s.buyer_refund + s.slash_to_buyer
        assert attacker_recovers == 0  # griefing costs the full price
        assert s.seller_net == s.buyer_paid_total - s.treasury_fee

    def test_B1_dribble_demand_griefing_bounded(self):
        # Attacker requests a dust amount the seller serves — still no loss
        s = settle_forward(
            size_mtok=100,
            price_micros_per_mtok=5_000_000,
            tokens_requested=1,
            tokens_delivered=1,
            collateral_pct=20,
        )
        assert s.buyer_refund + s.slash_to_buyer == 0

    def test_A2_thin_market_whale_bounded(self):
        honest = [
            _trade(5_000_000, 1_000, f"b{i}", f"s{i}") for i in range(3)
        ]
        wash = [_trade(50_000_000, 1_000_000, "att", "att2")]
        vwap, n_pairs = compute_vwap(honest + wash)
        # Equal weights in 4-pair market: (3*5 + 50)/4 = 16.25 — bounded
        # at 1/n influence; ceiling clamp bounds the rest downstream.
        assert vwap == 16_250_000 and n_pairs == 4


# ------------------------------------------------- conservation sweep


class TestConservationProperty:
    def test_randomized_conservation_sweep(self):
        rng = random.Random(0xA55E75)
        for _ in range(20_000):
            size = rng.choice((1, 10, 100))
            price = rng.randint(1, 10**9)
            requested = rng.randint(0, size * 3_000_000)
            delivered = rng.randint(0, size * 3_000_000)
            pct = rng.randint(5, 100)
            s = settle_forward(
                size_mtok=size,
                price_micros_per_mtok=price,
                tokens_requested=requested,
                tokens_delivered=delivered,
                collateral_pct=pct,
            )
            # check_invariants already ran inside; assert externally too
            assert s.seller_net + s.treasury_fee + s.buyer_refund == (
                s.buyer_paid_total
            )
            assert s.collateral_released + s.slash_to_buyer == s.collateral_locked
            assert 0 <= s.tokens_served <= s.tokens_demand <= size * 1_000_000

    def test_seller_payment_monotone_in_delivery(self):
        # Delivering more never pays less (no cliff exploits)
        prev = -1
        for delivered in range(0, 1_000_001, 50_000):
            s = settle_forward(
                size_mtok=1,
                price_micros_per_mtok=7_777_777,
                tokens_requested=1_000_000,
                tokens_delivered=delivered,
                collateral_pct=20,
            )
            payout = s.seller_net + s.collateral_released
            assert payout >= prev
            prev = payout


# --------------------------------------------------------- ceiling feed

from tinyassets.paid_market.ceiling import (  # noqa: E402
    CeilingError,
    ModelPrice,
    ceiling_for_capability,
    parse_models_payload,
    usd_per_token_to_micros_per_mtok,
)


class TestCeilingFeed:
    def test_conversion_exact(self):
        # $0.000003/token = $3/Mtok = 3_000_000 micros/Mtok
        assert usd_per_token_to_micros_per_mtok("0.000003") == 3_000_000
        assert usd_per_token_to_micros_per_mtok("0.0000005") == 500_000
        assert usd_per_token_to_micros_per_mtok("0") == 0

    def test_conversion_no_float_drift(self):
        # A value that misbehaves under binary floats stays exact
        assert usd_per_token_to_micros_per_mtok("0.0000001") == 100_000

    @pytest.mark.parametrize("bad", ["-0.001", "abc", "NaN", "Infinity"])
    def test_conversion_rejects_bad(self, bad):
        with pytest.raises(CeilingError):
            usd_per_token_to_micros_per_mtok(bad)

    def test_conversion_rejects_nonstring(self):
        with pytest.raises(CeilingError):
            usd_per_token_to_micros_per_mtok(0.000003)

    def test_parse_skips_absent_keeps_paid(self):
        payload = {
            "data": [
                {
                    "id": "prov/llama-405b",
                    "pricing": {"prompt": "0.000002", "completion": "0.000004"},
                },
                {"id": "prov/free-llama", "pricing": {"prompt": "0", "completion": "0"}},
                {"id": "prov/embedding-thing"},  # no pricing block
                {"id": "prov/partial", "pricing": {"prompt": "0.000001"}},  # no completion
            ]
        }
        prices = parse_models_payload(payload)
        assert [p.model_id for p in prices] == ["prov/llama-405b"]
        assert prices[0].completion_micros_per_mtok == 4_000_000

    def test_parse_malformed_price_is_fatal(self):
        # Present-but-broken must raise: dropping it could silently
        # erase the true minimum and inflate the published ceiling
        payload = {"data": [{"id": "x", "pricing": {"prompt": "oops", "completion": "0.1"}}]}
        with pytest.raises(CeilingError):
            parse_models_payload(payload)

    def test_parse_rejects_bad_shape(self):
        with pytest.raises(CeilingError):
            parse_models_payload({"data": "nope"})

    def test_ceiling_min_across_mapped_ids(self):
        prices = [
            ModelPrice("a/llama-405b", 1, 9_000_000),
            ModelPrice("b/llama-405b", 1, 7_000_000),
            ModelPrice("c/other-model", 1, 1_000_000),  # not mapped — ignored
        ]
        assert ceiling_for_capability(prices, ["a/llama-405b", "b/llama-405b"]) == 7_000_000

    def test_ceiling_none_when_unmatched(self):
        assert ceiling_for_capability([], ["a/x"]) is None
        assert ceiling_for_capability([ModelPrice("m", 1, 2)], []) is None

    def test_parse_skips_negative_sentinel(self):
        # Live-catalog regression: "-1" means dynamic pricing, not corruption
        payload = {"data": [
            {"id": "router/auto", "pricing": {"prompt": "-1", "completion": "-1"}},
            {"id": "prov/real", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
        ]}
        prices = parse_models_payload(payload)
        assert [p.model_id for p in prices] == ["prov/real"]


# ----------------------------------------------------- training market

from tinyassets.paid_market.training import (  # noqa: E402
    TrainingError,
    settle_training_window,
)


class TestTrainingSettlement:
    def test_full_run(self):
        s = settle_training_window(
            price_total_micros=100_000_000,
            checkpoints_contracted=24,
            checkpoints_scheduled=24,
            checkpoints_verified=24,
            collateral_pct=20,
        )
        assert s.seller_gross == 100_000_000
        assert s.treasury_fee == 1_000_000
        assert s.buyer_refund == 0 and s.slash_to_buyer == 0 and not s.defaulted

    def test_buyer_early_cancel_pays_full(self):
        # B-1 analogue: buyer cancels at checkpoint 6; all 6 verified
        s = settle_training_window(
            price_total_micros=100_000_000,
            checkpoints_contracted=24,
            checkpoints_scheduled=6,
            checkpoints_verified=6,
            collateral_pct=20,
        )
        assert s.buyer_refund == 0 and s.slash_to_buyer == 0 and not s.defaulted

    def test_seller_miss_within_schedule(self):
        # 24 scheduled, 20 verified → 4 unserved → refund 4/24, slashed
        s = settle_training_window(
            price_total_micros=24_000_000,
            checkpoints_contracted=24,
            checkpoints_scheduled=24,
            checkpoints_verified=20,
            collateral_pct=20,
        )
        assert s.buyer_refund == 4_000_000
        assert s.defaulted
        assert s.slash_to_buyer == (4_800_000 * 4) // 24
        assert s.collateral_released + s.slash_to_buyer == 4_800_000

    def test_zero_scheduled_no_default(self):
        s = settle_training_window(
            price_total_micros=1_000_000,
            checkpoints_contracted=12,
            checkpoints_scheduled=0,
            checkpoints_verified=0,
            collateral_pct=20,
        )
        assert not s.defaulted and s.seller_gross == 1_000_000

    def test_verified_capped_at_scheduled(self):
        s = settle_training_window(
            price_total_micros=1_000_000,
            checkpoints_contracted=12,
            checkpoints_scheduled=6,
            checkpoints_verified=99,
            collateral_pct=20,
        )
        assert s.checkpoints_verified == 6

    def test_conservation_sweep(self):
        rng = random.Random(0x77A17)
        for _ in range(10_000):
            contracted = rng.randint(1, 200)
            s = settle_training_window(
                price_total_micros=rng.randint(1, 10**12),
                checkpoints_contracted=contracted,
                checkpoints_scheduled=rng.randint(0, contracted * 2),
                checkpoints_verified=rng.randint(0, contracted * 2),
                collateral_pct=rng.randint(5, 100),
            )
            assert s.seller_net + s.treasury_fee + s.buyer_refund == s.buyer_paid_total
            assert s.collateral_released + s.slash_to_buyer == s.collateral_locked

    @pytest.mark.parametrize("bad", [0, -1])
    def test_bad_contracted_rejected(self, bad):
        with pytest.raises(TrainingError):
            settle_training_window(
                price_total_micros=1,
                checkpoints_contracted=bad,
                checkpoints_scheduled=0,
                checkpoints_verified=0,
                collateral_pct=20,
            )


# ------------------------------------------------------- pools (Track H)

from tinyassets.paid_market.pool import (  # noqa: E402
    PoolError,
    apportion_exact,
    distribute_revenue,
    settle_pool_funding,
)


class TestPoolFunding:
    def test_exact_fill(self):
        a = settle_pool_funding(
            target_micros=100, contributions=[("a", 60), ("b", 40)]
        )
        assert a.filled and a.accepted == {"a": 60, "b": 40} and a.refunds == {}

    def test_overshoot_split_on_crossing_contribution(self):
        a = settle_pool_funding(
            target_micros=100, contributions=[("a", 60), ("b", 70), ("c", 5)]
        )
        assert a.filled
        assert a.accepted == {"a": 60, "b": 40}
        assert a.refunds == {"b": 30, "c": 5}

    def test_failed_pool_full_refund(self):
        a = settle_pool_funding(
            target_micros=1000, contributions=[("a", 60), ("a", 40)]
        )
        assert not a.filled and a.accepted == {} and a.refunds == {"a": 100}

    def test_repeat_contributor_accumulates(self):
        a = settle_pool_funding(
            target_micros=100, contributions=[("a", 30), ("b", 30), ("a", 40)]
        )
        assert a.accepted == {"a": 70, "b": 30}

    @pytest.mark.parametrize("bad", [0, -5])
    def test_bad_contribution_rejected(self, bad):
        with pytest.raises(PoolError):
            settle_pool_funding(target_micros=10, contributions=[("a", bad)])


class TestApportionment:
    def test_exact_conservation_simple(self):
        out = apportion_exact(100, {"a": 1, "b": 1, "c": 1})
        assert sum(out.values()) == 100
        assert sorted(out.values()) == [33, 33, 34]

    def test_deterministic_tiebreak(self):
        # Equal remainders → extra micro goes to lexicographically first
        out1 = apportion_exact(1, {"b": 1, "a": 1})
        out2 = apportion_exact(1, {"a": 1, "b": 1})
        assert out1 == out2 == {"a": 1, "b": 0}

    def test_within_one_micro_of_exact(self):
        shares = {f"u{i}": (i * 7919) % 1000 + 1 for i in range(200)}
        amount = 999_999_937
        out = apportion_exact(amount, shares)
        assert sum(out.values()) == amount
        total_w = sum(shares.values())
        for k, w in shares.items():
            exact = Fraction(amount * w, total_w)
            assert abs(Fraction(out[k]) - exact) < 1

    def test_randomized_conservation_sweep(self):
        rng = random.Random(0x9001)
        for _ in range(5_000):
            n = rng.randint(1, 50)
            shares = {f"u{i}": rng.randint(1, 10**9) for i in range(n)}
            amount = rng.randint(0, 10**12)
            out = apportion_exact(amount, shares)
            assert sum(out.values()) == amount

    def test_zero_amount(self):
        assert sum(apportion_exact(0, {"a": 5, "b": 3}).values()) == 0


class TestRevenueDistribution:
    def test_no_attribution(self):
        owners, attrib, at = distribute_revenue(
            revenue_micros=1_000_000, owner_shares={"a": 3, "b": 1}
        )
        assert at == 0 and attrib == {}
        assert owners == {"a": 750_000, "b": 250_000}

    def test_with_attribution_chain(self):
        owners, attrib, at = distribute_revenue(
            revenue_micros=1_000_000,
            owner_shares={"a": 1, "b": 1},
            attribution_ppm=100_000,  # 10% to lineage
            attribution_shares={"base-model-owners": 1},
        )
        assert at == 100_000
        assert attrib == {"base-model-owners": 100_000}
        assert sum(owners.values()) == 900_000

    def test_joint_conservation_sweep(self):
        rng = random.Random(0xC0FFEE)
        for _ in range(3_000):
            n = rng.randint(1, 30)
            owners_s = {f"o{i}": rng.randint(1, 10**8) for i in range(n)}
            attrib_s = {f"l{i}": rng.randint(1, 10**6) for i in range(rng.randint(1, 5))}
            rev = rng.randint(0, 10**11)
            ppm = rng.randint(0, PPM - 1)
            o, a, _ = distribute_revenue(
                revenue_micros=rev,
                owner_shares=owners_s,
                attribution_ppm=ppm,
                attribution_shares=attrib_s,
            )
            assert sum(o.values()) + sum(a.values()) == rev

    def test_attribution_without_shares_rejected(self):
        with pytest.raises(PoolError):
            distribute_revenue(
                revenue_micros=100,
                owner_shares={"a": 1},
                attribution_ppm=1,
            )


# --------------------------------------------------- licenses (Track G)

from tinyassets.paid_market.license_terms import (  # noqa: E402
    LicenseError,
    check_trainable,
    compose_terms,
    terms_for,
)


class TestLicenseComposition:
    def test_permissive_stack_stays_permissive(self):
        t = check_trainable(["apache-2.0", "mit", "cc0"])
        assert t.attribution_required and not t.share_alike
        assert not t.non_commercial and not t.no_derivatives

    def test_union_of_restrictions(self):
        t = check_trainable(["apache-2.0", "cc-by-nc", "cc-by-sa"])
        assert t.attribution_required and t.share_alike and t.non_commercial

    def test_llama_base_carries_named_terms(self):
        t = check_trainable(["llama-community", "cc-by"])
        assert t.named_redistribution_terms and t.share_alike

    def test_no_derivatives_blocks(self):
        with pytest.raises(LicenseError):
            check_trainable(["apache-2.0", "cc-by-nd"])

    def test_unknown_license_fails_closed(self):
        with pytest.raises(LicenseError):
            check_trainable(["apache-2.0", "totally-new-license-2026"])

    def test_case_insensitive_resolution(self):
        assert terms_for("Apache-2.0").license_id == "apache-2.0"

    def test_empty_inputs_rejected(self):
        with pytest.raises(LicenseError):
            compose_terms([])
        with pytest.raises(LicenseError):
            check_trainable([])

    def test_composition_never_relaxes(self):
        # Property: composed flags are the OR of input flags, for every
        # subset of the registry that is trainable
        import itertools

        from tinyassets.paid_market.license_terms import TERMS_REGISTRY
        trainable = [t for t in TERMS_REGISTRY.values() if not t.no_derivatives]
        for combo in itertools.combinations(trainable, 2):
            c = compose_terms(list(combo))
            for flag in ("attribution_required", "share_alike",
                         "non_commercial", "named_redistribution_terms"):
                assert getattr(c, flag) == any(getattr(t, flag) for t in combo)


# ------------------------------------------------- shuttles (Track I)

from tinyassets.paid_market.shuttle import (  # noqa: E402
    ShuttleError,
    allocate_shuttle,
)


class TestShuttleAllocation:
    def test_area_proportional_exact(self):
        a = allocate_shuttle(
            die_area_um2=1_000_000,
            total_cost_micros=100_000_000,
            operator_fee_ppm=50_000,
            design_areas_um2={"d1": 600_000, "d2": 300_000, "d3": 100_000},
        )
        assert a.design_costs == {"d1": 60_000_000, "d2": 30_000_000, "d3": 10_000_000}
        assert sum(a.design_costs.values()) == a.total_cost_micros

    def test_unfilled_area_is_operator_risk(self):
        # 60% filled: designs pay only for their area, not the hole
        a = allocate_shuttle(
            die_area_um2=1_000_000,
            total_cost_micros=100_000_000,
            operator_fee_ppm=0,
            design_areas_um2={"d1": 600_000},
        )
        assert a.design_costs == {"d1": 60_000_000}

    def test_overcommit_rejected(self):
        with pytest.raises(ShuttleError):
            allocate_shuttle(
                die_area_um2=100,
                total_cost_micros=1_000,
                operator_fee_ppm=0,
                design_areas_um2={"d1": 60, "d2": 60},
            )

    def test_below_min_fill_rejected(self):
        with pytest.raises(ShuttleError):
            allocate_shuttle(
                die_area_um2=1_000_000,
                total_cost_micros=100_000_000,
                operator_fee_ppm=0,
                design_areas_um2={"d1": 100_000},  # 10% < 50% default
            )

    def test_gate_failed_designs_simply_absent(self):
        # Dropping a design and re-allocating never raises survivors'
        # per-area price (full-die cost basis)
        full = allocate_shuttle(
            die_area_um2=1_000_000,
            total_cost_micros=100_000_000,
            operator_fee_ppm=0,
            design_areas_um2={"d1": 500_000, "d2": 300_000},
        )
        after_drop = allocate_shuttle(
            die_area_um2=1_000_000,
            total_cost_micros=100_000_000,
            operator_fee_ppm=0,
            design_areas_um2={"d1": 500_000},
        )
        assert after_drop.design_costs["d1"] == full.design_costs["d1"]

    def test_conservation_sweep(self):
        rng = random.Random(0x51117)
        for _ in range(3_000):
            die = rng.randint(1_000, 10**9)
            n = rng.randint(1, 40)
            areas = {}
            budget = die
            for i in range(n):
                if budget <= 1:
                    break
                a = rng.randint(1, max(1, budget // 2))
                areas[f"d{i}"] = a
                budget -= a
            if sum(areas.values()) * 2 < die:
                areas["filler"] = die - sum(areas.values())
            alloc = allocate_shuttle(
                die_area_um2=die,
                total_cost_micros=rng.randint(1, 10**12),
                operator_fee_ppm=rng.randint(0, PPM - 1),
                design_areas_um2=areas,
            )
            assert sum(alloc.design_costs.values()) == alloc.total_cost_micros
            assert alloc.area_used_um2 <= die


# --------------------------------------------- fabrication (Track I §I4)

from tinyassets.paid_market.fabrication import (  # noqa: E402
    FabricationError,
    SellerOffer,
    haversine_km,
    quote_print_job,
    rank_sellers,
    settle_physical_job,
    shipping_cost_micros,
)


class TestPrintQuoting:
    def test_exact_quote(self):
        # 250g PETG @ $20/kg + 5h @ $1.20/h + $0.50 setup
        q = quote_print_job(
            mass_mg_per_unit=250_000,
            machine_seconds_per_unit=18_000,
            quantity=1,
            material_micros_per_kg=20_000_000,
            machine_micros_per_hour=1_200_000,
            setup_micros=500_000,
        )
        assert q == 5_000_000 + 6_000_000 + 500_000

    def test_quantity_no_rounding_advantage(self):
        # Total-first math: 10 units quoted together == within one
        # flooring of any split; here mass forces a remainder per unit
        kw = dict(
            mass_mg_per_unit=333,
            machine_seconds_per_unit=7,
            material_micros_per_kg=999_999,
            machine_micros_per_hour=999_999,
            setup_micros=0,
        )
        ten = quote_print_job(quantity=10, **kw)
        one = quote_print_job(quantity=1, **kw)
        assert ten >= one * 10  # splitting never gets cheaper
        # floor(10x) - 10*floor(x) < 10 per cost leg (2 legs) — bounded dust
        assert ten - one * 10 < 20

    @pytest.mark.parametrize("field", [
        "mass_mg_per_unit", "machine_seconds_per_unit", "quantity",
        "material_micros_per_kg", "machine_micros_per_hour",
    ])
    def test_nonpositive_rejected(self, field):
        kw = dict(
            mass_mg_per_unit=1, machine_seconds_per_unit=1, quantity=1,
            material_micros_per_kg=1, machine_micros_per_hour=1,
        )
        kw[field] = 0
        with pytest.raises(FabricationError):
            quote_print_job(**kw)


class TestGeography:
    def test_haversine_known_distance(self):
        # London ↔ Paris ≈ 344 km
        d = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
        assert 335 < d < 350

    def test_haversine_zero(self):
        assert haversine_km(10.0, 20.0, 10.0, 20.0) == 0.0

    @pytest.mark.parametrize("lat", [91, -91, float("nan")])
    def test_bad_coords_rejected(self, lat):
        with pytest.raises(FabricationError):
            haversine_km(lat, 0, 0, 0)

    def test_shipping_bands(self):
        bands = [(50, 300_000), (500, 900_000), (5000, 2_500_000)]
        assert shipping_cost_micros(10, bands) == 300_000
        assert shipping_cost_micros(50, bands) == 300_000  # inclusive edge
        assert shipping_cost_micros(51, bands) == 900_000
        assert shipping_cost_micros(9999, bands) is None  # unserviceable

    def test_nonascending_bands_rejected(self):
        with pytest.raises(FabricationError):
            shipping_cost_micros(1, [(100, 1), (100, 2)])

    def test_ranking_effective_cost_and_exclusion(self):
        offers = [
            SellerOffer("near-pricey", 51.6, -0.1, 5_000_000, [(100, 300_000)]),
            SellerOffer("far-cheap", 48.8566, 2.3522, 4_000_000, [(1000, 900_000)]),
            SellerOffer("unserviceable", 35.0, 139.0, 1_000, [(100, 1_000)]),
        ]
        ranked = rank_sellers(job_lat=51.5074, job_lon=-0.1278, offers=offers)
        assert [r[0] for r in ranked] == ["far-cheap", "near-pricey"]
        assert ranked[0][1] == 4_900_000  # quote + shipping

    def test_ranking_deterministic_tiebreak(self):
        offers = [
            SellerOffer("b", 10.0, 10.0, 1_000_000, [(10_000, 0)]),
            SellerOffer("a", 10.0, 10.0, 1_000_000, [(10_000, 0)]),
        ]
        ranked = rank_sellers(job_lat=10.0, job_lon=10.0, offers=offers)
        assert [r[0] for r in ranked] == ["a", "b"]


class TestPhysicalSettlement:
    def test_full_acceptance(self):
        s = settle_physical_job(
            goods_micros=10_000_000, shipping_micros=1_000_000,
            units_ordered=10, units_accepted=10,
        )
        assert s.seller_gross == 11_000_000
        assert s.treasury_fee == 110_000
        assert s.buyer_refund == 0 and not s.defaulted

    def test_partial_acceptance_prorata_goods_full_shipping(self):
        s = settle_physical_job(
            goods_micros=10_000_000, shipping_micros=1_000_000,
            units_ordered=10, units_accepted=9,
        )
        assert s.seller_gross == 9_000_000 + 1_000_000  # box shipped
        assert s.buyer_refund == 1_000_000
        assert not s.defaulted  # 9/10 == exactly 90% == threshold, not below

    def test_threshold_edges(self):
        at = settle_physical_job(
            goods_micros=100, shipping_micros=0, units_ordered=10, units_accepted=9
        )
        assert not at.defaulted  # exactly 90%
        below = settle_physical_job(
            goods_micros=100, shipping_micros=0, units_ordered=10, units_accepted=8
        )
        assert below.defaulted

    def test_total_rejection_refunds_everything(self):
        s = settle_physical_job(
            goods_micros=5_000_000, shipping_micros=700_000,
            units_ordered=5, units_accepted=0,
        )
        assert s.seller_net == 0 and s.treasury_fee == 0
        assert s.buyer_refund == 5_700_000
        assert s.defaulted

    def test_conservation_sweep(self):
        rng = random.Random(0xFAB)
        for _ in range(5_000):
            ordered = rng.randint(1, 500)
            s = settle_physical_job(
                goods_micros=rng.randint(1, 10**10),
                shipping_micros=rng.randint(0, 10**8),
                units_ordered=ordered,
                units_accepted=rng.randint(0, ordered * 2),
            )
            assert (
                s.seller_net + s.treasury_fee + s.buyer_refund
                == s.goods_paid_total + s.shipping_paid_total
            )


# --------------------------------------------------- fund / TINY (tokens)

from tinyassets.paid_market.fund import (  # noqa: E402
    FundError,
    FundState,
    mint_at_nav,
    nav_micros_per_token,
    record_fee_inflow,
    redeem_at_nav,
)


class TestFundMechanics:
    def test_genesis_bootstrap(self):
        s0 = FundState(aum_micros=0, supply_base_units=0)
        s1, minted = mint_at_nav(s0, 1_000_000)
        assert minted == 1_000_000
        assert nav_micros_per_token(s1) == 1_000_000  # 1.00 per whole token

    def test_fee_inflow_accretes_nav_without_minting(self):
        s = FundState(aum_micros=1_000_000, supply_base_units=1_000_000)
        s2 = record_fee_inflow(s, 500_000)
        assert s2.supply_base_units == s.supply_base_units
        assert nav_micros_per_token(s2) == 1_500_000  # holders got richer

    def test_mint_after_accretion_prices_at_nav(self):
        s = FundState(aum_micros=2_000_000, supply_base_units=1_000_000)  # NAV 2.0
        s2, minted = mint_at_nav(s, 1_000_000)
        assert minted == 500_000  # pays NAV, not genesis price
        # New entrant did not dilute incumbents:
        assert nav_micros_per_token(s2) == 2_000_000

    def test_mint_redeem_cycle_cannot_extract_value(self):
        # Fund-favoring rounding: a full cycle never returns more than
        # contributed, at any state
        rng = random.Random(0x71AB)
        for _ in range(5_000):
            s = FundState(
                aum_micros=rng.randint(1, 10**12),
                supply_base_units=rng.randint(1, 10**12),
            )
            contrib = rng.randint(1, 10**9)
            try:
                s1, minted = mint_at_nav(s, contrib)
            except FundError:
                continue  # contribution below one base unit at NAV
            s2, payout = redeem_at_nav(s1, minted)
            assert payout <= contrib  # dust stays with the fund
            assert s2.aum_micros >= s.aum_micros  # fund never shrinks on a cycle

    def test_full_winddown_pays_exact_aum(self):
        s = FundState(aum_micros=7_777_777, supply_base_units=3)
        s2, payout = redeem_at_nav(s, 3)
        assert payout == 7_777_777
        assert s2.aum_micros == 0 and s2.supply_base_units == 0

    def test_partial_redeem_floors(self):
        s = FundState(aum_micros=10, supply_base_units=3)
        s2, payout = redeem_at_nav(s, 1)
        assert payout == 3  # floor(10/3)
        assert s2.aum_micros == 7

    def test_overburn_rejected(self):
        with pytest.raises(FundError):
            redeem_at_nav(FundState(aum_micros=10, supply_base_units=5), 6)

    def test_dust_mint_rejected(self):
        # NAV so high that 1 micro mints zero units → explicit error,
        # never a free contribution
        s = FundState(aum_micros=10**12, supply_base_units=1)
        with pytest.raises(FundError):
            mint_at_nav(s, 1)

    def test_supply_without_assets_rejected(self):
        with pytest.raises(FundError):
            nav_micros_per_token(FundState(aum_micros=0, supply_base_units=5))

    def test_genesis_mint_against_preseeded_treasury_rejected(self):
        # Codex adversarial-review finding (PR #1440): a 1:1 bootstrap
        # against pre-genesis treasury AUM gives the first minter 100%
        # of supply — full-redeem then drains the entire treasury for
        # the price of the contribution. Must refuse until treasury
        # supply is explicitly allocated (founder-gated policy).
        treasury = FundState(aum_micros=1_000_000_000, supply_base_units=0)
        with pytest.raises(FundError, match="treasury"):
            mint_at_nav(treasury, 1)
        with pytest.raises(FundError, match="treasury"):
            mint_at_nav(treasury, 10**12)

    def test_genesis_mint_with_fee_against_preseeded_treasury_rejected(self):
        from tinyassets.paid_market.fund import mint_at_nav_with_fee

        treasury = FundState(aum_micros=1_000_000_000, supply_base_units=0)
        with pytest.raises(FundError, match="treasury"):
            mint_at_nav_with_fee(treasury, 1_000_000, entry_fee_ppm=10_000)

    def test_pre_genesis_fee_inflow_then_genesis_mint_rejected(self):
        # Fees can legally accrete before genesis; that state must also
        # refuse public minting rather than gift the accrued fees.
        s = record_fee_inflow(FundState(aum_micros=0, supply_base_units=0), 5)
        with pytest.raises(FundError, match="treasury"):
            mint_at_nav(s, 1_000_000)

    def test_redemption_capacity_limited_by_stable_reserves(self):
        from tinyassets.paid_market.fund import redemption_capacity_base_units
        # AUM 100 (60 stable, 40 illiquid positions), supply 100
        s = FundState(aum_micros=100, supply_base_units=100)
        cap = redemption_capacity_base_units(s, stable_reserves_micros=60)
        assert cap == 60
        # The capacity actually pays out within reserves:
        _, payout = redeem_at_nav(s, cap)
        assert payout <= 60
        # Reserve floor shrinks capacity
        assert redemption_capacity_base_units(s, 60, reserve_floor_micros=50) == 10
        # Reserves cannot exceed AUM (accounting fault)
        with pytest.raises(FundError):
            redemption_capacity_base_units(s, 101)

    def test_entry_fee_accrues_to_holders(self):
        from tinyassets.paid_market.fund import mint_at_nav_with_fee
        s = FundState(aum_micros=10_000_000, supply_base_units=10_000_000)  # NAV 1.0
        s2, minted = mint_at_nav_with_fee(s, 1_000_000, entry_fee_ppm=10_000)  # 1%
        assert minted == 990_000  # net of fee mints at NAV
        assert s2.aum_micros == 11_000_000  # full contribution in AUM
        # NAV rose for incumbents (fee accrued):
        assert nav_micros_per_token(s2) > 1_000_000

    def test_exit_fee_stays_in_fund_and_winddown_exempt(self):
        from tinyassets.paid_market.fund import redeem_at_nav_with_fee
        s = FundState(aum_micros=10_000_000, supply_base_units=10_000_000)
        s2, payout = redeem_at_nav_with_fee(s, 1_000_000, exit_fee_ppm=10_000)
        assert payout == 990_000
        assert s2.aum_micros == 10_000_000 - 990_000  # fee retained
        # Full wind-down pays exact AUM, no fee:
        s3, payout3 = redeem_at_nav_with_fee(s, 10_000_000, exit_fee_ppm=10_000)
        assert payout3 == 10_000_000 and s3.aum_micros == 0

    def test_fee_cycle_strictly_unprofitable(self):
        from tinyassets.paid_market.fund import (
            mint_at_nav_with_fee,
            redeem_at_nav_with_fee,
        )
        s = FundState(aum_micros=9_999_991, supply_base_units=7_777_777)
        s1, minted = mint_at_nav_with_fee(s, 1_000_000, 5_000)
        _, back = redeem_at_nav_with_fee(s1, minted, 5_000)
        assert back < 1_000_000  # round trip always loses the fees


# --------------------------------------------------- ledger (Wave 2 core)

from tinyassets.paid_market.ledger import (  # noqa: E402
    Ledger,
    LedgerError,
    escrow_lock_entries,
    forward_sale_entries,
    forward_settlement_entries,
    physical_settlement_entries,
    pool_close_entries,
    training_settlement_entries,
)


class TestLedger:
    def test_zero_sum_enforced(self):
        led = Ledger({"user:a": 100})
        with pytest.raises(LedgerError):
            led.apply([("user:a", -10), ("user:b", 9)])

    def test_overdraft_atomic(self):
        led = Ledger({"user:a": 5})
        with pytest.raises(LedgerError):
            led.apply([("user:a", -10), ("user:b", 10)])
        assert led.balance("user:a") == 5 and led.balance("user:b") == 0

    def test_net_before_overdraft_check(self):
        # +10 then -7 on same account within one tx nets +3: valid even
        # from zero, regardless of entry order
        led = Ledger({"user:a": 3})
        led.apply([("user:a", -3), ("user:b", 10), ("user:b", -7)])
        assert led.balance("user:b") == 3

    def test_external_boundary_accounts_may_go_negative(self):
        led = Ledger()
        led.apply([("external:funding", -100), ("user:a", 100)])
        assert led.balance("external:funding") == -100  # net-inflow audit
        with pytest.raises(LedgerError):
            led.apply([("user:zz", -1), ("user:a", 1)])  # internal still strict

    def test_full_forward_lifecycle_drains_escrows(self):
        led = Ledger({"user:buyer": 100_000_000, "user:seller": 20_000_000})
        s = settle_forward(
            size_mtok=10, price_micros_per_mtok=5_000_000,
            tokens_requested=10_000_000, tokens_delivered=9_000_000,
            collateral_pct=20,
        )
        led.apply(forward_sale_entries(
            buyer_account="user:buyer", seller_account="user:seller",
            goods_escrow="escrow:f1", collateral_escrow="collateral:f1",
            total_micros=s.buyer_paid_total, collateral_micros=s.collateral_locked,
        ))
        led.apply(forward_settlement_entries(
            s, goods_escrow="escrow:f1", collateral_escrow="collateral:f1",
            seller_account="user:seller", buyer_account="user:buyer",
        ))
        led.assert_drained("escrow:f1")
        led.assert_drained("collateral:f1")
        # System-wide conservation: total balances unchanged
        assert sum(led.balances.values()) == 120_000_000

    def test_training_and_physical_adapters_drain(self):
        led = Ledger({"user:b": 10**9, "user:s": 10**9})
        ts = settle_training_window(
            price_total_micros=24_000_000, checkpoints_contracted=24,
            checkpoints_scheduled=24, checkpoints_verified=20, collateral_pct=20,
        )
        led.apply(forward_sale_entries(
            buyer_account="user:b", seller_account="user:s",
            goods_escrow="escrow:t1", collateral_escrow="collateral:t1",
            total_micros=ts.buyer_paid_total, collateral_micros=ts.collateral_locked,
        ))
        led.apply(training_settlement_entries(
            ts, goods_escrow="escrow:t1", collateral_escrow="collateral:t1",
            seller_account="user:s", buyer_account="user:b",
        ))
        led.assert_drained("escrow:t1")
        led.assert_drained("collateral:t1")

        ps = settle_physical_job(
            goods_micros=10_000_000, shipping_micros=1_000_000,
            units_ordered=10, units_accepted=9,
        )
        led.apply(escrow_lock_entries(
            payer_account="user:b", escrow_account="escrow:p1",
            amount_micros=11_000_000,
        ))
        led.apply(physical_settlement_entries(
            ps, escrow_account="escrow:p1",
            seller_account="user:s", buyer_account="user:b",
        ))
        led.assert_drained("escrow:p1")

    def test_pool_close_filled_and_failed(self):
        led = Ledger()
        # contributions arrive into per-contributor escrow
        for who, amt in [("a", 60), ("b", 70), ("c", 5)]:
            led.apply([(f"pesc:{who}", amt), ("external:funding", -amt)])
        acct = settle_pool_funding(
            target_micros=100, contributions=[("a", 60), ("b", 70), ("c", 5)]
        )
        led.apply(pool_close_entries(
            acct, pool_account="pool:g1", escrow_prefix="pesc:",
        ))
        for who in ("a", "b", "c"):
            led.assert_drained(f"pesc:{who}")
        assert led.balance("pool:g1") == 100
        assert led.balance("user:b") == 30 and led.balance("user:c") == 5


# ---------------------------------------------- best execution (Wave 2)

from tinyassets.paid_market.match import (  # noqa: E402
    BookOffer,
    MatchError,
    best_execution,
)


class TestBestExecution:
    def test_greedy_is_wrong_dp_is_right(self):
        offers = [BookOffer(f"s{i}", 1, 5_000_000) for i in range(9)]
        offers.append(BookOffer("big", 10, 4_000_000))
        cost, ids = best_execution(offers, 9)
        assert ids == ["big"] and cost == 40_000_000

    def test_exact_fill_beats_overbuy_when_cheaper(self):
        offers = [BookOffer("a", 1, 4_000_000), BookOffer("big", 10, 4_000_000)]
        cost, ids = best_execution(offers, 1)
        assert ids == ["a"] and cost == 4_000_000

    def test_insufficient_supply_none(self):
        assert best_execution([BookOffer("a", 10, 1)], 11) is None

    def test_deterministic_tiebreak(self):
        offers = [BookOffer("b", 1, 1_000_000), BookOffer("a", 1, 1_000_000)]
        _, ids = best_execution(offers, 1)
        assert ids == ["a"]

    def test_duplicate_offer_ids_rejected(self):
        with pytest.raises(MatchError):
            best_execution([BookOffer("x", 1, 1), BookOffer("x", 1, 1)], 1)

    def test_matches_brute_force(self):
        import itertools
        rng = random.Random(0xBE57)
        for _ in range(300):
            n = rng.randint(1, 9)
            offers = [
                BookOffer(f"o{i}", rng.choice((1, 10, 100)),
                          rng.randint(1, 100) * 100_000)
                for i in range(n)
            ]
            need = rng.randint(1, 120)
            got = best_execution(offers, need)
            # brute force
            best = None
            for r in range(1, n + 1):
                for combo in itertools.combinations(offers, r):
                    if sum(o.size_mtok for o in combo) >= need:
                        c = sum(o.cost_micros for o in combo)
                        key = (c, sum(o.size_mtok for o in combo),
                               tuple(sorted(o.offer_id for o in combo)))
                        if best is None or key < best:
                            best = key
            if best is None:
                assert got is None
            else:
                assert got is not None
                assert got[0] == best[0]
                assert tuple(got[1]) == best[2]

    def test_break_even_units(self):
        from tinyassets.paid_market.shuttle import break_even_units
        # $2400 NRE, $92 module vs $11 chip -> ceil(2400/81) = 30... at
        # micros scale: 2_400e6 / 81e6 -> 30 units per $ of margin? Use
        # demo-scale numbers directly:
        n = break_even_units(
            nre_micros=2_400_000_000,
            commodity_unit_micros=92_000_000,
            custom_unit_micros=11_000_000,
        )
        assert n == 30  # ceil(2400/81)
        # exact divisibility has no phantom extra unit
        assert break_even_units(
            nre_micros=810_000_000,
            commodity_unit_micros=92_000_000,
            custom_unit_micros=11_000_000,
        ) == 10
        # custom never wins -> None
        assert break_even_units(
            nre_micros=1, commodity_unit_micros=10, custom_unit_micros=10
        ) is None
