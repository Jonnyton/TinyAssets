"""Pure mandate-scoped economic routing and privacy-minimal receipts."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Sequence


class RoutingError(ValueError):
    """Routing input is malformed or attempts to bypass market policy."""


@dataclass(frozen=True)
class RouteCandidate:
    quote_id: str
    quote_version: int
    descriptor_id: str
    market_class_id: str
    path: str
    authority_class: str
    requester_owned_authority: bool
    total_micros: int
    fee_micros: int
    currency: str
    fee_schedule_version: str
    observed_at: int
    expires_at: int
    eligibility_current: bool
    eligibility_facts: frozenset[str]
    hard_attributes: tuple[tuple[str, str], ...]
    service_attributes: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class RouteRequest:
    fulfillment: str
    settlement_currency: str
    canonical_fee_version: str
    now: int
    price_cap_micros: int
    spend_cap_remaining_micros: int
    required_eligibility: frozenset[str]
    hard_constraints: tuple[tuple[str, str], ...]
    objective_version: str
    service_weights: tuple[tuple[str, int], ...]
    top_line_reference_micros: int | None


@dataclass(frozen=True)
class CandidateEvaluation:
    quote_id: str
    quote_version: int
    market_class_id: str
    total_micros: int
    currency: str
    observed_at: int
    expires_at: int
    eligible: bool
    reason_codes: tuple[str, ...]
    service_score: int


@dataclass(frozen=True)
class RouteDecision:
    status: str
    fulfillment: str
    selected: RouteCandidate | None
    candidates: tuple[CandidateEvaluation, ...]
    objective_version: str
    service_weights: tuple[tuple[str, int], ...]
    top_line_reference_micros: int | None
    selected_below_top_line: bool | None
    locks_money: bool = False
    reserves_capacity: bool = False
    authorizes_provider: bool = False
    authorizes_execution: bool = False
    accepts_delivery: bool = False
    settles: bool = False


@dataclass(frozen=True)
class EvaluationRetention:
    retain_until: int
    legal_hold: bool
    deletion_allowed: bool
    export_allowed: bool


@dataclass(frozen=True)
class EvaluationReceipt:
    receipt_id: str
    tenant_id: str
    universe_id: str
    descriptor_commitment: str
    policy_commitment: str
    objective_version: str
    service_weights: tuple[tuple[str, int], ...]
    candidates: tuple[CandidateEvaluation, ...]
    selected_quote_id: str | None
    top_line_reference_micros: int | None
    decision_digest: str
    created_at: int
    retention: EvaluationRetention
    allowed_roles: frozenset[str]


@dataclass(frozen=True)
class ReceiptReplay:
    selected_quote_id: str | None
    candidates: tuple[CandidateEvaluation, ...]
    decision_digest: str


@dataclass(frozen=True)
class PublicEvaluation:
    market_class_id: str | None
    selected_total_micros: int | None
    currency: str | None
    candidate_count: int
    eligible_count: int
    top_line_reference_micros: int | None
    caveat: str


def rank_routes(
    request: RouteRequest, candidates: Sequence[RouteCandidate]
) -> RouteDecision:
    _validate_request(request)
    evaluations: list[CandidateEvaluation] = []
    eligible: list[tuple[RouteCandidate, int]] = []
    for candidate in candidates:
        _validate_candidate(candidate)
        reasons = _rejection_reasons(request, candidate)
        service_score = _service_score(request, candidate)
        evaluation = CandidateEvaluation(
            quote_id=candidate.quote_id,
            quote_version=candidate.quote_version,
            market_class_id=candidate.market_class_id,
            total_micros=candidate.total_micros,
            currency=candidate.currency,
            observed_at=candidate.observed_at,
            expires_at=candidate.expires_at,
            eligible=not reasons,
            reason_codes=tuple(reasons),
            service_score=service_score,
        )
        evaluations.append(evaluation)
        if not reasons:
            eligible.append((candidate, service_score))

    selected: RouteCandidate | None = None
    if request.fulfillment != "free" and eligible:
        selected = min(
            eligible,
            key=lambda item: (
                item[0].total_micros,
                -item[1],
                item[0].quote_id,
            ),
        )[0]
    status = (
        "pending"
        if request.fulfillment == "free"
        else "selected"
        if selected is not None
        else "no_route"
    )
    below_reference = (
        None
        if selected is None or request.top_line_reference_micros is None
        else selected.total_micros <= request.top_line_reference_micros
    )
    return RouteDecision(
        status=status,
        fulfillment=request.fulfillment,
        selected=selected,
        candidates=tuple(evaluations),
        objective_version=request.objective_version,
        service_weights=request.service_weights,
        top_line_reference_micros=request.top_line_reference_micros,
        selected_below_top_line=below_reference,
    )


def create_evaluation_receipt(
    decision: RouteDecision,
    *,
    tenant_id: str,
    universe_id: str,
    tenant_key: bytes,
    receipt_nonce: str,
    descriptor_material: bytes,
    policy_material: bytes,
    created_at: int,
    retention: EvaluationRetention,
) -> EvaluationReceipt:
    if not tenant_id or not universe_id or not receipt_nonce or not tenant_key:
        raise RoutingError("tenant, universe, nonce, and tenant key are required")
    if not descriptor_material or not policy_material:
        raise RoutingError("receipt commitments require non-empty material")
    _nonnegative_int(created_at, "created_at")
    _nonnegative_int(retention.retain_until, "retain_until")
    if retention.retain_until < created_at:
        raise RoutingError("retention cannot expire before receipt creation")

    receipt_id = "receipt_" + _hmac_hex(
        tenant_key,
        b"receipt-id\0"
        + tenant_id.encode()
        + b"\0"
        + universe_id.encode()
        + b"\0"
        + receipt_nonce.encode(),
    )
    descriptor_commitment = "hmac-sha256:" + _hmac_hex(
        tenant_key, b"descriptor\0" + descriptor_material
    )
    policy_commitment = "hmac-sha256:" + _hmac_hex(
        tenant_key, b"policy\0" + policy_material
    )
    selected_quote_id = (
        decision.selected.quote_id if decision.selected is not None else None
    )
    digest_body = {
        "candidates": [
            {
                "currency": item.currency,
                "eligible": item.eligible,
                "expires_at": item.expires_at,
                "market_class_id": item.market_class_id,
                "observed_at": item.observed_at,
                "quote_id": item.quote_id,
                "quote_version": item.quote_version,
                "reason_codes": list(item.reason_codes),
                "service_score": item.service_score,
                "total_micros": item.total_micros,
            }
            for item in decision.candidates
        ],
        "fulfillment": decision.fulfillment,
        "objective_version": decision.objective_version,
        "selected_quote_id": selected_quote_id,
        "service_weights": [list(item) for item in decision.service_weights],
        "top_line_reference_micros": decision.top_line_reference_micros,
    }
    canonical = json.dumps(
        digest_body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return EvaluationReceipt(
        receipt_id=receipt_id,
        tenant_id=tenant_id,
        universe_id=universe_id,
        descriptor_commitment=descriptor_commitment,
        policy_commitment=policy_commitment,
        objective_version=decision.objective_version,
        service_weights=decision.service_weights,
        candidates=decision.candidates,
        selected_quote_id=selected_quote_id,
        top_line_reference_micros=decision.top_line_reference_micros,
        decision_digest="sha256:" + hashlib.sha256(canonical).hexdigest(),
        created_at=created_at,
        retention=retention,
        allowed_roles=frozenset({"owner", "admin", "auditor"}),
    )


def can_read_receipt(
    receipt: EvaluationReceipt, *, tenant_id: str, role: str
) -> bool:
    return tenant_id == receipt.tenant_id and role in receipt.allowed_roles


def can_delete_receipt(receipt: EvaluationReceipt, *, now: int) -> bool:
    return (
        receipt.retention.deletion_allowed
        and not receipt.retention.legal_hold
        and now >= receipt.retention.retain_until
    )


def replay_receipt(receipt: EvaluationReceipt) -> ReceiptReplay:
    return ReceiptReplay(
        selected_quote_id=receipt.selected_quote_id,
        candidates=receipt.candidates,
        decision_digest=receipt.decision_digest,
    )


def project_public_evaluation(receipt: EvaluationReceipt) -> PublicEvaluation:
    selected = next(
        (
            candidate
            for candidate in receipt.candidates
            if candidate.quote_id == receipt.selected_quote_id
        ),
        None,
    )
    market_class_id = (
        selected.market_class_id
        if selected is not None
        else receipt.candidates[0].market_class_id
        if receipt.candidates
        else None
    )
    return PublicEvaluation(
        market_class_id=market_class_id,
        selected_total_micros=selected.total_micros if selected else None,
        currency=selected.currency if selected else None,
        candidate_count=len(receipt.candidates),
        eligible_count=sum(candidate.eligible for candidate in receipt.candidates),
        top_line_reference_micros=receipt.top_line_reference_micros,
        caveat=(
            "Aggregate economic evaluation only; not reservation, execution, "
            "acceptance, invoice, or settlement authority."
        ),
    )


def _rejection_reasons(
    request: RouteRequest, candidate: RouteCandidate
) -> list[str]:
    if request.fulfillment == "free" or candidate.path != request.fulfillment:
        return ["fulfillment_not_authorized"]
    reasons: list[str] = []
    if candidate.path == "byoc" and (
        candidate.authority_class != "requester_owned"
        or not candidate.requester_owned_authority
    ):
        reasons.append("requester_authority_missing")
    if candidate.path == "paid":
        if candidate.authority_class != "native_firm":
            reasons.append("firm_authority_missing")
        if candidate.fee_micros <= 0:
            raise RoutingError("every paid settlement requires the canonical fee")
    if candidate.expires_at <= request.now:
        reasons.append("expired")
    if candidate.fee_schedule_version != request.canonical_fee_version:
        reasons.append("fee_version_mismatch")
    if candidate.currency != request.settlement_currency:
        reasons.append("currency_mismatch")
    if not candidate.eligibility_current:
        reasons.append("eligibility_revoked")
    for fact in sorted(request.required_eligibility - candidate.eligibility_facts):
        reasons.append(f"missing_eligibility:{fact}")
    attributes = dict(candidate.hard_attributes)
    for name, expected in request.hard_constraints:
        if attributes.get(name) != expected:
            reasons.append(f"hard_constraint:{name}")
    if candidate.total_micros > request.price_cap_micros:
        reasons.append("price_cap_exceeded")
    if candidate.total_micros > request.spend_cap_remaining_micros:
        reasons.append("spend_cap_exceeded")
    return reasons


def _service_score(request: RouteRequest, candidate: RouteCandidate) -> int:
    attributes = dict(candidate.service_attributes)
    return sum(
        attributes.get(name, 0) * weight for name, weight in request.service_weights
    )


def _validate_request(request: RouteRequest) -> None:
    if request.fulfillment not in {"free", "byoc", "paid"}:
        raise RoutingError("unsupported fulfillment mandate")
    if (
        not request.settlement_currency
        or not request.canonical_fee_version
        or not request.objective_version
    ):
        raise RoutingError("routing versions and currency are required")
    for value, name in (
        (request.now, "now"),
        (request.price_cap_micros, "price_cap_micros"),
        (request.spend_cap_remaining_micros, "spend_cap_remaining_micros"),
    ):
        _nonnegative_int(value, name)
    _unique_pairs(request.hard_constraints, "hard constraints")
    _unique_pairs(request.service_weights, "service weights")
    if any(weight < 0 for _, weight in request.service_weights):
        raise RoutingError("service weights must be non-negative")


def _validate_candidate(candidate: RouteCandidate) -> None:
    for value, name in (
        (candidate.quote_id, "quote_id"),
        (candidate.descriptor_id, "descriptor_id"),
        (candidate.market_class_id, "market_class_id"),
        (candidate.currency, "currency"),
        (candidate.fee_schedule_version, "fee_schedule_version"),
    ):
        if not value:
            raise RoutingError(f"{name} is required")
    if candidate.path not in {"byoc", "paid", "reference"}:
        raise RoutingError("unsupported candidate path")
    for value, name, positive in (
        (candidate.quote_version, "quote_version", True),
        (candidate.total_micros, "total_micros", True),
        (candidate.fee_micros, "fee_micros", False),
        (candidate.observed_at, "observed_at", False),
        (candidate.expires_at, "expires_at", True),
    ):
        if positive:
            _positive_int(value, name)
        else:
            _nonnegative_int(value, name)
    _unique_pairs(candidate.hard_attributes, "hard attributes")
    _unique_pairs(candidate.service_attributes, "service attributes")


def _unique_pairs(values: tuple[tuple[str, object], ...], label: str) -> None:
    names = [name for name, _ in values]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise RoutingError(f"{label} must have unique non-empty names")


def _hmac_hex(key: bytes, value: bytes) -> str:
    return hmac.new(key, value, hashlib.sha256).hexdigest()


def _positive_int(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RoutingError(f"{name} must be a positive integer")


def _nonnegative_int(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RoutingError(f"{name} must be a non-negative integer")
