from __future__ import annotations

import pytest


def _source() -> dict[str, object]:
    return {
        "owner_user_id": "alice",
        "universe_id": "universe_alice",
        "agent_binding_id": "agent_binding_123",
        "binding_revision": 3,
        "binding_configuration_digest": f"sha256:{'d' * 64}",
        "agent_definition_id": "agent_definition_123",
        "definition_fingerprint": "e" * 64,
    }


def _compile(
    *,
    public_components=None,
    runtime_components=None,
    configuration=None,
    plan_configuration=None,
    component_descriptors=None,
    plan_descriptors=None,
    plan_registry=None,
    plan_adapter_ref="builtin:single-provider-turn",
    available_confinement_classes=None,
):
    from tinyassets.agent_runtime_compiler import GovernedComponentRegistry
    from tinyassets.agent_runtime_plan_compiler import (
        GovernedPlanRegistry,
        builtin_provider_turn_component_descriptor,
        builtin_single_provider_turn_plan_descriptor,
        compile_agent_runtime_manifest_input,
    )

    return compile_agent_runtime_manifest_input(
        **_source(),
        public_components=public_components
        or {"identity": {"kind": "prompt", "config": {"text": "Be useful."}}},
        runtime_components=runtime_components or {},
        component_configuration=configuration or {"identity": {"tone": "careful"}},
        component_registry=GovernedComponentRegistry(
            component_descriptors or (builtin_provider_turn_component_descriptor(),)
        ),
        plan_adapter_ref=plan_adapter_ref,
        plan_configuration=plan_configuration
        or {"entry_component": "identity", "component_order": ["identity"]},
        plan_registry=plan_registry
        or GovernedPlanRegistry(
            plan_descriptors or (builtin_single_provider_turn_plan_descriptor(),)
        ),
        available_confinement_classes=available_confinement_classes or {"provider_turn"},
        requested_references={
            "capability_ids": ["provider.invoke"],
            "resource_ids": [],
            "provider_policy_ids": ["provider_policy_alice"],
        },
        budgets={"max_tokens": 2_000, "max_turns": 1},
        compiler_contract_version="agent-runtime-compiler/v1",
    )


def test_builtin_provider_turn_pair_assembles_final_immutable_manifest_input():
    result = _compile()

    assert result.diagnostics == ()
    payload = result.manifest_input.to_dict()
    assert payload["plan_adapter"] == {
        "adapter_kind": "plan",
        "adapter_ref": "builtin:single-provider-turn",
        "adapter_version": "1",
        "adapter_digest": f"sha256:{'b' * 64}",
        "plan_class": "single_provider_turn",
    }
    assert payload["execution_plan"] == {
        "component_order": ["identity"],
        "entry_component": "identity",
        "plan_class": "single_provider_turn",
        "topology_class": "single_entry_sequence",
    }
    assert payload["components"]["identity"]["adapter"]["adapter_ref"] == (
        "builtin:prompt-component"
    )


def test_adapter_declared_recurrent_multi_entry_topology_is_not_forced_into_a_dag():
    from tinyassets.agent_runtime_plan_compiler import GovernedPlanDescriptor

    recurrent = GovernedPlanDescriptor.from_dict(
        {
            "adapter_ref": "test:recurrent-swarm",
            "adapter_version": "9",
            "adapter_digest": f"sha256:{'f' * 64}",
            "plan_class": "user.recurrent-swarm.v9",
            "topology_class": "cyclic_mesh",
            "topology_schema": {
                "members": "component_key_list",
                "transitions": "object",
            },
            "entry_schema": {"entry_components": "component_key_list"},
            "coverage_field": "members",
            "coverage_rule": "all_execute_exactly_once",
            "compatible_component_inputs": ["text"],
            "compatible_component_outputs": ["text"],
            "confinement_class": "provider_turn",
            "canonical_compiler": "schema-plan/v1",
        }
    )
    result = _compile(
        public_components={
            "alpha": {"kind": "prompt"},
            "beta": {"kind": "prompt"},
        },
        configuration={"alpha": {"tone": "a"}, "beta": {"tone": "b"}},
        plan_adapter_ref="test:recurrent-swarm",
        plan_descriptors=(recurrent,),
        plan_configuration={
            "members": ["alpha", "beta"],
            "entry_components": ["alpha", "beta"],
            "transitions": {"alpha": ["beta"], "beta": ["alpha"]},
        },
    )

    assert result.diagnostics == ()
    plan = result.manifest_input.to_dict()["execution_plan"]
    assert plan["plan_class"] == "user.recurrent-swarm.v9"
    assert plan["topology_class"] == "cyclic_mesh"
    assert plan["entry_components"] == ["alpha", "beta"]
    assert plan["transitions"]["beta"] == ["alpha"]


