"""Atomic handoff from an admitted custom-agent invocation to provider work."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from tinyassets.agent_runtime_grants import AgentRuntimeGrantResolver
from tinyassets.agent_runtime_invocation import AgentInvocationState
from tinyassets.agent_runtime_principal import AgentRuntimePrincipal
from tinyassets.provider_work_authority import (
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkRoot,
    ProviderWorkBindingState,
    ProviderWorkReceiptWriteResult,
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


class AgentRuntimeProviderExecutionService:
    """Mint one replay-safe provider receipt under one SQLite authority fence."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        grant_resolver: AgentRuntimeGrantResolver,
        clock: Callable[[], datetime] | None = None,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        if not isinstance(grant_resolver, AgentRuntimeGrantResolver):
            raise ValueError("grant_resolver must be server-owned")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.grant_resolver = grant_resolver
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
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise AgentRuntimeProviderExecutionBlocked("server clock is unavailable")
        now = now.astimezone(timezone.utc)
        with self.invocation_store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = self._issue_in_transaction(
                    conn,
                    invocation_id=invocation_id,
                    evaluated_at=now.timestamp(),
                )
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    def _issue_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        invocation_id: str,
        evaluated_at: float,
    ) -> ProviderWorkReceiptWriteResult:
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
            actor_id=invocation.invocation_id,
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
        return self.provider_store._issue_universe_receipt_in_transaction(
            conn,
            authority,
        )


__all__ = [
    "AgentRuntimeProviderExecutionBlocked",
    "AgentRuntimeProviderExecutionService",
]
