from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from tinyassets.paid_market.routing import (
    EvaluationRetention,
    RouteCandidate,
    RouteRequest,
    RoutingError,
    can_delete_receipt,
    can_read_receipt,
    create_evaluation_receipt,
    project_public_evaluation,
    rank_routes,
    replay_receipt,
)


def _candidate(
    quote_id: str,
    *,
    path: str = "paid",
    total: int = 100,
    fee: int = 1,
    authority_class: str = "native_firm",
    requester_owned_authority: bool = False,
    facts: frozenset[str] = frozenset({"privacy:private", "region:us"}),
    attributes: tuple[tuple[str, int], ...] = (
        ("latency_score", 90),
        ("reliability_score", 95),
    ),
    expires_at: int = 200,
    fee_version: str = "fee-v1",
    currency: str = "tiny",
    eligible: bool = True,
) -> RouteCandidate:
    return RouteCandidate(
        quote_id=quote_id,
        quote_version=1,
        descriptor_id="sha256:descriptor",
        market_class_id="sha256:market",
        path=path,
        authority_class=authority_class,
        requester_owned_authority=requester_owned_authority,
        total_micros=total,
        fee_micros=fee,
        currency=currency,
        fee_schedule_version=fee_version,
        observed_at=100,
        expires_at=expires_at,
        eligibility_current=eligible,
        eligibility_facts=facts,
        hard_attributes=(
            ("model", "model-a"),
            ("privacy", "private"),
            ("region", "us"),
        ),
        service_attributes=attributes,
    )


def _request(
    fulfillment: str,
    *,
    price_cap: int = 1_000,
    spend_cap_remaining: int = 1_000,
) -> RouteRequest:
    return RouteRequest(
        fulfillment=fulfillment,
        settlement_currency="tiny",
        canonical_fee_version="fee-v1",
        now=150,
        price_cap_micros=price_cap,
        spend_cap_remaining_micros=spend_cap_remaining,
        required_eligibility=frozenset({"privacy:private", "region:us"}),
        hard_constraints=(
            ("model", "model-a"),
            ("privacy", "private"),
            ("region", "us"),
        ),
        objective_version="cost-then-service-v1",
        service_weights=(("latency_score", 2), ("reliability_score", 1)),
        top_line_reference_micros=120,
    )


def test_free_mandate_never_silently_selects_paid_or_byoc() -> None:
    decision = rank_routes(
        _request("free"),
        [
            _candidate("paid"),
            _candidate(
                "byoc",
                path="byoc",
                fee=0,
                authority_class="requester_owned",
                requester_owned_authority=True,
            ),
        ],
    )

    assert decision.status == "pending"
    assert decision.selected is None
    assert {item.reason_codes for item in decision.candidates} == {
        ("fulfillment_not_authorized",)
    }
    assert decision.locks_money is False
    assert decision.reserves_capacity is False
    assert decision.authorizes_provider is False
    assert decision.authorizes_execution is False
    assert decision.accepts_delivery is False
    assert decision.settles is False


def test_byoc_requires_requester_owned_authority_and_never_creates_market_fee() -> None:
    decision = rank_routes(
        _request("byoc"),
        [
            _candidate(
                "connected",
                path="byoc",
                total=80,
                fee=0,
                authority_class="requester_owned",
                requester_owned_authority=True,
            ),
            _candidate("paid", total=70),
        ],
    )

    assert decision.status == "selected"
    assert decision.selected is not None
    assert decision.selected.quote_id == "connected"
    assert decision.selected.fee_micros == 0
    assert next(
        item for item in decision.candidates if item.quote_id == "paid"
    ).reason_codes == ("fulfillment_not_authorized",)
    assert decision.locks_money is False


