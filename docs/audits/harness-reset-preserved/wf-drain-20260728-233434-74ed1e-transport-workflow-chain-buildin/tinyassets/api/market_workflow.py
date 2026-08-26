"""Dark API delegation boundary for the paid-request workflow.

The canonical MCP routers may construct only verified, immutable commands and
delegate them here.  This module deliberately does not register actions, parse
caller identity, create persistence, or expose delivery/settlement transitions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from tinyassets.payments.market_workflow import (
    CancelBidCommand,
    CancelRequestCommand,
    ClaimMatchCommand,
    MarketWorkflow,
    MatchAndClaimCommand,
    OpenBiddingCommand,
    PlaceBidCommand,
    RecordMatchCommand,
    SubmitRequestCommand,
    WorkflowResult,
)

MARKET_WORKFLOW_ACTIONS = (
    "market_submit_request",
    "market_open_bidding",
    "market_cancel_request",
    "market_place_bid",
    "market_cancel_bid",
    "market_record_match",
    "market_claim_match",
    "market_match_and_claim",
)

_ROUTES = {
    "market_submit_request": (SubmitRequestCommand, "submit", "none"),
    "market_open_bidding": (OpenBiddingCommand, "open_bidding", "datetime"),
    "market_cancel_request": (CancelRequestCommand, "cancel", "datetime"),
    "market_place_bid": (PlaceBidCommand, "place_bid", "integer"),
    "market_cancel_bid": (CancelBidCommand, "cancel_bid", "integer"),
    "market_record_match": (RecordMatchCommand, "record_match", "integer"),
    "market_claim_match": (ClaimMatchCommand, "claim_match", "integer"),
    "market_match_and_claim": (
        MatchAndClaimCommand,
        "match_and_claim",
        "integer",
    ),
}


class MarketWorkflowRoutingError(ValueError):
    """A canonical router supplied an invalid dark-workflow invocation."""


def dispatch_market_workflow(
    workflow: MarketWorkflow,
    *,
    action: str,
    command: object,
    trusted_now: datetime | int | None = None,
    jitter: Callable[[int], None] | None = None,
) -> WorkflowResult:
    """Delegate one verified pre-delivery command without changing its body."""

    route = _ROUTES.get(action)
    if route is None:
        raise MarketWorkflowRoutingError(f"unknown market workflow action: {action}")
    command_type, method_name, clock_kind = route
    if not isinstance(command, command_type):
        raise MarketWorkflowRoutingError(
            f"{action} requires {command_type.__name__}"
        )

    kwargs: dict[str, object] = {}
    if clock_kind == "none":
        if trusted_now is not None:
            raise MarketWorkflowRoutingError(f"{action} does not accept a clock")
    elif clock_kind == "datetime":
        if (
            not isinstance(trusted_now, datetime)
            or trusted_now.tzinfo is None
            or trusted_now.utcoffset() is None
        ):
            raise MarketWorkflowRoutingError(
                f"{action} requires a trusted timezone-aware datetime"
            )
        kwargs["now"] = trusted_now
    else:
        if (
            not isinstance(trusted_now, int)
            or isinstance(trusted_now, bool)
            or trusted_now < 0
        ):
            raise MarketWorkflowRoutingError(
                f"{action} requires a trusted non-negative integer clock"
            )
        kwargs["now"] = trusted_now

    if action == "market_match_and_claim":
        if jitter is not None and not callable(jitter):
            raise MarketWorkflowRoutingError("jitter must be an injected callback")
        kwargs["jitter"] = jitter
    elif jitter is not None:
        raise MarketWorkflowRoutingError(f"{action} does not accept jitter")

    handler = getattr(workflow, method_name)
    return handler(command, **kwargs)
