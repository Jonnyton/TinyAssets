from __future__ import annotations

import threading

from tinyassets.paid_market.match import best_execution
from tinyassets.payments.market_workflow import (
    Applied,
    CancelRequestCommand,
    ClaimMatchCommand,
    Conflict,
    Contention,
    InMemoryMarketRequestStore,
    InsufficientSupply,
    MarketWorkflow,
    MatchAndClaimCommand,
    OpenBiddingCommand,
    PlaceBidCommand,
    RecordMatchCommand,
    SubmitRequestCommand,
    VerifiedWorkflowAuthority,
)


def _authority(subject_id: str):
    return VerifiedWorkflowAuthority(subject_id=subject_id, tenant_id="tenant-a")


def _workflow_with_book(
    offers: tuple[tuple[str, int, int], ...],
    *,
    fanout_limit: int = 4,
    store: InMemoryMarketRequestStore | None = None,
    request_key: str = "request",
    capacity_grant_id: str | None = None,
    shared_owner: bool = True,
):
    store = store or InMemoryMarketRequestStore()
    workflow = MarketWorkflow(store)
    submitted = workflow.submit(
        SubmitRequestCommand(
            idempotency_key=request_key,
            authority=_authority("buyer"),
            requester_user_id="buyer",
            capability_digest="cap:v1",
            payload_sha256="a" * 64,
            budget_micros=1_000_000,
            spend_cap_micros=1_000_000,
            bid_window_ends_at=2_000_000_000,
            deadline=2_000_003_600,
            acceptance_policy="machine_gate_only:v1",
            settlement_policy_version="spot:v1",
            visibility="paid",
            fanout_limit=fanout_limit,
        )
    )
    assert isinstance(submitted, Applied)
    opened = workflow.open_bidding(
        OpenBiddingCommand(
            idempotency_key=f"{request_key}:open",
            request_id=submitted.request.request_id,
            expected_version=1,
            authority=_authority("buyer"),
        )
    )
    assert isinstance(opened, Applied)
    for index, (bid_id, size_mtok, price) in enumerate(offers):
        owner_id = "seller" if shared_owner else f"seller-{bid_id}"
        placed = workflow.place_bid(
            PlaceBidCommand(
                idempotency_key=f"{request_key}:place:{bid_id}",
                authority=_authority(owner_id),
                request_id=opened.request.request_id,
                expected_request_version=2,
                bid_id=bid_id,
                bid_version=1,
                host_id=f"host-{bid_id}",
                host_owner_user_id=owner_id,
                capability_digest="cap:v1",
                size_mtok=size_mtok,
                price_micros_per_mtok=price,
                expires_at=2_000_000_000,
                capacity_grant_id=capacity_grant_id or f"capacity-{bid_id}",
                capacity_fence=index + 1,
            ),
            now=1_900_000_000,
        )
        assert isinstance(placed, Applied)
    return workflow, store, opened.request


def _record_match(workflow, request, *, key="match", need_mtok=10):
    result = workflow.record_match(
        RecordMatchCommand(
            idempotency_key=key,
            authority=_authority("buyer"),
            request_id=request.request_id,
            expected_request_version=2,
            need_mtok=need_mtok,
            matcher_version="best_execution:v1",
        ),
        now=1_900_000_001,
    )
    assert isinstance(result, Applied)
    assert result.match is not None
    return result.match


def test_single_and_multi_bid_claims_consume_exact_match_in_canonical_lock_order():
    workflow, store, request = _workflow_with_book(
        (
            ("bid-z", 10, 10),
            ("bid-b", 1, 2),
            ("bid-a", 10, 20),
        )
    )
    match = _record_match(workflow, request, need_mtok=11)
    snapshot = store.eligible_bids(request.request_id, now=1_900_000_001)
    assert best_execution([bid.as_book_offer() for bid in snapshot], 11) == (
        102,
        ["bid-b", "bid-z"],
    )

    result = workflow.claim_match(
        ClaimMatchCommand(
            idempotency_key="claim",
            authority=_authority("seller"),
            request_id=request.request_id,
            expected_request_version=2,
            match_id=match.match_id,
        ),
        now=1_900_000_002,
    )

    assert isinstance(result, Applied)
    assert result.claim is not None
    assert result.request.state == "claimed"
    assert result.claim.selected_bid_versions == (("bid-b", 1), ("bid-z", 1))
    assert tuple(slot.slot_index for slot in result.claim.slots) == (0, 1)
    assert store.last_claim_lock_order() == (
        f"request:{request.request_id}",
        "slot:0",
        "slot:1",
        "bid:bid-b",
        "bid:bid-z",
    )
    assert [(bid.bid_id, bid.state) for bid in store.claimed_bids(match.match_id)] == [
        ("bid-b", "claimed"),
        ("bid-z", "claimed"),
    ]


