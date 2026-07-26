"""Pure application boundary for the dark paid-request workflow.

The module owns immutable commands and deterministic state transitions.  I/O is
injected through protocols; the in-memory store exists for unit, fault, and
concurrency proofs and is not a live persistence adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal, Protocol

from tinyassets.paid_market.match import BookOffer, best_execution

RequestState = Literal[
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
]

_ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
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
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_FANOUT = 16
_REQUEST_NAMESPACE = uuid.UUID("7cc39eef-ffab-5bd9-a740-c1194b2fb079")


@dataclass(frozen=True)
class VerifiedWorkflowGrant:
    grant_id: str
    host_actor_id: str
    target_actor_id: str
    target_tenant_id: str
    allowed_actions: frozenset[str]
    issued_at: datetime
    expires_at: datetime
    revocation_generation: int
    verified_signature_sha256: str


@dataclass(frozen=True)
class VerifiedWorkflowAuthority:
    subject_id: str
    tenant_id: str
    grant: VerifiedWorkflowGrant | None = None


@dataclass(frozen=True)
class SubmitRequestCommand:
    idempotency_key: str
    authority: VerifiedWorkflowAuthority
    requester_user_id: str
    capability_digest: str
    payload_sha256: str
    budget_micros: int
    spend_cap_micros: int
    bid_window_ends_at: int
    deadline: int
    acceptance_policy: str
    settlement_policy_version: str
    visibility: str
    fanout_limit: int = 1


@dataclass(frozen=True)
class OpenBiddingCommand:
    idempotency_key: str
    request_id: str
    expected_version: int
    authority: VerifiedWorkflowAuthority


@dataclass(frozen=True)
class CancelRequestCommand:
    idempotency_key: str
    request_id: str
    expected_version: int
    authority: VerifiedWorkflowAuthority


@dataclass(frozen=True)
class BidQuoteBinding:
    quote_id: str
    quote_version: int
    quote_digest: str
    canonical_quote: bytes


@dataclass(frozen=True)
class PlaceBidCommand:
    idempotency_key: str
    authority: VerifiedWorkflowAuthority
    request_id: str
    expected_request_version: int
    bid_id: str
    bid_version: int
    host_id: str
    host_owner_user_id: str
    capability_digest: str
    size_mtok: int
    price_micros_per_mtok: int
    expires_at: int
    capacity_grant_id: str
    capacity_fence: int
    quote: BidQuoteBinding | None = None


@dataclass(frozen=True)
class CancelBidCommand:
    idempotency_key: str
    authority: VerifiedWorkflowAuthority
    request_id: str
    bid_id: str
    expected_bid_version: int


@dataclass(frozen=True)
class RecordMatchCommand:
    idempotency_key: str
    authority: VerifiedWorkflowAuthority
    request_id: str
    expected_request_version: int
    need_mtok: int
    matcher_version: str


@dataclass(frozen=True)
class ClaimMatchCommand:
    idempotency_key: str
    authority: VerifiedWorkflowAuthority
    request_id: str
    expected_request_version: int
    match_id: str


@dataclass(frozen=True)
class MatchAndClaimCommand:
    idempotency_key: str
    authority: VerifiedWorkflowAuthority
    request_id: str
    expected_request_version: int
    need_mtok: int
    matcher_version: str


@dataclass(frozen=True)
class MarketRequest:
    request_id: str
    tenant_id: str
    requester_user_id: str
    capability_digest: str
    payload_sha256: str
    budget_micros: int
    spend_cap_micros: int
    bid_window_ends_at: int
    deadline: int
    acceptance_policy: str
    settlement_policy_version: str
    visibility: str
    fanout_limit: int
    state: RequestState
    version: int


@dataclass(frozen=True)
class MarketBid:
    bid_id: str
    request_id: str
    tenant_id: str
    version: int
    host_id: str
    host_owner_user_id: str
    capability_digest: str
    size_mtok: int
    price_micros_per_mtok: int
    expires_at: int
    capacity_grant_id: str
    capacity_fence: int
    quote: BidQuoteBinding | None
    state: Literal["offered", "cancelled", "claimed", "replaced"]
    command_digest: str

    def as_book_offer(self) -> BookOffer:
        return BookOffer(
            offer_id=self.bid_id,
            size_mtok=self.size_mtok,
            price_micros_per_mtok=self.price_micros_per_mtok,
        )


@dataclass(frozen=True)
class MarketMatch:
    match_id: str
    request_id: str
    tenant_id: str
    request_version: int
    selected_bid_versions: tuple[tuple[str, int], ...]
    rejected_bids: tuple[tuple[str, str], ...]
    matcher_version: str
    need_mtok: int
    total_cost_micros: int
    requester_authorized: bool
    decision_digest: str


@dataclass(frozen=True)
class ClaimSlot:
    slot_id: str
    slot_index: int
    bid_id: str
    bid_version: int


@dataclass(frozen=True)
class MarketClaim:
    claim_id: str
    match_id: str
    request_id: str
    tenant_id: str
    request_version: int
    selected_bid_versions: tuple[tuple[str, int], ...]
    slots: tuple[ClaimSlot, ...]
    command_digest: str


@dataclass(frozen=True)
class TransitionEvent:
    event_id: str
    request_id: str
    tenant_id: str
    prior_state: RequestState | None
    new_state: RequestState
    version: int
    actor_id: str
    grant_id: str | None
    command_digest: str
    related_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutboxEvent:
    event_id: str
    shard_cursor: int
    request_id: str
    request_version: int
    capability_digest: str
    visibility: str
    fanout_limit: int
    bid_window_ends_at: int
    deadline: int


@dataclass(frozen=True)
class Applied:
    request: MarketRequest
    bid: MarketBid | None = None
    match: MarketMatch | None = None
    claim: MarketClaim | None = None


@dataclass(frozen=True)
class Replayed:
    request: MarketRequest
    bid: MarketBid | None = None
    match: MarketMatch | None = None
    claim: MarketClaim | None = None


@dataclass(frozen=True)
class Conflict:
    reason: str


@dataclass(frozen=True)
class Contention:
    reason: str


@dataclass(frozen=True)
class InsufficientSupply:
    reason: str = "insufficient_supply"


WorkflowResult = Applied | Replayed | Conflict | Contention | InsufficientSupply


class MarketRequestStore(Protocol):
    def submit(self, command: SubmitRequestCommand) -> WorkflowResult:
        """Create or replay one body-bound tenant-scoped request."""

    def open_bidding(
        self, command: OpenBiddingCommand, *, now: datetime
    ) -> WorkflowResult:
        """Compare-and-set a pending request to bidding."""

    def cancel(
        self, command: CancelRequestCommand, *, now: datetime
    ) -> WorkflowResult:
        """Compare-and-set a pending/bidding request to cancelled."""

    def place_bid(self, command: PlaceBidCommand, *, now: int) -> WorkflowResult:
        """Append one immutable bid version."""

    def cancel_bid(self, command: CancelBidCommand, *, now: int) -> WorkflowResult:
        """Append a terminal cancelled bid version."""

    def record_match(
        self, command: RecordMatchCommand, *, now: int
    ) -> WorkflowResult:
        """Persist one pure-oracle match decision."""

    def claim_match(
        self, command: ClaimMatchCommand, *, now: int
    ) -> WorkflowResult:
        """Atomically consume the exact versions in one match decision."""


class MarketRealtimeBus(Protocol):
    def announce(self, event: OutboxEvent) -> None:
        """Announce one already-committed privacy-minimal invalidation."""


class MarketDeliveryStore(Protocol):
    """Reserved dependency boundary owned by the fenced delivery successor."""


class MarketLedgerRpc(Protocol):
    """Logical-accounting dependency; it grants no wallet or chain authority."""


class FaultInjector(Protocol):
    def checkpoint(self, name: str) -> None:
        """Raise at a deterministic test boundary when requested."""


def allowed_transition(source: str, target: str) -> bool:
    """Return whether the delta spec explicitly permits this lifecycle edge."""
    return (source, target) in _ALLOWED_TRANSITIONS


def _enforce_transition(source: RequestState, target: RequestState) -> None:
    if not allowed_transition(source, target):
        raise ValueError("state_transition_forbidden")


class InMemoryMarketRequestStore:
    """Thread-safe reference store for deterministic workflow proofs."""

    def __init__(self, *, fault_injector: FaultInjector | None = None) -> None:
        self._lock = threading.RLock()
        self._fault_injector = fault_injector
        self._requests: dict[str, MarketRequest] = {}
        self._history: dict[str, list[TransitionEvent]] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, Applied]] = {}
        self._effects: dict[tuple[str, str], tuple[str, Applied]] = {}
        self._bids: dict[str, list[MarketBid]] = {}
        self._request_bids: dict[str, set[str]] = {}
        self._revoked_hosts: set[str] = set()
        self._capacity_fences: dict[str, int] = {}
        self._matches: dict[str, MarketMatch] = {}
        self._claims: dict[str, MarketClaim] = {}
        self._claim_bids: dict[str, tuple[str, ...]] = {}
        self._capacity_consumed: dict[str, int] = {}
        self._last_claim_locks: tuple[str, ...] = ()
        self._outbox: dict[str, list[OutboxEvent]] = {}
        self._outbox_by_event: dict[str, OutboxEvent] = {}

    def requests(self) -> tuple[MarketRequest, ...]:
        with self._lock:
            return tuple(self._requests[key] for key in sorted(self._requests))

    def get(self, request_id: str) -> MarketRequest | None:
        with self._lock:
            return self._requests.get(request_id)

    def history(self, request_id: str) -> tuple[TransitionEvent, ...]:
        with self._lock:
            return tuple(self._history.get(request_id, ()))

    def bid_history(self, bid_id: str) -> tuple[MarketBid, ...]:
        with self._lock:
            history = tuple(self._bids.get(bid_id, ()))
            if len(history) < 2:
                return history
            return tuple(
                replace(bid, state="replaced")
                if index < len(history) - 1 and bid.state == "offered"
                else bid
                for index, bid in enumerate(history)
            )

    def eligible_bids(self, request_id: str, *, now: int) -> tuple[MarketBid, ...]:
        with self._lock:
            return tuple(
                bid
                for bid in self._current_bids(request_id)
                if self._bid_rejection(bid, now=now) is None
            )

    def bid_rejections(
        self, request_id: str, *, now: int
    ) -> tuple[tuple[str, str], ...]:
        with self._lock:
            rejected = (
                (bid.bid_id, reason)
                for bid in self._current_bids(request_id)
                if (reason := self._bid_rejection(bid, now=now)) is not None
            )
            return tuple(sorted(rejected))

    def revoke_host(self, host_id: str) -> None:
        with self._lock:
            self._revoked_hosts.add(host_id)

    def set_capacity_fence(self, capacity_grant_id: str, fence: int) -> None:
        if not _positive_int(fence):
            raise ValueError("capacity fence must be a positive integer")
        with self._lock:
            self._capacity_fences[capacity_grant_id] = fence

    def match_decision(self, match_id: str) -> MarketMatch | None:
        with self._lock:
            return self._matches.get(match_id)

    def matches_for_request(self, request_id: str) -> tuple[MarketMatch, ...]:
        with self._lock:
            return tuple(
                match
                for match in self._matches.values()
                if match.request_id == request_id
            )

    def claimed_bids(self, match_id: str) -> tuple[MarketBid, ...]:
        with self._lock:
            return tuple(
                self._bids[bid_id][-1]
                for bid_id in self._claim_bids.get(match_id, ())
            )

    def capacity_consumptions(self, capacity_grant_id: str) -> int:
        with self._lock:
            return self._capacity_consumed.get(capacity_grant_id, 0)

    def last_claim_lock_order(self) -> tuple[str, ...]:
        with self._lock:
            return self._last_claim_locks

    def outbox(self, capability_digest: str) -> tuple[OutboxEvent, ...]:
        with self._lock:
            return tuple(self._outbox.get(capability_digest, ()))

    def outbox_event_for_transition(self, event_id: str) -> OutboxEvent | None:
        with self._lock:
            return self._outbox_by_event.get(event_id)

    def submit(self, command: SubmitRequestCommand) -> WorkflowResult:
        validation_error = _validate_submission(command)
        if validation_error is not None:
            return Conflict(validation_error)
        if not _authorized(
            command.authority,
            target_actor_id=command.requester_user_id,
            action="submit_request",
            now=datetime.now(UTC),
        ):
            return Conflict("requester_authority_required")

        digest = _submission_digest(command)
        scope = (command.authority.tenant_id, command.idempotency_key)
        with self._lock:
            prior = self._idempotency.get(scope)
            if prior is not None:
                prior_digest, prior_result = prior
                if prior_digest != digest:
                    return Conflict("idempotency_body_conflict")
                return Replayed(prior_result.request)

            request_id = str(
                uuid.uuid5(
                    _REQUEST_NAMESPACE,
                    f"{command.authority.tenant_id}\0{command.idempotency_key}",
                )
            )
            request = MarketRequest(
                request_id=request_id,
                tenant_id=command.authority.tenant_id,
                requester_user_id=command.requester_user_id,
                capability_digest=command.capability_digest,
                payload_sha256=command.payload_sha256,
                budget_micros=command.budget_micros,
                spend_cap_micros=command.spend_cap_micros,
                bid_window_ends_at=command.bid_window_ends_at,
                deadline=command.deadline,
                acceptance_policy=command.acceptance_policy,
                settlement_policy_version=command.settlement_policy_version,
                visibility=command.visibility,
                fanout_limit=command.fanout_limit,
                state="pending",
                version=1,
            )
            event = _event(
                request=request,
                prior_state=None,
                actor_id=command.authority.subject_id,
                grant=command.authority.grant,
                command_digest=digest,
            )
            self._checkpoint("before_request_commit")
            self._requests[request_id] = request
            self._history[request_id] = [event]
            result = Applied(request)
            self._idempotency[scope] = (digest, result)
            self._checkpoint("after_database_commit")
            return result

    def open_bidding(
        self, command: OpenBiddingCommand, *, now: datetime
    ) -> WorkflowResult:
        return self._transition(
            command=command,
            target_state="bidding",
            action="open_bidding",
            now=now,
        )

    def cancel(
        self, command: CancelRequestCommand, *, now: datetime
    ) -> WorkflowResult:
        return self._transition(
            command=command,
            target_state="cancelled",
            action="cancel_request",
            now=now,
        )

    def _transition(
        self,
        *,
        command: OpenBiddingCommand | CancelRequestCommand,
        target_state: RequestState,
        action: str,
        now: datetime,
    ) -> WorkflowResult:
        digest = _transition_digest(action, command)
        scope = (command.authority.tenant_id, command.idempotency_key)
        with self._lock:
            prior = self._idempotency.get(scope)
            if prior is not None:
                prior_digest, prior_result = prior
                if prior_digest != digest:
                    return Conflict("idempotency_body_conflict")
                return Replayed(prior_result.request)

            request = self._requests.get(command.request_id)
            if request is None or request.tenant_id != command.authority.tenant_id:
                return Conflict("request_not_found")
            if not _authorized(
                command.authority,
                target_actor_id=request.requester_user_id,
                action=action,
                now=now,
            ):
                return Conflict("requester_authority_required")
            if request.version != command.expected_version:
                return Contention("stale_request_version")
            try:
                _enforce_transition(request.state, target_state)
            except ValueError:
                return Conflict("state_transition_forbidden")

            updated = replace(
                request,
                state=target_state,
                version=request.version + 1,
            )
            event = _event(
                request=updated,
                prior_state=request.state,
                actor_id=command.authority.subject_id,
                grant=command.authority.grant,
                command_digest=digest,
            )
            self._checkpoint("before_request_commit")
            self._checkpoint("before_outbox_append")
            self._checkpoint("after_outbox_append_before_commit")
            self._requests[request.request_id] = updated
            self._history[request.request_id].append(event)
            shard_events = self._outbox.setdefault(updated.capability_digest, [])
            outbox_event = OutboxEvent(
                event_id=event.event_id,
                shard_cursor=len(shard_events) + 1,
                request_id=updated.request_id,
                request_version=updated.version,
                capability_digest=updated.capability_digest,
                visibility=updated.visibility,
                fanout_limit=updated.fanout_limit,
                bid_window_ends_at=updated.bid_window_ends_at,
                deadline=updated.deadline,
            )
            shard_events.append(outbox_event)
            self._outbox_by_event[event.event_id] = outbox_event
            result = Applied(updated)
            self._idempotency[scope] = (digest, result)
            self._checkpoint("after_database_commit")
            return result

    def place_bid(self, command: PlaceBidCommand, *, now: int) -> WorkflowResult:
        validation_error = _validate_bid(command, now=now)
        if validation_error is not None:
            return Conflict(validation_error)
        digest = _bid_digest(command)
        scope = (command.authority.tenant_id, command.idempotency_key)
        with self._lock:
            replay = self._effect_replay(scope, digest)
            if replay is not None:
                return replay
            request = self._requests.get(command.request_id)
            if (
                request is None
                or request.tenant_id != command.authority.tenant_id
            ):
                return Conflict("request_not_found")
            if request.version != command.expected_request_version:
                return Contention("stale_request_version")
            if request.state != "bidding":
                return Conflict("request_not_bidding")
            if request.capability_digest != command.capability_digest:
                return Conflict("capability_binding_mismatch")
            if not _authorized(
                command.authority,
                target_actor_id=command.host_owner_user_id,
                action="place_bid",
                now=datetime.fromtimestamp(now, UTC),
            ):
                return Conflict("host_authority_required")

            history = self._bids.get(command.bid_id, [])
            expected_version = history[-1].version + 1 if history else 1
            if command.bid_version != expected_version:
                return Conflict("bid_version_conflict")
            if history:
                prior = history[-1]
                if (
                    prior.request_id,
                    prior.host_id,
                    prior.host_owner_user_id,
                    prior.capacity_grant_id,
                ) != (
                    command.request_id,
                    command.host_id,
                    command.host_owner_user_id,
                    command.capacity_grant_id,
                ):
                    return Conflict("bid_identity_binding_mismatch")
                if prior.state != "offered":
                    return Conflict("bid_not_replaceable")
                if command.capacity_fence < prior.capacity_fence:
                    return Conflict("capacity_fence_stale")

            current_fence = self._capacity_fences.get(command.capacity_grant_id)
            if current_fence is not None and current_fence > command.capacity_fence:
                return Conflict("capacity_fence_stale")
            bid = MarketBid(
                bid_id=command.bid_id,
                request_id=command.request_id,
                tenant_id=command.authority.tenant_id,
                version=command.bid_version,
                host_id=command.host_id,
                host_owner_user_id=command.host_owner_user_id,
                capability_digest=command.capability_digest,
                size_mtok=command.size_mtok,
                price_micros_per_mtok=command.price_micros_per_mtok,
                expires_at=command.expires_at,
                capacity_grant_id=command.capacity_grant_id,
                capacity_fence=command.capacity_fence,
                quote=command.quote,
                state="offered",
                command_digest=digest,
            )
            self._checkpoint("before_bid_replacement_commit")
            history.append(bid)
            self._bids[command.bid_id] = history
            self._request_bids.setdefault(command.request_id, set()).add(
                command.bid_id
            )
            self._capacity_fences[command.capacity_grant_id] = (
                command.capacity_fence
            )
            result = Applied(request=request, bid=bid)
            self._effects[scope] = (digest, result)
            self._checkpoint("after_database_commit")
            return result

    def claim_match(
        self, command: ClaimMatchCommand, *, now: int
    ) -> WorkflowResult:
        digest = _digest(
            {
                "action": "claim_match",
                "expected_request_version": command.expected_request_version,
                "match_id": command.match_id,
                "request_id": command.request_id,
                "subject_id": command.authority.subject_id,
                "tenant_id": command.authority.tenant_id,
            }
        )
        scope = (command.authority.tenant_id, command.idempotency_key)
        with self._lock:
            replay = self._effect_replay(scope, digest)
            if replay is not None:
                return replay
            request = self._requests.get(command.request_id)
            decision = self._matches.get(command.match_id)
            if (
                request is None
                or decision is None
                or request.request_id != decision.request_id
                or request.tenant_id != command.authority.tenant_id
                or decision.tenant_id != command.authority.tenant_id
            ):
                return Conflict("match_not_found")
            if (
                request.version != command.expected_request_version
                or decision.request_version != command.expected_request_version
                or request.state != "bidding"
            ):
                return Contention("request_already_transitioned")
            if now >= request.deadline:
                return Conflict("request_deadline_elapsed")
            if now < request.bid_window_ends_at and not decision.requester_authorized:
                return Conflict("bid_window_open")
            if decision.total_cost_micros > request.spend_cap_micros:
                return Conflict("match_spend_cap_exceeded")
            try:
                _enforce_transition(request.state, "claimed")
            except ValueError:
                return Conflict("state_transition_forbidden")

            selected = decision.selected_bid_versions
            if not selected or len(selected) > request.fanout_limit:
                return Conflict("fanout_limit_exceeded")
            selected_ids = tuple(sorted(bid_id for bid_id, _ in selected))
            slots = tuple(
                ClaimSlot(
                    slot_id=str(
                        uuid.uuid5(
                            _REQUEST_NAMESPACE,
                            f"{decision.match_id}\0{index}\0{bid_id}",
                        )
                    ),
                    slot_index=index,
                    bid_id=bid_id,
                    bid_version=version,
                )
                for index, (bid_id, version) in enumerate(
                    sorted(selected, key=lambda item: item[0])
                )
            )
            self._last_claim_locks = (
                f"request:{request.request_id}",
                *(f"slot:{slot.slot_index}" for slot in slots),
                *(f"bid:{bid_id}" for bid_id in selected_ids),
            )

            current_by_id = {
                bid.bid_id: bid for bid in self._current_bids(request.request_id)
            }
            selected_owners = {
                bid.host_owner_user_id
                for bid_id, _expected_version in selected
                if (bid := current_by_id.get(bid_id)) is not None
            }
            if len(selected_owners) > 1:
                return Conflict("independent_host_claims_required")
            if not selected_owners or not _authorized(
                command.authority,
                target_actor_id=next(iter(selected_owners)),
                action="claim_match",
                now=datetime.fromtimestamp(now, UTC),
            ):
                return Conflict("selected_host_authority_required")
            for bid_id, expected_version in selected:
                bid = current_by_id.get(bid_id)
                if (
                    bid is None
                    or bid.version != expected_version
                    or self._bid_rejection(bid, now=now) is not None
                ):
                    return Contention("selected_bid_version_stale")

            claimed_versions: list[MarketBid] = []
            for bid_id in selected_ids:
                bid = current_by_id[bid_id]
                claimed = replace(
                    bid,
                    version=bid.version + 1,
                    state="claimed",
                    command_digest=digest,
                )
                claimed_versions.append(claimed)
            updated = replace(
                request,
                state="claimed",
                version=request.version + 1,
            )
            claim_id = str(
                uuid.uuid5(
                    _REQUEST_NAMESPACE,
                    f"{command.authority.tenant_id}\0{command.idempotency_key}",
                )
            )
            claim = MarketClaim(
                claim_id=claim_id,
                match_id=decision.match_id,
                request_id=request.request_id,
                tenant_id=request.tenant_id,
                request_version=updated.version,
                selected_bid_versions=tuple(sorted(selected)),
                slots=slots,
                command_digest=digest,
            )
            event = _event(
                request=updated,
                prior_state=request.state,
                actor_id=command.authority.subject_id,
                grant=command.authority.grant,
                command_digest=digest,
                related_ids=(
                    decision.match_id,
                    claim_id,
                    *selected_ids,
                ),
            )
            self._checkpoint("before_claim_cas_commit")
            for bid in claimed_versions:
                self._bids[bid.bid_id].append(bid)
                self._capacity_consumed[bid.capacity_grant_id] = (
                    self._capacity_consumed.get(bid.capacity_grant_id, 0) + 1
                )
            self._requests[request.request_id] = updated
            self._history[request.request_id].append(event)
            self._claims[claim_id] = claim
            self._claim_bids[decision.match_id] = selected_ids
            result = Applied(
                request=updated,
                match=decision,
                claim=claim,
            )
            self._effects[scope] = (digest, result)
            self._checkpoint("after_database_commit")
            return result

    def cancel_bid(self, command: CancelBidCommand, *, now: int) -> WorkflowResult:
        digest = _digest(
            {
                "action": "cancel_bid",
                "bid_id": command.bid_id,
                "expected_bid_version": command.expected_bid_version,
                "request_id": command.request_id,
                "subject_id": command.authority.subject_id,
                "tenant_id": command.authority.tenant_id,
            }
        )
        scope = (command.authority.tenant_id, command.idempotency_key)
        with self._lock:
            replay = self._effect_replay(scope, digest)
            if replay is not None:
                return replay
            request = self._requests.get(command.request_id)
            history = self._bids.get(command.bid_id)
            if (
                request is None
                or history is None
                or history[-1].request_id != command.request_id
                or request.tenant_id != command.authority.tenant_id
            ):
                return Conflict("bid_not_found")
            bid = history[-1]
            if bid.version != command.expected_bid_version:
                return Contention("stale_bid_version")
            if bid.state != "offered":
                return Conflict("bid_not_cancellable")
            if not _authorized(
                command.authority,
                target_actor_id=bid.host_owner_user_id,
                action="cancel_bid",
                now=datetime.fromtimestamp(now, UTC),
            ):
                return Conflict("host_authority_required")
            cancelled = replace(
                bid,
                version=bid.version + 1,
                state="cancelled",
                command_digest=digest,
            )
            history.append(cancelled)
            result = Applied(request=request, bid=cancelled)
            self._effects[scope] = (digest, result)
            return result

    def record_match(
        self, command: RecordMatchCommand, *, now: int
    ) -> WorkflowResult:
        digest = _digest(
            {
                "action": "record_match",
                "expected_request_version": command.expected_request_version,
                "matcher_version": command.matcher_version,
                "need_mtok": command.need_mtok,
                "request_id": command.request_id,
                "subject_id": command.authority.subject_id,
                "tenant_id": command.authority.tenant_id,
            }
        )
        scope = (command.authority.tenant_id, command.idempotency_key)
        with self._lock:
            replay = self._effect_replay(scope, digest)
            if replay is not None:
                return replay
            request = self._requests.get(command.request_id)
            if (
                request is None
                or request.tenant_id != command.authority.tenant_id
            ):
                return Conflict("request_not_found")
            if request.version != command.expected_request_version:
                return Contention("stale_request_version")
            if request.state != "bidding":
                return Conflict("request_not_bidding")
            if not _positive_int(command.need_mtok):
                return Conflict("need_mtok_invalid")
            if command.matcher_version != "best_execution:v1":
                return Conflict("matcher_version_invalid")
            if now >= request.deadline:
                return Conflict("request_deadline_elapsed")
            eligible = tuple(
                bid
                for bid in self._current_bids(command.request_id)
                if self._bid_rejection(bid, now=now) is None
            )
            actor_is_requester = _authorized(
                command.authority,
                target_actor_id=request.requester_user_id,
                action="record_match",
                now=datetime.fromtimestamp(now, UTC),
            )
            actor_is_eligible_host = any(
                _authorized(
                    command.authority,
                    target_actor_id=bid.host_owner_user_id,
                    action="record_match",
                    now=datetime.fromtimestamp(now, UTC),
                )
                for bid in eligible
            )
            if not actor_is_requester and not actor_is_eligible_host:
                return Conflict("match_authority_required")
            if now < request.bid_window_ends_at and not actor_is_requester:
                return Conflict("bid_window_open")
            oracle = best_execution(
                [bid.as_book_offer() for bid in eligible],
                command.need_mtok,
            )
            if oracle is None:
                return InsufficientSupply()
            total_cost, selected_ids = oracle
            if total_cost > request.spend_cap_micros:
                return Conflict("match_spend_cap_exceeded")
            if len(selected_ids) > request.fanout_limit:
                return Conflict("fanout_limit_exceeded")
            selected = {
                bid.bid_id: bid for bid in eligible if bid.bid_id in selected_ids
            }
            selected_versions = tuple(
                (bid_id, selected[bid_id].version) for bid_id in selected_ids
            )
            rejected = self.bid_rejections(command.request_id, now=now)
            decision_digest = _digest(
                {
                    "matcher_version": command.matcher_version,
                    "need_mtok": command.need_mtok,
                    "rejected_bids": rejected,
                    "request_id": command.request_id,
                    "request_version": request.version,
                    "requester_authorized": actor_is_requester,
                    "selected_bid_versions": selected_versions,
                    "total_cost_micros": total_cost,
                }
            )
            match_id = str(
                uuid.uuid5(
                    _REQUEST_NAMESPACE,
                    f"{command.authority.tenant_id}\0{command.idempotency_key}",
                )
            )
            decision = MarketMatch(
                match_id=match_id,
                request_id=request.request_id,
                tenant_id=request.tenant_id,
                request_version=request.version,
                selected_bid_versions=selected_versions,
                rejected_bids=rejected,
                matcher_version=command.matcher_version,
                need_mtok=command.need_mtok,
                total_cost_micros=total_cost,
                requester_authorized=actor_is_requester,
                decision_digest=decision_digest,
            )
            self._checkpoint("before_match_recording_commit")
            self._matches[match_id] = decision
            result = Applied(request=request, match=decision)
            self._effects[scope] = (digest, result)
            self._checkpoint("after_database_commit")
            return result

    def _effect_replay(
        self, scope: tuple[str, str], digest: str
    ) -> Replayed | Conflict | None:
        prior = self._effects.get(scope)
        if prior is None:
            return None
        prior_digest, result = prior
        if prior_digest != digest:
            return Conflict("idempotency_body_conflict")
        return Replayed(
            request=result.request,
            bid=result.bid,
            match=result.match,
            claim=result.claim,
        )

    def _current_bids(self, request_id: str) -> tuple[MarketBid, ...]:
        return tuple(
            self._bids[bid_id][-1]
            for bid_id in sorted(self._request_bids.get(request_id, ()))
        )

    def _bid_rejection(self, bid: MarketBid, *, now: int) -> str | None:
        if bid.state != "offered":
            return bid.state
        if bid.expires_at <= now:
            return "expired"
        if bid.host_id in self._revoked_hosts:
            return "host_revoked"
        if self._capacity_fences.get(bid.capacity_grant_id) != bid.capacity_fence:
            return "capacity_fence_stale"
        if self._capacity_consumed.get(bid.capacity_grant_id, 0) > 0:
            return "capacity_consumed"
        return None

    def _checkpoint(self, name: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector.checkpoint(name)


class MarketWorkflow:
    """Application service that delegates all durable state to one store."""

    def __init__(
        self,
        store: MarketRequestStore,
        *,
        realtime_bus: MarketRealtimeBus | None = None,
        delivery_store: MarketDeliveryStore | None = None,
        ledger_rpc: MarketLedgerRpc | None = None,
    ) -> None:
        self.store = store
        self.realtime_bus = realtime_bus
        self.delivery_store = delivery_store
        self.ledger_rpc = ledger_rpc

    def submit(self, command: SubmitRequestCommand) -> WorkflowResult:
        return self.store.submit(command)

    def open_bidding(
        self, command: OpenBiddingCommand, *, now: datetime | None = None
    ) -> WorkflowResult:
        result = self.store.open_bidding(command, now=now or datetime.now(UTC))
        self._announce_if_applied(result)
        return result

    def cancel(
        self, command: CancelRequestCommand, *, now: datetime | None = None
    ) -> WorkflowResult:
        result = self.store.cancel(command, now=now or datetime.now(UTC))
        self._announce_if_applied(result)
        return result

    def place_bid(
        self, command: PlaceBidCommand, *, now: int
    ) -> WorkflowResult:
        return self.store.place_bid(command, now=now)

    def cancel_bid(
        self, command: CancelBidCommand, *, now: int
    ) -> WorkflowResult:
        return self.store.cancel_bid(command, now=now)

    def record_match(
        self, command: RecordMatchCommand, *, now: int
    ) -> WorkflowResult:
        return self.store.record_match(command, now=now)

    def claim_match(
        self, command: ClaimMatchCommand, *, now: int
    ) -> WorkflowResult:
        return self.store.claim_match(command, now=now)

    def match_and_claim(
        self,
        command: MatchAndClaimCommand,
        *,
        now: int,
        jitter: object | None = None,
    ) -> WorkflowResult:
        jitter_callback = jitter if callable(jitter) else lambda _attempt: None
        for attempt in range(1, 4):
            matched = self.record_match(
                RecordMatchCommand(
                    idempotency_key=f"{command.idempotency_key}:match:{attempt}",
                    authority=command.authority,
                    request_id=command.request_id,
                    expected_request_version=command.expected_request_version,
                    need_mtok=command.need_mtok,
                    matcher_version=command.matcher_version,
                ),
                now=now,
            )
            if not isinstance(matched, Applied) or matched.match is None:
                return matched
            claimed = self.claim_match(
                ClaimMatchCommand(
                    idempotency_key=f"{command.idempotency_key}:claim:{attempt}",
                    authority=command.authority,
                    request_id=command.request_id,
                    expected_request_version=command.expected_request_version,
                    match_id=matched.match.match_id,
                ),
                now=now,
            )
            if not isinstance(claimed, Contention):
                return claimed
            if attempt < 3:
                jitter_callback(attempt)
        return Contention("retry_budget_exhausted")

    def _announce_if_applied(self, result: WorkflowResult) -> None:
        if not isinstance(result, Applied) or self.realtime_bus is None:
            return
        history = getattr(self.store, "history", None)
        outbox_lookup = getattr(self.store, "outbox_event_for_transition", None)
        if history is None or outbox_lookup is None:
            return
        transition = history(result.request.request_id)[-1]
        outbox_event = outbox_lookup(transition.event_id)
        if outbox_event is not None:
            self.realtime_bus.announce(outbox_event)


def _validate_submission(command: SubmitRequestCommand) -> str | None:
    for value in (
        command.idempotency_key,
        command.authority.subject_id,
        command.authority.tenant_id,
        command.requester_user_id,
        command.capability_digest,
        command.acceptance_policy,
        command.settlement_policy_version,
    ):
        if not isinstance(value, str) or not value:
            return "required_field_missing"
    if command.visibility not in {"self", "network", "paid", "public"}:
        return "visibility_invalid"
    if not _SHA256_RE.fullmatch(command.payload_sha256):
        return "payload_digest_invalid"
    for amount in (command.budget_micros, command.spend_cap_micros):
        if not _positive_int(amount):
            return "budget_invalid"
    if command.spend_cap_micros > command.budget_micros:
        return "spend_cap_exceeds_budget"
    if not _positive_int(command.bid_window_ends_at):
        return "bid_window_invalid"
    if (
        not _positive_int(command.deadline)
        or command.deadline <= command.bid_window_ends_at
    ):
        return "deadline_invalid"
    if (
        not _positive_int(command.fanout_limit)
        or command.fanout_limit > _MAX_FANOUT
    ):
        return "fanout_limit_out_of_bounds"
    return None


def _validate_bid(command: PlaceBidCommand, *, now: int) -> str | None:
    for value in (
        command.idempotency_key,
        command.authority.subject_id,
        command.authority.tenant_id,
        command.request_id,
        command.bid_id,
        command.host_id,
        command.host_owner_user_id,
        command.capability_digest,
        command.capacity_grant_id,
    ):
        if not isinstance(value, str) or not value:
            return "required_field_missing"
    if not _positive_int(command.bid_version):
        return "bid_version_invalid"
    if not _positive_int(command.expected_request_version):
        return "request_version_invalid"
    if command.size_mtok not in {1, 10, 100}:
        return "bid_size_invalid"
    if not _positive_int(command.price_micros_per_mtok):
        return "bid_price_invalid"
    if not _positive_int(command.expires_at) or command.expires_at <= now:
        return "bid_expired"
    if not _positive_int(command.capacity_fence):
        return "capacity_fence_invalid"
    quote = command.quote
    if quote is not None and (
        not quote.quote_id
        or not _positive_int(quote.quote_version)
        or not _SHA256_RE.fullmatch(quote.quote_digest)
        or hashlib.sha256(quote.canonical_quote).hexdigest() != quote.quote_digest
    ):
        return "quote_binding_invalid"
    return None


def _authorized(
    authority: VerifiedWorkflowAuthority,
    *,
    target_actor_id: str,
    action: str,
    now: datetime,
) -> bool:
    if authority.subject_id == target_actor_id:
        return True
    grant = authority.grant
    return bool(
        grant is not None
        and now.tzinfo is not None
        and grant.issued_at.tzinfo is not None
        and grant.expires_at.tzinfo is not None
        and grant.host_actor_id == authority.subject_id
        and grant.target_actor_id == target_actor_id
        and grant.target_tenant_id == authority.tenant_id
        and action in grant.allowed_actions
        and grant.issued_at <= now < grant.expires_at
        and _non_negative_int(grant.revocation_generation)
        and _SHA256_RE.fullmatch(grant.verified_signature_sha256) is not None
    )


def _submission_digest(command: SubmitRequestCommand) -> str:
    return _digest(
        {
            "acceptance_policy": command.acceptance_policy,
            "bid_window_ends_at": command.bid_window_ends_at,
            "budget_micros": command.budget_micros,
            "capability_digest": command.capability_digest,
            "deadline": command.deadline,
            "fanout_limit": command.fanout_limit,
            "payload_sha256": command.payload_sha256,
            "requester_user_id": command.requester_user_id,
            "settlement_policy_version": command.settlement_policy_version,
            "spend_cap_micros": command.spend_cap_micros,
            "tenant_id": command.authority.tenant_id,
            "visibility": command.visibility,
        }
    )


def _transition_digest(
    action: str, command: OpenBiddingCommand | CancelRequestCommand
) -> str:
    return _digest(
        {
            "action": action,
            "expected_version": command.expected_version,
            "request_id": command.request_id,
            "subject_id": command.authority.subject_id,
            "tenant_id": command.authority.tenant_id,
        }
    )


def _bid_digest(command: PlaceBidCommand) -> str:
    quote = command.quote
    return _digest(
        {
            "bid_id": command.bid_id,
            "bid_version": command.bid_version,
            "capability_digest": command.capability_digest,
            "capacity_fence": command.capacity_fence,
            "capacity_grant_id": command.capacity_grant_id,
            "expected_request_version": command.expected_request_version,
            "expires_at": command.expires_at,
            "host_id": command.host_id,
            "host_owner_user_id": command.host_owner_user_id,
            "price_micros_per_mtok": command.price_micros_per_mtok,
            "quote": (
                {
                    "quote_digest": quote.quote_digest,
                    "quote_id": quote.quote_id,
                    "quote_version": quote.quote_version,
                }
                if quote is not None
                else None
            ),
            "request_id": command.request_id,
            "size_mtok": command.size_mtok,
            "tenant_id": command.authority.tenant_id,
        }
    )


def _digest(value: dict[str, object]) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(body).hexdigest()


def _event(
    *,
    request: MarketRequest,
    prior_state: RequestState | None,
    actor_id: str,
    grant: VerifiedWorkflowGrant | None,
    command_digest: str,
    related_ids: tuple[str, ...] = (),
) -> TransitionEvent:
    event_id = str(
        uuid.uuid5(
            _REQUEST_NAMESPACE,
            f"{request.request_id}\0{request.version}\0{command_digest}",
        )
    )
    return TransitionEvent(
        event_id=event_id,
        request_id=request.request_id,
        tenant_id=request.tenant_id,
        prior_state=prior_state,
        new_state=request.state,
        version=request.version,
        actor_id=actor_id,
        grant_id=grant.grant_id if grant is not None else None,
        command_digest=command_digest,
        related_ids=related_ids,
    )


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
