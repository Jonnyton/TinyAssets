from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from tinyassets.paid_market.match import BookOffer, best_execution
from tinyassets.payments.market_workflow import (
    Applied,
    BidQuoteBinding,
    CancelBidCommand,
    Conflict,
    InMemoryMarketRequestStore,
    MarketWorkflow,
    OpenBiddingCommand,
    PlaceBidCommand,
    RecordMatchCommand,
    SubmitRequestCommand,
    VerifiedWorkflowAuthority,
    VerifiedWorkflowGrant,
)


def _authority(subject_id: str, tenant_id: str = "tenant-a"):
    return VerifiedWorkflowAuthority(subject_id=subject_id, tenant_id=tenant_id)


def _open_request(
    workflow: MarketWorkflow,
    *,
    key: str = "request-1",
    capability_digest: str = "cap:gpu:v1",
):
    submitted = workflow.submit(
        SubmitRequestCommand(
            idempotency_key=key,
            authority=_authority("buyer"),
            requester_user_id="buyer",
            capability_digest=capability_digest,
            payload_sha256="a" * 64,
            budget_micros=1_000_000,
            spend_cap_micros=1_000_000,
            bid_window_ends_at=2_000_000_000,
            deadline=2_000_003_600,
            acceptance_policy="machine_gate_only:v1",
            settlement_policy_version="spot:v1",
            visibility="paid",
            fanout_limit=4,
        )
    )
    assert isinstance(submitted, Applied)
    opened = workflow.open_bidding(
        OpenBiddingCommand(
            idempotency_key=f"{key}:open",
            request_id=submitted.request.request_id,
            expected_version=1,
            authority=_authority("buyer"),
        )
    )
    assert isinstance(opened, Applied)
    return opened.request


def _bid(
    request_id: str,
    *,
    bid_id: str,
    host_id: str,
    owner_id: str,
    version: int = 1,
    size_mtok: int = 10,
    price_micros_per_mtok: int = 10,
    expires_at: int = 2_000_000_000,
    capacity_fence: int = 1,
    quote: BidQuoteBinding | None = None,
) -> PlaceBidCommand:
    return PlaceBidCommand(
        idempotency_key=f"{bid_id}:v{version}",
        authority=_authority(owner_id),
        request_id=request_id,
        expected_request_version=2,
        bid_id=bid_id,
        bid_version=version,
        host_id=host_id,
        host_owner_user_id=owner_id,
        capability_digest="cap:gpu:v1",
        size_mtok=size_mtok,
        price_micros_per_mtok=price_micros_per_mtok,
        expires_at=expires_at,
        capacity_grant_id=f"capacity:{host_id}",
        capacity_fence=capacity_fence,
        quote=quote,
    )


def test_bid_requires_host_authority_and_exact_quote_binding():
    workflow = MarketWorkflow(InMemoryMarketRequestStore())
    request = _open_request(workflow)
    quote_bytes = b'{"quote_id":"quote-1","offer_version":7}'
    quote = BidQuoteBinding(
        quote_id="quote-1",
        quote_version=7,
        quote_digest=hashlib.sha256(quote_bytes).hexdigest(),
        canonical_quote=quote_bytes,
    )
    command = _bid(
        request.request_id,
        bid_id="bid-1",
        host_id="host-1",
        owner_id="seller",
        quote=quote,
    )
    denied = workflow.place_bid(
        PlaceBidCommand(
            **{
                **command.__dict__,
                "authority": _authority("intruder"),
                "idempotency_key": "denied",
            }
        ),
        now=1_900_000_000,
    )
    assert isinstance(denied, Conflict)
    assert denied.reason == "host_authority_required"

    now = datetime.fromtimestamp(1_900_000_000, UTC)
    delegated = workflow.place_bid(
        replace(
            command,
            idempotency_key="delegated",
            authority=VerifiedWorkflowAuthority(
                subject_id="host-agent",
                tenant_id="tenant-a",
                grant=VerifiedWorkflowGrant(
                    grant_id="grant-1",
                    host_actor_id="host-agent",
                    target_actor_id="seller",
                    target_tenant_id="tenant-a",
                    allowed_actions=frozenset({"place_bid"}),
                    issued_at=now - timedelta(minutes=1),
                    expires_at=now + timedelta(minutes=1),
                    revocation_generation=0,
                    verified_signature_sha256="b" * 64,
                ),
            ),
        ),
        now=1_900_000_000,
    )
    assert isinstance(delegated, Applied)

    applied = workflow.place_bid(
        replace(command, bid_id="bid-2", idempotency_key="bid-2:v1"),
        now=1_900_000_000,
    )
    assert isinstance(applied, Applied)
    assert applied.bid is not None
    assert applied.bid.quote == quote
    assert applied.bid.as_book_offer() == BookOffer(
        offer_id="bid-2",
        size_mtok=10,
        price_micros_per_mtok=10,
    )


