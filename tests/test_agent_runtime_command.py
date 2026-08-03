from __future__ import annotations

import json
import sqlite3
from dataclasses import FrozenInstanceError

import pytest

from tinyassets.agent_runtime_command import (
    AgentInvocationBudgetEnvelope,
    AgentInvocationCommand,
    AgentInvocationCommandIntegrityError,
)
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.storage import db_path
from tinyassets.storage.agent_runtime_commands import AgentRuntimeCommandStore
from tinyassets.storage.automation_activations import AutomationActivationExecutor


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"


def _budget(**changes: object) -> AgentInvocationBudgetEnvelope:
    values: dict[str, object] = {
        "max_invocations": 1,
        "max_tokens": 8_000,
        "max_cost_microunits": 2_000_000,
        "max_turns": 4,
        "expires_at": "2026-08-02T13:00:00.000000Z",
    }
    values.update(changes)
    return AgentInvocationBudgetEnvelope.build(**values)  # type: ignore[arg-type]


def _command(**changes: object) -> AgentInvocationCommand:
    values: dict[str, object] = {
        "schema_version": 1,
        "command_id": "agent_invocation_command_01",
        "generation": 1,
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
        "provider_work_binding_id": f"pwb_{'3' * 32}",
        "provider_work_binding_generation": 2,
        "provider_work_binding_digest": _digest("d"),
        "idempotency_key_digest": _digest("e"),
        "request_digest": _digest("f"),
        "budget": _budget(),
        "admission_witness_id": "agent_invocation_admission_01",
        "admission_witness_digest": _digest("2"),
        "created_at": "2026-08-02T12:00:00.000000Z",
    }
    values.update(changes)
    return AgentInvocationCommand.build(**values)  # type: ignore[arg-type]


def _initialize(store: AgentRuntimeCommandStore) -> None:
    assert store.resolve_current(command_id="agent_invocation_command_missing") is None


def _insert(base_path, command: AgentInvocationCommand) -> None:
    with sqlite3.connect(db_path(base_path)) as conn:
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
                json.dumps(command.to_dict(), sort_keys=True, separators=(",", ":")),
                command.created_at,
            ),
        )


def test_command_is_canonical_immutable_and_not_a_runtime_principal() -> None:
    command = _command()

    assert AgentInvocationCommand.from_dict(command.to_dict()) == command
    assert "principal_digest" not in command.to_dict()
    assert "grant_evidence_set_digest" not in command.to_dict()
    with pytest.raises(FrozenInstanceError):
        command.universe_id = "universe_other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="agent runtime manifest"):
        _command(
            execution_subject=ExecutionSubject(
                kind=ExecutionSubjectKind.BRANCH_VERSION,
                ref="branch_version_01",
                digest=_digest("a"),
            )
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"max_invocations": 0}, "max_invocations"),
        ({"max_tokens": -1}, "max_tokens"),
        ({"max_cost_microunits": -1}, "max_cost_microunits"),
        ({"max_turns": 0}, "max_turns"),
        ({"max_invocations": 1 << 63}, "max_invocations"),
        ({"max_tokens": 1 << 63}, "max_tokens"),
        ({"max_turns": True}, "max_turns"),
        ({"expires_at": "2026-08-02"}, "timezone"),
    ],
)
def test_budget_envelope_is_typed_and_bounded(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _budget(**changes)


def test_budget_digest_covers_every_limit() -> None:
    budget = _budget()

    for changes in (
        {"max_invocations": 2},
        {"max_tokens": 7_999},
        {"max_cost_microunits": 1_999_999},
        {"max_turns": 3},
        {"expires_at": "2026-08-02T12:59:59.000000Z"},
    ):
        assert _budget(**changes).budget_digest != budget.budget_digest


def test_store_has_no_writer_verifier_or_generic_transaction_surface(tmp_path) -> None:
    store = AgentRuntimeCommandStore(tmp_path)

    for name in (
        "create",
        "append",
        "insert",
        "issue",
        "admit",
        "connection",
        "verify_current_admission",
    ):
        assert not hasattr(store, name)
    with pytest.raises(TypeError, match="witness_verifier"):
        AgentRuntimeCommandStore(
            tmp_path,
            witness_verifier=lambda _: True,  # type: ignore[call-arg]
        )


def test_empty_store_resolves_no_current_command(tmp_path) -> None:
    assert (
        AgentRuntimeCommandStore(tmp_path).resolve_current(command_id="agent_invocation_command_01")
        is None
    )


def test_self_consistent_command_is_never_authority(tmp_path) -> None:
    store = AgentRuntimeCommandStore(tmp_path)
    _initialize(store)
    command = _command()
    _insert(tmp_path, command)

    assert store.resolve_current(command_id=command.command_id) is None


@pytest.mark.parametrize("tamper", ["projection", "json", "digest"])
def test_persisted_command_tampering_fails_closed(tmp_path, tamper: str) -> None:
    store = AgentRuntimeCommandStore(tmp_path)
    _initialize(store)
    command = _command()
    _insert(tmp_path, command)
    with sqlite3.connect(db_path(tmp_path)) as conn:
        if tamper == "projection":
            conn.execute(
                "UPDATE agent_runtime_invocation_commands SET universe_id = ?",
                ("universe_other",),
            )
        elif tamper == "json":
            payload = command.to_dict()
            payload["lease_id"] = "lease_forged"
            conn.execute(
                "UPDATE agent_runtime_invocation_commands SET record_json = ?",
                (json.dumps(payload, sort_keys=True, separators=(",", ":")),),
            )
        else:
            conn.execute(
                "UPDATE agent_runtime_invocation_commands SET command_digest = ?",
                (_digest("9"),),
            )

    with pytest.raises(AgentInvocationCommandIntegrityError):
        store.resolve_current(command_id=command.command_id)


def test_command_digest_covers_every_shared_authority_link() -> None:
    command = _command()

    for changes in (
        {"authorizing_grant_generation": 8},
        {"binding_revision": 4},
        {"activation_epoch": 5},
        {"typed_input_digest": _digest("8")},
        {"provider_work_binding_generation": 3},
        {"provider_work_binding_digest": _digest("8")},
        {"request_digest": _digest("8")},
        {"budget": _budget(max_tokens=7_999)},
    ):
        assert _command(**changes).command_digest != command.command_digest


def test_command_links_one_way_without_invocation_root_digest() -> None:
    command = _command()
    payload = command.to_dict()

    assert payload["invocation_id"] == "agent_invocation_01"
    assert "root_digest" not in payload
    assert payload["budget_digest"] == command.budget.budget_digest
