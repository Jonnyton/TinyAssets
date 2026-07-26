from __future__ import annotations

import pytest

from tinyassets.payments.market_workflow import (
    Applied,
    ClaimMatchCommand,
    InMemoryMarketRequestStore,
    MarketWorkflow,
    OpenBiddingCommand,
    PlaceBidCommand,
    RecordMatchCommand,
    Replayed,
    SubmitRequestCommand,
    VerifiedWorkflowAuthority,
)


class InjectedFault(RuntimeError):
    pass


class FaultController:
    def __init__(self):
        self.fail_at = None
        self.seen = []

    def checkpoint(self, name):
        self.seen.append(name)
        if name == self.fail_at:
            raise InjectedFault(name)


def _authority(subject_id: str):
    return VerifiedWorkflowAuthority(subject_id=subject_id, tenant_id="tenant-a")


def _submission():
    return SubmitRequestCommand(
        idempotency_key="request",
        authority=_authority("buyer"),
        requester_user_id="buyer",
        capability_digest="cap:v1",
        payload_sha256="a" * 64,
        budget_micros=100_000,
        spend_cap_micros=100_000,
        bid_window_ends_at=2_000_000_000,
        deadline=2_000_003_600,
        acceptance_policy="machine_gate_only:v1",
        settlement_policy_version="spot:v1",
        visibility="paid",
        fanout_limit=1,
    )


def _prepared(controller: FaultController):
    store = InMemoryMarketRequestStore(fault_injector=controller)
    workflow = MarketWorkflow(store)
    submitted = workflow.submit(_submission())
    assert isinstance(submitted, Applied)
    opened = workflow.open_bidding(
        OpenBiddingCommand(
            idempotency_key="open",
            request_id=submitted.request.request_id,
            expected_version=1,
            authority=_authority("buyer"),
        )
    )
    assert isinstance(opened, Applied)
    bid = PlaceBidCommand(
        idempotency_key="bid",
        authority=_authority("seller"),
        request_id=opened.request.request_id,
        expected_request_version=2,
        bid_id="bid-a",
        bid_version=1,
        host_id="host-a",
        host_owner_user_id="seller",
        capability_digest="cap:v1",
        size_mtok=10,
        price_micros_per_mtok=5,
        expires_at=2_000_000_000,
        capacity_grant_id="capacity-a",
        capacity_fence=1,
    )
    assert isinstance(workflow.place_bid(bid, now=1_900_000_000), Applied)
    return workflow, store, opened.request, bid


@pytest.mark.parametrize(
    "checkpoint,committed",
    [
        ("before_request_commit", False),
        ("after_database_commit", True),
    ],
)
def test_request_commit_fault_recovers_to_zero_or_one_effect(checkpoint, committed):
    controller = FaultController()
    controller.fail_at = checkpoint
    store = InMemoryMarketRequestStore(fault_injector=controller)
    workflow = MarketWorkflow(store)

    with pytest.raises(InjectedFault, match=checkpoint):
        workflow.submit(_submission())
    assert len(store.requests()) == int(committed)

    controller.fail_at = None
    recovered = workflow.submit(_submission())
    assert isinstance(recovered, Replayed if committed else Applied)
    assert len(store.requests()) == 1
    assert len(store.history(recovered.request.request_id)) == 1


@pytest.mark.parametrize(
    "checkpoint",
    [
        "before_outbox_append",
        "after_outbox_append_before_commit",
    ],
)
def test_outbox_fault_rolls_back_request_eligibility_and_retry_commits_both(checkpoint):
    controller = FaultController()
    store = InMemoryMarketRequestStore(fault_injector=controller)
    workflow = MarketWorkflow(store)
    submitted = workflow.submit(_submission())
    assert isinstance(submitted, Applied)
    command = OpenBiddingCommand(
        idempotency_key="open",
        request_id=submitted.request.request_id,
        expected_version=1,
        authority=_authority("buyer"),
    )

    controller.fail_at = checkpoint
    with pytest.raises(InjectedFault, match=checkpoint):
        workflow.open_bidding(command)
    assert store.get(submitted.request.request_id).state == "pending"
    assert store.outbox("cap:v1") == ()

    controller.fail_at = None
    recovered = workflow.open_bidding(command)
    assert isinstance(recovered, Applied)
    assert recovered.request.state == "bidding"
    assert len(store.outbox("cap:v1")) == 1


