from __future__ import annotations

import json
import sqlite3
from dataclasses import FrozenInstanceError

import pytest

from tinyassets.agent_runtime_invocation import (
    AgentInvocationEvent,
    AgentInvocationEventState,
    AgentInvocationIntegrityError,
    AgentInvocationRoot,
)
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.storage import db_path
from tinyassets.storage.agent_runtime_invocations import AgentRuntimeInvocationStore
from tinyassets.storage.automation_activations import AutomationActivationExecutor


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"


def _root(**changes: object) -> AgentInvocationRoot:
    values: dict[str, object] = {
        "schema_version": 1,
        "invocation_id": "agent_invocation_01",
        "authorizing_subject_id": "user::alice",
        "authorizing_grant_generation": 7,
        "universe_id": "universe_alice",
        "agent_binding_id": "agent_binding_alice",
        "binding_revision": 3,
        "execution_subject": ExecutionSubject(
            kind=ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST,
            ref="agent_manifest_alice",
            digest=_digest("a"),
        ),
        "activation_automation_id": "agent_binding:agent_binding_alice",
        "activation_epoch": 4,
        "executor_class": AutomationActivationExecutor.CLOUD,
        "lease_id": "lease_agent_alice_4",
        "typed_input_digest": _digest("b"),
        "command_id": "agent_invocation_command_01",
        "command_generation": 1,
        "command_digest": _digest("c"),
        "provider_work_binding_id": f"pwb_{'3' * 32}",
        "provider_work_binding_generation": 2,
        "provider_work_binding_digest": _digest("d"),
        "idempotency_key_digest": _digest("e"),
        "request_digest": _digest("f"),
        "budget_digest": _digest("1"),
        "admission_witness_id": "agent_invocation_admission_01",
        "admission_witness_digest": _digest("2"),
        "created_at": "2026-08-02T12:00:00.000000Z",
    }
    values.update(changes)
    return AgentInvocationRoot.build(**values)  # type: ignore[arg-type]


def _admitted(root: AgentInvocationRoot, **changes: object) -> AgentInvocationEvent:
    values: dict[str, object] = {
        "schema_version": 1,
        "event_id": "agent_invocation_event_01",
        "invocation_id": root.invocation_id,
        "generation": 1,
        "state": AgentInvocationEventState.ADMITTED,
        "previous_event_digest": None,
        "root_digest": root.root_digest,
        "reason_code": None,
        "occurred_at": root.created_at,
    }
    values.update(changes)
    return AgentInvocationEvent.build(**values)  # type: ignore[arg-type]


class _WitnessVerifier:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.records: list[AgentInvocationRoot] = []

    def verify_current_admission(self, *, root: AgentInvocationRoot) -> bool:
        self.records.append(root)
        return self.accepted


def _initialize(store: AgentRuntimeInvocationStore) -> None:
    assert store.resolve_current(invocation_id="agent_invocation_missing") is None


