"""Governed, deterministic component compilation for custom agents.

This module compiles components only. It cannot create a plan, manifest,
activation, provider call, workflow, app reply, or effect.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA_TYPES = {
    "array": list,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "object": dict,
    "string": str,
}


class GovernedDescriptorError(ValueError):
    """A governed descriptor or registry violates the immutable contract."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernedDescriptorError(f"{name} must be a non-empty string")
    return value.strip()


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GovernedDescriptorError(f"{name} must be a list")
    return tuple(sorted({_text(item, name) for item in value}))


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (RecursionError, TypeError, ValueError) as exc:
        raise GovernedDescriptorError(f"content must be canonical JSON: {exc}") from exc


@dataclass(frozen=True, slots=True)
class GovernedAdapterPin:
    adapter_ref: str
    adapter_version: str
    adapter_digest: str

    def to_dict(self) -> dict[str, str]:
        return {
            "adapter_ref": self.adapter_ref,
            "adapter_version": self.adapter_version,
            "adapter_digest": self.adapter_digest,
        }


@dataclass(frozen=True, slots=True)
class GovernedComponentDescriptor:
    pin: GovernedAdapterPin
    component_kinds: tuple[str, ...]
    configuration_schema: tuple[tuple[str, str], ...]
    typed_inputs: tuple[str, ...]
    typed_outputs: tuple[str, ...]
    required_capability_classes: tuple[str, ...]
    required_resource_classes: tuple[str, ...]
    required_provider_classes: tuple[str, ...]
    confinement_class: str
    budget_dimensions: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]):
        fields = {
            "adapter_ref",
            "adapter_version",
            "adapter_digest",
            "component_kinds",
            "configuration_schema",
            "typed_inputs",
            "typed_outputs",
            "required_capability_classes",
            "required_resource_classes",
            "required_provider_classes",
            "confinement_class",
            "budget_dimensions",
        }
        if not isinstance(payload, Mapping) or set(payload) != fields:
            raise GovernedDescriptorError("descriptor fields do not match contract")
        digest = _text(payload["adapter_digest"], "adapter_digest")
        if not _SHA256.fullmatch(digest):
            raise GovernedDescriptorError("adapter_digest must be canonical sha256")
        schema = payload["configuration_schema"]
        if not isinstance(schema, Mapping):
            raise GovernedDescriptorError("configuration_schema must be an object")
        normalized_schema: list[tuple[str, str]] = []
        for raw_key, raw_type in schema.items():
            key = _text(raw_key, "configuration_schema key")
            type_name = _text(raw_type, f"configuration_schema.{key}")
            if type_name not in _SCHEMA_TYPES:
                raise GovernedDescriptorError(f"unsupported schema type {type_name!r}")
            normalized_schema.append((key, type_name))
        kinds = _strings(payload["component_kinds"], "component_kinds")
        if not kinds:
            raise GovernedDescriptorError("component_kinds must not be empty")
        return cls(
            pin=GovernedAdapterPin(
                adapter_ref=_text(payload["adapter_ref"], "adapter_ref"),
                adapter_version=_text(payload["adapter_version"], "adapter_version"),
                adapter_digest=digest,
            ),
            component_kinds=kinds,
            configuration_schema=tuple(sorted(normalized_schema)),
            typed_inputs=_strings(payload["typed_inputs"], "typed_inputs"),
            typed_outputs=_strings(payload["typed_outputs"], "typed_outputs"),
            required_capability_classes=_strings(
                payload["required_capability_classes"], "required_capability_classes"
            ),
            required_resource_classes=_strings(
                payload["required_resource_classes"], "required_resource_classes"
            ),
            required_provider_classes=_strings(
                payload["required_provider_classes"], "required_provider_classes"
            ),
            confinement_class=_text(payload["confinement_class"], "confinement_class"),
            budget_dimensions=_strings(payload["budget_dimensions"], "budget_dimensions"),
        )


class GovernedComponentRegistry:
    """Immutable installed descriptor index; tenant content cannot register entries."""

    def __init__(self, descriptors=()) -> None:
        by_ref: dict[str, GovernedComponentDescriptor] = {}
        by_digest: dict[str, GovernedComponentDescriptor] = {}
        by_kind: dict[str, list[GovernedComponentDescriptor]] = {}
        for descriptor in descriptors:
            if not isinstance(descriptor, GovernedComponentDescriptor):
                raise GovernedDescriptorError("registry accepts governed descriptors only")
            ref = descriptor.pin.adapter_ref
            digest = descriptor.pin.adapter_digest
            if ref in by_ref:
                raise GovernedDescriptorError(f"duplicate adapter_ref {ref!r}")
            if digest in by_digest:
                raise GovernedDescriptorError(f"descriptor digest reused by {ref!r}")
            by_ref[ref] = descriptor
            by_digest[digest] = descriptor
            for kind in descriptor.component_kinds:
                by_kind.setdefault(kind, []).append(descriptor)
        self._by_ref = by_ref
        self._by_kind = {key: tuple(value) for key, value in by_kind.items()}

    def resolve(self, *, adapter_ref: str | None, component_kind: str):
        if adapter_ref:
            return self._by_ref.get(adapter_ref)
        candidates = self._by_kind.get(component_kind, ())
        return candidates[0] if len(candidates) == 1 else None


