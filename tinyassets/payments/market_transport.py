"""Single-path transport for paid-market logical-accounting settlements.

This module deliberately has no database or wallet implementation.  It
validates a complete command, serializes one canonical request, and hands that
request to the sole privileged settlement RPC.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Mapping, Protocol

SettlementStatus = Literal[
    "applied", "replayed", "conflict", "contention", "not_available"
]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MarketTransportError(ValueError):
    """The settlement command is invalid or exceeds verified authority."""


@dataclass(frozen=True)
class VerifiedOnBehalfGrant:
    grant_id: str
    host_actor_id: str
    target_actor_id: str
    target_tenant_id: str
    account: str
    allowed_actions: frozenset[str]
    max_amount_micros: int
    issued_at: datetime
    expires_at: datetime
    revocation_generation: int
    verified_signature_sha256: str


@dataclass(frozen=True)
class VerifiedMarketAuthority:
    subject_id: str
    tenant_id: str
    requester_user_id: str
    host_owner_user_id: str
    grant: VerifiedOnBehalfGrant | None = None


@dataclass(frozen=True)
class SettlementCommand:
    idempotency_key: str
    business_reference: str
    expected_state_version: int
    authority: VerifiedMarketAuthority
    action: str
    amount_micros: int
    escrow_account: str
    postings: tuple[tuple[str, int], ...]
    memo: str


@dataclass(frozen=True)
class SerializedSettlement:
    canonical_body: bytes
    request_sha256: str
    authority: VerifiedMarketAuthority
    postings: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class MarketTransportResult:
    status: SettlementStatus
    tx_id: int | None


class MarketLedgerRpc(Protocol):
    def apply_settlement(self, command: SerializedSettlement) -> Mapping[str, object]:
        """Apply or replay one complete logical-accounting transaction."""


class MarketTransport:
    """Validate and send settlements through the sole privileged RPC path."""

    def __init__(self, rpc: MarketLedgerRpc, *, enabled: bool = False) -> None:
        self._rpc = rpc
        self._enabled = enabled

    def settle(
        self, command: SettlementCommand, *, now: datetime | None = None
    ) -> MarketTransportResult:
        if not self._enabled:
            return MarketTransportResult(status="not_available", tx_id=None)

        effective_now = now or datetime.now(UTC)
        _validate_command(command, effective_now)
        serialized = _serialize(command)
        raw_result = self._rpc.apply_settlement(serialized)
        status = raw_result.get("status")
        tx_id = raw_result.get("tx_id")
        if status not in {"applied", "replayed", "conflict", "contention"}:
            raise MarketTransportError("settlement RPC returned an invalid status")
        if tx_id is not None and (not isinstance(tx_id, int) or isinstance(tx_id, bool)):
            raise MarketTransportError("settlement RPC returned an invalid tx_id")
        return MarketTransportResult(status=status, tx_id=tx_id)  # type: ignore[arg-type]


def _validate_command(command: SettlementCommand, now: datetime) -> None:
    for label, value in (
        ("idempotency key", command.idempotency_key),
        ("business reference", command.business_reference),
        ("action", command.action),
        ("escrow account", command.escrow_account),
    ):
        if not value:
            raise MarketTransportError(f"{label} is required")
    if not _is_int(command.expected_state_version) or command.expected_state_version < 0:
        raise MarketTransportError("expected state version must be a non-negative integer")
    if not _is_int(command.amount_micros) or command.amount_micros <= 0:
        raise MarketTransportError("amount must be a positive integer")

    authority = command.authority
    for label, value in (
        ("subject", authority.subject_id),
        ("tenant", authority.tenant_id),
        ("requester", authority.requester_user_id),
        ("host owner", authority.host_owner_user_id),
    ):
        if not value:
            raise MarketTransportError(f"{label} is required")

    if authority.subject_id != authority.requester_user_id:
        _validate_grant(command, now)

    if not command.postings or len(command.postings) > 16:
        raise MarketTransportError("postings must contain between 1 and 16 entries")
    if any(
        not account
        or len(account.encode("utf-8")) > 256
        or not _is_int(delta)
        for account, delta in command.postings
    ):
        raise MarketTransportError("posting accounts and integer deltas are required")
    if sum(delta for _, delta in command.postings) != 0:
        raise MarketTransportError("postings must balance exactly")
    if sum(
        delta
        for account, delta in command.postings
        if account == command.escrow_account
    ) != -command.amount_micros:
        raise MarketTransportError("escrow postings must debit the settlement amount")
    if not any(account == "treasury" and delta >= 0 for account, delta in command.postings):
        raise MarketTransportError("every settlement must include the canonical fee posting")


def _validate_grant(command: SettlementCommand, now: datetime) -> None:
    authority = command.authority
    grant = authority.grant
    if grant is None or grant.host_actor_id != authority.subject_id:
        raise MarketTransportError("verified on-behalf grant is required")
    if grant.target_actor_id != authority.requester_user_id:
        raise MarketTransportError("grant target does not match requester")
    if grant.target_tenant_id != authority.tenant_id:
        raise MarketTransportError("grant tenant does not match authority")
    if grant.account != command.escrow_account:
        raise MarketTransportError("grant account does not match escrow")
    if command.action not in grant.allowed_actions:
        raise MarketTransportError("grant does not allow this action")
    if command.amount_micros > grant.max_amount_micros:
        raise MarketTransportError("settlement amount exceeds grant")
    if grant.issued_at > now:
        raise MarketTransportError("grant is not yet valid")
    if grant.expires_at <= now:
        raise MarketTransportError("grant is expired")
    if not _is_int(grant.revocation_generation) or grant.revocation_generation < 0:
        raise MarketTransportError("grant revocation generation is invalid")
    if not _SHA256_RE.fullmatch(grant.verified_signature_sha256):
        raise MarketTransportError("grant signature was not verified")


def _serialize(command: SettlementCommand) -> SerializedSettlement:
    authority = command.authority
    grant = authority.grant
    body = {
        "action": command.action,
        "amount_micros": command.amount_micros,
        "authority": {
            "grant": (
                {
                    "account": grant.account,
                    "allowed_actions": sorted(grant.allowed_actions),
                    "expires_at": _utc_iso(grant.expires_at),
                    "grant_id": grant.grant_id,
                    "host_actor_id": grant.host_actor_id,
                    "issued_at": _utc_iso(grant.issued_at),
                    "max_amount_micros": grant.max_amount_micros,
                    "revocation_generation": grant.revocation_generation,
                    "target_actor_id": grant.target_actor_id,
                    "target_tenant_id": grant.target_tenant_id,
                    "verified_signature_sha256": grant.verified_signature_sha256,
                }
                if grant is not None
                else None
            ),
            "host_owner_user_id": authority.host_owner_user_id,
            "requester_user_id": authority.requester_user_id,
            "subject_id": authority.subject_id,
            "tenant_id": authority.tenant_id,
        },
        "business_reference": command.business_reference,
        "escrow_account": command.escrow_account,
        "expected_state_version": command.expected_state_version,
        "idempotency_key": command.idempotency_key,
        "memo": command.memo,
        "postings": [
            {"account": account, "delta_micros": delta}
            for account, delta in command.postings
        ],
        "schema_version": 1,
    }
    canonical_body = json.dumps(
        body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return SerializedSettlement(
        canonical_body=canonical_body,
        request_sha256=hashlib.sha256(canonical_body).hexdigest(),
        authority=authority,
        postings=command.postings,
    )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise MarketTransportError("grant timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
