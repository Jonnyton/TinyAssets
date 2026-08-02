"""SQLite owner for the dark agent-invocation admission aggregate."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.agent_invocation_authority import (
    AgentInvocationEvent,
    AgentInvocationEventState,
    AgentInvocationRoot,
)
from tinyassets.agent_runtime_command import (
    AgentInvocationBudgetEnvelope,
    AgentInvocationCommand,
)
from tinyassets.agent_runtime_grants import AgentRuntimeGrantResolver
from tinyassets.agent_runtime_invocation import (
    AgentInvocationAdmissionBlocked,
    AgentInvocationAdmissionOutcome,
    AgentInvocationAdmissionResult,
    AgentInvocationConflict,
    AgentInvocationExternalAuthorityFenceSource,
    AgentInvocationExternalAuthoritySnapshot,
    _AgentInvocationStoreGrant,
    _consume_store_grant,
    _digest,
)
from tinyassets.agent_runtime_principal import AgentInvocationAuthorityEvidence
from tinyassets.ids import new_ulid
from tinyassets.provider_work_authority import (
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBinding,
)
from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore
from tinyassets.storage.agent_runtime_commands import (
    _SCHEMA as _COMMAND_SCHEMA,
)
from tinyassets.storage.agent_runtime_commands import (
    _command as _canonical_command,
)
from tinyassets.storage.agent_runtime_invocations import (
    _SCHEMA as _ROOT_SCHEMA,
)
from tinyassets.storage.agent_runtime_invocations import (
    _event as _canonical_event,
)
from tinyassets.storage.agent_runtime_invocations import (
    _root as _canonical_root,
)
from tinyassets.storage.agent_runtime_invocations import (
    _validated_chain,
)
from tinyassets.storage.automation_activations import AutomationActivationStore
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
)

_SCHEMA = _COMMAND_SCHEMA + _ROOT_SCHEMA


class SQLiteAgentInvocationExternalAuthorityFenceSource:
    """Validate every canonical external authority in the admission write lock."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        grant_resolver: AgentRuntimeGrantResolver,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(grant_resolver, AgentRuntimeGrantResolver):
            raise ValueError("grant_resolver must be server-owned")
        self._grant_resolver = grant_resolver
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._manifest_store = AgentRuntimeManifestStore(base_path)
        self._provider_store = SQLiteProviderWorkAuthorityStore(
            base_path,
            clock=self._clock,
        )
        with self._manifest_store.connection():
            pass

    def validate_current_in_transaction(
        self,
        connection: object,
        snapshot: AgentInvocationExternalAuthoritySnapshot,
        binding: ProviderWorkBinding,
    ) -> bool:
        if not isinstance(connection, sqlite3.Connection) or not connection.in_transaction:
            return False
        try:
            manifest = AgentRuntimeManifestStore.resolve_current_in_transaction(
                connection,
                owner_user_id=snapshot.owner_user_id,
                manifest_id=snapshot.manifest_id,
                manifest_digest=snapshot.manifest_digest,
            )
            if manifest is None:
                return False
            content = manifest.manifest_input.to_dict()
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                return False
            grants = self._grant_resolver.resolve_in_transaction(
                manifest,
                connection,
                evaluated_at=now.timestamp(),
            )
        except Exception:
            return False
        return all(
            (
                content["universe_id"] == snapshot.universe_id,
                content["agent_binding_id"] == snapshot.agent_binding_id,
                grants.ready,
                grants.evidence == snapshot.grant_evidence,
                grants.evidence_set_digest == snapshot.grant_evidence_set_digest,
                self._provider_store.validate_in_transaction(
                    connection,
                    binding_id=binding.binding_id,
                    binding_generation=binding.generation,
                    binding_digest=binding.binding_digest,
                    owner_user_id=snapshot.owner_user_id,
                    universe_id=snapshot.universe_id,
                    provider=snapshot.provider,
                    operation="agent_invocation",
                    role="agent_runtime",
                ),
                binding.assignment_generation == snapshot.assignment_generation,
                binding.assignment_digest == snapshot.assignment_digest,
                binding.credential_reference_digest == snapshot.credential_reference_digest,
            )
        )


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _command_record(row: sqlite3.Row) -> AgentInvocationCommand:
    return _canonical_command(row)


def _invocation_record(row: sqlite3.Row) -> AgentInvocationRoot:
    return _canonical_root(row)


