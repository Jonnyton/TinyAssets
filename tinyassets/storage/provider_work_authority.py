"""SQLite persistence for dark requester-owned provider bindings."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import weakref
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.provider_work_authority import (
    ProviderInvocationCarrier,
    ProviderInvocationLaunchRequest,
    ProviderInvocationReservation,
    ProviderInvocationReservationRequest,
    ProviderInvocationReservationState,
    ProviderInvocationReservationWriteResult,
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkReceipt,
    ProviderUniverseWorkRoot,
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBinding,
    ProviderWorkBindingFence,
    ProviderWorkBindingSeed,
    ProviderWorkBindingState,
    ProviderWorkBindingWriteResult,
    ProviderWorkExecutionClaim,
    ProviderWorkExecutionClaimRequest,
    ProviderWorkExecutionClaimState,
    ProviderWorkExecutionClaimWriteResult,
    ProviderWorkReceiptState,
    ProviderWorkReceiptWriteResult,
    _claim_from_request,
    _from_seed,
    _mint_provider_invocation_carrier,
    _receipt_from_authority,
    _reservation_from_request,
    _reservation_with_state,
    provider_invocation_reservation_id,
    provider_work_binding_id,
    provider_work_claim_id,
    provider_work_receipt_id,
)
from tinyassets.storage import db_path

_PROVIDER_INVOCATION_STORE_MINT_LOCK = threading.Lock()
_ACTIVE_PROVIDER_INVOCATION_STORE_MINT_PROOFS: dict[str, tuple[str, int]] = {}
_PLACEHOLDER_DIGEST = f"sha256:{'0' * 64}"


def _reset_provider_invocation_store_mint_state_after_fork() -> None:
    global _PROVIDER_INVOCATION_STORE_MINT_LOCK
    global _ACTIVE_PROVIDER_INVOCATION_STORE_MINT_PROOFS

    _PROVIDER_INVOCATION_STORE_MINT_LOCK = threading.Lock()
    _ACTIVE_PROVIDER_INVOCATION_STORE_MINT_PROOFS = {}


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_provider_invocation_store_mint_state_after_fork)


def _discard_provider_invocation_store_mint_proof(
    proof_id: str,
    issuer_pid: int,
) -> None:
    if issuer_pid != os.getpid():
        return
    with _PROVIDER_INVOCATION_STORE_MINT_LOCK:
        _ACTIVE_PROVIDER_INVOCATION_STORE_MINT_PROOFS.pop(proof_id, None)


class _ProviderInvocationStoreMintProof:
    __slots__ = (
        "_issuer_pid",
        "_proof_id",
        "_reservation_digest",
        "__weakref__",
    )

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("provider invocation mint proofs are store-issued")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("provider invocation mint proof is immutable")

    def __reduce__(self):
        raise TypeError("provider invocation mint proof is non-serializable")

    def _consume(self, reservation_digest: str) -> None:
        if type(self) is not _ProviderInvocationStoreMintProof:
            raise PermissionError("provider invocation mint proof is not store-issued")
        current_pid = os.getpid()
        if self._issuer_pid != current_pid:
            raise PermissionError("provider invocation mint proof belongs to another process")
        expected = (self._reservation_digest, self._issuer_pid)
        if expected != (reservation_digest, current_pid):
            raise PermissionError("provider invocation mint proof is for another reservation")
        with _PROVIDER_INVOCATION_STORE_MINT_LOCK:
            active = _ACTIVE_PROVIDER_INVOCATION_STORE_MINT_PROOFS.get(self._proof_id)
            if active != expected:
                raise PermissionError("provider invocation mint proof is invalid or consumed")
            del _ACTIVE_PROVIDER_INVOCATION_STORE_MINT_PROOFS[self._proof_id]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_work_bindings (
    binding_id TEXT PRIMARY KEY,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state IN ('active', 'revoked', 'expired')),
    owner_user_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    binding_digest TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_provider_work_bindings_scope
ON provider_work_bindings(owner_user_id, universe_id, provider, state);

CREATE TABLE IF NOT EXISTS provider_work_receipts (
    receipt_id TEXT PRIMARY KEY,
    receipt_digest TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state IN ('active', 'revoked', 'expired', 'fenced')),
    work_item_kind TEXT NOT NULL,
    work_item_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    binding_id TEXT NOT NULL,
    binding_generation INTEGER NOT NULL CHECK (binding_generation >= 1),
    binding_digest TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    UNIQUE (universe_id, work_item_kind, work_item_id),
    FOREIGN KEY(binding_id) REFERENCES provider_work_bindings(binding_id)
);

CREATE TABLE IF NOT EXISTS provider_work_execution_claims (
    claim_id TEXT PRIMARY KEY,
    claim_digest TEXT NOT NULL,
    receipt_id TEXT NOT NULL UNIQUE,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state IN ('active', 'released', 'invalidated')),
    lease_expires_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    FOREIGN KEY(receipt_id) REFERENCES provider_work_receipts(receipt_id)
);

CREATE TABLE IF NOT EXISTS provider_invocation_reservations (
    reservation_id TEXT PRIMARY KEY,
    reservation_digest TEXT NOT NULL,
    receipt_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    claim_digest TEXT NOT NULL,
    claim_generation INTEGER NOT NULL CHECK (claim_generation >= 1),
    invocation_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    state TEXT NOT NULL CHECK (state IN (
        'reserved', 'launch_started', 'succeeded', 'failed',
        'cancelled_before_launch', 'indeterminate'
    )),
    max_tokens INTEGER NOT NULL CHECK (max_tokens >= 0),
    max_cost_microunits INTEGER NOT NULL CHECK (max_cost_microunits >= 0),
    record_json TEXT NOT NULL,
    UNIQUE (receipt_id, invocation_key),
    UNIQUE (receipt_id, ordinal),
    FOREIGN KEY(receipt_id) REFERENCES provider_work_receipts(receipt_id),
    FOREIGN KEY(claim_id) REFERENCES provider_work_execution_claims(claim_id)
);
"""


