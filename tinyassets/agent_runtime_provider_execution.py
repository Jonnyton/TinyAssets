"""Atomic handoff from an admitted custom-agent invocation to provider work."""

from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from tinyassets.agent_runtime_grants import AgentRuntimeGrantResolver
from tinyassets.agent_runtime_invocation import AgentInvocationState
from tinyassets.agent_runtime_principal import AgentRuntimePrincipal
from tinyassets.provider_work_authority import (
    ProviderInvocationCarrier,
    ProviderInvocationReservationWriteResult,
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkRoot,
    ProviderWorkBindingRoot,
    ProviderWorkBindingSeed,
    ProviderWorkBindingState,
    ProviderWorkExecutionClaimWriteResult,
    ProviderWorkReceiptWriteResult,
    ProviderWorkTransactionalBindingResolver,
    _mint_provider_invocation_carrier,
)
from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore
from tinyassets.storage.agent_runtime_invocation import (
    SQLiteAgentInvocationExternalAuthorityFenceSource,
    SQLiteAgentRuntimeInvocationStore,
)
from tinyassets.storage.automation_activations import AutomationActivationStore
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
)


class AgentRuntimeProviderExecutionBlocked(PermissionError):
    """Raised when admitted work no longer has exact current authority."""


class _AgentProviderReceiptStoreGrant:
    """One-shot, process-local proof that the agent authority fence passed."""

    __slots__ = ("_grant_id", "_issuer_pid", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("agent provider receipt grants are service-issued")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("agent provider receipt grants are immutable")

    def __reduce__(self):
        raise TypeError("agent provider receipt grants are non-serializable")

    def _resolve(self, *, consume: bool) -> ProviderUniverseWorkAuthority:
        if type(self) is not _AgentProviderReceiptStoreGrant:
            raise PermissionError("agent provider receipt grant is not service-issued")
        current_pid = os.getpid()
        if self._issuer_pid != current_pid:
            raise PermissionError("agent provider receipt grant belongs to another process")
        with _RECEIPT_GRANT_LOCK:
            entry = _ACTIVE_RECEIPT_GRANTS.get(self._grant_id)
            if entry is None or entry[0]() is not self or entry[2] != current_pid:
                raise PermissionError("agent provider receipt grant is invalid or consumed")
            if consume:
                del _ACTIVE_RECEIPT_GRANTS[self._grant_id]
        return entry[1]

    def _peek(self) -> ProviderUniverseWorkAuthority:
        return self._resolve(consume=False)

    def _consume(self) -> ProviderUniverseWorkAuthority:
        return self._resolve(consume=True)

    def _discard(self) -> None:
        if type(self) is not _AgentProviderReceiptStoreGrant:
            raise PermissionError("agent provider receipt grant is not service-issued")
        _discard_receipt_grant(self._grant_id, self._issuer_pid)


_RECEIPT_GRANT_LOCK = threading.Lock()
_ACTIVE_RECEIPT_GRANTS: dict[
    str,
    tuple[
        weakref.ReferenceType[_AgentProviderReceiptStoreGrant],
        ProviderUniverseWorkAuthority,
        int,
    ],
] = {}


def _reset_receipt_grants_after_fork() -> None:
    global _RECEIPT_GRANT_LOCK
    global _ACTIVE_RECEIPT_GRANTS
    _RECEIPT_GRANT_LOCK = threading.Lock()
    _ACTIVE_RECEIPT_GRANTS = {}


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_receipt_grants_after_fork)


def _discard_receipt_grant(grant_id: str, issuer_pid: int) -> None:
    if issuer_pid != os.getpid():
        return
    with _RECEIPT_GRANT_LOCK:
        _ACTIVE_RECEIPT_GRANTS.pop(grant_id, None)