@dataclass(frozen=True, slots=True)
class ComponentCompilationDiagnostic:
    component_key: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class CompiledAgentComponent:
    component_key: str
    component_kind: str
    runtime_mode: str
    public_component_json: str
    configuration_json: str
    adapter: GovernedAdapterPin | None
    typed_inputs: tuple[str, ...] = ()
    typed_outputs: tuple[str, ...] = ()
    required_capability_classes: tuple[str, ...] = ()
    required_resource_classes: tuple[str, ...] = ()
    required_provider_classes: tuple[str, ...] = ()
    confinement_class: str | None = None
    budget_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComponentCompilationResult:
    compiled_components: tuple[CompiledAgentComponent, ...]
    diagnostics: tuple[ComponentCompilationDiagnostic, ...]


def _configuration_valid(configuration: object, schema: tuple[tuple[str, str], ...]) -> bool:
    if not isinstance(configuration, Mapping) or set(configuration) != {key for key, _ in schema}:
        return False
    for key, type_name in schema:
        value = configuration[key]
        expected = _SCHEMA_TYPES[type_name]
        if type_name in {"integer", "number"} and isinstance(value, bool):
            return False
        if not isinstance(value, expected):
            return False
    return True


def compile_agent_components(
    *,
    public_components: Mapping[str, object],
    runtime_components: Mapping[str, object],
    component_configuration: Mapping[str, object],
    registry: GovernedComponentRegistry,
    available_confinement_classes: set[str],
) -> ComponentCompilationResult:
    """Compile every public component or return deterministic complete diagnostics."""

    diagnostics: list[ComponentCompilationDiagnostic] = []
    compiled: list[CompiledAgentComponent] = []
    public_keys = set(public_components)
    for extra in sorted((set(runtime_components) | set(component_configuration)) - public_keys):
        diagnostics.append(
            ComponentCompilationDiagnostic(
                extra, "component_unknown", "binding names no public component"
            )
        )
    for key in sorted(public_keys):
        public = public_components[key]
        runtime = runtime_components.get(key, {})
        configuration = component_configuration.get(key, {})
        if not isinstance(public, Mapping) or not isinstance(runtime, Mapping):
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key, "component_invalid", "component metadata is invalid"
                )
            )
            continue
        kind = public.get("kind")
        mode = runtime.get("mode", "execute")
        if not isinstance(kind, str) or not kind or mode not in {"execute", "descriptive_only"}:
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key, "component_invalid", "kind or runtime mode is invalid"
                )
            )
            continue
        if mode == "descriptive_only":
            if runtime.get("adapter_ref") is not None:
                diagnostics.append(
                    ComponentCompilationDiagnostic(
                        key,
                        "component_invalid",
                        "descriptive-only component cannot select an adapter",
                    )
                )
                continue
            compiled.append(
                CompiledAgentComponent(
                    component_key=key,
                    component_kind=kind,
                    runtime_mode=mode,
                    public_component_json=_canonical(public),
                    configuration_json=_canonical(configuration),
                    adapter=None,
                )
            )
            continue
        adapter_ref = runtime.get("adapter_ref")
        if adapter_ref is not None and (
            not isinstance(adapter_ref, str) or not adapter_ref.strip()
        ):
            diagnostics.append(
                ComponentCompilationDiagnostic(key, "component_invalid", "adapter_ref is invalid")
            )
            continue
        descriptor = registry.resolve(
            adapter_ref=adapter_ref if isinstance(adapter_ref, str) else None,
            component_kind=kind,
        )
        if descriptor is None or kind not in descriptor.component_kinds:
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key, "adapter_unavailable", "no compatible governed adapter"
                )
            )
            continue
        if descriptor.confinement_class not in available_confinement_classes:
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key, "sandbox_unavailable", "required confinement is unavailable"
                )
            )
            continue
        if not _configuration_valid(configuration, descriptor.configuration_schema):
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key, "configuration_invalid", "private configuration is invalid"
                )
            )
            continue
        compiled.append(
            CompiledAgentComponent(
                component_key=key,
                component_kind=kind,
                runtime_mode=mode,
                public_component_json=_canonical(public),
                configuration_json=_canonical(configuration),
                adapter=descriptor.pin,
                typed_inputs=descriptor.typed_inputs,
                typed_outputs=descriptor.typed_outputs,
                required_capability_classes=descriptor.required_capability_classes,
                required_resource_classes=descriptor.required_resource_classes,
                required_provider_classes=descriptor.required_provider_classes,
                confinement_class=descriptor.confinement_class,
                budget_dimensions=descriptor.budget_dimensions,
            )
        )
    ordered_diagnostics = tuple(
        sorted(diagnostics, key=lambda item: (item.component_key, item.code))
    )
    return ComponentCompilationResult(
        compiled_components=() if ordered_diagnostics else tuple(compiled),
        diagnostics=ordered_diagnostics,
    )


__all__ = [
    "CompiledAgentComponent",
    "ComponentCompilationDiagnostic",
    "ComponentCompilationResult",
    "GovernedAdapterPin",
    "GovernedComponentDescriptor",
    "GovernedComponentRegistry",
    "GovernedDescriptorError",
    "compile_agent_components",
]
