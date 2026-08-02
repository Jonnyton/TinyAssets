"""SQLite owner for the dark agent-invocation admission aggregate."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.agent_runtime_invocation import (
    AgentInvocation,
    AgentInvocationAdmissionBlocked,
    AgentInvocationAdmissionOutcome,
    AgentInvocationAdmissionResult,
    AgentInvocationCommand,
    AgentInvocationConflict,
    AgentInvocationState,
    _AgentInvocationStoreGrant,
    _consume_store_grant,
    _digest,
)
from tinyassets.agent_runtime_principal import (
    AgentInvocationAuthorityEvidence,
    AgentRuntimePrincipal,
)
from tinyassets.ids import new_ulid
from tinyassets.provider_work_authority import ProviderWorkAuthorityWriteOutcome
from tinyassets.storage.automation_activations import AutomationActivationStore
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
)

_PLACEHOLDER_DIGEST = f"sha256:{'0' * 64}"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_invocation_commands (
    command_id TEXT PRIMARY KEY,
    command_digest TEXT NOT NULL UNIQUE,
    invocation_id TEXT NOT NULL UNIQUE,
    owner_user_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    agent_binding_id TEXT NOT NULL,
    idempotency_key_digest TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    provider_work_binding_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner_user_id, idempotency_key_digest),
    FOREIGN KEY(provider_work_binding_id)
        REFERENCES provider_work_bindings(binding_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_invocation_command_target
ON agent_invocation_commands(owner_user_id, universe_id, agent_binding_id);

CREATE TABLE IF NOT EXISTS agent_invocations (
    invocation_id TEXT PRIMARY KEY,
    invocation_digest TEXT NOT NULL UNIQUE,
    generation INTEGER NOT NULL CHECK(generation >= 1),
    state TEXT NOT NULL CHECK(state IN ('admitted')),
    command_id TEXT NOT NULL UNIQUE,
    command_digest TEXT NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(command_id) REFERENCES agent_invocation_commands(command_id)
);

CREATE TABLE IF NOT EXISTS agent_invocation_events (
    event_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK(generation >= 1),
    event_digest TEXT NOT NULL UNIQUE,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(invocation_id, generation),
    FOREIGN KEY(invocation_id) REFERENCES agent_invocations(invocation_id)
);

CREATE TRIGGER IF NOT EXISTS trg_agent_invocation_commands_no_update
BEFORE UPDATE ON agent_invocation_commands BEGIN
    SELECT RAISE(ABORT, 'agent invocation commands are immutable');
END;
CREATE TRIGGER IF NOT EXISTS trg_agent_invocation_commands_no_delete
BEFORE DELETE ON agent_invocation_commands BEGIN
    SELECT RAISE(ABORT, 'agent invocation commands are immutable');
END;
CREATE TRIGGER IF NOT EXISTS trg_agent_invocations_no_update
BEFORE UPDATE ON agent_invocations BEGIN
    SELECT RAISE(ABORT, 'agent invocation roots are append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_agent_invocations_no_delete
BEFORE DELETE ON agent_invocations BEGIN
    SELECT RAISE(ABORT, 'agent invocation roots are append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_agent_invocation_events_no_update
BEFORE UPDATE ON agent_invocation_events BEGIN
    SELECT RAISE(ABORT, 'agent invocation events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS trg_agent_invocation_events_no_delete
BEFORE DELETE ON agent_invocation_events BEGIN
    SELECT RAISE(ABORT, 'agent invocation events are append-only');
END;
"""


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _command_record(row: sqlite3.Row) -> AgentInvocationCommand:
    try:
        command = AgentInvocationCommand.from_dict(json.loads(row["record_json"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted agent invocation command is invalid") from exc
    exact = (
        command.command_id == row["command_id"],
        command.command_digest == row["command_digest"],
        command.invocation_id == row["invocation_id"],
        command.authorizing_subject_id == row["owner_user_id"],
        command.universe_id == row["universe_id"],
        command.agent_binding_id == row["agent_binding_id"],
        command.idempotency_key_digest == row["idempotency_key_digest"],
        command.provider_work_binding_id == row["provider_work_binding_id"],
        command.created_at == row["created_at"],
        command.command_digest == command.expected_digest(),
    )
    if not all(exact):
        raise ValueError("persisted agent invocation command failed integrity validation")
    return command


def _invocation_record(row: sqlite3.Row) -> AgentInvocation:
    try:
        invocation = AgentInvocation.from_dict(json.loads(row["record_json"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted agent invocation root is invalid") from exc
    exact = (
        invocation.invocation_id == row["invocation_id"],
        invocation.invocation_digest == row["invocation_digest"],
        invocation.generation == row["generation"],
        invocation.state.value == row["state"],
        invocation.command_id == row["command_id"],
        invocation.command_digest == row["command_digest"],
        invocation.created_at == row["created_at"],
        invocation.invocation_digest == invocation.expected_digest(),
    )
    if not all(exact):
        raise ValueError("persisted agent invocation root failed integrity validation")
    return invocation


def _record_json(record: object) -> str:
    return json.dumps(
        record.to_dict(),  # type: ignore[attr-defined]
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _require_initial_event(
    conn: sqlite3.Connection,
    invocation: AgentInvocation,
) -> None:
    rows = conn.execute(
        """
        SELECT * FROM agent_invocation_events
        WHERE invocation_id = ? AND generation = 1
        """,
        (invocation.invocation_id,),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("persisted agent invocation initial event is missing")
    row = rows[0]
    try:
        event = json.loads(row["event_json"])
        stored_digest = event.pop("event_digest")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("persisted agent invocation event is invalid") from exc
    exact = (
        row["event_id"] == event.get("event_id"),
        row["invocation_id"] == invocation.invocation_id == event.get("invocation_id"),
        row["generation"] == invocation.generation == event.get("generation"),
        row["event_digest"] == stored_digest == _digest(event),
        event.get("state") == invocation.state.value,
        event.get("command_id") == invocation.command_id,
        event.get("command_digest") == invocation.command_digest,
        event.get("created_at") == invocation.created_at == row["created_at"],
    )
    if not all(exact):
        raise ValueError("persisted agent invocation event failed integrity validation")


class SQLiteAgentRuntimeInvocationStore:
    """Atomic persistence and bearer-free current invocation evidence."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_path = Path(base_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if self._busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
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
                if not payload.revalidate_external_authority():
                    raise AgentInvocationAdmissionBlocked(
                        "authority_changed",
                        "agent invocation authority changed before atomic admission",
                    )
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
                request_digest = _digest(
                    {
                        "authorizing_subject_id": payload.owner_user_id,
                        "universe_id": manifest_content["universe_id"],
                        "agent_binding_id": manifest_content["agent_binding_id"],
                        "binding_revision": manifest_content["binding_revision"],
                        "execution_subject": activation.subject.to_dict(),
                        "activation_automation_id": activation.automation_id,
                        "activation_epoch": activation.epoch,
                        "executor_class": activation.executor_class.value,
                        "lease_id": activation.lease_id,
                        "typed_input_digest": payload.typed_input_digest,
                        "grant_evidence_set_digest": payload.grants.evidence_set_digest,
                        "provider_work_binding_id": binding.binding_id,
                        "provider_work_binding_generation": binding.generation,
                        "provider_work_binding_digest": binding.binding_digest,
                        "max_tokens": payload.max_tokens,
                        "max_cost_microunits": payload.max_cost_microunits,
                    }
                )
                existing = conn.execute(
                    """
                    SELECT * FROM agent_invocation_commands
                    WHERE owner_user_id = ? AND idempotency_key_digest = ?
                    """,
                    (payload.owner_user_id, key_digest),
                ).fetchone()
                if existing is not None:
                    if existing["request_digest"] != request_digest:
                        raise AgentInvocationConflict(
                            "idempotency_key was already used for different invocation input"
                        )
                    command = _command_record(existing)
                    invocation_row = conn.execute(
                        "SELECT * FROM agent_invocations WHERE invocation_id = ?",
                        (command.invocation_id,),
                    ).fetchone()
                    if invocation_row is None:
                        raise ValueError("persisted agent invocation aggregate is incomplete")
                    invocation = _invocation_record(invocation_row)
                    _require_initial_event(conn, invocation)
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
                    if not final_activation_current or not payload.revalidate_external_authority():
                        raise AgentInvocationAdmissionBlocked(
                            "authority_changed",
                            "agent invocation authority changed during atomic replay",
                        )
                    conn.commit()
                    return AgentInvocationAdmissionResult(
                        outcome=AgentInvocationAdmissionOutcome.REPLAYED,
                        binding=binding,
                        command=command,
                        invocation=invocation,
                    )

                invocation_id = f"agent_invocation_{new_ulid()}"
                principal = AgentRuntimePrincipal(
                    authorizing_subject_id=payload.owner_user_id,
                    universe_id=str(manifest_content["universe_id"]),
                    agent_binding_id=str(manifest_content["agent_binding_id"]),
                    binding_revision=int(manifest_content["binding_revision"]),
                    execution_subject=activation.subject,
                    activation_automation_id=activation.automation_id,
                    activation_epoch=activation.epoch,
                    executor_class=activation.executor_class,
                    lease_id=activation.lease_id,
                    invocation_id=invocation_id,
                    invocation_generation=1,
                    typed_input_digest=payload.typed_input_digest,
                    evaluated_at=payload.grants.evaluated_at,
                    grant_evidence=tuple(payload.grants.evidence),
                    grant_evidence_set_digest=payload.grants.evidence_set_digest,
                )
                provisional_command = AgentInvocationCommand(
                    schema_version=1,
                    command_id=f"agent_invocation_command_{new_ulid()}",
                    command_digest=_PLACEHOLDER_DIGEST,
                    invocation_id=invocation_id,
                    invocation_generation=1,
                    authorizing_subject_id=payload.owner_user_id,
                    authorizing_principal_digest=principal.principal_digest,
                    grant_evidence_set_digest=payload.grants.evidence_set_digest,
                    grant_evaluated_at=payload.grants.evaluated_at,
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
                    provider=binding.provider,
                    max_tokens=payload.max_tokens,
                    max_cost_microunits=payload.max_cost_microunits,
                    idempotency_key_digest=key_digest,
                    created_at=created_at,
                )
                command = replace(
                    provisional_command,
                    command_digest=provisional_command.expected_digest(),
                )
                provisional_invocation = AgentInvocation(
                    schema_version=1,
                    invocation_id=invocation_id,
                    invocation_digest=_PLACEHOLDER_DIGEST,
                    generation=1,
                    state=AgentInvocationState.ADMITTED,
                    command_id=command.command_id,
                    command_digest=command.command_digest,
                    created_at=created_at,
                )
                invocation = replace(
                    provisional_invocation,
                    invocation_digest=provisional_invocation.expected_digest(),
                )
                event = {
                    "event_id": f"agent_invocation_event_{new_ulid()}",
                    "invocation_id": invocation.invocation_id,
                    "generation": invocation.generation,
                    "state": invocation.state.value,
                    "command_id": command.command_id,
                    "command_digest": command.command_digest,
                    "created_at": created_at,
                }
                event["event_digest"] = _digest(event)
                conn.execute(
                    """
                    INSERT INTO agent_invocation_commands (
                        command_id, command_digest, invocation_id, owner_user_id,
                        universe_id, agent_binding_id, idempotency_key_digest,
                        request_digest, provider_work_binding_id, record_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        command.command_id,
                        command.command_digest,
                        command.invocation_id,
                        command.authorizing_subject_id,
                        command.universe_id,
                        command.agent_binding_id,
                        command.idempotency_key_digest,
                        request_digest,
                        command.provider_work_binding_id,
                        _record_json(command),
                        command.created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO agent_invocations (
                        invocation_id, invocation_digest, generation, state,
                        command_id, command_digest, record_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invocation.invocation_id,
                        invocation.invocation_digest,
                        invocation.generation,
                        invocation.state.value,
                        invocation.command_id,
                        invocation.command_digest,
                        _record_json(invocation),
                        invocation.created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO agent_invocation_events (
                        event_id, invocation_id, generation, event_digest,
                        event_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_id"],
                        event["invocation_id"],
                        event["generation"],
                        event["event_digest"],
                        json.dumps(event, separators=(",", ":"), sort_keys=True),
                        event["created_at"],
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
                if not final_activation_current or not payload.revalidate_external_authority():
                    raise AgentInvocationAdmissionBlocked(
                        "authority_changed",
                        "agent invocation authority changed during atomic admission",
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
    ) -> tuple[AgentInvocationCommand, AgentInvocation] | None:
        with self.connection() as conn:
            invocation_row = conn.execute(
                "SELECT * FROM agent_invocations WHERE invocation_id = ?",
                (invocation_id,),
            ).fetchone()
            if invocation_row is None:
                return None
            invocation = _invocation_record(invocation_row)
            _require_initial_event(conn, invocation)
            command_row = conn.execute(
                "SELECT * FROM agent_invocation_commands WHERE command_id = ?",
                (invocation.command_id,),
            ).fetchone()
        if command_row is None:
            raise ValueError("persisted agent invocation aggregate is incomplete")
        command = _command_record(command_row)
        if command.command_digest != invocation.command_digest:
            raise ValueError("persisted agent invocation aggregate failed linkage validation")
        return command, invocation

    def resolve_current(
        self,
        *,
        invocation_id: str,
    ) -> AgentInvocationAuthorityEvidence | None:
        aggregate = self.get(invocation_id=invocation_id)
        if aggregate is None:
            return None
        command, invocation = aggregate
        if invocation.state is not AgentInvocationState.ADMITTED:
            return None
        return AgentInvocationAuthorityEvidence(
            invocation_id=invocation.invocation_id,
            invocation_generation=invocation.generation,
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


__all__ = ["SQLiteAgentRuntimeInvocationStore"]
