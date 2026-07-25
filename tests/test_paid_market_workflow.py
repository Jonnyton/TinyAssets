from __future__ import annotations

import dataclasses
import inspect
import threading
from datetime import UTC, datetime, timedelta

import pytest

from tinyassets.api import market as market_api
from tinyassets.payments.market_workflow import (
    Applied,
    CancelRequestCommand,
    Conflict,
    InMemoryMarketRequestStore,
    MarketWorkflow,
    OpenBiddingCommand,
    Replayed,
    SubmitRequestCommand,
    VerifiedWorkflowAuthority,
    VerifiedWorkflowGrant,
    allowed_transition,
)


def _authority(
    *,
    subject_id: str = "buyer",
    tenant_id: str = "tenant-a",
    grant: VerifiedWorkflowGrant | None = None,
) -> VerifiedWorkflowAuthority:
    return VerifiedWorkflowAuthority(
        subject_id=subject_id,
        tenant_id=tenant_id,
        grant=grant,
    )


def _submission(
    *,
    key: str = "submit-1",
    authority: VerifiedWorkflowAuthority | None = None,
    fanout_limit: int = 1,
    payload_sha256: str = "a" * 64,
) -> SubmitRequestCommand:
    return SubmitRequestCommand(
        idempotency_key=key,
        authority=authority or _authority(),
        requester_user_id="buyer",
        capability_digest="cap:v1:sha256",
        payload_sha256=payload_sha256,
        budget_micros=20_000,
        spend_cap_micros=20_000,
        bid_window_ends_at=2_000_000_000,
        deadline=2_000_003_600,
        acceptance_policy="machine_gate_only:v1",
        settlement_policy_version="spot:v1",
        visibility="paid",
        fanout_limit=fanout_limit,
    )


def test_workflow_commands_are_immutable_and_protocol_dependencies_are_injected():
    command = _submission()
    with pytest.raises(dataclasses.FrozenInstanceError):
        command.budget_micros = 1  # type: ignore[misc]

    parameters = inspect.signature(MarketWorkflow).parameters
    assert "store" in parameters
    assert "realtime_bus" in parameters
    assert "delivery_store" in parameters
    assert "ledger_rpc" in parameters


def test_identical_submission_replays_and_changed_body_conflicts():
    workflow = MarketWorkflow(InMemoryMarketRequestStore())
    first = workflow.submit(_submission())
    replay = workflow.submit(_submission())
    conflict = workflow.submit(_submission(payload_sha256="b" * 64))

    assert isinstance(first, Applied)
    assert isinstance(replay, Replayed)
    assert replay.request == first.request
    assert isinstance(conflict, Conflict)
    assert conflict.reason == "idempotency_body_conflict"
    assert workflow.store.requests() == (first.request,)
    assert [event.new_state for event in workflow.store.history(first.request.request_id)] == [
        "pending"
    ]


def test_replay_returns_the_original_result_snapshot_after_later_transitions():
    workflow = MarketWorkflow(InMemoryMarketRequestStore())
    submitted = workflow.submit(_submission())
    assert isinstance(submitted, Applied)
    opened = workflow.open_bidding(
        OpenBiddingCommand(
            idempotency_key="open",
            request_id=submitted.request.request_id,
            expected_version=1,
            authority=_authority(),
        )
    )
    assert isinstance(opened, Applied)
    cancelled = workflow.cancel(
        CancelRequestCommand(
            idempotency_key="cancel",
            request_id=submitted.request.request_id,
            expected_version=2,
            authority=_authority(),
        )
    )
    assert isinstance(cancelled, Applied)

    submission_replay = workflow.submit(_submission())
    open_replay = workflow.open_bidding(
        OpenBiddingCommand(
            idempotency_key="open",
            request_id=submitted.request.request_id,
            expected_version=1,
            authority=_authority(),
        )
    )

    assert isinstance(submission_replay, Replayed)
    assert submission_replay.request.state == "pending"
    assert submission_replay.request.version == 1
    assert isinstance(open_replay, Replayed)
    assert open_replay.request.state == "bidding"
    assert open_replay.request.version == 2


