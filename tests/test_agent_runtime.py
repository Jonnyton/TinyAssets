from __future__ import annotations

import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets.custom_agents import (
    create_binding,
    publish_definition,
    update_binding,
)


def _agent_definition() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "Remixable coding partner",
        "description": "A portable definition compiled only after private binding.",
        "tags": ["coding", "agent"],
        "components": {
            "identity": {
                "kind": "soul",
                "config": {"instructions": "Test before changing code."},
            }
        },
    }


def _binding_configuration(*, tone: str = "careful") -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "Alice's coding partner",
        "component_configuration": {"identity": {"tone": tone}},
        "authority": {"capability_refs": ["provider.invoke"]},
        "resources": {"repository": "resource_repo_alice"},
        "provider": {"provider_policy_id": "provider_policy_alice"},
        "runtime": {
            "plan_adapter_ref": "builtin:single-provider-turn",
            "components": {
                "identity": {
                    "mode": "execute",
                    "adapter_ref": "builtin:prompt-component",
                }
            },
            "budgets": {"max_turns": 1, "max_tokens": 2_000},
        },
    }


def _bound_agent(tmp_path):
    definition = publish_definition(
        tmp_path,
        author_id="alice",
        payload=_agent_definition(),
    )
    binding = create_binding(
        tmp_path,
        universe_id="universe_alice",
        definition_id=definition["agent_definition_id"],
        created_by="alice",
        payload=_binding_configuration(),
    )
    return definition, binding


def _manifest_input(definition, binding):
    from tinyassets.agent_runtime import (
        AgentRuntimeManifestInput,
        canonical_content_digest,
    )

    return AgentRuntimeManifestInput.from_dict(
        {
            "schema_version": 1,
            "owner_user_id": "alice",
            "universe_id": binding["universe_id"],
            "agent_binding_id": binding["agent_binding_id"],
            "binding_revision": binding["revision"],
            "binding_configuration_digest": canonical_content_digest(
                binding["configuration"]
            ),
            "agent_definition_id": definition["agent_definition_id"],
            "definition_fingerprint": definition["content_fingerprint"],
            "components": {
                "identity": {
                    "runtime_mode": "execute",
                    "configuration": binding["configuration"][
                        "component_configuration"
                    ]["identity"],
                    "adapter": {
                        "adapter_kind": "component",
                        "adapter_ref": "builtin:prompt-component",
                        "adapter_version": "1",
                        "adapter_digest": f"sha256:{'a' * 64}",
                    },
                }
            },
            "plan_adapter": {
                "adapter_kind": "plan",
                "adapter_ref": "builtin:single-provider-turn",
                "adapter_version": "1",
                "adapter_digest": f"sha256:{'b' * 64}",
                "plan_class": "single_provider_turn",
            },
            "execution_plan": {
                "plan_class": "single_provider_turn",
                "entry_component": "identity",
                "component_order": ["identity"],
            },
            "requested_references": {
                "capability_ids": ["provider.invoke"],
                "resource_ids": ["resource_repo_alice"],
                "provider_policy_ids": ["provider_policy_alice"],
            },
            "budgets": {
                "max_cost_microunits": 50_000,
                "max_tokens": 2_000,
                "max_turns": 1,
            },
            "compiler_contract_version": "agent-runtime-compiler/v1",
        }
    )


