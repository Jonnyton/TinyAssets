from __future__ import annotations

import pytest


def _descriptor(**overrides):
    from tinyassets.agent_runtime_compiler import GovernedComponentDescriptor

    payload = {
        "adapter_ref": "builtin:prompt-component",
        "adapter_version": "1",
        "adapter_digest": f"sha256:{'a' * 64}",
        "component_kinds": ["soul"],
        "configuration_schema": {"tone": "string"},
        "typed_inputs": ["text"],
        "typed_outputs": ["text"],
        "required_capability_classes": ["provider.invoke"],
        "required_resource_classes": [],
        "required_provider_classes": ["text_generation"],
        "confinement_class": "provider_turn",
        "budget_dimensions": ["max_tokens", "max_turns"],
    }
    payload.update(overrides)
    return GovernedComponentDescriptor.from_dict(payload)


def _compile(*, public_components, runtime_components, configuration, descriptors=()):
    from tinyassets.agent_runtime_compiler import (
        GovernedComponentRegistry,
        compile_agent_components,
    )

    return compile_agent_components(
        public_components=public_components,
        runtime_components=runtime_components,
        component_configuration=configuration,
        registry=GovernedComponentRegistry(descriptors),
        available_confinement_classes={"provider_turn"},
    )


def test_executable_components_require_governed_adapters_with_exhaustive_diagnostics():
    result = _compile(
        public_components={
            "zeta": {"kind": "unknown.z", "config": {}},
            "alpha": {"kind": "unknown.a", "config": {}},
        },
        runtime_components={},
        configuration={},
    )

    assert result.compiled_components == ()
    assert [(item.component_key, item.code) for item in result.diagnostics] == [
        ("alpha", "adapter_unavailable"),
        ("zeta", "adapter_unavailable"),
    ]


def test_unknown_descriptive_component_is_preserved_without_authority():
    result = _compile(
        public_components={"memory": {"kind": "novel.v9", "config": {"format": "x"}}},
        runtime_components={"memory": {"mode": "descriptive_only"}},
        configuration={"memory": {"scope": "project"}},
    )

    assert result.diagnostics == ()
    component = result.compiled_components[0]
    assert component.component_key == "memory"
    assert component.runtime_mode == "descriptive_only"
    assert component.adapter is None
    assert component.required_capability_classes == ()
    assert component.required_resource_classes == ()
    assert component.required_provider_classes == ()


def test_explicit_descriptor_pins_complete_typed_contract():
    result = _compile(
        public_components={"identity": {"kind": "soul", "config": {"text": "help"}}},
        runtime_components={
            "identity": {"mode": "execute", "adapter_ref": "builtin:prompt-component"}
        },
        configuration={"identity": {"tone": "careful"}},
        descriptors=(_descriptor(),),
    )

    assert result.diagnostics == ()
    component = result.compiled_components[0]
    assert component.adapter.to_dict()["adapter_digest"] == f"sha256:{'a' * 64}"
    assert component.typed_inputs == ("text",)
    assert component.required_capability_classes == ("provider.invoke",)
    assert component.budget_dimensions == ("max_tokens", "max_turns")


def test_compilation_is_deterministic_across_mapping_order():
    descriptor = _descriptor()
    first = _compile(
        public_components={
            "b": {"kind": "soul", "config": {}},
            "a": {"kind": "soul", "config": {}},
        },
        runtime_components={},
        configuration={"b": {"tone": "b"}, "a": {"tone": "a"}},
        descriptors=(descriptor,),
    )
    second = _compile(
        public_components={
            "a": {"config": {}, "kind": "soul"},
            "b": {"config": {}, "kind": "soul"},
        },
        runtime_components={},
        configuration={"a": {"tone": "a"}, "b": {"tone": "b"}},
        descriptors=(descriptor,),
    )

    assert first == second
    assert [item.component_key for item in first.compiled_components] == ["a", "b"]


@pytest.mark.parametrize(
    ("configuration", "descriptor", "code"),
    [
        ({"identity": {"tone": 7}}, _descriptor(), "configuration_invalid"),
        (
            {"identity": {"tone": "safe"}},
            _descriptor(confinement_class="tenant_code"),
            "sandbox_unavailable",
        ),
    ],
)
def test_invalid_configuration_and_unavailable_confinement_fail_closed(
    configuration, descriptor, code
):
    result = _compile(
        public_components={"identity": {"kind": "soul", "config": {}}},
        runtime_components={},
        configuration=configuration,
        descriptors=(descriptor,),
    )

    assert result.compiled_components == ()
    assert [(item.component_key, item.code) for item in result.diagnostics] == [("identity", code)]


def test_registry_rejects_duplicate_refs_and_digest_aliases():
    from tinyassets.agent_runtime_compiler import (
        GovernedComponentRegistry,
        GovernedDescriptorError,
    )

    with pytest.raises(GovernedDescriptorError, match="duplicate adapter_ref"):
        GovernedComponentRegistry((_descriptor(), _descriptor(adapter_version="2")))
    with pytest.raises(GovernedDescriptorError, match="digest reused"):
        GovernedComponentRegistry(
            (
                _descriptor(),
                _descriptor(adapter_ref="builtin:other", component_kinds=["other"]),
            )
        )