def test_bid_versions_are_immutable_monotonic_and_only_current_version_is_eligible():
    store = InMemoryMarketRequestStore()
    workflow = MarketWorkflow(store)
    request = _open_request(workflow)

    first = workflow.place_bid(
        _bid(
            request.request_id,
            bid_id="bid-1",
            host_id="host-1",
            owner_id="seller",
            price_micros_per_mtok=12,
        ),
        now=1_900_000_000,
    )
    replacement = workflow.place_bid(
        _bid(
            request.request_id,
            bid_id="bid-1",
            host_id="host-1",
            owner_id="seller",
            version=2,
            price_micros_per_mtok=9,
            capacity_fence=2,
        ),
        now=1_900_000_001,
    )
    stale = workflow.place_bid(
        replace(
            _bid(
            request.request_id,
            bid_id="bid-1",
            host_id="host-1",
            owner_id="seller",
            version=2,
            ),
            idempotency_key="bid-1:stale-version",
        ),
        now=1_900_000_002,
    )

    assert isinstance(first, Applied)
    assert isinstance(replacement, Applied)
    assert replacement.bid is not None and replacement.bid.version == 2
    assert isinstance(stale, Conflict)
    assert stale.reason == "bid_version_conflict"
    history = store.bid_history("bid-1")
    assert [(bid.version, bid.state) for bid in history] == [
        (1, "replaced"),
        (2, "offered"),
    ]
    assert store.eligible_bids(request.request_id, now=1_900_000_003) == (
        replacement.bid,
    )


def test_cancel_expiry_revocation_and_capacity_fence_remove_bid_eligibility():
    store = InMemoryMarketRequestStore()
    workflow = MarketWorkflow(store)
    request = _open_request(workflow)
    commands = [
        _bid(
            request.request_id,
            bid_id="cancelled",
            host_id="host-cancelled",
            owner_id="seller-cancelled",
        ),
        _bid(
            request.request_id,
            bid_id="expired",
            host_id="host-expired",
            owner_id="seller-expired",
            expires_at=1_900_000_001,
        ),
        _bid(
            request.request_id,
            bid_id="revoked",
            host_id="host-revoked",
            owner_id="seller-revoked",
        ),
        _bid(
            request.request_id,
            bid_id="fenced",
            host_id="host-fenced",
            owner_id="seller-fenced",
            capacity_fence=4,
        ),
    ]
    for command in commands:
        assert isinstance(workflow.place_bid(command, now=1_900_000_000), Applied)

    cancelled = workflow.cancel_bid(
        CancelBidCommand(
            idempotency_key="cancel-bid",
            authority=_authority("seller-cancelled"),
            request_id=request.request_id,
            bid_id="cancelled",
            expected_bid_version=1,
        ),
        now=1_900_000_002,
    )
    assert isinstance(cancelled, Applied)
    store.revoke_host("host-revoked")
    store.set_capacity_fence("capacity:host-fenced", 5)

    assert store.eligible_bids(request.request_id, now=1_900_000_002) == ()
    assert dict(store.bid_rejections(request.request_id, now=1_900_000_002)) == {
        "cancelled": "cancelled",
        "expired": "expired",
        "fenced": "capacity_fence_stale",
        "revoked": "host_revoked",
    }


def test_match_uses_exact_oracle_snapshot_tie_break_and_persists_rejections():
    store = InMemoryMarketRequestStore()
    workflow = MarketWorkflow(store)
    request = _open_request(workflow)
    for bid_id, host_id in (("bid-b", "host-b"), ("bid-a", "host-a")):
        assert isinstance(
            workflow.place_bid(
                _bid(
                    request.request_id,
                    bid_id=bid_id,
                    host_id=host_id,
                    owner_id=f"seller-{bid_id}",
                    size_mtok=10,
                    price_micros_per_mtok=5,
                ),
                now=1_900_000_000,
            ),
            Applied,
        )
    expired = _bid(
        request.request_id,
        bid_id="bid-expired",
        host_id="host-expired",
        owner_id="seller-expired",
        size_mtok=1,
        price_micros_per_mtok=1,
        expires_at=1_900_000_001,
    )
    assert isinstance(workflow.place_bid(expired, now=1_900_000_000), Applied)

    result = workflow.record_match(
        RecordMatchCommand(
            idempotency_key="match-1",
            authority=_authority("buyer"),
            request_id=request.request_id,
            expected_request_version=2,
            need_mtok=10,
            matcher_version="best_execution:v1",
        ),
        now=1_900_000_002,
    )

    assert isinstance(result, Applied)
    assert result.match is not None
    eligible = store.eligible_bids(request.request_id, now=1_900_000_002)
    oracle = best_execution([bid.as_book_offer() for bid in eligible], 10)
    assert oracle == (50, ["bid-a"])
    assert result.match.selected_bid_versions == (("bid-a", 1),)
    assert result.match.total_cost_micros == oracle[0]
    assert result.match.rejected_bids == (("bid-expired", "expired"),)
    assert store.match_decision(result.match.match_id) == result.match