def _record_json(record: object) -> str:
    return json.dumps(
        record.to_dict(),  # type: ignore[attr-defined]
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _current_event(
    conn: sqlite3.Connection,
    invocation: AgentInvocationRoot,
) -> AgentInvocationEvent:
    rows = conn.execute(
        """
        SELECT * FROM agent_runtime_invocation_events
        WHERE invocation_id = ? ORDER BY generation ASC
        """,
        (invocation.invocation_id,),
    ).fetchall()
    events = tuple(_canonical_event(row) for row in rows)
    _validated_chain(invocation, events)
    return events[-1]


class SQLiteAgentRuntimeInvocationStore:
    """Atomic persistence and bearer-free current invocation evidence."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        external_authority_fence_source: AgentInvocationExternalAuthorityFenceSource,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if self._busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        if not isinstance(
            external_authority_fence_source,
            AgentInvocationExternalAuthorityFenceSource,
        ):
            raise ValueError("external_authority_fence_source must be server-owned")
        self._external_authority_fence_source = external_authority_fence_source
        self._provider_store = SQLiteProviderWorkAuthorityStore(
            base_path,
            busy_timeout_ms=busy_timeout_ms,
            clock=self._clock,
        )
        with self.connection():
            pass

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._provider_store.connection() as conn:
            conn.executescript(_SCHEMA)
            yield conn

    def admit(
        self,
        grant: _AgentInvocationStoreGrant,
    ) -> AgentInvocationAdmissionResult:
        payload = _consume_store_grant(grant)
        manifest_content = payload.manifest.manifest_input.to_dict()
        activation = payload.activation
        if (
            activation.subject is None
            or activation.executor_class is None
            or activation.lease_id is None
        ):
            raise AgentInvocationAdmissionBlocked(
                "activation_not_current",
                "the exact cloud agent activation is not current",
            )
        now = self._clock()
        created_at = _timestamp(now)
        expires_at = datetime.fromisoformat(
            payload.provider_seed.expires_at.removesuffix("Z") + "+00:00"
        )
        if expires_at <= now.astimezone(timezone.utc):
            raise AgentInvocationAdmissionBlocked(
                "provider_assignment_expired",
                "the requester-owned provider assignment is expired",
            )
        key_digest = _digest(
            {
                "authorizing_subject_id": payload.owner_user_id,
                "idempotency_key": payload.idempotency_key,
            }
        )

        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                activation_current = AutomationActivationStore.validate_claim_in_transaction(
                    conn,
                    universe_id=activation.universe_id,
                    automation_id=activation.automation_id,
                    epoch=activation.epoch,
                    executor_class=activation.executor_class,
                    subject=activation.subject,
                    lease_id=activation.lease_id,
                )
                if not activation_current:
                    raise AgentInvocationAdmissionBlocked(
                        "activation_not_current",
                        "the exact cloud agent activation changed before admission",
                    )
                binding_result = self._provider_store._issue_binding_in_transaction(
                    conn,
                    payload.provider_seed,
                )
                if (
                    binding_result.outcome
                    not in {
                        ProviderWorkAuthorityWriteOutcome.APPLIED,
                        ProviderWorkAuthorityWriteOutcome.REPLAYED,
                    }
                    or binding_result.record is None
                ):
                    raise AgentInvocationAdmissionBlocked(
                        "provider_binding_conflict",
                        "the requester-owned provider binding could not be linked",
                    )
                binding = binding_result.record
                if not self._external_authority_fence_source.validate_current_in_transaction(
                    conn,
                    payload.external_authority_snapshot,
                    binding,
                ):
                    raise AgentInvocationAdmissionBlocked(
                        "authority_changed",
                        "agent invocation external authority is not current",
                    )
                request_digest = _digest(
                    {
                        "schema_version": 1,
                        "authorizing_subject_id": payload.owner_user_id,
                        "authorizing_grant_generation": payload.authorizing_grant_generation,
                        "universe_id": manifest_content["universe_id"],
                        "agent_binding_id": manifest_content["agent_binding_id"],
                        "binding_revision": manifest_content["binding_revision"],
                        "execution_subject": activation.subject.to_dict(),
                        "activation_automation_id": activation.automation_id,
                        "activation_epoch": activation.epoch,
                        "executor_class": activation.executor_class.value,
                        "lease_id": activation.lease_id,
                        "typed_input_digest": payload.typed_input_digest,
                        "provider_work_binding_id": binding.binding_id,
                        "provider_work_binding_generation": binding.generation,
                        "provider_work_binding_digest": binding.binding_digest,
                        "max_tokens": payload.max_tokens,
                        "max_cost_microunits": payload.max_cost_microunits,
                    }
                )
                existing = conn.execute(
                    """
                    SELECT * FROM agent_runtime_invocation_commands
                    WHERE authorizing_subject_id = ? AND universe_id = ?
                      AND json_extract(record_json, '$.idempotency_key_digest') = ?
                    """,
                    (payload.owner_user_id, manifest_content["universe_id"], key_digest),
                ).fetchone()
                if existing is not None:
                    command = _command_record(existing)
                    if command.request_digest != request_digest:
                        raise AgentInvocationConflict(
                            "idempotency_key was already used for different invocation input"
                        )
                    invocation_row = conn.execute(
                        "SELECT * FROM agent_runtime_invocation_roots WHERE invocation_id = ?",
                        (command.invocation_id,),
                    ).fetchone()
                    if invocation_row is None:
                        raise ValueError("persisted agent invocation aggregate is incomplete")
                    invocation = _invocation_record(invocation_row)
                    event = _current_event(conn, invocation)
                    if event.state is not AgentInvocationEventState.ADMITTED:
                        raise AgentInvocationConflict("idempotent invocation is no longer admitted")
                    final_activation_current = (
                        AutomationActivationStore.validate_claim_in_transaction(
                            conn,
                            universe_id=activation.universe_id,
                            automation_id=activation.automation_id,
                            epoch=activation.epoch,
                            executor_class=activation.executor_class,
                            subject=activation.subject,
                            lease_id=activation.lease_id,
                        )
                    )
                    if not final_activation_current:
                        raise AgentInvocationAdmissionBlocked(
                            "authority_changed",
                            "agent invocation activation changed during atomic replay",
                        )
                    conn.commit()
                    return AgentInvocationAdmissionResult(
                        outcome=AgentInvocationAdmissionOutcome.REPLAYED,
                        binding=binding,
                        command=command,
                        invocation=invocation,
                    )

                invocation_id = f"agent_invocation_{new_ulid()}"
                budget = AgentInvocationBudgetEnvelope.build(
                    max_invocations=1,
                    max_tokens=payload.max_tokens,
                    max_cost_microunits=payload.max_cost_microunits,
                    max_turns=1,
                    expires_at=payload.provider_seed.expires_at,
                )
                command = AgentInvocationCommand.build(
                    schema_version=1,
                    command_id=f"agent_invocation_command_{new_ulid()}",
                    generation=1,
                    invocation_id=invocation_id,
                    authorizing_subject_id=payload.owner_user_id,
                    authorizing_grant_generation=payload.authorizing_grant_generation,
                    universe_id=str(manifest_content["universe_id"]),
                    agent_binding_id=str(manifest_content["agent_binding_id"]),
                    binding_revision=int(manifest_content["binding_revision"]),
                    execution_subject=activation.subject,
                    activation_automation_id=activation.automation_id,
                    activation_epoch=activation.epoch,
                    executor_class=activation.executor_class,
                    lease_id=activation.lease_id,
                    typed_input_digest=payload.typed_input_digest,
                    provider_work_binding_id=binding.binding_id,
                    provider_work_binding_generation=binding.generation,
                    provider_work_binding_digest=binding.binding_digest,
                    idempotency_key_digest=key_digest,
                    request_digest=request_digest,
                    budget=budget,
                    admission_witness_id=payload.admission_witness_id,
                    admission_witness_digest=payload.admission_witness_digest,
                    created_at=created_at,
                )
                invocation = AgentInvocationRoot.build(
                    schema_version=1,
                    invocation_id=invocation_id,
                    authorizing_subject_id=command.authorizing_subject_id,
                    authorizing_grant_generation=command.authorizing_grant_generation,
                    universe_id=command.universe_id,
                    agent_binding_id=command.agent_binding_id,
                    binding_revision=command.binding_revision,
                    execution_subject=command.execution_subject,
                    activation_automation_id=command.activation_automation_id,
                    activation_epoch=command.activation_epoch,
                    executor_class=command.executor_class,
                    lease_id=command.lease_id,
                    typed_input_digest=command.typed_input_digest,
                    command_id=command.command_id,
                    command_generation=command.generation,
                    command_digest=command.command_digest,
                    provider_work_binding_id=command.provider_work_binding_id,
                    provider_work_binding_generation=command.provider_work_binding_generation,
                    provider_work_binding_digest=command.provider_work_binding_digest,
                    idempotency_key_digest=command.idempotency_key_digest,
                    request_digest=command.request_digest,
                    budget_digest=command.budget.budget_digest,
                    admission_witness_id=command.admission_witness_id,
                    admission_witness_digest=command.admission_witness_digest,
                    created_at=created_at,
                )
                event = AgentInvocationEvent.build(
                    schema_version=1,
                    event_id=f"agent_invocation_event_{new_ulid()}",
                    invocation_id=invocation.invocation_id,
                    generation=1,
                    state=AgentInvocationEventState.ADMITTED,
                    previous_event_digest=None,
                    root_digest=invocation.root_digest,
                    reason_code=None,
                    occurred_at=created_at,
                )
                conn.execute(
                    """
                    INSERT INTO agent_runtime_invocation_commands (
                        command_id, invocation_id, authorizing_subject_id,
                        universe_id, agent_binding_id, provider_work_binding_id,
                        admission_witness_id, command_digest, record_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        command.command_id,
                        command.invocation_id,
                        command.authorizing_subject_id,
                        command.universe_id,
                        command.agent_binding_id,
                        command.provider_work_binding_id,
                        command.admission_witness_id,
                        command.command_digest,
                        _record_json(command),
                        command.created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO agent_runtime_invocation_roots (
                        invocation_id, authorizing_subject_id, universe_id,
                        agent_binding_id, command_id, provider_work_binding_id,
                        admission_witness_id, root_digest, record_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invocation.invocation_id,
                        invocation.authorizing_subject_id,
                        invocation.universe_id,
                        invocation.agent_binding_id,
                        invocation.command_id,
                        invocation.provider_work_binding_id,
                        invocation.admission_witness_id,
                        invocation.root_digest,
                        _record_json(invocation),
                        invocation.created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO agent_runtime_invocation_events (
                        event_id, invocation_id, generation, state,
                        previous_event_digest, root_digest, event_digest,
                        record_json, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.invocation_id,
                        event.generation,
                        event.state.value,
                        event.previous_event_digest,
                        event.root_digest,
                        event.event_digest,
                        _record_json(event),
                        event.occurred_at,
                    ),
                )
                final_activation_current = AutomationActivationStore.validate_claim_in_transaction(
                    conn,
                    universe_id=activation.universe_id,
                    automation_id=activation.automation_id,
                    epoch=activation.epoch,
                    executor_class=activation.executor_class,
                    subject=activation.subject,
                    lease_id=activation.lease_id,
                )
                if not final_activation_current:
                    raise AgentInvocationAdmissionBlocked(
                        "authority_changed",
                        "agent invocation activation changed during atomic admission",
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return AgentInvocationAdmissionResult(
            outcome=AgentInvocationAdmissionOutcome.APPLIED,
            binding=binding,
            command=command,
            invocation=invocation,
        )

    def get(
        self,
        *,
        invocation_id: str,
    ) -> tuple[AgentInvocationCommand, AgentInvocationRoot, AgentInvocationEvent] | None:
        with self.connection() as conn:
            conn.execute("BEGIN")
            return self.get_in_transaction(conn, invocation_id=invocation_id)

    @staticmethod
    def get_in_transaction(
        conn: sqlite3.Connection,
        *,
        invocation_id: str,
    ) -> tuple[AgentInvocationCommand, AgentInvocationRoot, AgentInvocationEvent] | None:
        """Read and integrity-check one aggregate inside the caller's fence."""

        if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
            return None
        invocation_row = conn.execute(
            "SELECT * FROM agent_runtime_invocation_roots WHERE invocation_id = ?",
            (invocation_id,),
        ).fetchone()
        if invocation_row is None:
            return None
        invocation = _invocation_record(invocation_row)
        event = _current_event(conn, invocation)
        command_row = conn.execute(
            "SELECT * FROM agent_runtime_invocation_commands WHERE command_id = ?",
            (invocation.command_id,),
        ).fetchone()
        if command_row is None:
            raise ValueError("persisted agent invocation aggregate is incomplete")
        command = _command_record(command_row)
        exact = (
            command.invocation_id == invocation.invocation_id,
            command.generation == invocation.command_generation,
            command.command_digest == invocation.command_digest,
            command.provider_work_binding_id == invocation.provider_work_binding_id,
            command.provider_work_binding_generation == invocation.provider_work_binding_generation,
            command.provider_work_binding_digest == invocation.provider_work_binding_digest,
            command.budget.budget_digest == invocation.budget_digest,
            command.admission_witness_id == invocation.admission_witness_id,
            command.admission_witness_digest == invocation.admission_witness_digest,
        )
        if not all(exact):
            raise ValueError("persisted agent invocation aggregate failed linkage validation")
        return command, invocation, event

    def resolve_current(
        self,
        *,
        invocation_id: str,
    ) -> AgentInvocationAuthorityEvidence | None:
        aggregate = self.get(invocation_id=invocation_id)
        if aggregate is None:
            return None
        command, invocation, event = aggregate
        if event.state is not AgentInvocationEventState.ADMITTED:
            return None
        return AgentInvocationAuthorityEvidence(
            invocation_id=invocation.invocation_id,
            invocation_generation=event.generation,
            authorizing_subject_id=command.authorizing_subject_id,
            universe_id=command.universe_id,
            agent_binding_id=command.agent_binding_id,
            binding_revision=command.binding_revision,
            execution_subject=command.execution_subject,
            activation_automation_id=command.activation_automation_id,
            activation_epoch=command.activation_epoch,
            executor_class=command.executor_class,
            lease_id=command.lease_id,
            typed_input_digest=command.typed_input_digest,
        )


__all__ = [
    "SQLiteAgentInvocationExternalAuthorityFenceSource",
    "SQLiteAgentRuntimeInvocationStore",
]