class AgentRuntimeProviderExecutionService:
    """Mint one replay-safe provider receipt under one SQLite authority fence."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        grant_resolver: AgentRuntimeGrantResolver,
        provider_binding_resolver: ProviderWorkTransactionalBindingResolver,
        clock: Callable[[], datetime] | None = None,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        if not isinstance(grant_resolver, AgentRuntimeGrantResolver):
            raise ValueError("grant_resolver must be server-owned")
        if not isinstance(
            provider_binding_resolver,
            ProviderWorkTransactionalBindingResolver,
        ):
            raise ValueError("provider_binding_resolver must be transactional")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.grant_resolver = grant_resolver
        self.provider_binding_resolver = provider_binding_resolver
        self.provider_store = SQLiteProviderWorkAuthorityStore(
            base_path,
            busy_timeout_ms=busy_timeout_ms,
            clock=self._clock,
        )
        external_authority_fence_source = (
            SQLiteAgentInvocationExternalAuthorityFenceSource(
                base_path,
                grant_resolver=grant_resolver,
                clock=self._clock,
            )
        )
        self.invocation_store = SQLiteAgentRuntimeInvocationStore(
            base_path,
            external_authority_fence_source=external_authority_fence_source,
            busy_timeout_ms=busy_timeout_ms,
            clock=self._clock,
        )

    def issue_receipt(self, invocation_id: str) -> ProviderWorkReceiptWriteResult:
        result = self._transition(invocation_id, transition="receipt")
        assert isinstance(result, ProviderWorkReceiptWriteResult)
        return result

    def claim(self, invocation_id: str) -> ProviderWorkExecutionClaimWriteResult:
        result = self._transition(invocation_id, transition="claim")
        assert isinstance(result, ProviderWorkExecutionClaimWriteResult)
        return result

    def reserve(self, invocation_id: str) -> ProviderInvocationReservationWriteResult:
        result = self._transition(invocation_id, transition="reserve")
        assert isinstance(result, ProviderInvocationReservationWriteResult)
        return result

    def arm_launch(self, invocation_id: str) -> ProviderInvocationCarrier:
        result = self._transition(invocation_id, transition="launch")
        assert isinstance(result, ProviderInvocationReservationWriteResult)
        if result.outcome.value == "replayed":
            raise PermissionError("provider invocation reservation is already armed")
        if (
            result.outcome.value != "applied"
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

    def _transition(
        self,
        invocation_id: str,
        *,
        transition: Literal["receipt", "claim", "reserve", "launch"],
    ) -> object:
        with self.invocation_store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = self._clock()
                if now.tzinfo is None or now.utcoffset() is None:
                    raise AgentRuntimeProviderExecutionBlocked(
                        "server clock is unavailable"
                    )
                now = now.astimezone(timezone.utc)
                store_grant = self._validated_store_grant(
                    conn,
                    invocation_id=invocation_id,
                    evaluated_at=now.timestamp(),
                )
                if transition == "receipt":
                    result = self.provider_store._issue_universe_receipt_in_transaction(
                        conn,
                        store_grant,
                    )
                elif transition == "claim":
                    result = self.provider_store._claim_agent_in_transaction(
                        conn,
                        store_grant,
                    )
                elif transition == "reserve":
                    result = self.provider_store._reserve_agent_in_transaction(
                        conn,
                        store_grant,
                    )
                else:
                    result = self.provider_store._arm_agent_launch_in_transaction(
                        conn,
                        store_grant,
                    )
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    def _validated_store_grant(
        self,
        conn: sqlite3.Connection,
        *,
        invocation_id: str,
        evaluated_at: float,
    ) -> _AgentProviderReceiptStoreGrant:
        try:
            aggregate = self.invocation_store.get_in_transaction(
                conn,
                invocation_id=invocation_id,
            )
        except (TypeError, ValueError):
            raise AgentRuntimeProviderExecutionBlocked(
                "agent invocation integrity validation failed"
            ) from None
        if aggregate is None:
            raise AgentRuntimeProviderExecutionBlocked("agent invocation is not current")
        command, invocation = aggregate
        if invocation.state is not AgentInvocationState.ADMITTED:
            raise AgentRuntimeProviderExecutionBlocked("agent invocation is not admitted")

        manifest = AgentRuntimeManifestStore.resolve_current_in_transaction(
            conn,
            owner_user_id=command.authorizing_subject_id,
            manifest_id=command.execution_subject.ref,
            manifest_digest=command.execution_subject.digest,
        )
        if manifest is None:
            raise AgentRuntimeProviderExecutionBlocked("agent manifest is not current")
        if not AutomationActivationStore.validate_claim_in_transaction(
            conn,
            universe_id=command.universe_id,
            automation_id=command.activation_automation_id,
            epoch=command.activation_epoch,
            executor_class=command.executor_class,
            subject=command.execution_subject,
            lease_id=command.lease_id,
        ):
            raise AgentRuntimeProviderExecutionBlocked("agent activation is not current")

        grants = self.grant_resolver.resolve_in_transaction(
            manifest,
            conn,
            evaluated_at=evaluated_at,
        )
        if not grants.ready:
            raise AgentRuntimeProviderExecutionBlocked("agent grant is not current")
        principal = AgentRuntimePrincipal(
            authorizing_subject_id=command.authorizing_subject_id,
            universe_id=command.universe_id,
            agent_binding_id=command.agent_binding_id,
            binding_revision=command.binding_revision,
            execution_subject=command.execution_subject,
            activation_automation_id=command.activation_automation_id,
            activation_epoch=command.activation_epoch,
            executor_class=command.executor_class,
            lease_id=command.lease_id,
            invocation_id=invocation.invocation_id,
            invocation_generation=invocation.generation,
            typed_input_digest=command.typed_input_digest,
            evaluated_at=command.grant_evaluated_at,
            grant_evidence=tuple(grants.evidence),
            grant_evidence_set_digest=grants.evidence_set_digest,
        )
        if (
            grants.evidence_set_digest != command.grant_evidence_set_digest
            or principal.principal_digest != command.authorizing_principal_digest
        ):
            raise AgentRuntimeProviderExecutionBlocked("agent principal is not current")

        binding = self.provider_store.get_binding_in_transaction(
            conn,
            binding_id=command.provider_work_binding_id,
        )
        if binding is None:
            raise AgentRuntimeProviderExecutionBlocked("provider binding is not current")
        assignment_root = ProviderWorkBindingRoot(
            owner_user_id=command.authorizing_subject_id,
            universe_id=command.universe_id,
            provider=command.provider,
        )
        try:
            assignment = self.provider_binding_resolver.resolve_current_in_transaction(
                conn,
                assignment_root,
            )
        except Exception:
            raise AgentRuntimeProviderExecutionBlocked(
                "provider assignment source is unavailable"
            ) from None
        if type(assignment) is not ProviderWorkBindingSeed:
            raise AgentRuntimeProviderExecutionBlocked(
                "provider assignment is not current"
            )
        binding_matches = (
            binding.state is ProviderWorkBindingState.ACTIVE,
            binding.generation == command.provider_work_binding_generation,
            binding.binding_digest == command.provider_work_binding_digest,
            binding.owner_user_id == command.authorizing_subject_id,
            binding.universe_id == command.universe_id,
            binding.provider == command.provider,
            "agent_invocation" in binding.allowed_operations,
            "agent_runtime" in binding.allowed_roles,
            binding.max_invocations >= 1,
            binding.max_tokens >= command.max_tokens,
            binding.max_cost_microunits >= command.max_cost_microunits,
            assignment.owner_user_id == binding.owner_user_id,
            assignment.universe_id == binding.universe_id,
            assignment.provider == binding.provider,
            assignment.credential_reference_digest
            == binding.credential_reference_digest,
            assignment.allowed_operations == binding.allowed_operations,
            assignment.allowed_roles == binding.allowed_roles,
            assignment.assignment_generation == binding.assignment_generation,
            assignment.assignment_digest == binding.assignment_digest,
            assignment.max_invocations == binding.max_invocations,
            assignment.max_tokens == binding.max_tokens,
            assignment.max_cost_microunits == binding.max_cost_microunits,
            assignment.expires_at == binding.expires_at,
        )
        if not all(binding_matches):
            raise AgentRuntimeProviderExecutionBlocked("provider binding is not current")

        authority = ProviderUniverseWorkAuthority(
            root=ProviderUniverseWorkRoot(
                work_item_kind="agent_invocation",
                work_item_id=invocation.invocation_id,
            ),
            binding=binding,
            principal_id=principal.principal_digest,
            actor_id=command.lease_id,
            operation="agent_invocation",
            role="agent_runtime",
            executor_class="cloud",
            max_invocations=1,
            max_tokens=command.max_tokens,
            max_cost_microunits=command.max_cost_microunits,
            expires_at=binding.expires_at,
            execution_subject=command.execution_subject,
            agent_invocation_command_id=command.command_id,
            agent_invocation_command_digest=command.command_digest,
            agent_invocation_generation=invocation.generation,
        )
        # Keep minting inline after every authority check. A module-level or
        # store-level mint helper would let a lower-level caller launder a
        # fabricated authority object around this sole issuance owner.
        grant_id = secrets.token_hex(32)
        issuer_pid = os.getpid()
        store_grant = object.__new__(_AgentProviderReceiptStoreGrant)
        object.__setattr__(store_grant, "_grant_id", grant_id)
        object.__setattr__(store_grant, "_issuer_pid", issuer_pid)
        with _RECEIPT_GRANT_LOCK:
            _ACTIVE_RECEIPT_GRANTS[grant_id] = (
                weakref.ref(store_grant),
                authority,
                issuer_pid,
            )
        weakref.finalize(
            store_grant,
            _discard_receipt_grant,
            grant_id,
            issuer_pid,
        )
        return store_grant


__all__ = [
    "AgentRuntimeProviderExecutionBlocked",
    "AgentRuntimeProviderExecutionService",
]
