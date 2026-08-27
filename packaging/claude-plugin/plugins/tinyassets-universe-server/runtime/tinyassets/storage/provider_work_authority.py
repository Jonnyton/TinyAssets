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
    ProviderInvocationSettlementOwner,
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
    provider_work_binding_class,
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


def _provider_invocation_store_mint_proof(
    reservation: ProviderInvocationReservation,
) -> _ProviderInvocationStoreMintProof:
    proof_id = secrets.token_hex(32)
    issuer_pid = os.getpid()
    proof = object.__new__(_ProviderInvocationStoreMintProof)
    object.__setattr__(proof, "_proof_id", proof_id)
    object.__setattr__(proof, "_issuer_pid", issuer_pid)
    object.__setattr__(proof, "_reservation_digest", reservation.reservation_digest)
    weakref.finalize(
        proof,
        _discard_provider_invocation_store_mint_proof,
        proof_id,
        issuer_pid,
    )
    with _PROVIDER_INVOCATION_STORE_MINT_LOCK:
        _ACTIVE_PROVIDER_INVOCATION_STORE_MINT_PROOFS[proof_id] = (
            reservation.reservation_digest,
            issuer_pid,
        )
    return proof


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
    actual_input_tokens INTEGER,
    actual_output_tokens INTEGER,
    actual_total_tokens INTEGER,
    actual_cost_microunits INTEGER,
    settled_at TEXT,
    record_json TEXT NOT NULL,
    UNIQUE (receipt_id, invocation_key),
    UNIQUE (receipt_id, ordinal),
    FOREIGN KEY(receipt_id) REFERENCES provider_work_receipts(receipt_id),
    FOREIGN KEY(claim_id) REFERENCES provider_work_execution_claims(claim_id)
);
"""


def _ensure_invocation_settlement_columns(conn: sqlite3.Connection) -> None:
    columns = {
        str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
        for row in conn.execute("PRAGMA table_info(provider_invocation_reservations)")
    }
    for name, column_type in (
        ("actual_input_tokens", "INTEGER"),
        ("actual_output_tokens", "INTEGER"),
        ("actual_total_tokens", "INTEGER"),
        ("actual_cost_microunits", "INTEGER"),
        ("settled_at", "TEXT"),
    ):
        if name not in columns:
            conn.execute(
                f"ALTER TABLE provider_invocation_reservations "
                f"ADD COLUMN {name} {column_type}"
            )


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


def _same_receipt_authority_intent(
    current: ProviderUniverseWorkReceipt,
    candidate: ProviderUniverseWorkReceipt,
) -> bool:
    """Compare immutable authority while permitting an explicit lease migration."""
    left = current.to_dict()
    right = candidate.to_dict()
    for payload in (left, right):
        for field in (
            "receipt_digest",
            "generation",
            "expires_at",
            "created_at",
        ):
            del payload[field]
    return left == right


def _receipt_matches_authority(
    receipt: ProviderUniverseWorkReceipt,
    authority: ProviderUniverseWorkAuthority,
) -> bool:
    expected = _receipt_from_authority(
        authority,
        created_at=receipt.created_at,
    )
    provisional = replace(
        expected,
        generation=receipt.generation,
        receipt_digest=_PLACEHOLDER_DIGEST,
    )
    return receipt == replace(
        provisional,
        receipt_digest=provisional.expected_digest(),
    )


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


def _background_receipt_authority(
    conn: sqlite3.Connection,
    receipt: ProviderUniverseWorkReceipt,
    *,
    now: datetime,
    claim: ProviderWorkExecutionClaim | None = None,
) -> tuple[object, object, object]:
    """Reconstruct one background launch root from canonical rows only."""

    from tinyassets.background_branch_authority import (
        BackgroundBranchAttemptLifecycle,
        BackgroundBranchBindingStatus,
    )
    from tinyassets.background_branch_authority_service import (
        BackgroundBranchAuthorityOwnerFence,
        BackgroundBranchAuthorityOwnerKind,
        BackgroundBranchAuthorityOwnerState,
    )
    from tinyassets.cloud_automation_continuation import build_request_task_attempt_key
    from tinyassets.storage.background_branch_authority import (
        _attempt_from_row,
        _attempt_matches_binding,
        _binding_from_row,
        _owner_from_row,
        _SQLiteBackgroundBranchAuthorityTransaction,
    )

    def expires_after(value: str | None) -> bool:
        if value is None:
            return False
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.astimezone(timezone.utc) > now

    try:
        attempt_row = conn.execute(
            "SELECT * FROM background_branch_attempts WHERE attempt_id = ?",
            (receipt.work_item_id,),
        ).fetchone()
        if attempt_row is None:
            raise PermissionError("background provider attempt is missing")
        attempt = _attempt_from_row(attempt_row)
        binding_row = conn.execute(
            "SELECT * FROM background_branch_bindings WHERE binding_id = ?",
            (attempt.binding_id,),
        ).fetchone()
        if binding_row is None:
            raise PermissionError("background provider binding is missing")
        binding = _binding_from_row(binding_row)
        owner_rows = conn.execute(
            """
            SELECT * FROM background_branch_authority_owners
            WHERE owner_kind = ?
              AND json_extract(record_json, '$.attempt.attempt_id') = ?
            """,
            (BackgroundBranchAuthorityOwnerKind.QUEUE_TASK.value, attempt.attempt_id),
        ).fetchall()
        if len(owner_rows) != 1:
            raise PermissionError("background queue authority owner is missing or ambiguous")
        owner = _owner_from_row(owner_rows[0])
        task = conn.execute(
            """
            SELECT t.*, a.actor_id, a.body_digest, a.grant_generation
            FROM branch_tasks_v2 AS t
            JOIN request_admissions AS a
              ON a.admission_id = t.admission_id
             AND a.request_id = t.request_id
             AND a.branch_task_id = t.branch_task_id
            WHERE t.branch_task_id = ?
            LIMIT 1
            """,
            (owner.owner_id,),
        ).fetchone()
        if task is None:
            raise PermissionError("background queue task authority is missing")
        logical_key = build_request_task_attempt_key(
            tenant_id=str(task["actor_id"]),
            request_id=str(task["request_id"]),
            admission_id=str(task["admission_id"]),
            task_id=str(task["branch_task_id"]),
            body_digest=str(task["body_digest"]),
            admission_generation=int(task["grant_generation"]),
        )
        subject = receipt.execution_subject
        exact = (
            binding.status is BackgroundBranchBindingStatus.ACTIVE,
            expires_after(binding.expires_at),
            _attempt_matches_binding(attempt, binding),
            attempt.lifecycle
            in {
                BackgroundBranchAttemptLifecycle.CLAIMED,
                BackgroundBranchAttemptLifecycle.RUNNING,
            },
            expires_after(attempt.lease_expires_at),
            owner.binding is not None,
            owner.binding is not None and owner.binding.expected_record == binding,
            owner.attempt is not None,
            owner.attempt is not None and owner.attempt.expected_record == attempt,
            owner.universe_id == binding.universe_id,
            owner.authorizing_principal_id == binding.authorizing_principal_id,
            owner.source_generation == attempt.source_generation,
            logical_key == attempt.logical_attempt_key,
            task["status"] in {"running", "cancel_requested"},
            bool(str(task["claimed_by"] or "").strip()),
            expires_after(str(task["lease_expires_at"] or "")),
            str(task["universe_id"]) == binding.universe_id,
            str(task["branch_def_id"]) == binding.branch_def_id,
            str(task["automation_branch_version"]) == attempt.branch_version_id,
            str(task["automation_subject_digest"]) == attempt.branch_content_digest,
            str(task["actor_id"]) == binding.authorizing_principal_id,
            receipt.work_item_id == attempt.attempt_id,
            receipt.principal_id == binding.authorizing_principal_id,
            receipt.actor_id == binding.daemon_id,
            receipt.universe_id == binding.universe_id,
            receipt.branch_def_id == binding.branch_def_id,
            receipt.branch_version_id == attempt.branch_version_id,
            subject is not None,
            subject is not None and subject.ref == attempt.branch_version_id,
            subject is not None and subject.digest == attempt.branch_content_digest,
            expires_after(receipt.expires_at),
            datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00"))
            <= datetime.fromisoformat(binding.expires_at.replace("Z", "+00:00")),
            datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00"))
            <= datetime.fromisoformat(attempt.lease_expires_at.replace("Z", "+00:00")),
        )
        if not all(exact):
            raise PermissionError("background provider authority is stale or mismatched")
        if claim is not None and (
            claim.worker_id != binding.daemon_id
            or claim.runtime_id != binding.runtime_id
        ):
            raise PermissionError("background provider claim identity is mismatched")
        if owner.state is BackgroundBranchAuthorityOwnerState.PENDING:
            transitioned_at = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
            owner_updated = datetime.fromisoformat(owner.updated_at.replace("Z", "+00:00"))
            if datetime.fromisoformat(transitioned_at.replace("Z", "+00:00")) <= owner_updated:
                transitioned_at = (owner_updated + timedelta(microseconds=1)).isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z")
            replacement = replace(
                owner,
                transition_generation=owner.transition_generation + 1,
                state=BackgroundBranchAuthorityOwnerState.RUNNING,
                updated_at=transitioned_at,
            )
            result = _SQLiteBackgroundBranchAuthorityTransaction(conn).compare_and_swap_owner(
                expected=BackgroundBranchAuthorityOwnerFence(owner),
                replacement=replacement,
            )
            if result.record != replacement:
                raise PermissionError("background queue authority owner changed")
            owner = replacement
        if owner.state is not BackgroundBranchAuthorityOwnerState.RUNNING:
            raise PermissionError("background queue authority owner is not running")
        return binding, attempt, owner
    except PermissionError:
        raise
    except (KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise PermissionError("cloud Branch durable authority is unavailable") from exc


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
                binding_class=provider_work_binding_class(
                    allowed_operations=binding.allowed_operations,
                    allowed_roles=binding.allowed_roles,
                ),
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
        identity = replacement.binding_id == provider_work_binding_id(
            owner_user_id=replacement.owner_user_id,
            universe_id=replacement.universe_id,
            provider=replacement.provider,
            binding_class=provider_work_binding_class(
                allowed_operations=replacement.allowed_operations,
                allowed_roles=replacement.allowed_roles,
            ),
        )
        common = (
            replacement.generation == current.generation + 1,
            identity,
            replacement.binding_digest == replacement.expected_digest(),
            replacement.updated_at >= current.updated_at,
        )
        revoke_transition = (
            immutable,
            current.state is ProviderWorkBindingState.ACTIVE,
            replacement.state is ProviderWorkBindingState.REVOKED,
            replacement.revocation_generation == current.revocation_generation + 1,
        )
        rebind_transition = (
            current.state in {
                ProviderWorkBindingState.ACTIVE,
                ProviderWorkBindingState.REVOKED,
            },
            replacement.state is ProviderWorkBindingState.ACTIVE,
            replacement.revocation_generation == 0,
        )
        legal_transition = (*common, revoke_transition or rebind_transition)
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
            set(authority.allowed_roles).issubset(binding.allowed_roles),
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
            candidate.allowed_roles == authority.allowed_roles,
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
            if _same_receipt_intent(current, candidate):
                return ProviderWorkReceiptWriteResult(
                    ProviderWorkAuthorityWriteOutcome.REPLAYED,
                    current,
                )
            current_expiry = datetime.fromisoformat(
                current.expires_at.removesuffix("Z") + "+00:00"
            )
            candidate_expiry = datetime.fromisoformat(
                candidate.expires_at.removesuffix("Z") + "+00:00"
            )
            has_claim = self._conn.execute(
                "SELECT 1 FROM provider_work_execution_claims "
                "WHERE receipt_id = ? LIMIT 1",
                (current.receipt_id,),
            ).fetchone()
            has_reservation = self._conn.execute(
                "SELECT 1 FROM provider_invocation_reservations "
                "WHERE receipt_id = ? LIMIT 1",
                (current.receipt_id,),
            ).fetchone()
            if (
                current.work_item_kind == "background_attempt"
                and current.state is ProviderWorkReceiptState.ACTIVE
                and _same_receipt_authority_intent(current, candidate)
                and candidate_expiry > current_expiry
                and has_claim is None
                and has_reservation is None
            ):
                provisional = replace(
                    candidate,
                    generation=current.generation + 1,
                    receipt_digest=_PLACEHOLDER_DIGEST,
                    created_at=current.created_at,
                )
                replacement = replace(
                    provisional,
                    receipt_digest=provisional.expected_digest(),
                )
                cursor = self._conn.execute(
                    """
                    UPDATE provider_work_receipts
                    SET receipt_digest = ?, generation = ?, expires_at = ?,
                        record_json = ?
                    WHERE receipt_id = ? AND generation = ? AND receipt_digest = ?
                    """,
                    (
                        replacement.receipt_digest,
                        replacement.generation,
                        replacement.expires_at,
                        _json_record(replacement),
                        current.receipt_id,
                        current.generation,
                        current.receipt_digest,
                    ),
                )
                if cursor.rowcount == 1:
                    return ProviderWorkReceiptWriteResult(
                        ProviderWorkAuthorityWriteOutcome.APPLIED,
                        replacement,
                    )
            return ProviderWorkReceiptWriteResult(
                ProviderWorkAuthorityWriteOutcome.CONFLICT,
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
        allow_test_fixtures: bool = False,
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
        if receipt.work_item_kind == "background_attempt" and not allow_test_fixtures:
            _background_receipt_authority(
                self._conn,
                receipt,
                now=now,
                claim=candidate,
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
        allow_test_fixtures: bool = False,
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
        if receipt.work_item_kind == "background_attempt" and not allow_test_fixtures:
            _background_receipt_authority(
                self._conn,
                receipt,
                now=now,
                claim=claim,
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
        charged = tuple(
            (
                0,
                0,
                0,
            )
            if item.state is ProviderInvocationReservationState.CANCELLED_BEFORE_LAUNCH
            else (
                1,
                int(item.actual_total_tokens),
                int(item.actual_cost_microunits),
            )
            if item.state
            in {
                ProviderInvocationReservationState.SUCCEEDED,
                ProviderInvocationReservationState.FAILED,
            }
            and item.actual_total_tokens is not None
            and item.actual_cost_microunits is not None
            else (1, item.max_tokens, item.max_cost_microunits)
            for item in reservations
        )
        exhausted = (
            sum(item[0] for item in charged) >= receipt.max_invocations,
            sum(item[1] for item in charged) + request.max_tokens > receipt.max_tokens,
            sum(item[2] for item in charged) + request.max_cost_microunits
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
        allow_test_fixtures: bool = False,
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
        if receipt.work_item_kind == "background_attempt" and not allow_test_fixtures:
            _background_receipt_authority(
                self._conn,
                receipt,
                now=now,
                claim=claim,
            )
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

    def settle_invocation(
        self,
        reservation: ProviderInvocationReservation,
        state: ProviderInvocationReservationState,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_microunits: int | None,
        settled_at: str,
    ) -> ProviderInvocationReservationWriteResult:
        if state not in {
            ProviderInvocationReservationState.SUCCEEDED,
            ProviderInvocationReservationState.FAILED,
            ProviderInvocationReservationState.CANCELLED_BEFORE_LAUNCH,
            ProviderInvocationReservationState.INDETERMINATE,
        }:
            raise ValueError("provider invocation settlement state is not terminal")
        row = self._conn.execute(
            "SELECT * FROM provider_invocation_reservations WHERE reservation_id = ?",
            (reservation.reservation_id,),
        ).fetchone()
        if row is None:
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.MISSING,
                None,
            )
        current = _reservation_record(row)
        if (
            current.reservation_digest != reservation.reservation_digest
            or current.state is not ProviderInvocationReservationState.LAUNCH_STARTED
        ):
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.CONFLICT,
                current,
            )
        if state is ProviderInvocationReservationState.INDETERMINATE:
            actual_input = actual_output = actual_total = actual_cost = None
        else:
            values = (input_tokens, output_tokens, cost_microunits)
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in values
            ):
                raise ValueError("known provider invocation usage must be non-negative integers")
            actual_input = int(input_tokens)
            actual_output = int(output_tokens)
            actual_total = actual_input + actual_output
            actual_cost = int(cost_microunits)
        provisional = replace(
            current,
            schema_version=2,
            reservation_digest=_PLACEHOLDER_DIGEST,
            state=state,
            actual_input_tokens=actual_input,
            actual_output_tokens=actual_output,
            actual_total_tokens=actual_total,
            actual_cost_microunits=actual_cost,
            settled_at=settled_at,
        )
        settled = replace(
            provisional,
            reservation_digest=provisional.expected_digest(),
        )
        cursor = self._conn.execute(
            """
            UPDATE provider_invocation_reservations
               SET reservation_digest = ?, state = ?,
                   actual_input_tokens = ?, actual_output_tokens = ?,
                   actual_total_tokens = ?, actual_cost_microunits = ?,
                   settled_at = ?, record_json = ?
             WHERE reservation_id = ? AND reservation_digest = ?
               AND state = 'launch_started'
            """,
            (
                settled.reservation_digest,
                settled.state.value,
                settled.actual_input_tokens,
                settled.actual_output_tokens,
                settled.actual_total_tokens,
                settled.actual_cost_microunits,
                settled.settled_at,
                _json_record(settled),
                settled.reservation_id,
                current.reservation_digest,
            ),
        )
        if cursor.rowcount != 1:
            return ProviderInvocationReservationWriteResult(
                ProviderWorkAuthorityWriteOutcome.CONFLICT,
                current,
            )
        return ProviderInvocationReservationWriteResult(
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            settled,
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
            _ensure_invocation_settlement_columns(conn)
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

    def list_bindings(
        self,
        *,
        owner_user_id: str,
        universe_id: str,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[ProviderWorkBinding]:
        """List integrity-checked bindings for one exact owner/universe."""

        if limit < 1:
            raise ValueError("limit must be positive")
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM provider_work_bindings
                WHERE owner_user_id = ? AND universe_id = ?
                  AND (? = 0 OR state = 'active')
                ORDER BY binding_id LIMIT ?
                """,
                (owner_user_id, universe_id, int(active_only), limit),
            ).fetchall()
        return [_record(row) for row in rows]

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
            if reservation.state is not ProviderInvocationReservationState.RESERVED:
                return ProviderInvocationReservationWriteResult(
                    ProviderWorkAuthorityWriteOutcome.REPLAYED,
                    reservation,
                )
            request = ProviderInvocationLaunchRequest.from_reservation(
                reservation
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
            return replace(
                result,
                mint_proof=_provider_invocation_store_mint_proof(result.record),
            )

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
            return transaction.claim_receipt(
                request,
                candidate,
                now=now,
                allow_test_fixtures=self._allow_test_fixtures,
            )

    def _claim_or_renew_cloud_branch(
        self,
        request: ProviderWorkExecutionClaimRequest,
        authority_grant: object,
    ) -> ProviderWorkExecutionClaimWriteResult:
        """Explicitly renew one exact cloud claim under a service grant."""
        if not isinstance(request, ProviderWorkExecutionClaimRequest):
            raise ValueError("request must be a ProviderWorkExecutionClaimRequest")
        from tinyassets.cloud_automation_continuation import (
            _CloudProviderClaimAuthorityGrant,
        )

        if type(authority_grant) is not _CloudProviderClaimAuthorityGrant:
            raise PermissionError("cloud provider claim requires a service-issued grant")
        now = self._now()
        candidate = _claim_from_request(
            request,
            created_at=self._timestamp(now),
            lease_expires_at=self._timestamp(
                now + timedelta(seconds=request.lease_seconds)
            ),
        )
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                authority = authority_grant._consume(request, conn)
                receipt_row = conn.execute(
                    "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
                    (request.receipt_id,),
                ).fetchone()
                if receipt_row is None:
                    conn.commit()
                    return ProviderWorkExecutionClaimWriteResult(
                        ProviderWorkAuthorityWriteOutcome.MISSING,
                        None,
                    )
                receipt = _receipt_record(receipt_row)
                if (
                    authority.root.work_item_kind != "background_attempt"
                    or not _receipt_matches_authority(receipt, authority)
                    or datetime.fromisoformat(
                        candidate.lease_expires_at.removesuffix("Z") + "+00:00"
                    )
                    > datetime.fromisoformat(
                        receipt.expires_at.removesuffix("Z") + "+00:00"
                    )
                ):
                    raise PermissionError("cloud provider claim authority is not current")
                transaction = _Transaction(conn)
                result = transaction.claim_receipt(
                    request,
                    candidate,
                    now=now,
                    allow_test_fixtures=self._allow_test_fixtures,
                )
                current = result.record
                if (
                    result.outcome is not ProviderWorkAuthorityWriteOutcome.STALE
                    or current is None
                    or current.state is not ProviderWorkExecutionClaimState.ACTIVE
                    or datetime.fromisoformat(
                        current.lease_expires_at.removesuffix("Z") + "+00:00"
                    )
                    > now
                    or not _same_claim_intent(current, candidate)
                ):
                    conn.commit()
                    return result
                reserved = conn.execute(
                    """
                    SELECT 1 FROM provider_invocation_reservations
                    WHERE receipt_id = ? AND state = ? LIMIT 1
                    """,
                    (
                        receipt.receipt_id,
                        ProviderInvocationReservationState.RESERVED.value,
                    ),
                ).fetchone()
                if reserved is not None:
                    conn.commit()
                    return result
                renewed = replace(
                    current,
                    claim_digest=_PLACEHOLDER_DIGEST,
                    generation=current.generation + 1,
                    lease_expires_at=candidate.lease_expires_at,
                    created_at=candidate.created_at,
                )
                renewed = replace(renewed, claim_digest=renewed.expected_digest())
                cursor = conn.execute(
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
                if cursor.rowcount != 1:
                    conn.rollback()
                    return ProviderWorkExecutionClaimWriteResult(
                        ProviderWorkAuthorityWriteOutcome.CONFLICT,
                        current,
                    )
                conn.commit()
                return ProviderWorkExecutionClaimWriteResult(
                    ProviderWorkAuthorityWriteOutcome.APPLIED,
                    renewed,
                )
            except Exception:
                conn.rollback()
                raise

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
                allow_test_fixtures=self._allow_test_fixtures,
            )

    def arm_launch(
        self,
        request: ProviderInvocationLaunchRequest,
    ) -> ProviderInvocationReservationWriteResult:
        if not isinstance(request, ProviderInvocationLaunchRequest):
            raise ValueError("request must be a ProviderInvocationLaunchRequest")
        now = self._now()
        with self._ledger_transaction() as transaction:
            result = transaction.arm_launch(
                request,
                now=now,
                allow_test_fixtures=self._allow_test_fixtures,
            )
        if result.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED or result.record is None:
            return result

        return replace(
            result,
            mint_proof=_provider_invocation_store_mint_proof(result.record),
        )

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
            settlement_owner=ProviderInvocationSettlementOwner.ROUTER,
            settler=self._settle_carrier,
        )

    def _reserve_and_arm_cloud_branch_carrier_in_transaction(
        self,
        conn: sqlite3.Connection,
        request: ProviderInvocationReservationRequest,
        authority_fence: object,
    ) -> ProviderInvocationCarrier:
        """Linearize current Branch authority validation with provider launch."""
        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("cloud Branch launch requires an active transaction")
        from tinyassets.cloud_automation_continuation import (
            _CloudBranchInvocationAuthorityFence,
        )

        if type(authority_fence) is not _CloudBranchInvocationAuthorityFence:
            raise PermissionError("cloud Branch launch authority was not revalidated")
        authority_fence._consume(request)
        now = self._now()
        transaction = _Transaction(conn)
        reserved = transaction.reserve_invocation(
            request,
            now=now,
            created_at=self._timestamp(now),
            allow_test_fixtures=self._allow_test_fixtures,
        )
        if (
            reserved.record is None
            or reserved.outcome
            not in {
                ProviderWorkAuthorityWriteOutcome.APPLIED,
                ProviderWorkAuthorityWriteOutcome.REPLAYED,
            }
            or reserved.record.state is not ProviderInvocationReservationState.RESERVED
        ):
            raise PermissionError("provider invocation budget or authority is unavailable")
        launch = ProviderInvocationLaunchRequest.from_reservation(reserved.record)
        armed = transaction.arm_launch(
            launch,
            now=now,
            allow_test_fixtures=self._allow_test_fixtures,
        )
        if (
            armed.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED
            or armed.record is None
            or armed.receipt is None
            or armed.claim is None
        ):
            raise PermissionError("provider invocation reservation could not be armed")
        return _mint_provider_invocation_carrier(
            armed.receipt,
            armed.claim,
            armed.record,
            _provider_invocation_store_mint_proof(armed.record),
            settlement_owner=ProviderInvocationSettlementOwner.ROUTER,
            settler=self._settler_for_transaction(conn),
        )

    def _reserve_and_arm_background_branch_carrier_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        authority: ProviderUniverseWorkAuthority,
        worker_id: str,
        runtime_id: str,
        claim_nonce_digest: str,
        lease_seconds: int,
        invocation_key: str,
        role: str,
        max_tokens: int,
        max_cost_microunits: int,
    ) -> ProviderInvocationCarrier:
        """Issue/claim from durable background state and arm atomically."""

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("background Branch launch requires an active transaction")

        now = self._now()
        transaction = _Transaction(conn)
        receipt_candidate = _receipt_from_authority(
            authority,
            created_at=self._timestamp(now),
        )
        issued = transaction._issue_universe_receipt(
            authority,
            receipt_candidate,
            now=now,
        )
        if (
            issued.outcome
            not in {
                ProviderWorkAuthorityWriteOutcome.APPLIED,
                ProviderWorkAuthorityWriteOutcome.REPLAYED,
            }
            or issued.record is None
        ):
            raise PermissionError("background provider receipt is unavailable")
        receipt = issued.record
        receipt_expiry = datetime.fromisoformat(
            receipt.expires_at.removesuffix("Z") + "+00:00"
        )
        bounded_lease_seconds = min(
            lease_seconds,
            int((receipt_expiry - now).total_seconds()),
        )
        if bounded_lease_seconds < 1:
            raise PermissionError("background provider claim lease is expired")
        claim_request = ProviderWorkExecutionClaimRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            worker_id=worker_id,
            runtime_id=runtime_id,
            claim_nonce_digest=claim_nonce_digest,
            lease_seconds=bounded_lease_seconds,
        )
        claim_candidate = _claim_from_request(
            claim_request,
            created_at=self._timestamp(now),
            lease_expires_at=self._timestamp(
                now + timedelta(seconds=bounded_lease_seconds)
            ),
        )
        claimed = transaction.claim_receipt(
            claim_request,
            claim_candidate,
            now=now,
            allow_test_fixtures=self._allow_test_fixtures,
        )
        if (
            claimed.outcome
            not in {
                ProviderWorkAuthorityWriteOutcome.APPLIED,
                ProviderWorkAuthorityWriteOutcome.REPLAYED,
            }
            or claimed.record is None
        ):
            raise PermissionError("background provider execution claim is unavailable")
        claim = claimed.record
        request = ProviderInvocationReservationRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            claim_id=claim.claim_id,
            claim_digest=claim.claim_digest,
            claim_generation=claim.generation,
            invocation_key=invocation_key,
            operation=authority.operation,
            role=role,
            max_tokens=max_tokens,
            max_cost_microunits=max_cost_microunits,
        )
        reserved = transaction.reserve_invocation(
            request,
            now=now,
            created_at=self._timestamp(now),
            allow_test_fixtures=self._allow_test_fixtures,
        )
        if (
            reserved.record is None
            or reserved.outcome
            not in {
                ProviderWorkAuthorityWriteOutcome.APPLIED,
                ProviderWorkAuthorityWriteOutcome.REPLAYED,
            }
            or reserved.record.state is not ProviderInvocationReservationState.RESERVED
        ):
            raise PermissionError("background provider invocation is unavailable")
        armed = transaction.arm_launch(
            ProviderInvocationLaunchRequest.from_reservation(reserved.record),
            now=now,
            allow_test_fixtures=self._allow_test_fixtures,
        )
        if (
            armed.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED
            or armed.record is None
            or armed.receipt is None
            or armed.claim is None
        ):
            raise PermissionError("background provider invocation could not be armed")
        return _mint_provider_invocation_carrier(
            armed.receipt,
            armed.claim,
            armed.record,
            _provider_invocation_store_mint_proof(armed.record),
            settlement_owner=ProviderInvocationSettlementOwner.ROUTER,
            settler=self._settler_for_transaction(conn),
        )

    def _admit_run_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        authority: ProviderUniverseWorkAuthority,
        worker_id: str,
        runtime_id: str,
        claim_nonce_digest: str,
        lease_seconds: int,
    ) -> tuple[ProviderUniverseWorkReceipt, ProviderWorkExecutionClaim]:
        """Issue one inert run receipt and claim inside the admission fence."""

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("run provider admission requires an active transaction")
        if authority.root.work_item_kind != "run":
            raise PermissionError("run provider admission requires run authority")
        now = self._now()
        transaction = _Transaction(conn)
        candidate = _receipt_from_authority(
            authority,
            created_at=self._timestamp(now),
        )
        issued = transaction._issue_universe_receipt(
            authority,
            candidate,
            now=now,
        )
        if (
            issued.outcome
            not in {
                ProviderWorkAuthorityWriteOutcome.APPLIED,
                ProviderWorkAuthorityWriteOutcome.REPLAYED,
            }
            or issued.record is None
        ):
            raise PermissionError("run provider receipt is unavailable")
        receipt = issued.record
        receipt_expiry = datetime.fromisoformat(
            receipt.expires_at.removesuffix("Z") + "+00:00"
        )
        bounded_lease = min(lease_seconds, int((receipt_expiry - now).total_seconds()))
        if bounded_lease < 1:
            raise PermissionError("run provider claim lease is expired")
        request = ProviderWorkExecutionClaimRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            worker_id=worker_id,
            runtime_id=runtime_id,
            claim_nonce_digest=claim_nonce_digest,
            lease_seconds=bounded_lease,
        )
        claim_candidate = _claim_from_request(
            request,
            created_at=self._timestamp(now),
            lease_expires_at=self._timestamp(now + timedelta(seconds=bounded_lease)),
        )
        claimed = transaction.claim_receipt(
            request,
            claim_candidate,
            now=now,
            allow_test_fixtures=self._allow_test_fixtures,
        )
        if (
            claimed.outcome
            not in {
                ProviderWorkAuthorityWriteOutcome.APPLIED,
                ProviderWorkAuthorityWriteOutcome.REPLAYED,
            }
            or claimed.record is None
        ):
            raise PermissionError("run provider execution claim is unavailable")
        return receipt, claimed.record

    def _reserve_and_arm_run_carrier_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        receipt: ProviderUniverseWorkReceipt,
        claim: ProviderWorkExecutionClaim,
        invocation_key: str,
        role: str,
        max_tokens: int,
        max_cost_microunits: int,
    ) -> ProviderInvocationCarrier:
        """Reserve and arm one run attempt after caller-owned revalidation."""

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("run provider launch requires an active transaction")
        if receipt.work_item_kind != "run":
            raise PermissionError("provider receipt is not run authority")
        request = ProviderInvocationReservationRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            claim_id=claim.claim_id,
            claim_digest=claim.claim_digest,
            claim_generation=claim.generation,
            invocation_key=invocation_key,
            operation="run_graph",
            role=role,
            max_tokens=max_tokens,
            max_cost_microunits=max_cost_microunits,
        )
        now = self._now()
        transaction = _Transaction(conn)
        reserved = transaction.reserve_invocation(
            request,
            now=now,
            created_at=self._timestamp(now),
            allow_test_fixtures=self._allow_test_fixtures,
        )
        if (
            reserved.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED
            or reserved.record is None
        ):
            raise PermissionError("run provider invocation budget is unavailable")
        armed = transaction.arm_launch(
            ProviderInvocationLaunchRequest.from_reservation(reserved.record),
            now=now,
            allow_test_fixtures=self._allow_test_fixtures,
        )
        if (
            armed.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED
            or armed.record is None
            or armed.receipt is None
            or armed.claim is None
        ):
            raise PermissionError("run provider invocation could not be armed")
        return _mint_provider_invocation_carrier(
            armed.receipt,
            armed.claim,
            armed.record,
            _provider_invocation_store_mint_proof(armed.record),
            settlement_owner=ProviderInvocationSettlementOwner.ROUTER,
            settler=self._settler_for_transaction(conn),
        )

    def release_run_claim(self, receipt_id: str) -> None:
        """Fence a terminal run and cancel reservations never armed."""

        with self._ledger_transaction() as transaction:
            conn = transaction._conn
            receipt_row = conn.execute(
                "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if receipt_row is None:
                return
            receipt = _receipt_record(receipt_row)
            if receipt.work_item_kind != "run":
                raise PermissionError("only run claims can be released here")
            now = self.timestamp()
            rows = conn.execute(
                "SELECT * FROM provider_invocation_reservations "
                "WHERE receipt_id = ? AND state = 'reserved'",
                (receipt_id,),
            ).fetchall()
            for row in rows:
                current = _reservation_record(row)
                provisional = replace(
                    current,
                    schema_version=2,
                    reservation_digest=_PLACEHOLDER_DIGEST,
                    state=ProviderInvocationReservationState.CANCELLED_BEFORE_LAUNCH,
                    actual_input_tokens=0,
                    actual_output_tokens=0,
                    actual_total_tokens=0,
                    actual_cost_microunits=0,
                    settled_at=now,
                )
                cancelled = replace(
                    provisional,
                    reservation_digest=provisional.expected_digest(),
                )
                conn.execute(
                    """
                    UPDATE provider_invocation_reservations
                       SET reservation_digest = ?, state = ?,
                           actual_input_tokens = 0, actual_output_tokens = 0,
                           actual_total_tokens = 0, actual_cost_microunits = 0,
                           settled_at = ?, record_json = ?
                     WHERE reservation_id = ? AND reservation_digest = ?
                       AND state = 'reserved'
                    """,
                    (
                        cancelled.reservation_digest,
                        cancelled.state.value,
                        cancelled.settled_at,
                        _json_record(cancelled),
                        cancelled.reservation_id,
                        current.reservation_digest,
                    ),
                )
            claim_row = conn.execute(
                "SELECT * FROM provider_work_execution_claims WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if claim_row is None:
                return
            claim = _claim_record(claim_row)
            if claim.state is not ProviderWorkExecutionClaimState.ACTIVE:
                return
            provisional_claim = replace(
                claim,
                claim_digest=_PLACEHOLDER_DIGEST,
                generation=claim.generation + 1,
                state=ProviderWorkExecutionClaimState.RELEASED,
            )
            released = replace(
                provisional_claim,
                claim_digest=provisional_claim.expected_digest(),
            )
            conn.execute(
                """
                UPDATE provider_work_execution_claims
                   SET claim_digest = ?, generation = ?, state = ?, record_json = ?
                 WHERE claim_id = ? AND claim_digest = ? AND state = 'active'
                """,
                (
                    released.claim_digest,
                    released.generation,
                    released.state.value,
                    _json_record(released),
                    released.claim_id,
                    claim.claim_digest,
                ),
            )

    def _settler_for_transaction(self, conn: sqlite3.Connection):
        database = conn.execute("PRAGMA database_list").fetchone()
        database_path = str(database[2] or "") if database is not None else ""
        if database_path:
            return self._settle_carrier

        def settle_in_memory(
            reservation: ProviderInvocationReservation,
            state: ProviderInvocationReservationState,
            input_tokens: int | None,
            output_tokens: int | None,
            cost_microunits: int | None,
        ) -> None:
            started = not conn.in_transaction
            if started:
                conn.execute("BEGIN IMMEDIATE")
            try:
                result = _Transaction(conn).settle_invocation(
                    reservation,
                    state,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_microunits=cost_microunits,
                    settled_at=self.timestamp(),
                )
                if result.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED:
                    raise PermissionError("provider invocation settlement conflicted")
                if started:
                    conn.commit()
            except Exception:
                if started:
                    conn.rollback()
                raise

        return settle_in_memory

    def _settle_carrier(
        self,
        reservation: ProviderInvocationReservation,
        state: ProviderInvocationReservationState,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_microunits: int | None,
    ) -> None:
        with self._ledger_transaction() as transaction:
            result = transaction.settle_invocation(
                reservation,
                state,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_microunits=cost_microunits,
                settled_at=self.timestamp(),
            )
        if result.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED:
            raise PermissionError("provider invocation settlement conflicted")

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

    def _compare_and_swap_binding_in_transaction(
        self,
        conn: sqlite3.Connection,
        expected: ProviderWorkBindingFence,
        replacement: ProviderWorkBinding,
    ) -> ProviderWorkBindingWriteResult:
        """Compose a validated binding transition into a larger transaction."""

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            raise ValueError("binding transition requires an active SQLite transaction")
        return _Transaction(conn).compare_and_swap(expected, replacement)

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

    def validate_worker_runtime_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        binding_id: str,
        binding_generation: int,
        binding_digest: str,
        owner_user_id: str,
        universe_id: str,
        daemon_id: str,
        runtime_id: str,
        worker_id: str,
    ) -> bool:
        """Validate exact requester provider and physical runtime in one fence."""
        try:
            binding_row = conn.execute(
                "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            runtime_row = conn.execute(
                "SELECT * FROM author_runtime_instances WHERE instance_id = ?",
                (runtime_id,),
            ).fetchone()
            if binding_row is None or runtime_row is None:
                return False
            binding = _record(binding_row)
            metadata = json.loads(str(runtime_row["metadata_json"]))
            expires_at = datetime.fromisoformat(
                binding.expires_at.removesuffix("Z") + "+00:00"
            )
            now = self._clock().astimezone(timezone.utc)
        except (TypeError, ValueError, json.JSONDecodeError, sqlite3.Error):
            return False
        return all(
            (
                binding.state is ProviderWorkBindingState.ACTIVE,
                binding.binding_id == binding_id,
                binding.generation == binding_generation,
                binding.binding_digest == binding_digest,
                binding.owner_user_id == owner_user_id,
                binding.universe_id == universe_id,
                expires_at > now,
                runtime_row["universe_id"] == universe_id,
                runtime_row["provider_name"] == binding.provider,
                runtime_row["status"] == "provisioned",
                isinstance(metadata, dict),
                str(metadata.get("daemon_id") or "") == daemon_id,
                str(metadata.get("worker_id") or "") == worker_id,
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