def _insert_root(base_path, root: AgentInvocationRoot) -> None:
    with sqlite3.connect(db_path(base_path)) as conn:
        conn.execute(
            """
            INSERT INTO agent_runtime_invocation_roots (
                invocation_id, authorizing_subject_id, universe_id,
                agent_binding_id, command_id, provider_work_binding_id,
                admission_witness_id, root_digest, record_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                root.invocation_id,
                root.authorizing_subject_id,
                root.universe_id,
                root.agent_binding_id,
                root.command_id,
                root.provider_work_binding_id,
                root.admission_witness_id,
                root.root_digest,
                json.dumps(root.to_dict(), sort_keys=True, separators=(",", ":")),
                root.created_at,
            ),
        )


def _insert_event(base_path, event: AgentInvocationEvent) -> None:
    with sqlite3.connect(db_path(base_path)) as conn:
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
                json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")),
                event.occurred_at,
            ),
        )


def test_records_are_canonical_immutable_and_reject_broad_subjects() -> None:
    root = _root()
    event = _admitted(root)

    assert AgentInvocationRoot.from_dict(root.to_dict()) == root
    assert AgentInvocationEvent.from_dict(event.to_dict()) == event
    with pytest.raises(FrozenInstanceError):
        root.universe_id = "universe_other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="agent runtime manifest"):
        _root(
            execution_subject=ExecutionSubject(
                kind=ExecutionSubjectKind.BRANCH_VERSION,
                ref="branch_version_01",
                digest=_digest("a"),
            )
        )


def test_store_has_no_production_writer_or_generic_transaction_surface(tmp_path) -> None:
    store = AgentRuntimeInvocationStore(tmp_path)

    for name in ("create", "append", "insert", "issue", "admit", "connection"):
        assert not hasattr(store, name)


def test_empty_store_resolves_no_current_invocation(tmp_path) -> None:
    assert (
        AgentRuntimeInvocationStore(tmp_path).resolve_current(invocation_id="agent_invocation_01")
        is None
    )


def test_self_consistent_row_is_not_authority_without_canonical_witness_verifier(
    tmp_path,
) -> None:
    store = AgentRuntimeInvocationStore(tmp_path)
    _initialize(store)
    root = _root()
    _insert_root(tmp_path, root)
    _insert_event(tmp_path, _admitted(root))

    assert store.resolve_current(invocation_id=root.invocation_id) is None


def test_rejected_admission_witness_is_not_current(tmp_path) -> None:
    verifier = _WitnessVerifier(accepted=False)
    store = AgentRuntimeInvocationStore(tmp_path, witness_verifier=verifier)
    _initialize(store)
    root = _root()
    _insert_root(tmp_path, root)
    _insert_event(tmp_path, _admitted(root))

    assert store.resolve_current(invocation_id=root.invocation_id) is None
    assert verifier.records == [root]


def test_verified_admitted_root_resolves_exact_principal_evidence(tmp_path) -> None:
    verifier = _WitnessVerifier()
    store = AgentRuntimeInvocationStore(tmp_path, witness_verifier=verifier)
    _initialize(store)
    root = _root()
    _insert_root(tmp_path, root)
    _insert_event(tmp_path, _admitted(root))

    evidence = store.resolve_current(invocation_id=root.invocation_id)

    assert evidence is not None
    assert evidence.invocation_id == root.invocation_id
    assert evidence.invocation_generation == 1
    assert evidence.authorizing_subject_id == root.authorizing_subject_id
    assert evidence.execution_subject == root.execution_subject
    assert evidence.activation_epoch == root.activation_epoch
    assert evidence.typed_input_digest == root.typed_input_digest
    assert verifier.records == [root]


def test_invalidated_invocation_cannot_resurrect(tmp_path) -> None:
    store = AgentRuntimeInvocationStore(tmp_path, witness_verifier=_WitnessVerifier())
    _initialize(store)
    root = _root()
    admitted = _admitted(root)
    invalidated = AgentInvocationEvent.build(
        schema_version=1,
        event_id="agent_invocation_event_02",
        invocation_id=root.invocation_id,
        generation=2,
        state=AgentInvocationEventState.INVALIDATED,
        previous_event_digest=admitted.event_digest,
        root_digest=root.root_digest,
        reason_code="activation_fence_changed",
        occurred_at="2026-08-02T12:01:00.000000Z",
    )
    _insert_root(tmp_path, root)
    _insert_event(tmp_path, admitted)
    _insert_event(tmp_path, invalidated)

    assert store.resolve_current(invocation_id=root.invocation_id) is None

    resurrected = AgentInvocationEvent.build(
        schema_version=1,
        event_id="agent_invocation_event_03",
        invocation_id=root.invocation_id,
        generation=3,
        state=AgentInvocationEventState.ADMITTED,
        previous_event_digest=invalidated.event_digest,
        root_digest=root.root_digest,
        reason_code=None,
        occurred_at="2026-08-02T12:02:00.000000Z",
    )
    _insert_event(tmp_path, resurrected)
    with pytest.raises(AgentInvocationIntegrityError, match="transition"):
        store.resolve_current(invocation_id=root.invocation_id)


@pytest.mark.parametrize("tamper", ["projection", "json", "digest"])
def test_persisted_root_tampering_fails_closed(tmp_path, tamper: str) -> None:
    store = AgentRuntimeInvocationStore(tmp_path, witness_verifier=_WitnessVerifier())
    _initialize(store)
    root = _root()
    _insert_root(tmp_path, root)
    _insert_event(tmp_path, _admitted(root))
    with sqlite3.connect(db_path(tmp_path)) as conn:
        if tamper == "projection":
            conn.execute(
                "UPDATE agent_runtime_invocation_roots SET universe_id = ?",
                ("universe_other",),
            )
        elif tamper == "json":
            payload = root.to_dict()
            payload["lease_id"] = "lease_forged"
            conn.execute(
                "UPDATE agent_runtime_invocation_roots SET record_json = ?",
                (json.dumps(payload, sort_keys=True, separators=(",", ":")),),
            )
        else:
            conn.execute(
                "UPDATE agent_runtime_invocation_roots SET root_digest = ?",
                (_digest("9"),),
            )

    with pytest.raises(AgentInvocationIntegrityError):
        store.resolve_current(invocation_id=root.invocation_id)


def test_event_generation_gap_or_hash_break_fails_closed(tmp_path) -> None:
    store = AgentRuntimeInvocationStore(tmp_path, witness_verifier=_WitnessVerifier())
    _initialize(store)
    root = _root()
    admitted = _admitted(root)
    _insert_root(tmp_path, root)
    _insert_event(tmp_path, admitted)
    broken = AgentInvocationEvent.build(
        schema_version=1,
        event_id="agent_invocation_event_03",
        invocation_id=root.invocation_id,
        generation=3,
        state=AgentInvocationEventState.INVALIDATED,
        previous_event_digest=_digest("8"),
        root_digest=root.root_digest,
        reason_code="grant_revoked",
        occurred_at="2026-08-02T12:02:00.000000Z",
    )
    _insert_event(tmp_path, broken)

    with pytest.raises(AgentInvocationIntegrityError, match="chain"):
        store.resolve_current(invocation_id=root.invocation_id)


def test_invalidation_during_witness_verification_fails_closed(tmp_path) -> None:
    root = _root()
    admitted = _admitted(root)

    class _RevokingVerifier:
        def verify_current_admission(self, *, root: AgentInvocationRoot) -> bool:
            invalidated = AgentInvocationEvent.build(
                schema_version=1,
                event_id="agent_invocation_event_02",
                invocation_id=root.invocation_id,
                generation=2,
                state=AgentInvocationEventState.INVALIDATED,
                previous_event_digest=admitted.event_digest,
                root_digest=root.root_digest,
                reason_code="grant_revoked",
                occurred_at="2026-08-02T12:01:00.000000Z",
            )
            _insert_event(tmp_path, invalidated)
            return True

    store = AgentRuntimeInvocationStore(
        tmp_path,
        witness_verifier=_RevokingVerifier(),
    )
    _initialize(store)
    _insert_root(tmp_path, root)
    _insert_event(tmp_path, admitted)

    with pytest.raises(AgentInvocationIntegrityError, match="changed"):
        store.resolve_current(invocation_id=root.invocation_id)


def test_canonical_digest_changes_for_every_authority_link() -> None:
    root = _root()

    for changes in (
        {"command_digest": _digest("8")},
        {"provider_work_binding_generation": 3},
        {"budget_digest": _digest("8")},
    ):
        changed = _root(**changes)
        assert changed.root_digest != root.root_digest