def test_missing_or_unavailable_explicit_plan_adapter_never_uses_a_default():
    missing = _compile(plan_adapter_ref=" ")
    unavailable = _compile(plan_adapter_ref="user:not-installed")

    assert [(item.path, item.code) for item in missing.diagnostics] == [
        ("$plan_adapter_ref", "plan_adapter_invalid")
    ]
    assert [(item.path, item.code) for item in unavailable.diagnostics] == [
        ("$plan_adapter_ref", "plan_adapter_unavailable")
    ]
    assert missing.manifest_input is None
    assert unavailable.manifest_input is None


def test_complete_coverage_rejects_silent_component_omission():
    result = _compile(
        public_components={
            "identity": {"kind": "prompt"},
            "reviewer": {"kind": "prompt"},
        },
        configuration={
            "identity": {"tone": "careful"},
            "reviewer": {"tone": "skeptical"},
        },
        plan_configuration={
            "entry_component": "identity",
            "component_order": ["identity"],
        },
    )

    assert result.manifest_input is None
    assert [(item.path, item.code) for item in result.diagnostics] == [
        ("component_order", "component_coverage_invalid")
    ]


def test_descriptive_only_data_is_pinned_but_excluded_from_execution_coverage():
    result = _compile(
        public_components={
            "identity": {"kind": "prompt"},
            "notes": {"kind": "user.unknown-memory.v17", "format": "markdown"},
        },
        runtime_components={"notes": {"mode": "descriptive_only"}},
        configuration={
            "identity": {"tone": "careful"},
            "notes": {"retention": "project"},
        },
        plan_configuration={
            "entry_component": "identity",
            "component_order": ["identity"],
        },
    )

    assert result.diagnostics == ()
    payload = result.manifest_input.to_dict()
    assert payload["components"]["notes"] == {
        "runtime_mode": "descriptive_only",
        "configuration": {"retention": "project"},
        "adapter": None,
    }
    assert payload["execution_plan"]["component_order"] == ["identity"]


def test_plan_contract_and_confinement_fail_closed_with_sorted_diagnostics():
    from tinyassets.agent_runtime_compiler import GovernedComponentDescriptor
    from tinyassets.agent_runtime_plan_compiler import GovernedPlanDescriptor

    image_component = GovernedComponentDescriptor.from_dict(
        {
            "adapter_ref": "test:image-component",
            "adapter_version": "1",
            "adapter_digest": f"sha256:{'1' * 64}",
            "component_kinds": ["image"],
            "configuration_schema": {},
            "typed_inputs": ["image"],
            "typed_outputs": ["image"],
            "required_capability_classes": [],
            "required_resource_classes": [],
            "required_provider_classes": [],
            "confinement_class": "provider_turn",
            "budget_dimensions": [],
        }
    )
    tenant_plan = GovernedPlanDescriptor.from_dict(
        {
            "adapter_ref": "test:tenant-plan",
            "adapter_version": "1",
            "adapter_digest": f"sha256:{'2' * 64}",
            "plan_class": "tenant.graph",
            "topology_class": "tenant_defined",
            "topology_schema": {"members": "component_key_list"},
            "entry_schema": {"entry": "component_key"},
            "coverage_field": "members",
            "coverage_rule": "all_execute_exactly_once",
            "compatible_component_inputs": ["text"],
            "compatible_component_outputs": ["text"],
            "confinement_class": "tenant_code",
            "canonical_compiler": "schema-plan/v1",
        }
    )
    result = _compile(
        public_components={"visual": {"kind": "image"}},
        configuration={"visual": {}},
        component_descriptors=(image_component,),
        plan_adapter_ref="test:tenant-plan",
        plan_descriptors=(tenant_plan,),
        plan_configuration={"entry": "visual", "members": ["visual"]},
    )

    assert result.manifest_input is None
    assert [(item.path, item.code) for item in result.diagnostics] == [
        ("$plan", "sandbox_unavailable"),
        ("visual", "component_contract_incompatible"),
    ]


def test_component_compile_failure_is_preserved_and_plan_is_not_produced():
    result = _compile(
        public_components={"unknown": {"kind": "uninstalled.kind"}},
        configuration={"unknown": {}},
        plan_configuration={
            "entry_component": "unknown",
            "component_order": ["unknown"],
        },
    )

    assert result.manifest_input is None
    assert [(item.path, item.code) for item in result.diagnostics] == [
        ("unknown", "adapter_unavailable")
    ]