def test_requester_cannot_claim_a_selected_hosts_match():
    workflow, _store, request = _workflow_with_book((("bid-a", 10, 5),))
    match = _record_match(workflow, request)

    denied = workflow.claim_match(
        ClaimMatchCommand(
            idempotency_key="buyer-claim",
            authority=_authority("buyer"),
            request_id=request.request_id,
            expected_request_version=2,
            match_id=match.match_id,
        ),
        now=1_900_000_002,
    )

    assert isinstance(denied, Conflict)
    assert denied.reason == "selected_host_authority_required"


def test_one_selected_host_cannot_claim_another_owners_bid():
    workflow, _store, request = _workflow_with_book(
        (("bid-a", 10, 10), ("bid-b", 1, 2)),
        shared_owner=False,
    )
    match = _record_match(workflow, request, need_mtok=11)

    denied = workflow.claim_match(
        ClaimMatchCommand(
            idempotency_key="cross-owner-claim",
            authority=_authority("seller-bid-a"),
            request_id=request.request_id,
            expected_request_version=2,
            match_id=match.match_id,
        ),
        now=1_900_000_002,
    )

    assert isinstance(denied, Conflict)
    assert denied.reason == "independent_host_claims_required"


def test_stale_selected_bid_rejects_every_selected_bid_atomically():
    workflow, store, request = _workflow_with_book(
        (("bid-a", 10, 10), ("bid-b", 10, 11))
    )
    match = _record_match(workflow, request)
    current = store.bid_history("bid-a")[-1]
    replacement = workflow.place_bid(
        PlaceBidCommand(
            idempotency_key="replace-a",
            authority=_authority("seller"),
            request_id=request.request_id,
            expected_request_version=2,
            bid_id="bid-a",
            bid_version=2,
            host_id=current.host_id,
            host_owner_user_id=current.host_owner_user_id,
            capability_digest=current.capability_digest,
            size_mtok=current.size_mtok,
            price_micros_per_mtok=9,
            expires_at=current.expires_at,
            capacity_grant_id=current.capacity_grant_id,
            capacity_fence=current.capacity_fence + 1,
        ),
        now=1_900_000_002,
    )
    assert isinstance(replacement, Applied)

    result = workflow.claim_match(
        ClaimMatchCommand(
            idempotency_key="stale-claim",
            authority=_authority("seller"),
            request_id=request.request_id,
            expected_request_version=2,
            match_id=match.match_id,
        ),
        now=1_900_000_003,
    )

    assert isinstance(result, Contention)
    assert result.reason == "selected_bid_version_stale"
    assert store.get(request.request_id).state == "bidding"
    assert store.claimed_bids(match.match_id) == ()


def test_insufficient_supply_is_honest_and_creates_no_match_or_claim():
    workflow, store, request = _workflow_with_book((("bid-a", 1, 5),))
    result = workflow.match_and_claim(
        MatchAndClaimCommand(
            idempotency_key="short",
            authority=_authority("seller"),
            request_id=request.request_id,
            expected_request_version=2,
            need_mtok=10,
            matcher_version="best_execution:v1",
        ),
        now=1_900_000_002,
    )
    assert isinstance(result, InsufficientSupply)
    assert store.get(request.request_id).state == "bidding"
    assert store.matches_for_request(request.request_id) == ()