def test_paid_routing_uses_cheapest_adequate_total_and_requires_fee() -> None:
    decision = rank_routes(
        _request("paid"),
        [
            _candidate("expensive", total=110, fee=2),
            _candidate("cheap", total=90, fee=1),
            _candidate(
                "reference-only",
                path="reference",
                total=50,
                fee=0,
                authority_class="indicative",
            ),
        ],
    )

    assert decision.status == "selected"
    assert decision.selected is not None
    assert decision.selected.quote_id == "cheap"
    assert decision.selected.total_micros == 90
    assert decision.top_line_reference_micros == 120
    assert decision.selected_below_top_line is True
    assert next(
        item for item in decision.candidates if item.quote_id == "reference-only"
    ).reason_codes == ("fulfillment_not_authorized",)

    with pytest.raises(RoutingError, match="canonical fee"):
        rank_routes(_request("paid"), [_candidate("zero-fee", fee=0)])


@pytest.mark.parametrize(
    ("candidate", "route_request", "reason"),
    [
        (
            _candidate("stale", expires_at=150),
            _request("paid"),
            "expired",
        ),
        (
            _candidate("fee-drift", fee_version="fee-v2"),
            _request("paid"),
            "fee_version_mismatch",
        ),
        (
            _candidate("currency", currency="usd"),
            _request("paid"),
            "currency_mismatch",
        ),
        (
            _candidate("ineligible", eligible=False),
            _request("paid"),
            "eligibility_revoked",
        ),
        (
            _candidate("missing-fact", facts=frozenset({"region:us"})),
            _request("paid"),
            "missing_eligibility:privacy:private",
        ),
        (
            replace(
                _candidate("hard-mismatch"),
                hard_attributes=(
                    ("model", "model-b"),
                    ("privacy", "private"),
                    ("region", "us"),
                ),
            ),
            _request("paid"),
            "hard_constraint:model",
        ),
        (
            _candidate("price-cap", total=101),
            _request("paid", price_cap=100),
            "price_cap_exceeded",
        ),
        (
            _candidate("spend-cap", total=101),
            _request("paid", spend_cap_remaining=100),
            "spend_cap_exceeded",
        ),
        (
            _candidate(
                "byoc-no-authority",
                path="byoc",
                fee=0,
                authority_class="requester_owned",
                requester_owned_authority=False,
            ),
            _request("byoc"),
            "requester_authority_missing",
        ),
    ],
)
def test_every_material_rejection_reason_is_recorded(
    candidate: RouteCandidate, route_request: RouteRequest, reason: str
) -> None:
    decision = rank_routes(route_request, [candidate])

    assert decision.status == "no_route"
    assert decision.selected is None
    assert reason in decision.candidates[0].reason_codes


def test_service_attributes_are_explicit_tie_breaks_not_hidden_money() -> None:
    low_service = _candidate(
        "a-low-service",
        total=100,
        attributes=(("latency_score", 20), ("reliability_score", 20)),
    )
    high_service = _candidate(
        "z-high-service",
        total=100,
        attributes=(("latency_score", 90), ("reliability_score", 95)),
    )

    decision = rank_routes(_request("paid"), [low_service, high_service])

    assert decision.selected is not None
    assert decision.selected.quote_id == "z-high-service"
    scores = {item.quote_id: item.service_score for item in decision.candidates}
    assert scores["z-high-service"] > scores["a-low-service"]

    exact_tie = rank_routes(
        _request("paid"),
        [_candidate("b"), _candidate("a")],
    )
    assert exact_tie.selected is not None
    assert exact_tie.selected.quote_id == "a"


def test_ranking_is_immutable_and_grants_no_downstream_authority() -> None:
    candidates = [_candidate("one"), _candidate("two", total=120)]
    before = tuple(candidates)
    decision = rank_routes(_request("paid"), candidates)

    assert tuple(candidates) == before
    assert all(
        getattr(decision, name) is False
        for name in (
            "locks_money",
            "reserves_capacity",
            "authorizes_provider",
            "authorizes_execution",
            "accepts_delivery",
            "settles",
        )
    )
    assert not hasattr(decision, "credential")
    assert not hasattr(decision, "lease")
    assert not hasattr(decision, "invoice")


