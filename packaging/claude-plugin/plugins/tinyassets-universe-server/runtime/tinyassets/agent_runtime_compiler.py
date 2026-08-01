"""Governed, deterministic component compilation for custom agents.

This module compiles components only. It cannot create a plan, manifest,
activation, provider call, workflow, app reply, or effect.
"""

from __future__ import annotations

import json
import math
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
    _validate_json_value(value, set())
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


def _validate_json_value(value: object, ancestors: set[int]) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GovernedDescriptorError("content must contain finite JSON numbers")
        return
    if isinstance(value, (Mapping, list)):
        identity = id(value)
        if identity in ancestors:
            raise GovernedDescriptorError("content must not contain cycles")
        ancestors.add(identity)
        try:
            if isinstance(value, Mapping):
                if any(not isinstance(key, str) for key in value):
                    raise GovernedDescriptorError("JSON object keys must be strings")
                for item in value.values():
                    _validate_json_value(item, ancestors)
            else:
                for item in value:
                    _validate_json_value(item, ancestors)
        finally:
            ancestors.remove(identity)
        return
    raise GovernedDescriptorError("content contains a non-JSON value")


def _canonical_tuple(value: object, name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise GovernedDescriptorError(f"{name} must be a canonical tuple")
    normalized = tuple(sorted({_text(item, name) for item in value}))
    if value != normalized:
        raise GovernedDescriptorError(f"{name} must be sorted and unique")
    if nonempty and not value:
        raise GovernedDescriptorError(f"{name} must not be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class GovernedAdapterPin:
    adapter_ref: str
    adapter_version: str
    adapter_digest: str

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        for name in ("adapter_ref", "adapter_version", "adapter_digest"):
            value = getattr(self, name)
            if value != _text(value, name):
                raise GovernedDescriptorError(f"{name} must be canonical text")
        if not _SHA256.fullmatch(self.adapter_digest):
            raise GovernedDescriptorError("adapter_digest must be canonical sha256")

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

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not isinstance(self.pin, GovernedAdapterPin):
            raise GovernedDescriptorError("pin must be a governed adapter pin")
        self.pin._validate()
        _canonical_tuple(self.component_kinds, "component_kinds", nonempty=True)
        for name in (
            "typed_inputs",
            "typed_outputs",
            "required_capability_classes",
            "required_resource_classes",
            "required_provider_classes",
            "budget_dimensions",
        ):
            _canonical_tuple(getattr(self, name), name)
        if self.confinement_class != _text(self.confinement_class, "confinement_class"):
            raise GovernedDescriptorError("confinement_class must be canonical text")
        if not isinstance(self.configuration_schema, tuple):
            raise GovernedDescriptorError("configuration_schema must be a canonical tuple")
        normalized_schema: list[tuple[str, str]] = []
        for item in self.configuration_schema:
            if not isinstance(item, tuple) or len(item) != 2:
                raise GovernedDescriptorError("configuration_schema entries are invalid")
            key = _text(item[0], "configuration_schema key")
            type_name = _text(item[1], f"configuration_schema.{key}")
            if type_name not in _SCHEMA_TYPES:
                raise GovernedDescriptorError(f"unsupported schema type {type_name!r}")
            normalized_schema.append((key, type_name))
        schema_keys = [key for key, _ in normalized_schema]
        if len(schema_keys) != len(set(schema_keys)) or self.configuration_schema != tuple(
            sorted(set(normalized_schema))
        ):
            raise GovernedDescriptorError(
                "configuration_schema must be sorted, canonical, and unique"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            **self.pin.to_dict(),
            "component_kinds": list(self.component_kinds),
            "configuration_schema": dict(self.configuration_schema),
            "typed_inputs": list(self.typed_inputs),
            "typed_outputs": list(self.typed_outputs),
            "required_capability_classes": list(self.required_capability_classes),
            "required_resource_classes": list(self.required_resource_classes),
            "required_provider_classes": list(self.required_provider_classes),
            "confinement_class": self.confinement_class,
            "budget_dimensions": list(self.budget_dimensions),
        }

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
            descriptor._validate()
            descriptor = GovernedComponentDescriptor.from_dict(descriptor.to_dict())
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
        descriptor, _ = self.resolve_with_status(
            adapter_ref=adapter_ref, component_kind=component_kind
        )
        return descriptor

    def resolve_with_status(self, *, adapter_ref: str | None, component_kind: str):
        if adapter_ref:
            descriptor = self._by_ref.get(adapter_ref)
            return descriptor, "resolved" if descriptor else "unavailable"
        candidates = self._by_kind.get(component_kind, ())
        if len(candidates) == 1:
            return candidates[0], "resolved"
        return None, "ambiguous" if candidates else "unavailable"


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
        if type_name == "number" and isinstance(value, float) and not math.isfinite(value):
            return False
    return True


def _input_keys(
    value: object,
    name: str,
    diagnostics: list[ComponentCompilationDiagnostic],
) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        diagnostics.append(
            ComponentCompilationDiagnostic(
                f"${name}", "input_invalid", "input must be a component mapping"
            )
        )
        return ()
    keys: list[str] = []
    invalid = False
    for key in value:
        if not isinstance(key, str) or not key.strip() or key != key.strip():
            invalid = True
        else:
            keys.append(key)
    if invalid:
        diagnostics.append(
            ComponentCompilationDiagnostic(
                f"${name}",
                "input_invalid",
                "component keys must be canonical non-empty strings",
            )
        )
    return tuple(sorted(set(keys)))


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
    public_keys = set(_input_keys(public_components, "public_components", diagnostics))
    runtime_keys = set(_input_keys(runtime_components, "runtime_components", diagnostics))
    configuration_keys = set(
        _input_keys(component_configuration, "component_configuration", diagnostics)
    )
    registry_is_valid = isinstance(registry, GovernedComponentRegistry)
    if not registry_is_valid:
        diagnostics.append(
            ComponentCompilationDiagnostic("$registry", "input_invalid", "registry is not governed")
        )
    confinement_is_valid = isinstance(available_confinement_classes, (set, frozenset)) and not any(
        not isinstance(item, str) or not item.strip() or item != item.strip()
        for item in available_confinement_classes
    )
    if not confinement_is_valid:
        diagnostics.append(
            ComponentCompilationDiagnostic(
                "$available_confinement_classes",
                "input_invalid",
                "confinement classes are invalid",
            )
        )
    for extra in sorted((runtime_keys | configuration_keys) - public_keys):
        diagnostics.append(
            ComponentCompilationDiagnostic(
                extra, "component_unknown", "binding names no public component"
            )
        )
    for key in sorted(public_keys):
        public = public_components[key]
        runtime = runtime_components.get(key, {}) if isinstance(runtime_components, Mapping) else {}
        configuration = (
            component_configuration.get(key, {})
            if isinstance(component_configuration, Mapping)
            else {}
        )
        if not isinstance(public, Mapping) or not isinstance(runtime, Mapping):
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key, "component_invalid", "component metadata is invalid"
                )
            )
            continue
        try:
            public_json = _canonical(public)
            _canonical(runtime)
        except GovernedDescriptorError:
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key, "component_invalid", "component metadata is not canonical JSON"
                )
            )
            continue
        try:
            configuration_json = _canonical(configuration)
        except GovernedDescriptorError:
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key,
                    "configuration_invalid",
                    "private configuration is not canonical JSON",
                )
            )
            continue
        kind = public.get("kind")
        mode = runtime.get("mode", "execute")
        if (
            not isinstance(kind, str)
            or not kind.strip()
            or kind != kind.strip()
            or not isinstance(mode, str)
            or mode not in {"execute", "descriptive_only"}
        ):
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
                    public_component_json=public_json,
                    configuration_json=configuration_json,
                    adapter=None,
                )
            )
            continue
        adapter_ref = runtime.get("adapter_ref")
        if adapter_ref is not None and (
            not isinstance(adapter_ref, str)
            or not adapter_ref.strip()
            or adapter_ref != adapter_ref.strip()
        ):
            diagnostics.append(
                ComponentCompilationDiagnostic(key, "component_invalid", "adapter_ref is invalid")
            )
            continue
        descriptor, resolution = (
            registry.resolve_with_status(
                adapter_ref=adapter_ref if isinstance(adapter_ref, str) else None,
                component_kind=kind,
            )
            if registry_is_valid
            else (None, "unavailable")
        )
        if resolution == "ambiguous":
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key,
                    "adapter_ambiguous",
                    "multiple governed adapters match; select one explicitly",
                )
            )
            continue
        if descriptor is None or kind not in descriptor.component_kinds:
            diagnostics.append(
                ComponentCompilationDiagnostic(
                    key, "adapter_unavailable", "no compatible governed adapter"
                )
            )
            continue
        if not confinement_is_valid or (
            descriptor.confinement_class not in available_confinement_classes
        ):
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
                public_component_json=public_json,
                configuration_json=configuration_json,
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