@pytest.mark.parametrize(
    "checkpoint,committed",
    [
        ("before_bid_replacement_commit", False),
        ("after_database_commit", True),
    ],
)
def test_bid_commit_fault_replays_without_duplicate_version(checkpoint, committed):
    controller = FaultController()
    workflow, store, request, original = _prepared(controller)
    replacement = PlaceBidCommand(
        **{
            **original.__dict__,
            "idempotency_key": "replace",
            "bid_version": 2,
            "price_micros_per_mtok": 4,
            "capacity_fence": 2,
        }
    )
    controller.fail_at = checkpoint
    with pytest.raises(InjectedFault, match=checkpoint):
        workflow.place_bid(replacement, now=1_900_000_001)
    assert len(store.bid_history("bid-a")) == (2 if committed else 1)

    controller.fail_at = None
    recovered = workflow.place_bid(replacement, now=1_900_000_001)
    assert isinstance(recovered, Replayed if committed else Applied)
    assert [bid.version for bid in store.bid_history("bid-a")] == [1, 2]


@pytest.mark.parametrize(
    "checkpoint,committed",
    [
        ("before_match_recording_commit", False),
        ("after_database_commit", True),
    ],
)
def test_match_commit_fault_replays_one_decision(checkpoint, committed):
    controller = FaultController()
    workflow, store, request, _ = _prepared(controller)
    command = RecordMatchCommand(
        idempotency_key="match",
        authority=_authority("buyer"),
        request_id=request.request_id,
        expected_request_version=2,
        need_mtok=10,
        matcher_version="best_execution:v1",
    )
    controller.fail_at = checkpoint
    with pytest.raises(InjectedFault, match=checkpoint):
        workflow.record_match(command, now=1_900_000_001)
    assert len(store.matches_for_request(request.request_id)) == int(committed)

    controller.fail_at = None
    recovered = workflow.record_match(command, now=1_900_000_001)
    assert isinstance(recovered, Replayed if committed else Applied)
    assert len(store.matches_for_request(request.request_id)) == 1


@pytest.mark.parametrize(
    "checkpoint,committed",
    [
        ("before_claim_cas_commit", False),
        ("after_database_commit", True),
    ],
)
def test_claim_commit_fault_replays_one_claim_and_capacity_effect(checkpoint, committed):
    controller = FaultController()
    workflow, store, request, _ = _prepared(controller)
    matched = workflow.record_match(
        RecordMatchCommand(
            idempotency_key="match",
            authority=_authority("buyer"),
            request_id=request.request_id,
            expected_request_version=2,
            need_mtok=10,
            matcher_version="best_execution:v1",
        ),
        now=1_900_000_001,
    )
    assert isinstance(matched, Applied) and matched.match is not None
    command = ClaimMatchCommand(
        idempotency_key="claim",
        authority=_authority("seller"),
        request_id=request.request_id,
        expected_request_version=2,
        match_id=matched.match.match_id,
    )

    controller.fail_at = checkpoint
    with pytest.raises(InjectedFault, match=checkpoint):
        workflow.claim_match(command, now=1_900_000_002)
    assert store.capacity_consumptions("capacity-a") == int(committed)

    controller.fail_at = None
    recovered = workflow.claim_match(command, now=1_900_000_002)
    assert isinstance(recovered, Replayed if committed else Applied)
    assert store.capacity_consumptions("capacity-a") == 1
    assert len(store.claimed_bids(matched.match.match_id)) == 1