def test_manifest_safety_rejection_returns_a_diagnostic_instead_of_escaping():
    from tinyassets.agent_runtime_compiler import GovernedComponentDescriptor

    unsafe = GovernedComponentDescriptor.from_dict(
        {
            "adapter_ref": "test:unsafe-component",
            "adapter_version": "1",
            "adapter_digest": f"sha256:{'3' * 64}",
            "component_kinds": ["prompt"],
            "configuration_schema": {"api_key": "string"},
            "typed_inputs": ["text"],
            "typed_outputs": ["text"],
            "required_capability_classes": [],
            "required_resource_classes": [],
            "required_provider_classes": ["text_generation"],
            "confinement_class": "provider_turn",
            "budget_dimensions": ["max_tokens"],
        }
    )
    result = _compile(
        configuration={"identity": {"api_key": "not-even-a-real-key"}},
        component_descriptors=(unsafe,),
    )

    assert result.manifest_input is None
    assert [(item.path, item.code) for item in result.diagnostics] == [
        ("$manifest", "manifest_invalid")
    ]


def test_malformed_component_coverage_returns_diagnostics_without_an_exception():
    result = _compile(
        plan_configuration={
            "entry_component": "identity",
            "component_order": [{"not": "a component key"}],
        }
    )

    assert result.manifest_input is None
    assert [(item.path, item.code) for item in result.diagnostics] == [
        ("component_order", "component_coverage_invalid"),
        ("component_order", "plan_field_invalid"),
    ]


def test_plan_descriptor_trust_boundary_validates_and_detaches_canonical_facts():
    from tinyassets.agent_runtime_plan_compiler import (
        GovernedPlanDescriptor,
        GovernedPlanError,
        GovernedPlanPin,
        GovernedPlanRegistry,
        builtin_single_provider_turn_plan_descriptor,
    )

    with pytest.raises(GovernedPlanError, match="canonical sha256"):
        GovernedPlanPin("test:forged", "1", "not-a-digest", "test.plan")

    descriptor = builtin_single_provider_turn_plan_descriptor()
    registry = GovernedPlanRegistry((descriptor,))
    object.__setattr__(descriptor.pin, "adapter_digest", "mutated-after-registration")
    resolved = registry.resolve("builtin:single-provider-turn")

    assert isinstance(resolved, GovernedPlanDescriptor)
    assert resolved.pin.adapter_digest == f"sha256:{'b' * 64}"

    object.__setattr__(resolved, "topology_class", "forged-topology")
    object.__setattr__(resolved, "coverage_field", [])
    result = _compile(plan_registry=registry)

    assert result.diagnostics == ()
    assert result.manifest_input.to_dict()["execution_plan"]["topology_class"] == (
        "single_entry_sequence"
    )


def test_non_json_plan_shapes_are_refused_instead_of_normalized():
    tuple_plan = _compile(
        plan_configuration={
            "entry_component": "identity",
            "component_order": ("identity",),
        }
    )

    assert tuple_plan.manifest_input is None
    assert [(item.path, item.code) for item in tuple_plan.diagnostics] == [
        ("$plan_configuration", "plan_configuration_invalid")
    ]


def test_nested_non_string_plan_keys_are_refused_instead_of_rewritten():
    from tinyassets.agent_runtime_plan_compiler import GovernedPlanDescriptor

    descriptor = GovernedPlanDescriptor.from_dict(
        {
            "adapter_ref": "test:metadata-plan",
            "adapter_version": "1",
            "adapter_digest": f"sha256:{'4' * 64}",
            "plan_class": "user.metadata.v1",
            "topology_class": "user_defined",
            "topology_schema": {
                "members": "component_key_list",
                "metadata": "object",
            },
            "entry_schema": {"entry": "component_key"},
            "coverage_field": "members",
            "coverage_rule": "all_execute_exactly_once",
            "compatible_component_inputs": ["text"],
            "compatible_component_outputs": ["text"],
            "confinement_class": "provider_turn",
            "canonical_compiler": "schema-plan/v1",
        }
    )
    result = _compile(
        plan_adapter_ref="test:metadata-plan",
        plan_descriptors=(descriptor,),
        plan_configuration={
            "entry": "identity",
            "members": ["identity"],
            "metadata": {1: "identity"},
        },
    )

    assert result.manifest_input is None
    assert [(item.path, item.code) for item in result.diagnostics] == [
        ("$plan_configuration", "plan_configuration_invalid")
    ]
