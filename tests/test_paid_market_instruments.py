from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tinyassets.paid_market.forwards import settle_forward
from tinyassets.paid_market.instruments import (
    DEMAND_SIGNAL_ENABLED_DEFAULT,
    EXTERNAL_EXECUTION_ENABLED_DEFAULT,
    LIVE_PRICE_DISCOVERY_ENABLED_DEFAULT,
    ForwardOrder,
    InstrumentError,
    InstrumentTerms,
    best_forward_ask,
    bind_forward_collateral,
    create_forward_order,
    is_forward_order_executable,
    requires_collateral,
    transition_forward_order,
    validate_instrument,
)

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)
BUCKET = datetime(2026, 7, 25, 0, tzinfo=UTC)


def _order(
    order_id: str = "order-1",
    *,
    price: int = 100,
    collateral_receipt_id: str | None = "collateral-1",
    legal_valid_until: datetime = datetime(2026, 7, 30, tzinfo=UTC),
) -> ForwardOrder:
    return create_forward_order(
        order_id=order_id,
        market_class_id="sha256:market",
        seller_id="seller-1",
        bucket_start=BUCKET,
        bucket_hours=8,
        size_mtok=10,
        price_micros_per_mtok=price,
        posted_at=NOW,
        now=NOW,
        jurisdiction="US",
        legal_review_id="review-1",
        legal_policy_version="policy-v1",
        legal_valid_until=legal_valid_until,
        collateral_receipt_id=collateral_receipt_id,
        terms=InstrumentTerms(),
    )


@pytest.mark.parametrize("bucket_hours", [8, 24, 168])
@pytest.mark.parametrize("size_mtok", [1, 10, 100])
def test_forward_order_accepts_only_standard_bucket_and_size(
    bucket_hours: int, size_mtok: int
) -> None:
    bucket_start = (
        datetime(2026, 7, 27, 0, tzinfo=UTC)
        if bucket_hours == 168
        else BUCKET
    )
    order = create_forward_order(
        order_id=f"order-{bucket_hours}-{size_mtok}",
        market_class_id="sha256:market",
        seller_id="seller-1",
        bucket_start=bucket_start,
        bucket_hours=bucket_hours,
        size_mtok=size_mtok,
        price_micros_per_mtok=100,
        posted_at=NOW,
        now=NOW,
        jurisdiction="US",
        legal_review_id="review-1",
        legal_policy_version="policy-v1",
        legal_valid_until=NOW + timedelta(days=20),
        collateral_receipt_id="collateral",
        terms=InstrumentTerms(),
    )

    assert order.order_id == f"order-{bucket_hours}-{size_mtok}"
    assert order.state == "posted"
    assert order.version == 1


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"size_mtok": 2}, "size_mtok"),
        ({"bucket_hours": 6}, "bucket_hours"),
        (
            {"bucket_start": datetime(2026, 8, 23, 0, tzinfo=UTC)},
            "28-day horizon",
        ),
        ({"bucket_start": NOW + timedelta(hours=1)}, "boundary"),
    ],
)
def test_nonstandard_or_beyond_horizon_forward_is_refused(
    changes: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "order_id": "order",
        "market_class_id": "sha256:market",
        "seller_id": "seller",
        "bucket_start": BUCKET,
        "bucket_hours": 8,
        "size_mtok": 10,
        "price_micros_per_mtok": 100,
        "posted_at": NOW,
        "now": NOW,
        "jurisdiction": "US",
        "legal_review_id": "review",
        "legal_policy_version": "policy-v1",
        "legal_valid_until": NOW + timedelta(days=20),
        "collateral_receipt_id": "collateral",
        "terms": InstrumentTerms(),
    }
    values.update(changes)
    with pytest.raises(InstrumentError, match=message):
        create_forward_order(**values)  # type: ignore[arg-type]


def test_forward_remains_non_executable_until_collateral_is_bound() -> None:
    order = _order(collateral_receipt_id=None)

    assert is_forward_order_executable(order, now=NOW) is False
    collateralized = bind_forward_collateral(
        order,
        collateral_receipt_id="collateral-2",
        actor_id="seller-1",
    )
    assert is_forward_order_executable(collateralized, now=NOW) is True
    assert order.collateral_receipt_id is None
    assert collateralized.version == order.version + 1

    with pytest.raises(InstrumentError, match="seller authority"):
        bind_forward_collateral(
            order,
            collateral_receipt_id="collateral-3",
            actor_id="other",
        )