def test_manifest_pins_complete_private_input_and_survives_binding_update(tmp_path) -> None:
    from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore

    definition, binding = _bound_agent(tmp_path)
    store = AgentRuntimeManifestStore(tmp_path)
    original_input = _manifest_input(definition, binding)

    original = store.create(
        manifest_input=original_input,
        idempotency_key="compile-coding-partner-v1",
    )

    assert original.manifest_id.startswith("agent_manifest_")
    assert original.manifest_digest == original_input.input_digest
    assert original.to_dict()["components"]["identity"]["configuration"] == {
        "tone": "careful"
    }
    assert original.to_dict()["requested_references"]["provider_policy_ids"] == [
        "provider_policy_alice"
    ]
    assert original.to_dict()["budgets"]["max_tokens"] == 2_000

    updated_binding = update_binding(
        tmp_path,
        universe_id=binding["universe_id"],
        binding_id=binding["agent_binding_id"],
        expected_revision=1,
        updated_by="alice",
        payload=_binding_configuration(tone="terse"),
    )

    assert store.get(
        owner_user_id="alice",
        manifest_id=original.manifest_id,
    ) == original
    assert store.create(
        manifest_input=original_input,
        idempotency_key="compile-coding-partner-v1",
    ) == original
    with pytest.raises(PermissionError, match="binding_not_current"):
        store.create(
            manifest_input=original_input,
            idempotency_key="compile-stale-binding",
        )

    successor_input = _manifest_input(definition, updated_binding)
    successor = store.create(
        manifest_input=successor_input,
        idempotency_key="compile-coding-partner-v2",
    )
    assert successor.manifest_id != original.manifest_id
    assert successor.manifest_digest != original.manifest_digest


def test_manifest_compile_retry_is_owner_scoped_and_conflicts_on_changed_input(
    tmp_path,
) -> None:
    from tinyassets.agent_runtime import AgentRuntimeManifestConflict
    from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore

    definition, binding = _bound_agent(tmp_path)
    store = AgentRuntimeManifestStore(tmp_path)
    manifest_input = _manifest_input(definition, binding)
    first = store.create(
        manifest_input=manifest_input,
        idempotency_key="request-lost",
    )
    replay = store.create(
        manifest_input=manifest_input,
        idempotency_key="request-lost",
    )

    assert replay == first
    changed_payload = manifest_input.to_dict()
    changed_payload["budgets"]["max_tokens"] = 2_001
    with pytest.raises(AgentRuntimeManifestConflict, match="different input"):
        store.create(
            manifest_input=type(manifest_input).from_dict(changed_payload),
            idempotency_key="request-lost",
        )
    assert store.count_for_owner("alice") == 1


def test_manifest_idempotency_key_namespace_is_per_owner(tmp_path) -> None:
    from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore

    alice_definition, alice_binding = _bound_agent(tmp_path)
    bob_definition = publish_definition(
        tmp_path,
        author_id="bob",
        payload={**_agent_definition(), "name": "Bob's coding partner"},
    )
    bob_binding = create_binding(
        tmp_path,
        universe_id="universe_bob",
        definition_id=bob_definition["agent_definition_id"],
        created_by="bob",
        payload=_binding_configuration(),
    )
    bob_input_payload = _manifest_input(bob_definition, bob_binding).to_dict()
    bob_input_payload["owner_user_id"] = "bob"
    bob_input_payload["requested_references"]["resource_ids"] = [
        "resource_repo_bob"
    ]
    bob_input_payload["requested_references"]["provider_policy_ids"] = [
        "provider_policy_bob"
    ]

    store = AgentRuntimeManifestStore(tmp_path)
    alice = store.create(
        manifest_input=_manifest_input(alice_definition, alice_binding),
        idempotency_key="shared-client-key",
    )
    bob = store.create(
        manifest_input=type(_manifest_input(bob_definition, bob_binding)).from_dict(
            bob_input_payload
        ),
        idempotency_key="shared-client-key",
    )

    assert alice.manifest_id != bob.manifest_id
    assert store.count_for_owner("alice") == 1
    assert store.count_for_owner("bob") == 1