def test_every_specified_state_edge_is_explicit_and_other_edges_are_forbidden():
    allowed = {
        ("pending", "bidding"),
        ("pending", "cancelled"),
        ("pending", "expired"),
        ("bidding", "claimed"),
        ("bidding", "cancelled"),
        ("bidding", "expired"),
        ("claimed", "running"),
        ("claimed", "failed"),
        ("running", "completed"),
        ("running", "failed"),
        ("completed", "accepted"),
        ("completed", "auto_accepted"),
        ("completed", "disputed"),
        ("disputed", "accepted"),
        ("disputed", "refunded"),
        ("disputed", "running"),
        ("accepted", "settled"),
        ("auto_accepted", "settled"),
        ("failed", "refunded"),
    }
    states = {
        "pending",
        "bidding",
        "claimed",
        "running",
        "completed",
        "accepted",
        "auto_accepted",
        "settled",
        "cancelled",
        "expired",
        "failed",
        "refunded",
        "disputed",
    }

    assert {
        (source, target)
        for source in states
        for target in states
        if allowed_transition(source, target)
    } == allowed


def test_requester_or_current_bounded_grant_can_open_bidding_but_other_actor_cannot():
    now = datetime(2026, 7, 25, tzinfo=UTC)
    store = InMemoryMarketRequestStore()
    workflow = MarketWorkflow(store)
    submitted = workflow.submit(_submission())
    assert isinstance(submitted, Applied)

    denied = workflow.open_bidding(
        OpenBiddingCommand(
            idempotency_key="open-denied",
            request_id=submitted.request.request_id,
            expected_version=1,
            authority=_authority(subject_id="other"),
        ),
        now=now,
    )
    assert isinstance(denied, Conflict)
    assert denied.reason == "requester_authority_required"

    grant = VerifiedWorkflowGrant(
        grant_id="grant-1",
        host_actor_id="host",
        target_actor_id="buyer",
        target_tenant_id="tenant-a",
        allowed_actions=frozenset({"open_bidding"}),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=5),
        revocation_generation=3,
        verified_signature_sha256="c" * 64,
    )
    opened = workflow.open_bidding(
        OpenBiddingCommand(
            idempotency_key="open-granted",
            request_id=submitted.request.request_id,
            expected_version=1,
            authority=_authority(subject_id="host", grant=grant),
        ),
        now=now,
    )
    assert isinstance(opened, Applied)
    assert opened.request.state == "bidding"
    assert opened.request.version == 2
    assert store.history(opened.request.request_id)[-1].grant_id == "grant-1"


@pytest.mark.parametrize("fanout_limit", [0, 17, True])
def test_submission_rejects_unbounded_fanout(fanout_limit):
    workflow = MarketWorkflow(InMemoryMarketRequestStore())
    result = workflow.submit(_submission(fanout_limit=fanout_limit))
    assert isinstance(result, Conflict)
    assert result.reason == "fanout_limit_out_of_bounds"
    assert workflow.store.requests() == ()


def test_concurrent_identical_cancel_replays_one_append_only_transition():
    store = InMemoryMarketRequestStore()
    workflow = MarketWorkflow(store)
    submitted = workflow.submit(_submission())
    assert isinstance(submitted, Applied)
    opened = workflow.open_bidding(
        OpenBiddingCommand(
            idempotency_key="open",
            request_id=submitted.request.request_id,
            expected_version=1,
            authority=_authority(),
        )
    )
    assert isinstance(opened, Applied)

    barrier = threading.Barrier(20)
    results = []
    lock = threading.Lock()

    def cancel() -> None:
        barrier.wait()
        result = workflow.cancel(
            CancelRequestCommand(
                idempotency_key="cancel-same",
                request_id=opened.request.request_id,
                expected_version=2,
                authority=_authority(),
            )
        )
        with lock:
            results.append(result)

    threads = [threading.Thread(target=cancel) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sum(isinstance(result, Applied) for result in results) == 1
    assert sum(isinstance(result, Replayed) for result in results) == 19
    history = store.history(opened.request.request_id)
    assert [event.new_state for event in history] == ["pending", "bidding", "cancelled"]
    assert tuple(event.version for event in history) == (1, 2, 3)


def test_existing_market_api_does_not_advertise_a_new_paid_request_action():
    assert "paid_request" not in market_api._GATES_ACTIONS
    assert "paid_request" not in market_api._GOAL_ACTIONS