def test_forward_lifecycle_is_authenticated_monotone_and_id_is_immutable() -> None:
    original = _order()
    purchased = transition_forward_order(
        original,
        new_state="purchased",
        actor_id="buyer-1",
        actor_role="buyer",
        now=NOW,
    )
    delivering = transition_forward_order(
        purchased,
        new_state="delivering",
        actor_id="seller-1",
        actor_role="seller",
    )
    settled = transition_forward_order(
        delivering,
        new_state="settled",
        actor_id="settlement-owner",
        actor_role="settlement",
    )

    assert original.state == "posted"
    assert settled.order_id == original.order_id
    assert settled.buyer_id == "buyer-1"
    assert settled.version == 4
    with pytest.raises(InstrumentError, match="illegal transition"):
        transition_forward_order(
            settled,
            new_state="posted",
            actor_id="seller-1",
            actor_role="seller",
        )
    with pytest.raises(InstrumentError, match="buyer authority"):
        transition_forward_order(
            original,
            new_state="purchased",
            actor_id="seller-1",
            actor_role="seller",
            now=NOW,
        )


@pytest.mark.parametrize(
    "order",
    [
        _order(collateral_receipt_id=None),
        replace(_order(), legal_valid_until=NOW),
    ],
)
def test_non_executable_forward_cannot_be_purchased(order: ForwardOrder) -> None:
    with pytest.raises(InstrumentError, match="not executable"):
        transition_forward_order(
            order,
            new_state="purchased",
            actor_id="buyer-1",
            actor_role="buyer",
            now=NOW,
        )


def test_seller_can_cancel_open_order_and_system_can_expire_it() -> None:
    order = _order()
    cancelled = transition_forward_order(
        order,
        new_state="cancelled",
        actor_id="seller-1",
        actor_role="seller",
    )
    expired = transition_forward_order(
        replace(order, order_id="other"),
        new_state="expired",
        actor_id="scheduler",
        actor_role="system",
    )
    assert cancelled.state == "cancelled"
    assert expired.state == "expired"


def test_best_ask_is_exact_deterministic_and_executable_only() -> None:
    no_collateral = _order("cheap-but-locked", price=50, collateral_receipt_id=None)
    wrong_size = replace(_order("wrong-size", price=60), size_mtok=100)
    expensive = _order("z-expensive", price=100)
    tie_b = _order("b-tie", price=90)
    tie_a = _order("a-tie", price=90)

    ask = best_forward_ask(
        [no_collateral, wrong_size, expensive, tie_b, tie_a],
        market_class_id="sha256:market",
        bucket_start=BUCKET,
        bucket_hours=8,
        size_mtok=10,
        now=NOW,
    )

    assert ask is not None
    assert ask.order_id == "a-tie"
    assert ask.price_micros_per_mtok == 90
    assert ask.observed_at == NOW


def test_spot_is_collateral_free_and_forward_is_not() -> None:
    assert requires_collateral("spot") is False
    assert requires_collateral("forward") is True


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"delivery": "cash"}, "cash_settlement"),
        ({"secondary_transfer": True}, "secondary_transfer"),
        ({"leverage": True}, "leverage"),
        ({"netting": True}, "netting"),
        ({"proprietary_model_resale": True}, "proprietary_model_resale"),
        ({"f3_swarm": True}, "f3_swarm"),
        ({"batch_only": False}, "batch_only_required"),
    ],
)
def test_unsupported_instruments_are_refused_without_order_or_effect(
    changes: dict[str, object], reason: str
) -> None:
    terms = replace(InstrumentTerms(), **changes)
    result = validate_instrument(terms)

    assert result.status == "rejected"
    assert result.reason == reason
    assert result.creates_order is False
    assert result.locks_collateral is False
    assert result.settles is False


def test_forward_settlement_reuses_canonical_demand_relative_oracle() -> None:
    no_show = settle_forward(
        size_mtok=1,
        price_micros_per_mtok=1_000_000,
        tokens_requested=0,
        tokens_delivered=0,
        collateral_pct=20,
    )
    shortfall = settle_forward(
        size_mtok=1,
        price_micros_per_mtok=1_000_000,
        tokens_requested=1_000_000,
        tokens_delivered=900_000,
        collateral_pct=20,
    )

    assert no_show.seller_gross == no_show.buyer_paid_total
    assert no_show.defaulted is False
    assert no_show.slash_to_buyer == 0
    assert shortfall.seller_gross == 900_000
    assert shortfall.buyer_refund == 100_000
    assert shortfall.defaulted is True
    assert shortfall.slash_to_buyer > 0
    assert (
        shortfall.seller_net
        + shortfall.treasury_fee
        + shortfall.buyer_refund
        == shortfall.buyer_paid_total
    )


def test_all_new_market_surfaces_remain_default_off() -> None:
    assert LIVE_PRICE_DISCOVERY_ENABLED_DEFAULT is False
    assert DEMAND_SIGNAL_ENABLED_DEFAULT is False
    assert EXTERNAL_EXECUTION_ENABLED_DEFAULT is False