def _record(row: sqlite3.Row) -> ProviderWorkBinding:
    try:
        binding = ProviderWorkBinding.from_dict(json.loads(row["record_json"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted provider binding is invalid") from exc
    exact = (
        binding.binding_id == row["binding_id"],
        binding.generation == row["generation"],
        binding.state.value == row["state"],
        binding.owner_user_id == row["owner_user_id"],
        binding.universe_id == row["universe_id"],
        binding.provider == row["provider"],
        binding.binding_digest == row["binding_digest"],
        binding.expected_digest() == binding.binding_digest,
    )
    if not all(exact):
        raise ValueError("persisted provider binding failed integrity validation")
    return binding


def _payload(binding: ProviderWorkBinding) -> tuple[object, ...]:
    return (
        binding.binding_id,
        binding.generation,
        binding.state.value,
        binding.owner_user_id,
        binding.universe_id,
        binding.provider,
        binding.binding_digest,
        json.dumps(binding.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    )


def _same_creation_intent(
    current: ProviderWorkBinding,
    candidate: ProviderWorkBinding,
) -> bool:
    """Compare immutable seed facts while ignoring server clock differences."""

    current_payload = current.to_dict()
    candidate_payload = candidate.to_dict()
    for field in ("binding_digest", "created_at", "updated_at"):
        current_payload.pop(field)
        candidate_payload.pop(field)
    return current_payload == candidate_payload


def _json_record(record: object) -> str:
    return json.dumps(
        record.to_dict(),  # type: ignore[attr-defined]
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _receipt_record(row: sqlite3.Row) -> ProviderUniverseWorkReceipt:
    try:
        receipt = ProviderUniverseWorkReceipt.from_dict(json.loads(row["record_json"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted provider receipt is invalid") from exc
    exact = (
        receipt.receipt_id == row["receipt_id"],
        receipt.receipt_digest == row["receipt_digest"],
        receipt.generation == row["generation"],
        receipt.state.value == row["state"],
        receipt.work_item_kind == row["work_item_kind"],
        receipt.work_item_id == row["work_item_id"],
        receipt.universe_id == row["universe_id"],
        receipt.binding_id == row["binding_id"],
        receipt.binding_generation == row["binding_generation"],
        receipt.binding_digest == row["binding_digest"],
        receipt.expires_at == row["expires_at"],
        receipt.receipt_digest == receipt.expected_digest(),
        receipt.receipt_id
        == provider_work_receipt_id(
            universe_id=receipt.universe_id,
            root=ProviderUniverseWorkRoot(
                work_item_kind=receipt.work_item_kind,
                work_item_id=receipt.work_item_id,
            ),
        ),
    )
    if not all(exact):
        raise ValueError("persisted provider receipt failed integrity validation")
    return receipt


def _claim_record(row: sqlite3.Row) -> ProviderWorkExecutionClaim:
    try:
        claim = ProviderWorkExecutionClaim.from_dict(json.loads(row["record_json"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted provider claim is invalid") from exc
    exact = (
        claim.claim_id == row["claim_id"],
        claim.claim_digest == row["claim_digest"],
        claim.receipt_id == row["receipt_id"],
        claim.generation == row["generation"],
        claim.state.value == row["state"],
        claim.lease_expires_at == row["lease_expires_at"],
        claim.claim_digest == claim.expected_digest(),
        claim.claim_id == provider_work_claim_id(claim.receipt_id),
    )
    if not all(exact):
        raise ValueError("persisted provider claim failed integrity validation")
    return claim


def _reservation_record(row: sqlite3.Row) -> ProviderInvocationReservation:
    try:
        reservation = ProviderInvocationReservation.from_dict(json.loads(row["record_json"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted provider reservation is invalid") from exc
    exact = (
        reservation.reservation_id == row["reservation_id"],
        reservation.reservation_digest == row["reservation_digest"],
        reservation.receipt_id == row["receipt_id"],
        reservation.claim_id == row["claim_id"],
        reservation.claim_digest == row["claim_digest"],
        reservation.claim_generation == row["claim_generation"],
        reservation.invocation_key == row["invocation_key"],
        reservation.ordinal == row["ordinal"],
        reservation.state.value == row["state"],
        reservation.max_tokens == row["max_tokens"],
        reservation.max_cost_microunits == row["max_cost_microunits"],
        reservation.reservation_digest == reservation.expected_digest(),
        reservation.reservation_id
        == provider_invocation_reservation_id(
            receipt_id=reservation.receipt_id,
            invocation_key=reservation.invocation_key,
        ),
    )
    if not all(exact):
        raise ValueError("persisted provider reservation failed integrity validation")
    return reservation


def _agent_receipt_for_authority(
    conn: sqlite3.Connection,
    authority: ProviderUniverseWorkAuthority,
) -> ProviderUniverseWorkReceipt:
    if authority.root.work_item_kind != "agent_invocation":
        raise PermissionError("agent transition authority has the wrong lineage")
    receipt_id = provider_work_receipt_id(
        universe_id=authority.binding.universe_id,
        root=authority.root,
    )
    row = conn.execute(
        "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
        (receipt_id,),
    ).fetchone()
    if row is None:
        raise PermissionError("agent provider receipt is missing")
    receipt = _receipt_record(row)
    expected = _receipt_from_authority(
        authority,
        created_at=receipt.created_at,
    )
    if receipt != expected:
        raise PermissionError("agent provider receipt is not exact and current")
    return receipt


def _agent_claim_nonce_digest(receipt_digest: str) -> str:
    payload = f"agent-runtime-claim\0{receipt_digest}".encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _same_receipt_intent(
    current: ProviderUniverseWorkReceipt,
    candidate: ProviderUniverseWorkReceipt,
) -> bool:
    left = current.to_dict()
    right = candidate.to_dict()
    for payload in (left, right):
        del payload["receipt_digest"]
        del payload["created_at"]
    return left == right


def _same_claim_intent(
    current: ProviderWorkExecutionClaim,
    candidate: ProviderWorkExecutionClaim,
) -> bool:
    left = current.to_dict()
    right = candidate.to_dict()
    for payload in (left, right):
        del payload["claim_digest"]
        del payload["generation"]
        del payload["lease_expires_at"]
        del payload["created_at"]
    return left == right


class _Transaction:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _insert(self, binding: ProviderWorkBinding) -> ProviderWorkBindingWriteResult:
        if not isinstance(binding, ProviderWorkBinding):
            raise ValueError("binding must be a ProviderWorkBinding")
        if (
            binding.binding_id
            != provider_work_binding_id(
                owner_user_id=binding.owner_user_id,
                universe_id=binding.universe_id,
                provider=binding.provider,
            )
            or binding.binding_digest != binding.expected_digest()
        ):
            raise ValueError("provider binding identity or digest is invalid")
        row = self._conn.execute(
            "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
            (binding.binding_id,),
        ).fetchone()
        if row is not None:
            current = _record(row)
            return ProviderWorkBindingWriteResult(
                (
                    ProviderWorkAuthorityWriteOutcome.REPLAYED
                    if _same_creation_intent(current, binding)
                    else ProviderWorkAuthorityWriteOutcome.CONFLICT
                ),
                current,
            )
        self._conn.execute(
            """
            INSERT INTO provider_work_bindings (
                binding_id, generation, state, owner_user_id, universe_id,
                provider, binding_digest, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _payload(binding),
        )
        return ProviderWorkBindingWriteResult(
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            binding,
        )

    def compare_and_swap(
        self,
        expected: ProviderWorkBindingFence,
        replacement: ProviderWorkBinding,
    ) -> ProviderWorkBindingWriteResult:
        current_expected = expected.expected_record
        if replacement.binding_id != current_expected.binding_id:
            raise ValueError("provider binding CAS identities must match")
        row = self._conn.execute(
            "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
            (replacement.binding_id,),
        ).fetchone()
        if row is None:
            return ProviderWorkBindingWriteResult(
                ProviderWorkAuthorityWriteOutcome.MISSING,
                None,
            )
        current = _record(row)
        if current == replacement:
            return ProviderWorkBindingWriteResult(
                ProviderWorkAuthorityWriteOutcome.REPLAYED,
                current,
            )
        if current != current_expected:
            return ProviderWorkBindingWriteResult(
                (
                    ProviderWorkAuthorityWriteOutcome.GENERATION_MISMATCH
                    if current.generation != current_expected.generation
                    else ProviderWorkAuthorityWriteOutcome.CONFLICT
                ),
                current,
            )
        immutable_fields = (
            "schema_version",
            "binding_id",
            "owner_user_id",
            "universe_id",
            "provider",
            "credential_reference_digest",
            "allowed_operations",
            "allowed_roles",
            "assignment_generation",
            "assignment_digest",
            "max_invocations",
            "max_tokens",
            "max_cost_microunits",
            "expires_at",
            "created_at",
        )
        immutable = all(
            getattr(replacement, field) == getattr(current, field) for field in immutable_fields
        )
        legal_transition = (
            immutable,
            current.state is ProviderWorkBindingState.ACTIVE,
            replacement.state is ProviderWorkBindingState.REVOKED,
            replacement.generation == current.generation + 1,
            replacement.revocation_generation == current.revocation_generation + 1,
            replacement.binding_id
            == provider_work_binding_id(
                owner_user_id=replacement.owner_user_id,
                universe_id=replacement.universe_id,
                provider=replacement.provider,
            ),
            replacement.binding_digest == replacement.expected_digest(),
            replacement.updated_at >= current.updated_at,
        )
        if not all(legal_transition):
            raise ValueError("provider binding transition must preserve immutable authority")
        self._conn.execute(
            """
            UPDATE provider_work_bindings
               SET generation = ?, state = ?, owner_user_id = ?,
                   universe_id = ?, provider = ?, binding_digest = ?,
                   record_json = ?
             WHERE binding_id = ?
            """,
            (*_payload(replacement)[1:], replacement.binding_id),
        )
        return ProviderWorkBindingWriteResult(
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            replacement,
        )

    def _issue_universe_receipt(
        self,
        authority: ProviderUniverseWorkAuthority,
        candidate: ProviderUniverseWorkReceipt,
        *,
        now: datetime,
    ) -> ProviderWorkReceiptWriteResult:
        row = self._conn.execute(
            "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
            (authority.binding.binding_id,),
        ).fetchone()
        if row is None or _record(row) != authority.binding:
            raise PermissionError("provider binding is not exact and current")
        binding = authority.binding
        binding_expires = datetime.fromisoformat(binding.expires_at.removesuffix("Z") + "+00:00")
        receipt_expires = datetime.fromisoformat(candidate.expires_at.removesuffix("Z") + "+00:00")
        exact = (
            binding.state is ProviderWorkBindingState.ACTIVE,
            binding_expires > now,
            receipt_expires > now,
            receipt_expires <= binding_expires,
            authority.operation in binding.allowed_operations,
            authority.role in binding.allowed_roles,
            authority.executor_class == "cloud",
            authority.max_invocations <= binding.max_invocations,
            authority.max_tokens <= binding.max_tokens,
            authority.max_cost_microunits <= binding.max_cost_microunits,
            candidate.principal_id == authority.principal_id,
            candidate.universe_id == binding.universe_id,
            candidate.provider == binding.provider,
            candidate.credential_reference_digest == binding.credential_reference_digest,
            candidate.assignment_generation == binding.assignment_generation,
            candidate.assignment_digest == binding.assignment_digest,
            candidate.allowed_operations == (authority.operation,),
            candidate.allowed_roles == (authority.role,),
            candidate.receipt_digest == candidate.expected_digest(),
            candidate.receipt_id
            == provider_work_receipt_id(
                universe_id=binding.universe_id,
                root=authority.root,
            ),
        )
        if not all(exact):
            raise PermissionError("provider receipt authority is stale or invalid")
        existing = self._conn.execute(
            """
            SELECT * FROM provider_work_receipts
            WHERE universe_id = ? AND work_item_kind = ? AND work_item_id = ?
            """,
            (
                binding.universe_id,
                authority.root.work_item_kind,
                authority.root.work_item_id,
            ),
        ).fetchone()
        if existing is not None:
            current = _receipt_record(existing)
            return ProviderWorkReceiptWriteResult(
                (
                    ProviderWorkAuthorityWriteOutcome.REPLAYED
                    if _same_receipt_intent(current, candidate)
                    else ProviderWorkAuthorityWriteOutcome.CONFLICT
                ),
                current,
            )
        self._conn.execute(
            """
            INSERT INTO provider_work_receipts (
                receipt_id, receipt_digest, generation, state,
                work_item_kind, work_item_id, universe_id, binding_id,
                binding_generation, binding_digest, expires_at, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.receipt_id,
                candidate.receipt_digest,
                candidate.generation,
                candidate.state.value,
                candidate.work_item_kind,
                candidate.work_item_id,
                candidate.universe_id,
                candidate.binding_id,
                candidate.binding_generation,
                candidate.binding_digest,
                candidate.expires_at,
                _json_record(candidate),
            ),
        )
        return ProviderWorkReceiptWriteResult(
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            candidate,
        )

    def claim_receipt(
        self,
        request: ProviderWorkExecutionClaimRequest,
        candidate: ProviderWorkExecutionClaim,
        *,
        now: datetime,
        agent_store_grant: object | None = None,
    ) -> ProviderWorkExecutionClaimWriteResult:
        receipt_row = self._conn.execute(
            "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
            (request.receipt_id,),
        ).fetchone()
        if receipt_row is None:
            return ProviderWorkExecutionClaimWriteResult(
                ProviderWorkAuthorityWriteOutcome.MISSING,
                None,
            )
        receipt = _receipt_record(receipt_row)
        if receipt.work_item_kind == "agent_invocation":
            authority = SQLiteProviderWorkAuthorityStore._consume_agent_transition_grant(
                agent_store_grant
            )
            if _agent_receipt_for_authority(self._conn, authority) != receipt:
                raise PermissionError("agent claim authority does not match receipt")
        elif agent_store_grant is not None:
            raise PermissionError("agent transition grant cannot authorize Branch work")
        if (
            receipt.receipt_digest != request.receipt_digest
            or receipt.state is not ProviderWorkReceiptState.ACTIVE
            or datetime.fromisoformat(receipt.expires_at.removesuffix("Z") + "+00:00") <= now
        ):
            return ProviderWorkExecutionClaimWriteResult(
                ProviderWorkAuthorityWriteOutcome.STALE,
                None,
            )
        binding_row = self._conn.execute(
            "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
            (receipt.binding_id,),
        ).fetchone()
        if binding_row is None:
            return ProviderWorkExecutionClaimWriteResult(
                ProviderWorkAuthorityWriteOutcome.STALE,
                None,
            )
        binding = _record(binding_row)
        binding_current = (
            binding.state is ProviderWorkBindingState.ACTIVE,
            binding.generation == receipt.binding_generation,
            binding.binding_digest == receipt.binding_digest,
            binding.revocation_generation == receipt.binding_revocation_generation,
        )
        if not all(binding_current):
            return ProviderWorkExecutionClaimWriteResult(
                ProviderWorkAuthorityWriteOutcome.STALE,
                None,
            )
        existing = self._conn.execute(
            "SELECT * FROM provider_work_execution_claims WHERE receipt_id = ?",
            (receipt.receipt_id,),
        ).fetchone()
        if existing is not None:
            current = _claim_record(existing)
            if datetime.fromisoformat(current.lease_expires_at.removesuffix("Z") + "+00:00") <= now:
                return ProviderWorkExecutionClaimWriteResult(
                    ProviderWorkAuthorityWriteOutcome.STALE,
                    current,
                )
            return ProviderWorkExecutionClaimWriteResult(
                (
                    ProviderWorkAuthorityWriteOutcome.REPLAYED
                    if _same_claim_intent(current, candidate)
                    else ProviderWorkAuthorityWriteOutcome.CONFLICT
                ),
                current,
            )
        self._conn.execute(
            """
            INSERT INTO provider_work_execution_claims (
                claim_id, claim_digest, receipt_id, generation, state,
                lease_expires_at, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.claim_id,
                candidate.claim_digest,
                candidate.receipt_id,
                candidate.generation,
                candidate.state.value,
                candidate.lease_expires_at,
                _json_record(candidate),
            ),
        )
        return ProviderWorkExecutionClaimWriteResult(
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            candidate,
        )

    def reserve_invocation(
        self,
        request: ProviderInvocationReservationRequest,
        *,
        now: datetime,
        created_at: str,
        agent_store_grant: object | None = None,
    ) -> ProviderInvocationReservationWriteResult:
        receipt_row = self._conn.execute(
            "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
            (request.receipt_id,),
        ).fetchone()
        if receipt_row is None:
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.MISSING,
                None,
            )
        receipt = _receipt_record(receipt_row)
        if receipt.work_item_kind == "agent_invocation":
            authority = SQLiteProviderWorkAuthorityStore._consume_agent_transition_grant(
                agent_store_grant
            )
            if _agent_receipt_for_authority(self._conn, authority) != receipt:
                raise PermissionError("agent reservation authority does not match receipt")
        elif agent_store_grant is not None:
            raise PermissionError("agent transition grant cannot authorize Branch work")
        claim_row = self._conn.execute(
            "SELECT * FROM provider_work_execution_claims WHERE claim_id = ?",
            (request.claim_id,),
        ).fetchone()
        if claim_row is None:
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.STALE,
                None,
            )
        claim = _claim_record(claim_row)
        binding_row = self._conn.execute(
            "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
            (receipt.binding_id,),
        ).fetchone()
        binding = _record(binding_row) if binding_row is not None else None
        current = (
            receipt.receipt_digest == request.receipt_digest,
            receipt.state is ProviderWorkReceiptState.ACTIVE,
            datetime.fromisoformat(receipt.expires_at.removesuffix("Z") + "+00:00") > now,
            claim.receipt_id == receipt.receipt_id,
            claim.receipt_digest == receipt.receipt_digest,
            claim.claim_id == request.claim_id,
            claim.claim_digest == request.claim_digest,
            claim.generation == request.claim_generation,
            claim.state.value == "active",
            datetime.fromisoformat(claim.lease_expires_at.removesuffix("Z") + "+00:00") > now,
            binding is not None,
            binding is not None and binding.state is ProviderWorkBindingState.ACTIVE,
            binding is not None and binding.generation == receipt.binding_generation,
            binding is not None and binding.binding_digest == receipt.binding_digest,
        )
        if not all(current):
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.STALE,
                None,
            )
        existing = self._conn.execute(
            """
            SELECT * FROM provider_invocation_reservations
            WHERE receipt_id = ? AND invocation_key = ?
            """,
            (receipt.receipt_id, request.invocation_key),
        ).fetchone()
        if existing is not None:
            reservation = _reservation_record(existing)
            same = (
                reservation.receipt_digest == request.receipt_digest,
                reservation.claim_id == request.claim_id,
                reservation.claim_digest == request.claim_digest,
                reservation.claim_generation == request.claim_generation,
                reservation.operation == request.operation,
                reservation.role == request.role,
                reservation.max_tokens == request.max_tokens,
                reservation.max_cost_microunits == request.max_cost_microunits,
            )
            return ProviderInvocationReservationWriteResult(
                (
                    ProviderWorkAuthorityWriteOutcome.REPLAYED
                    if all(same)
                    else ProviderWorkAuthorityWriteOutcome.CONFLICT
                ),
                reservation,
            )
        if (
            request.operation not in receipt.allowed_operations
            or request.role not in receipt.allowed_roles
        ):
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.STALE,
                None,
            )
        rows = self._conn.execute(
            """
            SELECT * FROM provider_invocation_reservations
            WHERE receipt_id = ? ORDER BY ordinal ASC
            """,
            (receipt.receipt_id,),
        ).fetchall()
        reservations = tuple(_reservation_record(row) for row in rows)
        exhausted = (
            len(reservations) >= receipt.max_invocations,
            sum(item.max_tokens for item in reservations) + request.max_tokens > receipt.max_tokens,
            sum(item.max_cost_microunits for item in reservations) + request.max_cost_microunits
            > receipt.max_cost_microunits,
        )
        if any(exhausted):
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.EXHAUSTED,
                None,
            )
        candidate = _reservation_from_request(
            request,
            ordinal=len(reservations) + 1,
            created_at=created_at,
        )
        self._conn.execute(
            """
            INSERT INTO provider_invocation_reservations (
                reservation_id, reservation_digest, receipt_id, claim_id,
                claim_digest, claim_generation, invocation_key, ordinal, state,
                max_tokens, max_cost_microunits, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.reservation_id,
                candidate.reservation_digest,
                candidate.receipt_id,
                candidate.claim_id,
                candidate.claim_digest,
                candidate.claim_generation,
                candidate.invocation_key,
                candidate.ordinal,
                candidate.state.value,
                candidate.max_tokens,
                candidate.max_cost_microunits,
                _json_record(candidate),
            ),
        )
        return ProviderInvocationReservationWriteResult(
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            candidate,
        )

    def arm_launch(
        self,
        request: ProviderInvocationLaunchRequest,
        *,
        now: datetime,
        agent_store_grant: object | None = None,
    ) -> ProviderInvocationReservationWriteResult:
        if agent_store_grant is not None:
            agent_authority = SQLiteProviderWorkAuthorityStore._consume_agent_transition_grant(
                agent_store_grant
            )
            receipt = _agent_receipt_for_authority(self._conn, agent_authority)
            if (
                request.receipt_id != receipt.receipt_id
                or request.receipt_digest != receipt.receipt_digest
            ):
                raise PermissionError("agent launch authority does not match receipt")
        else:
            receipt_row = self._conn.execute(
                "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
                (request.receipt_id,),
            ).fetchone()
            if receipt_row is None:
                return ProviderInvocationReservationWriteResult(
                    ProviderWorkAuthorityWriteOutcome.MISSING,
                    None,
                )
            receipt = _receipt_record(receipt_row)
            if receipt.work_item_kind == "agent_invocation":
                SQLiteProviderWorkAuthorityStore._consume_agent_transition_grant(None)

        reservation_row = self._conn.execute(
            """
            SELECT * FROM provider_invocation_reservations
            WHERE reservation_id = ? AND receipt_id = ?
            """,
            (request.reservation_id, receipt.receipt_id),
        ).fetchone()
        if reservation_row is None:
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.MISSING,
                None,
            )
        reservation = _reservation_record(reservation_row)
        same_identity = (
            reservation.receipt_id == request.receipt_id,
            reservation.receipt_digest == request.receipt_digest,
            reservation.claim_id == request.claim_id,
            reservation.claim_digest == request.claim_digest,
            reservation.claim_generation == request.claim_generation,
            reservation.invocation_key == request.invocation_key,
        )
        reserved_form = _reservation_with_state(
            reservation,
            ProviderInvocationReservationState.RESERVED,
        )
        if not all(same_identity) or reserved_form.reservation_digest != request.reserved_digest:
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.CONFLICT,
                reservation,
            )
        if reservation.state is ProviderInvocationReservationState.LAUNCH_STARTED:
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.REPLAYED,
                reservation,
            )
        if reservation.state is not ProviderInvocationReservationState.RESERVED:
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.CONFLICT,
                reservation,
            )

        claim_row = self._conn.execute(
            "SELECT * FROM provider_work_execution_claims WHERE claim_id = ?",
            (request.claim_id,),
        ).fetchone()
        if claim_row is None:
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.STALE,
                None,
            )
        claim = _claim_record(claim_row)
        binding_row = self._conn.execute(
            "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
            (receipt.binding_id,),
        ).fetchone()
        binding = _record(binding_row) if binding_row is not None else None
        current = (
            receipt.receipt_digest == request.receipt_digest,
            receipt.state is ProviderWorkReceiptState.ACTIVE,
            datetime.fromisoformat(receipt.expires_at.removesuffix("Z") + "+00:00") > now,
            claim.receipt_id == receipt.receipt_id,
            claim.receipt_digest == receipt.receipt_digest,
            claim.claim_digest == request.claim_digest,
            claim.generation == request.claim_generation,
            claim.state.value == "active",
            datetime.fromisoformat(claim.lease_expires_at.removesuffix("Z") + "+00:00") > now,
            binding is not None,
            binding is not None and binding.state is ProviderWorkBindingState.ACTIVE,
            binding is not None and binding.generation == receipt.binding_generation,
            binding is not None and binding.binding_digest == receipt.binding_digest,
        )
        if not all(current):
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.STALE,
                None,
            )
        armed = _reservation_with_state(
            reservation,
            ProviderInvocationReservationState.LAUNCH_STARTED,
        )
        self._conn.execute(
            """
            UPDATE provider_invocation_reservations
            SET reservation_digest = ?, state = ?, record_json = ?
            WHERE reservation_id = ? AND reservation_digest = ? AND state = 'reserved'
            """,
            (
                armed.reservation_digest,
                armed.state.value,
                _json_record(armed),
                armed.reservation_id,
                request.reserved_digest,
            ),
        )
        return ProviderInvocationReservationWriteResult(
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            armed,
            receipt,
            claim,
        )


class _BindingTransaction:
    """Expose only the binding CAS surface to production service callers."""

    __slots__ = ("__transaction",)

    def __init__(self, transaction: _Transaction) -> None:
        self.__transaction = transaction

    def compare_and_swap(
        self,
        expected: ProviderWorkBindingFence,
        replacement: ProviderWorkBinding,
    ) -> ProviderWorkBindingWriteResult:
        return self.__transaction.compare_and_swap(expected, replacement)


class SQLiteProviderWorkAuthorityStore:
    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
        allow_test_fixtures: bool = False,
    ) -> None:
        self.base_path = Path(base_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._allow_test_fixtures = bool(allow_test_fixtures)
        if self._busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    def timestamp(self) -> str:
        return self._timestamp(self._now())

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        path = db_path(self.base_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _ledger_transaction(self) -> Iterator[_Transaction]:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield _Transaction(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @contextmanager
    def transaction(self) -> Iterator[_BindingTransaction]:
        with self._ledger_transaction() as transaction:
            yield _BindingTransaction(transaction)

    def get(self, binding_id: str) -> ProviderWorkBinding | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
        return _record(row) if row is not None else None

    def get_receipt(
        self,
        receipt_id: str,
    ) -> ProviderUniverseWorkReceipt | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
        return _receipt_record(row) if row is not None else None

    def _issue_universe_receipt(
        self,
        authority: ProviderUniverseWorkAuthority,
    ) -> ProviderWorkReceiptWriteResult:
        if not isinstance(authority, ProviderUniverseWorkAuthority):
            raise ValueError("authority must be a ProviderUniverseWorkAuthority")
        if authority.root.work_item_kind == "agent_invocation":
            raise PermissionError("agent receipts require the canonical runtime authority fence")
        now = self._now()
        candidate = _receipt_from_authority(
            authority,
            created_at=self._timestamp(now),
        )
        with self._ledger_transaction() as transaction:
            return transaction._issue_universe_receipt(
                authority,
                candidate,
                now=now,
            )

    def _issue_universe_receipt_in_transaction(
        self,
        conn: sqlite3.Connection,
        store_grant: object,
    ) -> ProviderWorkReceiptWriteResult:
        """Issue a receipt inside an existing trusted SQLite write fence."""

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("provider receipt issuance requires an active transaction")
        from tinyassets.agent_runtime_provider_execution import (
            _AgentProviderReceiptStoreGrant,
        )

        if type(store_grant) is not _AgentProviderReceiptStoreGrant:
            raise PermissionError("provider receipt transaction requires a service-issued grant")
        authority = store_grant._consume()
        now = self._now()
        candidate = _receipt_from_authority(
            authority,
            created_at=self._timestamp(now),
        )
        return _Transaction(conn)._issue_universe_receipt(
            authority,
            candidate,
            now=now,
        )

    @staticmethod
    def _consume_agent_transition_grant(
        store_grant: object,
    ) -> ProviderUniverseWorkAuthority:
        from tinyassets.agent_runtime_provider_execution import (
            _AgentProviderReceiptStoreGrant,
        )

        if type(store_grant) is not _AgentProviderReceiptStoreGrant:
            raise PermissionError("agent provider transition requires a service-issued grant")
        return store_grant._consume()

    @staticmethod
    def _peek_agent_transition_grant(
        store_grant: object,
    ) -> ProviderUniverseWorkAuthority:
        from tinyassets.agent_runtime_provider_execution import (
            _AgentProviderReceiptStoreGrant,
        )

        if type(store_grant) is not _AgentProviderReceiptStoreGrant:
            raise PermissionError("agent provider transition requires a service-issued grant")
        return store_grant._peek()

    @staticmethod
    def _discard_agent_transition_grant(store_grant: object) -> None:
        from tinyassets.agent_runtime_provider_execution import (
            _AgentProviderReceiptStoreGrant,
        )

        if type(store_grant) is not _AgentProviderReceiptStoreGrant:
            raise PermissionError("agent provider transition requires a service-issued grant")
        store_grant._discard()

    @contextmanager
    def _agent_transition_authority(
        self,
        store_grant: object,
    ) -> Iterator[ProviderUniverseWorkAuthority]:
        authority = self._peek_agent_transition_grant(store_grant)
        try:
            yield authority
        finally:
            self._discard_agent_transition_grant(store_grant)

    def _claim_agent_in_transaction(
        self,
        conn: sqlite3.Connection,
        store_grant: object,
    ) -> ProviderWorkExecutionClaimWriteResult:
        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("agent claim requires an active transaction")
        with self._agent_transition_authority(store_grant) as authority:
            receipt = _agent_receipt_for_authority(conn, authority)
            now = self._now()
            remaining_seconds = int(
                (
                    datetime.fromisoformat(receipt.expires_at.removesuffix("Z") + "+00:00") - now
                ).total_seconds()
            )
            if remaining_seconds < 1:
                return ProviderWorkExecutionClaimWriteResult(
                    ProviderWorkAuthorityWriteOutcome.STALE,
                    None,
                )
            request = ProviderWorkExecutionClaimRequest(
                receipt_id=receipt.receipt_id,
                receipt_digest=receipt.receipt_digest,
                worker_id=authority.actor_id,
                runtime_id=authority.execution_subject.ref,
                claim_nonce_digest=_agent_claim_nonce_digest(receipt.receipt_digest),
                lease_seconds=min(300, remaining_seconds),
            )
            candidate = _claim_from_request(
                request,
                created_at=self._timestamp(now),
                lease_expires_at=self._timestamp(now + timedelta(seconds=request.lease_seconds)),
            )
            result = _Transaction(conn).claim_receipt(
                request,
                candidate,
                now=now,
                agent_store_grant=store_grant,
            )
            if (
                result.outcome is not ProviderWorkAuthorityWriteOutcome.STALE
                or result.record is None
            ):
                return result
            current = result.record
            if (
                current.state is not ProviderWorkExecutionClaimState.ACTIVE
                or datetime.fromisoformat(current.lease_expires_at.removesuffix("Z") + "+00:00")
                > now
            ):
                return result
            reservation_row = conn.execute(
                "SELECT * FROM provider_invocation_reservations WHERE receipt_id = ?",
                (receipt.receipt_id,),
            ).fetchone()
            reservation = (
                _reservation_record(reservation_row) if reservation_row is not None else None
            )
            if (
                reservation is not None
                and reservation.state is not ProviderInvocationReservationState.RESERVED
            ):
                return result
            renewed = replace(
                current,
                claim_digest=_PLACEHOLDER_DIGEST,
                generation=current.generation + 1,
                lease_expires_at=candidate.lease_expires_at,
                created_at=candidate.created_at,
            )
            renewed = replace(renewed, claim_digest=renewed.expected_digest())
            conn.execute(
                """
                UPDATE provider_work_execution_claims
                SET claim_digest = ?, generation = ?, state = ?,
                    lease_expires_at = ?, record_json = ?
                WHERE claim_id = ? AND generation = ? AND claim_digest = ?
                """,
                (
                    renewed.claim_digest,
                    renewed.generation,
                    renewed.state.value,
                    renewed.lease_expires_at,
                    _json_record(renewed),
                    current.claim_id,
                    current.generation,
                    current.claim_digest,
                ),
            )
            if conn.total_changes < 1:
                return ProviderWorkExecutionClaimWriteResult(
                    ProviderWorkAuthorityWriteOutcome.CONFLICT,
                    current,
                )
            if reservation is not None:
                rebound = replace(
                    reservation,
                    reservation_digest=_PLACEHOLDER_DIGEST,
                    claim_generation=renewed.generation,
                    claim_digest=renewed.claim_digest,
                )
                rebound = replace(
                    rebound,
                    reservation_digest=rebound.expected_digest(),
                )
                conn.execute(
                    """
                    UPDATE provider_invocation_reservations
                    SET reservation_digest = ?, claim_digest = ?,
                        claim_generation = ?, record_json = ?
                    WHERE reservation_id = ? AND reservation_digest = ?
                    """,
                    (
                        rebound.reservation_digest,
                        rebound.claim_digest,
                        rebound.claim_generation,
                        _json_record(rebound),
                        reservation.reservation_id,
                        reservation.reservation_digest,
                    ),
                )
            return ProviderWorkExecutionClaimWriteResult(
                ProviderWorkAuthorityWriteOutcome.APPLIED,
                renewed,
            )

    def _reserve_agent_in_transaction(
        self,
        conn: sqlite3.Connection,
        store_grant: object,
    ) -> ProviderInvocationReservationWriteResult:
        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("agent reservation requires an active transaction")
        with self._agent_transition_authority(store_grant) as authority:
            receipt = _agent_receipt_for_authority(conn, authority)
            claim_row = conn.execute(
                "SELECT * FROM provider_work_execution_claims WHERE receipt_id = ?",
                (receipt.receipt_id,),
            ).fetchone()
            if claim_row is None:
                return ProviderInvocationReservationWriteResult(
                    ProviderWorkAuthorityWriteOutcome.MISSING,
                    None,
                )
            claim = _claim_record(claim_row)
            request = ProviderInvocationReservationRequest(
                receipt_id=receipt.receipt_id,
                receipt_digest=receipt.receipt_digest,
                claim_id=claim.claim_id,
                claim_digest=claim.claim_digest,
                claim_generation=claim.generation,
                invocation_key=authority.root.work_item_id,
                operation=authority.operation,
                role=authority.role,
                max_tokens=authority.max_tokens,
                max_cost_microunits=authority.max_cost_microunits,
            )
            now = self._now()
            return _Transaction(conn).reserve_invocation(
                request,
                now=now,
                created_at=self._timestamp(now),
                agent_store_grant=store_grant,
            )

    def _arm_agent_launch_in_transaction(
        self,
        conn: sqlite3.Connection,
        store_grant: object,
    ) -> ProviderInvocationReservationWriteResult:
        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("agent launch requires an active transaction")
        with self._agent_transition_authority(store_grant) as authority:
            receipt = _agent_receipt_for_authority(conn, authority)
            reservation_row = conn.execute(
                """
                SELECT * FROM provider_invocation_reservations
                WHERE receipt_id = ? AND invocation_key = ?
                """,
                (receipt.receipt_id, authority.root.work_item_id),
            ).fetchone()
            if reservation_row is None:
                return ProviderInvocationReservationWriteResult(
                    ProviderWorkAuthorityWriteOutcome.MISSING,
                    None,
                )
            reservation = _reservation_record(reservation_row)
            request = ProviderInvocationLaunchRequest.from_reservation(
                _reservation_with_state(
                    reservation,
                    ProviderInvocationReservationState.RESERVED,
                )
            )
            result = _Transaction(conn).arm_launch(
                request,
                now=self._now(),
                agent_store_grant=store_grant,
            )
            if (
                result.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED
                or result.record is None
            ):
                return result
            proof_id = secrets.token_hex(32)
            issuer_pid = os.getpid()
            proof = object.__new__(_ProviderInvocationStoreMintProof)
            object.__setattr__(proof, "_proof_id", proof_id)
            object.__setattr__(proof, "_issuer_pid", issuer_pid)
            object.__setattr__(proof, "_reservation_digest", result.record.reservation_digest)
            weakref.finalize(
                proof,
                _discard_provider_invocation_store_mint_proof,
                proof_id,
                issuer_pid,
            )
            with _PROVIDER_INVOCATION_STORE_MINT_LOCK:
                _ACTIVE_PROVIDER_INVOCATION_STORE_MINT_PROOFS[proof_id] = (
                    result.record.reservation_digest,
                    issuer_pid,
                )
            return replace(result, mint_proof=proof)

    def claim(
        self,
        request: ProviderWorkExecutionClaimRequest,
    ) -> ProviderWorkExecutionClaimWriteResult:
        if not isinstance(request, ProviderWorkExecutionClaimRequest):
            raise ValueError("request must be a ProviderWorkExecutionClaimRequest")
        now = self._now()
        candidate = _claim_from_request(
            request,
            created_at=self._timestamp(now),
            lease_expires_at=self._timestamp(now + timedelta(seconds=request.lease_seconds)),
        )
        with self._ledger_transaction() as transaction:
            return transaction.claim_receipt(request, candidate, now=now)

    def reserve(
        self,
        request: ProviderInvocationReservationRequest,
    ) -> ProviderInvocationReservationWriteResult:
        if not isinstance(request, ProviderInvocationReservationRequest):
            raise ValueError("request must be a ProviderInvocationReservationRequest")
        now = self._now()
        with self._ledger_transaction() as transaction:
            return transaction.reserve_invocation(
                request,
                now=now,
                created_at=self._timestamp(now),
            )

    def arm_launch(
        self,
        request: ProviderInvocationLaunchRequest,
    ) -> ProviderInvocationReservationWriteResult:
        if not isinstance(request, ProviderInvocationLaunchRequest):
            raise ValueError("request must be a ProviderInvocationLaunchRequest")
        now = self._now()
        with self._ledger_transaction() as transaction:
            result = transaction.arm_launch(request, now=now)
        if result.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED or result.record is None:
            return result

        proof_id = secrets.token_hex(32)
        issuer_pid = os.getpid()
        proof = object.__new__(_ProviderInvocationStoreMintProof)
        object.__setattr__(proof, "_proof_id", proof_id)
        object.__setattr__(proof, "_issuer_pid", issuer_pid)
        object.__setattr__(
            proof,
            "_reservation_digest",
            result.record.reservation_digest,
        )
        weakref.finalize(
            proof,
            _discard_provider_invocation_store_mint_proof,
            proof_id,
            issuer_pid,
        )
        with _PROVIDER_INVOCATION_STORE_MINT_LOCK:
            _ACTIVE_PROVIDER_INVOCATION_STORE_MINT_PROOFS[proof_id] = (
                result.record.reservation_digest,
                issuer_pid,
            )
        return replace(result, mint_proof=proof)

    def arm_launch_carrier(
        self,
        request: ProviderInvocationLaunchRequest,
    ) -> ProviderInvocationCarrier:
        """Atomically arm once, then mint one process-local call capability."""

        result = self.arm_launch(request)
        if result.outcome is ProviderWorkAuthorityWriteOutcome.REPLAYED:
            raise PermissionError("provider invocation reservation is already armed")
        if (
            result.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED
            or result.record is None
            or result.receipt is None
            or result.claim is None
            or result.mint_proof is None
        ):
            raise PermissionError("provider invocation reservation could not be armed")
        return _mint_provider_invocation_carrier(
            result.receipt,
            result.claim,
            result.record,
            result.mint_proof,
        )

    def list_reservations(
        self,
        receipt_id: str,
    ) -> tuple[ProviderInvocationReservation, ...]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM provider_invocation_reservations
                WHERE receipt_id = ? ORDER BY ordinal ASC
                """,
                (receipt_id,),
            ).fetchall()
        return tuple(_reservation_record(row) for row in rows)

    def get_reservation(
        self,
        reservation_id: str,
    ) -> ProviderInvocationReservation | None:
        if not isinstance(reservation_id, str) or not reservation_id.strip():
            raise ValueError("reservation_id must be non-empty")
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM provider_invocation_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
        return _reservation_record(row) if row is not None else None

    def _issue_binding(
        self,
        seed: ProviderWorkBindingSeed,
    ) -> ProviderWorkBindingWriteResult:
        """Persist only a seed already resolved by the binding service."""

        if not isinstance(seed, ProviderWorkBindingSeed):
            raise ValueError("seed must be a ProviderWorkBindingSeed")
        binding = _from_seed(seed, created_at=self.timestamp())
        with self._ledger_transaction() as transaction:
            return transaction._insert(binding)

    def _issue_binding_in_transaction(
        self,
        conn: sqlite3.Connection,
        seed: ProviderWorkBindingSeed,
    ) -> ProviderWorkBindingWriteResult:
        """Compose canonical binding issuance into a larger atomic aggregate.

        This is intentionally private: the caller must already own an active
        SQLite transaction and a trusted, server-resolved seed.  Provider work
        remains unusable without its later receipt/claim/reservation lineage.
        """

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("binding issuance requires an active SQLite transaction")
        if not isinstance(seed, ProviderWorkBindingSeed):
            raise ValueError("seed must be a ProviderWorkBindingSeed")
        binding = _from_seed(seed, created_at=self.timestamp())
        return _Transaction(conn)._insert(binding)

    def install_test_binding(
        self,
        seed: ProviderWorkBindingSeed,
    ) -> ProviderWorkBindingWriteResult:
        """Install inert test data only; production has no issuance root yet."""

        if not self._allow_test_fixtures:
            raise PermissionError("provider binding test fixtures are disabled")
        if not isinstance(seed, ProviderWorkBindingSeed):
            raise ValueError("seed must be a ProviderWorkBindingSeed")
        binding = _from_seed(seed, created_at=self.timestamp())
        with self._ledger_transaction() as transaction:
            return transaction._insert(binding)

    def validate_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        binding_id: str,
        binding_generation: int,
        binding_digest: str,
        owner_user_id: str,
        universe_id: str,
        provider: str,
        operation: str,
        role: str,
    ) -> bool:
        """Validate exact current state without minting provider authority."""

        try:
            row = conn.execute(
                "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            if row is None:
                return False
            binding = _record(row)
            expires_at = datetime.fromisoformat(binding.expires_at.removesuffix("Z") + "+00:00")
            now = self._clock().astimezone(timezone.utc)
        except (TypeError, ValueError, sqlite3.Error):
            return False
        return all(
            (
                binding.state is ProviderWorkBindingState.ACTIVE,
                binding.generation == binding_generation,
                binding.binding_digest == binding_digest,
                binding.owner_user_id == owner_user_id,
                binding.universe_id == universe_id,
                binding.provider == provider,
                operation in binding.allowed_operations,
                role in binding.allowed_roles,
                expires_at > now,
            )
        )

    @staticmethod
    def get_binding_in_transaction(
        conn: sqlite3.Connection,
        *,
        binding_id: str,
    ) -> ProviderWorkBinding | None:
        """Resolve one integrity-checked provider binding in the caller's fence."""

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            return None
        try:
            row = conn.execute(
                "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            return _record(row) if row is not None else None
        except (sqlite3.Error, ValueError):
            return None


__all__ = ["SQLiteProviderWorkAuthorityStore"]