def test_match_and_claim_retries_at_most_three_times_with_jitter():
    class AlwaysContendedStore(InMemoryMarketRequestStore):
        def __init__(self):
            super().__init__()
            self.claim_attempts = 0

        def claim_match(self, command, *, now):
            self.claim_attempts += 1
            return Contention("selected_bid_version_stale")

    store = AlwaysContendedStore()
    workflow, _, request = _workflow_with_book((("bid-a", 10, 5),), store=store)
    delays = []
    result = workflow.match_and_claim(
        MatchAndClaimCommand(
            idempotency_key="bounded",
            authority=_authority("buyer"),
            request_id=request.request_id,
            expected_request_version=2,
            need_mtok=10,
            matcher_version="best_execution:v1",
        ),
        now=1_900_000_002,
        jitter=lambda attempt: delays.append(attempt),
    )

    assert isinstance(result, Contention)
    assert result.reason == "retry_budget_exhausted"
    assert store.claim_attempts == 3
    assert delays == [1, 2]


def test_cancellation_and_claim_race_has_one_winner():
    workflow, store, request = _workflow_with_book((("bid-a", 10, 5),))
    match = _record_match(workflow, request)
    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def cancel():
        barrier.wait()
        result = workflow.cancel(
            CancelRequestCommand(
                idempotency_key="cancel-race",
                request_id=request.request_id,
                expected_version=2,
                authority=_authority("seller"),
            )
        )
        with lock:
            outcomes.append(result)

    def claim():
        barrier.wait()
        result = workflow.claim_match(
            ClaimMatchCommand(
                idempotency_key="claim-race",
                authority=_authority("seller"),
                request_id=request.request_id,
                expected_request_version=2,
                match_id=match.match_id,
            ),
            now=1_900_000_002,
        )
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=cancel), threading.Thread(target=claim)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sum(isinstance(outcome, Applied) for outcome in outcomes) == 1
    assert store.get(request.request_id).state in {"cancelled", "claimed"}
    assert len(store.history(request.request_id)) == 3


def test_one_hundred_concurrent_claims_never_double_sell_capacity():
    workflow, store, request = _workflow_with_book(
        (("bid-a", 10, 5), ("bid-b", 10, 6))
    )
    match = _record_match(workflow, request)
    snapshot = store.eligible_bids(request.request_id, now=1_900_000_001)
    oracle = best_execution([bid.as_book_offer() for bid in snapshot], 10)
    barrier = threading.Barrier(100)
    outcomes = []
    lock = threading.Lock()

    def claim(index):
        barrier.wait()
        result = workflow.claim_match(
            ClaimMatchCommand(
                idempotency_key=f"claim-{index}",
                authority=_authority("seller"),
                request_id=request.request_id,
                expected_request_version=2,
                match_id=match.match_id,
            ),
            now=1_900_000_002,
        )
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=claim, args=(index,)) for index in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    winners = [result for result in outcomes if isinstance(result, Applied)]
    assert len(winners) == 1
    assert winners[0].claim is not None
    assert [bid_id for bid_id, _ in winners[0].claim.selected_bid_versions] == oracle[1]
    assert store.capacity_consumptions("capacity-bid-a") == 1
    assert store.capacity_consumptions("capacity-bid-b") == 0
    assert len(store.claimed_bids(match.match_id)) == 1


def test_one_capacity_grant_cannot_sell_across_two_requests():
    store = InMemoryMarketRequestStore()
    workflow_a, _, request_a = _workflow_with_book(
        (("bid-a", 10, 5),),
        store=store,
        request_key="request-a",
        capacity_grant_id="shared-capacity",
    )
    workflow_b, _, request_b = _workflow_with_book(
        (("bid-b", 10, 5),),
        store=store,
        request_key="request-b",
        capacity_grant_id="shared-capacity",
    )
    match_a = _record_match(workflow_a, request_a, key="match-a")
    match_b = _record_match(workflow_b, request_b, key="match-b")
    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def claim(workflow, request, match, key):
        barrier.wait()
        result = workflow.claim_match(
            ClaimMatchCommand(
                idempotency_key=key,
                authority=_authority("seller"),
                request_id=request.request_id,
                expected_request_version=2,
                match_id=match.match_id,
            ),
            now=1_900_000_002,
        )
        with lock:
            outcomes.append(result)

    threads = [
        threading.Thread(
            target=claim,
            args=(workflow_a, request_a, match_a, "claim-a"),
        ),
        threading.Thread(
            target=claim,
            args=(workflow_b, request_b, match_b, "claim-b"),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sum(isinstance(outcome, Applied) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, Contention) for outcome in outcomes) == 1
    assert store.capacity_consumptions("shared-capacity") == 1