def test_manifest_is_private_and_detects_persisted_tampering(tmp_path) -> None:
    from tinyassets.agent_runtime import AgentRuntimeManifestIntegrityError
    from tinyassets.storage import db_path
    from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore

    definition, binding = _bound_agent(tmp_path)
    store = AgentRuntimeManifestStore(tmp_path)
    manifest = store.create(
        manifest_input=_manifest_input(definition, binding),
        idempotency_key="private-manifest",
    )

    assert store.get(
        owner_user_id="mallory",
        manifest_id=manifest.manifest_id,
    ) is None
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            "UPDATE agent_runtime_manifests SET manifest_digest = ? "
            "WHERE manifest_id = ?",
            (f"sha256:{'f' * 64}", manifest.manifest_id),
        )
    with pytest.raises(AgentRuntimeManifestIntegrityError):
        store.get(owner_user_id="alice", manifest_id=manifest.manifest_id)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["components"]["identity"]["configuration"].update(
            {"api_key": "do-not-store"}
        ),
        lambda payload: payload["execution_plan"].update(
            {"conversation_history": ["private"]}
        ),
        lambda payload: payload.update({"provider_output": "not a manifest pin"}),
    ],
)
def test_manifest_rejects_secret_runtime_and_unknown_content_atomically(
    tmp_path,
    mutation,
) -> None:
    from tinyassets.agent_runtime import (
        AgentRuntimeManifestInput,
        AgentRuntimeManifestValidationError,
    )
    from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore

    definition, binding = _bound_agent(tmp_path)
    store = AgentRuntimeManifestStore(tmp_path)
    payload = copy.deepcopy(_manifest_input(definition, binding).to_dict())
    mutation(payload)

    with pytest.raises(AgentRuntimeManifestValidationError):
        invalid = AgentRuntimeManifestInput.from_dict(payload)
        store.create(manifest_input=invalid, idempotency_key="invalid")
    assert store.count_for_owner("alice") == 0


def test_manifest_rejects_oversized_content_without_a_row(tmp_path) -> None:
    from tinyassets.agent_runtime import (
        MAX_AGENT_RUNTIME_MANIFEST_BYTES,
        AgentRuntimeManifestInput,
        AgentRuntimeManifestValidationError,
    )
    from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore

    definition, binding = _bound_agent(tmp_path)
    store = AgentRuntimeManifestStore(tmp_path)
    payload = _manifest_input(definition, binding).to_dict()
    payload["execution_plan"]["description"] = "x" * (
        MAX_AGENT_RUNTIME_MANIFEST_BYTES + 1
    )

    with pytest.raises(AgentRuntimeManifestValidationError, match="exceeds"):
        AgentRuntimeManifestInput.from_dict(payload)
    assert store.count_for_owner("alice") == 0


def test_store_revalidates_a_directly_constructed_manifest_input(tmp_path) -> None:
    from tinyassets.agent_runtime import (
        AgentRuntimeManifestInput,
        AgentRuntimeManifestValidationError,
    )
    from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore

    definition, binding = _bound_agent(tmp_path)
    payload = _manifest_input(definition, binding).to_dict()
    payload["components"]["identity"]["configuration"]["api_key"] = "hidden"
    forged = AgentRuntimeManifestInput(
        __import__("json").dumps(payload, sort_keys=True, separators=(",", ":"))
    )

    with pytest.raises(AgentRuntimeManifestValidationError):
        AgentRuntimeManifestStore(tmp_path).create(
            manifest_input=forged,
            idempotency_key="forged-constructor",
        )
    assert AgentRuntimeManifestStore(tmp_path).count_for_owner("alice") == 0


def test_concurrent_exact_manifest_replay_has_one_identity(tmp_path) -> None:
    from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore

    definition, binding = _bound_agent(tmp_path)
    manifest_input = _manifest_input(definition, binding)

    def compile_once(_index: int):
        return AgentRuntimeManifestStore(tmp_path).create(
            manifest_input=manifest_input,
            idempotency_key="concurrent-compile",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(compile_once, range(24)))

    assert len({item.manifest_id for item in results}) == 1
    assert len({item.manifest_digest for item in results}) == 1
    assert AgentRuntimeManifestStore(tmp_path).count_for_owner("alice") == 1