def test_private_receipt_uses_non_enumerable_tenant_keyed_commitments() -> None:
    decision = rank_routes(
        _request("paid"),
        [_candidate("winner", total=90), _candidate("loser", total=100)],
    )
    retention = EvaluationRetention(
        retain_until=1_000,
        legal_hold=False,
        deletion_allowed=True,
        export_allowed=True,
    )

    receipt = create_evaluation_receipt(
        decision,
        tenant_id="tenant-a",
        universe_id="universe-a",
        tenant_key=b"tenant-secret",
        receipt_nonce="opaque-random-nonce",
        descriptor_material=b"private descriptor request",
        policy_material=b"private routing policy",
        created_at=150,
        retention=retention,
    )
    other_tenant_key = create_evaluation_receipt(
        decision,
        tenant_id="tenant-a",
        universe_id="universe-a",
        tenant_key=b"other-tenant-secret",
        receipt_nonce="opaque-random-nonce",
        descriptor_material=b"private descriptor request",
        policy_material=b"private routing policy",
        created_at=150,
        retention=retention,
    )

    serialized = repr(asdict(receipt))
    assert receipt.receipt_id.startswith("receipt_")
    assert receipt.descriptor_commitment.startswith("hmac-sha256:")
    assert receipt.policy_commitment.startswith("hmac-sha256:")
    assert receipt.receipt_id != other_tenant_key.receipt_id
    assert "private descriptor request" not in serialized
    assert "private routing policy" not in serialized
    assert "tenant-secret" not in serialized
    assert can_read_receipt(receipt, tenant_id="tenant-a", role="owner")
    assert can_read_receipt(receipt, tenant_id="tenant-a", role="admin")
    assert can_read_receipt(receipt, tenant_id="tenant-a", role="auditor")
    assert not can_read_receipt(receipt, tenant_id="tenant-b", role="owner")
    assert not can_read_receipt(receipt, tenant_id="tenant-a", role="viewer")


def test_receipt_replay_and_public_projection_preserve_only_required_evidence() -> None:
    decision = rank_routes(
        _request("paid"),
        [_candidate("winner", total=90), _candidate("rejected", total=2_000)],
    )
    receipt = create_evaluation_receipt(
        decision,
        tenant_id="tenant-a",
        universe_id="universe-a",
        tenant_key=b"tenant-secret",
        receipt_nonce="nonce",
        descriptor_material=b"descriptor",
        policy_material=b"policy",
        created_at=150,
        retention=EvaluationRetention(
            retain_until=1_000,
            legal_hold=False,
            deletion_allowed=True,
            export_allowed=True,
        ),
    )

    replay = replay_receipt(receipt)
    public = project_public_evaluation(receipt)

    assert replay.selected_quote_id == "winner"
    assert replay.candidates == receipt.candidates
    assert public.market_class_id == "sha256:market"
    assert public.selected_total_micros == 90
    assert public.candidate_count == 2
    assert public.eligible_count == 1
    assert public.top_line_reference_micros == 120
    assert not hasattr(public, "tenant_id")
    assert not hasattr(public, "receipt_id")
    assert not hasattr(public, "selected_quote_id")
    assert not hasattr(public, "candidate_quote_ids")


def test_retention_and_legal_hold_fail_closed() -> None:
    decision = rank_routes(_request("paid"), [_candidate("winner")])
    receipt = create_evaluation_receipt(
        decision,
        tenant_id="tenant-a",
        universe_id="universe-a",
        tenant_key=b"tenant-secret",
        receipt_nonce="nonce",
        descriptor_material=b"descriptor",
        policy_material=b"policy",
        created_at=150,
        retention=EvaluationRetention(
            retain_until=200,
            legal_hold=False,
            deletion_allowed=True,
            export_allowed=False,
        ),
    )

    assert can_delete_receipt(receipt, now=199) is False
    assert can_delete_receipt(receipt, now=200) is True
    assert (
        can_delete_receipt(
            replace(
                receipt,
                retention=replace(receipt.retention, legal_hold=True),
            ),
            now=200,
        )
        is False
    )
