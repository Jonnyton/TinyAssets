"""Pure default-dark policy for native spot and physically delivered forwards."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Sequence

from tinyassets.paid_market.buckets import BucketError, validate_bucket_start
from tinyassets.paid_market.forwards import SIZES_MTOK

LIVE_PRICE_DISCOVERY_ENABLED_DEFAULT = False
DEMAND_SIGNAL_ENABLED_DEFAULT = False
EXTERNAL_EXECUTION_ENABLED_DEFAULT = False


class InstrumentError(ValueError):
    """An instrument, order, transition, or jurisdiction gate is invalid."""


@dataclass(frozen=True)
class InstrumentTerms:
    delivery: str = "physical"
    secondary_transfer: bool = False
    leverage: bool = False
    netting: bool = False
    proprietary_model_resale: bool = False
    f3_swarm: bool = False
    batch_only: bool = True


@dataclass(frozen=True)
class InstrumentPolicyResult:
    status: str
    reason: str | None
    creates_order: bool = False
    locks_collateral: bool = False
    settles: bool = False


@dataclass(frozen=True)
class LegalReview:
    review_id: str
    jurisdiction: str
    policy_version: str
    reviewer_kind: str
    issued_at: datetime
    valid_until: datetime
    covered_products: frozenset[str]
    findings_digest: str
    includes_forward_contract_analysis: bool
    includes_export_control_analysis: bool
    includes_money_rules_analysis: bool


@dataclass(frozen=True)
class JurisdictionGate:
    status: str
    reason: str | None
    review_id: str | None
    policy_version: str | None
    is_legal_approval: bool
    advertisable: bool
    executable: bool
    caveat: str


@dataclass(frozen=True)
class ForwardOrder:
    order_id: str
    market_class_id: str
    seller_id: str
    buyer_id: str | None
    bucket_start: datetime
    bucket_hours: int
    size_mtok: int
    price_micros_per_mtok: int
    posted_at: datetime
    jurisdiction: str
    legal_review_id: str
    legal_policy_version: str
    legal_valid_until: datetime
    collateral_receipt_id: str | None
    terms: InstrumentTerms
    state: str
    version: int


@dataclass(frozen=True)
class ForwardAsk:
    order_id: str
    price_micros_per_mtok: int
    observed_at: datetime


def validate_instrument(terms: InstrumentTerms) -> InstrumentPolicyResult:
    reason: str | None = None
    if terms.delivery != "physical":
        reason = "cash_settlement"
    elif terms.secondary_transfer:
        reason = "secondary_transfer"
    elif terms.leverage:
        reason = "leverage"
    elif terms.netting:
        reason = "netting"
    elif terms.proprietary_model_resale:
        reason = "proprietary_model_resale"
    elif terms.f3_swarm:
        reason = "f3_swarm"
    elif not terms.batch_only:
        reason = "batch_only_required"
    return InstrumentPolicyResult(
        status="allowed" if reason is None else "rejected",
        reason=reason,
    )


def requires_collateral(kind: str) -> bool:
    if kind == "spot":
        return False
    if kind == "forward":
        return True
    raise InstrumentError("unsupported instrument kind")


def jurisdiction_gate(
    product: str,
    jurisdiction: str,
    *,
    now: datetime,
    review: LegalReview | None,
) -> JurisdictionGate:
    if product not in {"forward", "training", "hardware"}:
        raise InstrumentError("unsupported jurisdiction-gated product")
    reason: str | None = None
    if review is None:
        reason = "legal_review_missing"
    elif review.valid_until <= now:
        reason = "legal_review_stale"
    elif review.issued_at > now:
        reason = "legal_review_not_yet_valid"
    elif review.jurisdiction != jurisdiction:
        reason = "jurisdiction_mismatch"
    elif review.reviewer_kind != "specialist_counsel":
        reason = "specialist_review_required"
    elif product not in review.covered_products:
        reason = "product_not_reviewed"
    elif not review.includes_forward_contract_analysis:
        reason = "forward_analysis_missing"
    elif not review.includes_export_control_analysis:
        reason = "export_control_analysis_missing"
    elif not review.includes_money_rules_analysis:
        reason = "money_rules_analysis_missing"
    elif (
        not review.review_id
        or not review.policy_version
        or not review.findings_digest
    ):
        reason = "legal_review_malformed"

    eligible = reason is None
    return JurisdictionGate(
        status="eligible" if eligible else "dark",
        reason=reason,
        review_id=review.review_id if eligible and review else None,
        policy_version=review.policy_version if eligible and review else None,
        is_legal_approval=False,
        advertisable=eligible,
        executable=eligible,
        caveat=(
            "Policy eligibility from a bound specialist artifact; not legal "
            "approval or a regulatory safe harbor."
        ),
    )


def create_forward_order(
    *,
    order_id: str,
    market_class_id: str,
    seller_id: str,
    bucket_start: datetime,
    bucket_hours: int,
    size_mtok: int,
    price_micros_per_mtok: int,
    posted_at: datetime,
    now: datetime,
    jurisdiction: str,
    legal_review_id: str,
    legal_policy_version: str,
    legal_valid_until: datetime,
    collateral_receipt_id: str | None,
    terms: InstrumentTerms,
) -> ForwardOrder:
    for value, name in (
        (order_id, "order_id"),
        (market_class_id, "market_class_id"),
        (seller_id, "seller_id"),
        (jurisdiction, "jurisdiction"),
        (legal_review_id, "legal_review_id"),
        (legal_policy_version, "legal_policy_version"),
    ):
        if not value:
            raise InstrumentError(f"{name} is required")
    if size_mtok not in SIZES_MTOK:
        raise InstrumentError(f"size_mtok must be one of {SIZES_MTOK}")
    _positive_int(price_micros_per_mtok, "price_micros_per_mtok")
    policy = validate_instrument(terms)
    if policy.status != "allowed":
        raise InstrumentError(f"unsupported instrument: {policy.reason}")
    try:
        validate_bucket_start(bucket_start, bucket_hours, now=now)
    except BucketError as exc:
        raise InstrumentError(str(exc)) from exc
    if posted_at.tzinfo is None or legal_valid_until.tzinfo is None:
        raise InstrumentError("order timestamps must be timezone-aware")
    if posted_at > now:
        raise InstrumentError("posted_at cannot be in the future")
    if legal_valid_until <= now:
        raise InstrumentError("legal review must be current")
    if collateral_receipt_id == "":
        raise InstrumentError("collateral receipt must be non-empty or absent")
    return ForwardOrder(
        order_id=order_id,
        market_class_id=market_class_id,
        seller_id=seller_id,
        buyer_id=None,
        bucket_start=bucket_start,
        bucket_hours=bucket_hours,
        size_mtok=size_mtok,
        price_micros_per_mtok=price_micros_per_mtok,
        posted_at=posted_at,
        jurisdiction=jurisdiction,
        legal_review_id=legal_review_id,
        legal_policy_version=legal_policy_version,
        legal_valid_until=legal_valid_until,
        collateral_receipt_id=collateral_receipt_id,
        terms=terms,
        state="posted",
        version=1,
    )


def bind_forward_collateral(
    order: ForwardOrder,
    *,
    collateral_receipt_id: str,
    actor_id: str,
) -> ForwardOrder:
    if actor_id != order.seller_id:
        raise InstrumentError("seller authority is required to bind collateral")
    if order.state != "posted":
        raise InstrumentError("collateral can bind only to a posted order")
    if not collateral_receipt_id:
        raise InstrumentError("collateral_receipt_id is required")
    if order.collateral_receipt_id is not None:
        raise InstrumentError("collateral is already bound")
    return replace(
        order,
        collateral_receipt_id=collateral_receipt_id,
        version=order.version + 1,
    )


def is_forward_order_executable(order: ForwardOrder, *, now: datetime) -> bool:
    return (
        order.state == "posted"
        and order.collateral_receipt_id is not None
        and now < order.legal_valid_until
        and validate_instrument(order.terms).status == "allowed"
    )


def transition_forward_order(
    order: ForwardOrder,
    *,
    new_state: str,
    actor_id: str,
    actor_role: str,
    now: datetime | None = None,
) -> ForwardOrder:
    edge = (order.state, new_state)
    allowed = {
        ("posted", "purchased"): "buyer",
        ("posted", "cancelled"): "seller",
        ("posted", "expired"): "system",
        ("purchased", "delivering"): "seller",
        ("delivering", "settled"): "settlement",
    }
    required_role = allowed.get(edge)
    if required_role is None:
        raise InstrumentError(
            f"illegal transition {order.state!r} -> {new_state!r}"
        )
    if new_state == "purchased" and (
        now is None or not is_forward_order_executable(order, now=now)
    ):
        raise InstrumentError("forward order is not executable")
    if actor_role != required_role:
        raise InstrumentError(f"{required_role} authority is required")
    if required_role == "seller" and actor_id != order.seller_id:
        raise InstrumentError("seller authority is required")
    if required_role == "buyer" and (not actor_id or actor_id == order.seller_id):
        raise InstrumentError("buyer authority is required")
    if required_role in {"system", "settlement"} and not actor_id:
        raise InstrumentError(f"{required_role} authority is required")
    return replace(
        order,
        state=new_state,
        buyer_id=actor_id if new_state == "purchased" else order.buyer_id,
        version=order.version + 1,
    )


def best_forward_ask(
    orders: Sequence[ForwardOrder],
    *,
    market_class_id: str,
    bucket_start: datetime,
    bucket_hours: int,
    size_mtok: int,
    now: datetime,
) -> ForwardAsk | None:
    eligible = [
        order
        for order in orders
        if order.market_class_id == market_class_id
        and order.bucket_start == bucket_start
        and order.bucket_hours == bucket_hours
        and order.size_mtok == size_mtok
        and is_forward_order_executable(order, now=now)
    ]
    if not eligible:
        return None
    best = min(
        eligible,
        key=lambda order: (order.price_micros_per_mtok, order.order_id),
    )
    return ForwardAsk(
        order_id=best.order_id,
        price_micros_per_mtok=best.price_micros_per_mtok,
        observed_at=best.posted_at,
    )


def _positive_int(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InstrumentError(f"{name} must be a positive integer")
