"""Governed plan compilation and immutable custom-agent manifest assembly.

The compiler is pure: it cannot activate an agent, invoke a provider, retain a
conversation, mutate a workflow, reply through an app, or perform an effect.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Mapping

from tinyassets.agent_runtime import (
    AGENT_RUNTIME_MANIFEST_SCHEMA_VERSION,
    AgentRuntimeManifestInput,
    AgentRuntimeManifestValidationError,
)
from tinyassets.agent_runtime_compiler import (
    CompiledAgentComponent,
    GovernedAdapterPin,
    GovernedComponentDescriptor,
    GovernedComponentRegistry,
    compile_agent_components,
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMPONENT_KEY = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_PLAN_FIELD_TYPES = frozenset(
    {
        "array",
        "boolean",
        "component_key",
        "component_key_list",
        "integer",
        "number",
        "object",
        "string",
        "string_list",
    }
)
_SUPPORTED_COMPILERS = frozenset({"schema-plan/v1"})
_SUPPORTED_COVERAGE_RULES = frozenset({"all_execute_exactly_once"})


class GovernedPlanError(ValueError):
    """A governed plan descriptor or registry violates its contract."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise GovernedPlanError(f"{name} must be canonical non-empty text")
    return value


def _strings(value: object, name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GovernedPlanError(f"{name} must be a list")
    normalized = tuple(sorted({_text(item, name) for item in value}))
    if nonempty and not normalized:
        raise GovernedPlanError(f"{name} must not be empty")
    return normalized


def _schema(value: object, name: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        raise GovernedPlanError(f"{name} must be an object")
    normalized: list[tuple[str, str]] = []
    for raw_field, raw_type in value.items():
        field = _text(raw_field, f"{name} field")
        field_type = _text(raw_type, f"{name}.{field}")
        if field_type not in _PLAN_FIELD_TYPES:
            raise GovernedPlanError(f"{name}.{field} has unsupported type {field_type!r}")
        normalized.append((field, field_type))
    return tuple(sorted(normalized))


def _validate_string_tuple(value: object, name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise GovernedPlanError(f"{name} must be a canonical tuple")
    normalized = tuple(sorted({_text(item, name) for item in value}))
    if value != normalized:
        raise GovernedPlanError(f"{name} must be sorted and unique")
    if nonempty and not normalized:
        raise GovernedPlanError(f"{name} must not be empty")
    return normalized


def _validate_schema_tuple(value: object, name: str) -> None:
    if not isinstance(value, tuple):
        raise GovernedPlanError(f"{name} must be a canonical tuple")
    normalized: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise GovernedPlanError(f"{name} entries are invalid")
        field = _text(item[0], f"{name} field")
        field_type = _text(item[1], f"{name}.{field}")
        if field_type not in _PLAN_FIELD_TYPES:
            raise GovernedPlanError(f"{name}.{field} has unsupported type {field_type!r}")
        normalized.append((field, field_type))
    field_names = [field for field, _ in normalized]
    if len(field_names) != len(set(field_names)) or value != tuple(sorted(set(normalized))):
        raise GovernedPlanError(f"{name} must be sorted and unique")


@dataclass(frozen=True, slots=True)
class GovernedPlanPin:
    adapter_ref: str
    adapter_version: str
    adapter_digest: str
    plan_class: str

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        for name in ("adapter_ref", "adapter_version", "adapter_digest", "plan_class"):
            _text(getattr(self, name), name)
        if not _SHA256.fullmatch(self.adapter_digest):
            raise GovernedPlanError("adapter_digest must be canonical sha256")

    def to_dict(self) -> dict[str, str]:
        return {
            "adapter_ref": self.adapter_ref,
            "adapter_version": self.adapter_version,
            "adapter_digest": self.adapter_digest,
            "plan_class": self.plan_class,
        }


@dataclass(frozen=True, slots=True)
class GovernedPlanDescriptor:
    pin: GovernedPlanPin
    topology_class: str
    topology_schema: tuple[tuple[str, str], ...]
    entry_schema: tuple[tuple[str, str], ...]
    coverage_field: str
    coverage_rule: str
    compatible_component_inputs: tuple[str, ...]
    compatible_component_outputs: tuple[str, ...]
    confinement_class: str
    canonical_compiler: str

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not isinstance(self.pin, GovernedPlanPin):
            raise GovernedPlanError("pin must be a governed plan pin")
        self.pin._validate()
        for name in (
            "topology_class",
            "coverage_field",
            "coverage_rule",
            "confinement_class",
            "canonical_compiler",
        ):
            _text(getattr(self, name), name)
        _validate_schema_tuple(self.topology_schema, "topology_schema")
        _validate_schema_tuple(self.entry_schema, "entry_schema")
        _validate_string_tuple(
            self.compatible_component_inputs,
            "compatible_component_inputs",
        )
        _validate_string_tuple(
            self.compatible_component_outputs,
            "compatible_component_outputs",
        )
        combined = dict(self.topology_schema)
        for field, field_type in self.entry_schema:
            if field in combined and combined[field] != field_type:
                raise GovernedPlanError("topology and entry schemas disagree")
            combined[field] = field_type
        if combined.get(self.coverage_field) != "component_key_list":
            raise GovernedPlanError("coverage_field must name a component_key_list field")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "GovernedPlanDescriptor":
        fields = {
            "adapter_ref",
            "adapter_version",
            "adapter_digest",
            "plan_class",
            "topology_class",
            "topology_schema",
            "entry_schema",
            "coverage_field",
            "coverage_rule",
            "compatible_component_inputs",
            "compatible_component_outputs",
            "confinement_class",
            "canonical_compiler",
        }
        if not isinstance(payload, Mapping) or set(payload) != fields:
            raise GovernedPlanError("plan descriptor fields do not match contract")
        return cls(
            pin=GovernedPlanPin(
                adapter_ref=_text(payload["adapter_ref"], "adapter_ref"),
                adapter_version=_text(payload["adapter_version"], "adapter_version"),
                adapter_digest=_text(payload["adapter_digest"], "adapter_digest"),
                plan_class=_text(payload["plan_class"], "plan_class"),
            ),
            topology_class=_text(payload["topology_class"], "topology_class"),
            topology_schema=_schema(payload["topology_schema"], "topology_schema"),
            entry_schema=_schema(payload["entry_schema"], "entry_schema"),
            coverage_field=_text(payload["coverage_field"], "coverage_field"),
            coverage_rule=_text(payload["coverage_rule"], "coverage_rule"),
            compatible_component_inputs=_strings(
                payload["compatible_component_inputs"],
                "compatible_component_inputs",
            ),
            compatible_component_outputs=_strings(
                payload["compatible_component_outputs"],
                "compatible_component_outputs",
            ),
            confinement_class=_text(payload["confinement_class"], "confinement_class"),
            canonical_compiler=_text(payload["canonical_compiler"], "canonical_compiler"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            **self.pin.to_dict(),
            "topology_class": self.topology_class,
            "topology_schema": dict(self.topology_schema),
            "entry_schema": dict(self.entry_schema),
            "coverage_field": self.coverage_field,
            "coverage_rule": self.coverage_rule,
            "compatible_component_inputs": list(self.compatible_component_inputs),
            "compatible_component_outputs": list(self.compatible_component_outputs),
            "confinement_class": self.confinement_class,
            "canonical_compiler": self.canonical_compiler,
        }


class GovernedPlanRegistry:
    """Immutable installed plan-descriptor index."""

    def __init__(self, descriptors=()) -> None:
        by_ref: dict[str, GovernedPlanDescriptor] = {}
        by_digest: dict[str, GovernedPlanDescriptor] = {}
        for descriptor in descriptors:
            if not isinstance(descriptor, GovernedPlanDescriptor):
                raise GovernedPlanError("registry accepts governed plan descriptors only")
            descriptor._validate()
            descriptor = GovernedPlanDescriptor.from_dict(descriptor.to_dict())
            ref = descriptor.pin.adapter_ref
            digest = descriptor.pin.adapter_digest
            if ref in by_ref:
                raise GovernedPlanError(f"duplicate adapter_ref {ref!r}")
            if digest in by_digest:
                raise GovernedPlanError(f"descriptor digest reused by {ref!r}")
            by_ref[ref] = descriptor
            by_digest[digest] = descriptor
        self._by_ref = by_ref

    def resolve(self, adapter_ref: str) -> GovernedPlanDescriptor | None:
        descriptor = self._by_ref.get(adapter_ref)
        return (
            GovernedPlanDescriptor.from_dict(descriptor.to_dict())
            if descriptor is not None
            else None
        )


@dataclass(frozen=True, slots=True)
class PlanCompilationDiagnostic:
    path: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class AgentRuntimeCompilationResult:
    manifest_input: AgentRuntimeManifestInput | None
    diagnostics: tuple[PlanCompilationDiagnostic, ...]


def builtin_provider_turn_component_descriptor() -> GovernedComponentDescriptor:
    """Return the bounded text provider-turn component adapter contract."""

    return GovernedComponentDescriptor.from_dict(
        {
            "adapter_ref": "builtin:prompt-component",
            "adapter_version": "1",
            "adapter_digest": f"sha256:{'a' * 64}",
            "component_kinds": ["prompt"],
            "configuration_schema": {"tone": "string"},
            "typed_inputs": ["text"],
            "typed_outputs": ["text"],
            "required_capability_classes": ["provider.invoke"],
            "required_resource_classes": [],
            "required_provider_classes": ["text_generation"],
            "confinement_class": "provider_turn",
            "budget_dimensions": ["max_tokens", "max_turns"],
        }
    )


def builtin_single_provider_turn_plan_descriptor() -> GovernedPlanDescriptor:
    """Return one bounded plan adapter; it is not a starter-agent template."""

    return GovernedPlanDescriptor.from_dict(
        {
            "adapter_ref": "builtin:single-provider-turn",
            "adapter_version": "1",
            "adapter_digest": f"sha256:{'b' * 64}",
            "plan_class": "single_provider_turn",
            "topology_class": "single_entry_sequence",
            "topology_schema": {"component_order": "component_key_list"},
            "entry_schema": {"entry_component": "component_key"},
            "coverage_field": "component_order",
            "coverage_rule": "all_execute_exactly_once",
            "compatible_component_inputs": ["text"],
            "compatible_component_outputs": ["text"],
            "confinement_class": "provider_turn",
            "canonical_compiler": "schema-plan/v1",
        }
    )


def _canonical_object(value: object) -> dict[str, object] | None:
    if not _is_canonical_json_shape(value, set()):
        return None
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (RecursionError, TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _is_canonical_json_shape(value: object, ancestors: set[int]) -> bool:
    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if not isinstance(value, (dict, list)):
        return False
    identity = id(value)
    if identity in ancestors:
        return False
    ancestors.add(identity)
    try:
        if isinstance(value, dict):
            return all(
                isinstance(key, str) and _is_canonical_json_shape(child, ancestors)
                for key, child in value.items()
            )
        return all(_is_canonical_json_shape(child, ancestors) for child in value)
    finally:
        ancestors.remove(identity)


def _value_matches(value: object, field_type: str, execute_keys: set[str]) -> bool:
    if field_type == "component_key":
        return isinstance(value, str) and value in execute_keys
    if field_type == "component_key_list":
        return (
            isinstance(value, list)
            and all(isinstance(item, str) and item in execute_keys for item in value)
            and len(value) == len(set(value))
        )
    if field_type == "string":
        return isinstance(value, str)
    if field_type == "string_list":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if field_type == "object":
        return isinstance(value, dict)
    if field_type == "array":
        return isinstance(value, list)
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if field_type == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
        )
    return False


def _manifest_components(
    components: tuple[CompiledAgentComponent, ...],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for component in components:
        adapter = component.adapter
        result[component.component_key] = {
            "runtime_mode": component.runtime_mode,
            "configuration": json.loads(component.configuration_json),
            "adapter": (
                {
                    "adapter_kind": "component",
                    **adapter.to_dict(),
                }
                if isinstance(adapter, GovernedAdapterPin)
                else None
            ),
        }
    return result


def compile_agent_runtime_manifest_input(
    *,
    owner_user_id: object,
    universe_id: object,
    agent_binding_id: object,
    binding_revision: object,
    binding_configuration_digest: object,
    agent_definition_id: object,
    definition_fingerprint: object,
    public_components: Mapping[str, object],
    runtime_components: Mapping[str, object],
    component_configuration: Mapping[str, object],
    component_registry: GovernedComponentRegistry,
    plan_adapter_ref: object,
    plan_configuration: Mapping[str, object],
    plan_registry: GovernedPlanRegistry,
    available_confinement_classes: set[str],
    requested_references: Mapping[str, object],
    budgets: Mapping[str, object],
    compiler_contract_version: object,
) -> AgentRuntimeCompilationResult:
    """Compile arbitrary components and one explicit adapter-declared plan."""

    component_result = compile_agent_components(
        public_components=public_components,
        runtime_components=runtime_components,
        component_configuration=component_configuration,
        registry=component_registry,
        available_confinement_classes=available_confinement_classes,
    )
    diagnostics = [
        PlanCompilationDiagnostic(item.component_key, item.code, item.message)
        for item in component_result.diagnostics
    ]
    if diagnostics:
        return AgentRuntimeCompilationResult(None, tuple(diagnostics))
    if (
        not isinstance(plan_adapter_ref, str)
        or not plan_adapter_ref.strip()
        or plan_adapter_ref != plan_adapter_ref.strip()
    ):
        return AgentRuntimeCompilationResult(
            None,
            (
                PlanCompilationDiagnostic(
                    "$plan_adapter_ref",
                    "plan_adapter_invalid",
                    "an explicit canonical plan adapter reference is required",
                ),
            ),
        )
    descriptor = (
        plan_registry.resolve(plan_adapter_ref)
        if isinstance(plan_registry, GovernedPlanRegistry)
        else None
    )
    if descriptor is None:
        return AgentRuntimeCompilationResult(
            None,
            (
                PlanCompilationDiagnostic(
                    "$plan_adapter_ref",
                    "plan_adapter_unavailable",
                    "the requested governed plan adapter is not installed",
                ),
            ),
        )
    if descriptor.canonical_compiler not in _SUPPORTED_COMPILERS:
        diagnostics.append(
            PlanCompilationDiagnostic(
                "$plan", "plan_compiler_unavailable", "canonical plan compiler is unavailable"
            )
        )
    if descriptor.coverage_rule not in _SUPPORTED_COVERAGE_RULES:
        diagnostics.append(
            PlanCompilationDiagnostic(
                "$plan", "coverage_rule_unavailable", "component coverage rule is unavailable"
            )
        )
    if descriptor.confinement_class not in available_confinement_classes:
        diagnostics.append(
            PlanCompilationDiagnostic(
                "$plan", "sandbox_unavailable", "required plan confinement is unavailable"
            )
        )
    execute_components = tuple(
        component
        for component in component_result.compiled_components
        if component.runtime_mode == "execute"
    )
    for component in execute_components:
        if not set(component.typed_inputs).issubset(
            descriptor.compatible_component_inputs
        ) or not set(component.typed_outputs).issubset(descriptor.compatible_component_outputs):
            diagnostics.append(
                PlanCompilationDiagnostic(
                    component.component_key,
                    "component_contract_incompatible",
                    "component typed contract is incompatible with the plan adapter",
                )
            )
    canonical_plan = _canonical_object(plan_configuration)
    schema = {**dict(descriptor.topology_schema), **dict(descriptor.entry_schema)}
    execute_keys = {component.component_key for component in execute_components}
    if canonical_plan is None or set(canonical_plan) != set(schema):
        diagnostics.append(
            PlanCompilationDiagnostic(
                "$plan_configuration",
                "plan_configuration_invalid",
                "plan fields do not match the adapter-declared schema",
            )
        )
    else:
        for field, field_type in sorted(schema.items()):
            if not _value_matches(canonical_plan[field], field_type, execute_keys):
                diagnostics.append(
                    PlanCompilationDiagnostic(
                        field,
                        "plan_field_invalid",
                        "plan field violates the adapter-declared schema",
                    )
                )
        coverage = canonical_plan.get(descriptor.coverage_field)
        coverage_is_key_list = isinstance(coverage, list) and all(
            isinstance(item, str) for item in coverage
        )
        if descriptor.coverage_rule == "all_execute_exactly_once" and (
            not coverage_is_key_list
            or len(coverage) != len(execute_keys)
            or set(coverage) != execute_keys
        ):
            diagnostics.append(
                PlanCompilationDiagnostic(
                    descriptor.coverage_field,
                    "component_coverage_invalid",
                    "plan must cover every executable component exactly once",
                )
            )
    ordered = tuple(sorted(diagnostics, key=lambda item: (item.path, item.code)))
    if ordered:
        return AgentRuntimeCompilationResult(None, ordered)
    execution_plan = {
        "plan_class": descriptor.pin.plan_class,
        "topology_class": descriptor.topology_class,
        **canonical_plan,
    }
    try:
        manifest_input = AgentRuntimeManifestInput.from_dict(
            {
                "schema_version": AGENT_RUNTIME_MANIFEST_SCHEMA_VERSION,
                "owner_user_id": owner_user_id,
                "universe_id": universe_id,
                "agent_binding_id": agent_binding_id,
                "binding_revision": binding_revision,
                "binding_configuration_digest": binding_configuration_digest,
                "agent_definition_id": agent_definition_id,
                "definition_fingerprint": definition_fingerprint,
                "components": _manifest_components(component_result.compiled_components),
                "plan_adapter": {
                    "adapter_kind": "plan",
                    **descriptor.pin.to_dict(),
                },
                "execution_plan": execution_plan,
                "requested_references": requested_references,
                "budgets": budgets,
                "compiler_contract_version": compiler_contract_version,
            }
        )
    except (AgentRuntimeManifestValidationError, TypeError, ValueError):
        return AgentRuntimeCompilationResult(
            None,
            (
                PlanCompilationDiagnostic(
                    "$manifest",
                    "manifest_invalid",
                    "compiled manifest input violates the immutable contract",
                ),
            ),
        )
    return AgentRuntimeCompilationResult(manifest_input, ())


__all__ = [
    "AgentRuntimeCompilationResult",
    "GovernedPlanDescriptor",
    "GovernedPlanError",
    "GovernedPlanPin",
    "GovernedPlanRegistry",
    "PlanCompilationDiagnostic",
    "builtin_provider_turn_component_descriptor",
    "builtin_single_provider_turn_plan_descriptor",
    "compile_agent_runtime_manifest_input",
]
