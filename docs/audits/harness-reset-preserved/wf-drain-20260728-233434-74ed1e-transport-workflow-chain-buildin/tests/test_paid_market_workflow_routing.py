from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tinyassets.api import market as market_api
from tinyassets.api.market_workflow import (
    MARKET_WORKFLOW_ACTIONS,
    MarketWorkflowRoutingError,
    dispatch_market_workflow,
)
from tinyassets.payments.market_workflow import (
    CancelBidCommand,
    CancelRequestCommand,
    ClaimMatchCommand,
    MatchAndClaimCommand,
    OpenBiddingCommand,
    PlaceBidCommand,
    RecordMatchCommand,
    SubmitRequestCommand,
)


class _RecordingWorkflow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, dict[str, object]]] = []

    def __getattr__(self, name: str):
        def record(command: object, **kwargs: object) -> object:
            self.calls.append((name, command, kwargs))
            return command

        return record


@pytest.mark.parametrize(
    ("action", "command_type", "method", "trusted_now"),
    [
        ("market_submit_request", SubmitRequestCommand, "submit", None),
        (
            "market_open_bidding",
            OpenBiddingCommand,
            "open_bidding",
            datetime(2026, 7, 29, tzinfo=UTC),
        ),
        (
            "market_cancel_request",
            CancelRequestCommand,
            "cancel",
            datetime(2026, 7, 29, tzinfo=UTC),
        ),
        ("market_place_bid", PlaceBidCommand, "place_bid", 2_000_000_000),
        ("market_cancel_bid", CancelBidCommand, "cancel_bid", 2_000_000_000),
        ("market_record_match", RecordMatchCommand, "record_match", 2_000_000_000),
        ("market_claim_match", ClaimMatchCommand, "claim_match", 2_000_000_000),
        (
            "market_match_and_claim",
            MatchAndClaimCommand,
            "match_and_claim",
            2_000_000_000,
        ),
    ],
)
def test_dark_api_boundary_delegates_each_pre_delivery_command_unchanged(
    action,
    command_type,
    method,
    trusted_now,
):
    workflow = _RecordingWorkflow()
    command = object.__new__(command_type)

    def jitter(_attempt):
        return None

    result = dispatch_market_workflow(
        workflow,
        action=action,
        command=command,
        trusted_now=trusted_now,
        jitter=jitter if action == "market_match_and_claim" else None,
    )

    expected_kwargs = {}
    if trusted_now is not None:
        expected_kwargs["now"] = trusted_now
    if action == "market_match_and_claim":
        expected_kwargs["jitter"] = jitter
    assert result is command
    assert workflow.calls == [(method, command, expected_kwargs)]


def test_dark_api_boundary_rejects_action_command_mismatch_and_caller_time():
    workflow = _RecordingWorkflow()
    command = object.__new__(SubmitRequestCommand)

    with pytest.raises(MarketWorkflowRoutingError, match="requires OpenBiddingCommand"):
        dispatch_market_workflow(
            workflow,
            action="market_open_bidding",
            command=command,
            trusted_now=datetime(2026, 7, 29, tzinfo=UTC),
        )
    with pytest.raises(MarketWorkflowRoutingError, match="does not accept a clock"):
        dispatch_market_workflow(
            workflow,
            action="market_submit_request",
            command=command,
            trusted_now=2_000_000_000,
        )
    assert workflow.calls == []


def test_dark_api_boundary_has_no_delivery_settlement_or_advertised_action():
    assert MARKET_WORKFLOW_ACTIONS == (
        "market_submit_request",
        "market_open_bidding",
        "market_cancel_request",
        "market_place_bid",
        "market_cancel_bid",
        "market_record_match",
        "market_claim_match",
        "market_match_and_claim",
    )
    assert not any(
        forbidden in action
        for action in MARKET_WORKFLOW_ACTIONS
        for forbidden in ("delivery", "accept", "dispute", "settle", "refund")
    )
    assert set(MARKET_WORKFLOW_ACTIONS).isdisjoint(market_api._GATES_ACTIONS)
    assert set(MARKET_WORKFLOW_ACTIONS).isdisjoint(market_api._GOAL_ACTIONS)
