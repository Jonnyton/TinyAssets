"""Immutable, non-authorizing custom-agent runtime manifest contracts.

The manifest freezes compiler output. It does not activate an agent, grant
authority, invoke a provider, retain a conversation, or perform an effect.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

AGENT_RUNTIME_MANIFEST_SCHEMA_VERSION = 1
MAX_AGENT_RUNTIME_MANIFEST_BYTES = 256 * 1024

_COMPONENT_KEY = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_BUDGET_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CONTENT_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_CREDENTIAL_VALUE = re.compile(
    r"(?i)(?:bearer\s+[a-z0-9._~+/-]{3,}|gh[pousr]_[a-z0-9_=-]{12,}|"
    r"xox[baprs]-[a-z0-9-]{12,}|sk-[a-z0-9_-]{16,}|"
    r"eyj[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\.[a-z0-9_-]{8,})"
)
_SECRET_FIELD_NAMES = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "bearer",
        "bot_token",
        "client_secret",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "secrets",
        "session_token",
        "signing_secret",
        "token",
        "webhook_secret",
    }
)
_FORBIDDEN_RUNTIME_FIELDS = frozenset(
    {
        "chat_history",
        "conversation",
        "conversation_history",
        "conversations",
        "effect_payload",
        "effect_payloads",
        "execution_history",
        "external_write_results",
        "message_history",
        "messages",
        "provider_output",
        "provider_outputs",
        "provider_response",
        "provider_responses",
        "run_history",
        "run_state",
        "runtime_state",
        "transcript",
        "transcripts",
    }
)
_SENSITIVE_SUFFIXES = (
    "_api_key",
    "_authorization",
    "_credential",
    "_credentials",
    "_password",
    "_private_key",
    "_secret",
    "_token",
)
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "owner_user_id",
        "universe_id",
        "agent_binding_id",
        "binding_revision",
        "binding_configuration_digest",
        "agent_definition_id",
        "definition_fingerprint",
        "components",
        "plan_adapter",
        "execution_plan",
        "requested_references",
        "budgets",
        "compiler_contract_version",
    }
)
_REFERENCE_FIELDS = frozenset({"capability_ids", "resource_ids", "provider_policy_ids"})


class AgentRuntimeManifestValidationError(ValueError):
    """Manifest input is incomplete, unsafe, or non-canonical."""


class AgentRuntimeManifestConflict(AgentRuntimeManifestValidationError):
    """An owner-scoped idempotency key was reused for different input."""


class AgentRuntimeManifestIntegrityError(RuntimeError):
    """Persisted manifest columns and canonical content disagree."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as exc:
        raise AgentRuntimeManifestValidationError(
            f"manifest content must be canonical JSON: {exc}"
        ) from exc


def canonical_content_digest(value: object) -> str:
    """Return a deterministic SHA-256 digest for one JSON-compatible value."""

    return f"sha256:{hashlib.sha256(_canonical_bytes(value)).hexdigest()}"


def _required_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentRuntimeManifestValidationError(f"{path} must be a non-empty string")
    clean = value.strip()
    if len(clean) > 512:
        raise AgentRuntimeManifestValidationError(f"{path} exceeds 512 characters")
    return clean


def _canonical_digest(value: object, path: str) -> str:
    clean = _required_text(value, path)
    if not _SHA256.fullmatch(clean):
        raise AgentRuntimeManifestValidationError(f"{path} must be a canonical sha256 digest")
    return clean


def _reject_private_content(value: object, path: str = "") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.strip().casefold().replace("-", "_")
            child_path = f"{path}.{key}" if path else key
            if (
                normalized in _SECRET_FIELD_NAMES
                or normalized in _FORBIDDEN_RUNTIME_FIELDS
                or normalized.endswith(_SENSITIVE_SUFFIXES)
                or _CREDENTIAL_VALUE.search(key)
            ):
                raise AgentRuntimeManifestValidationError(
                    f"{child_path} is credential, conversation, effect, output, "
                    "or mutable runtime content"
                )
            _reject_private_content(child, child_path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_private_content(child, f"{path}[{index}]")
        return
    if isinstance(value, str) and _CREDENTIAL_VALUE.search(value):
        raise AgentRuntimeManifestValidationError(f"{path} contains a credential-shaped value")


def _normalize_adapter(
    value: object,
    *,
    path: str,
    expected_kind: str,
    include_plan_class: bool,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise AgentRuntimeManifestValidationError(f"{path} must be an object")
    fields = {
        "adapter_kind",
        "adapter_ref",
        "adapter_version",
        "adapter_digest",
    }
    if include_plan_class:
        fields.add("plan_class")
    if set(value) != fields:
        raise AgentRuntimeManifestValidationError(f"{path} must contain exactly {sorted(fields)}")
    kind = _required_text(value["adapter_kind"], f"{path}.adapter_kind")
    if kind != expected_kind:
        raise AgentRuntimeManifestValidationError(f"{path}.adapter_kind must be {expected_kind!r}")
    normalized = {
        "adapter_kind": kind,
        "adapter_ref": _required_text(value["adapter_ref"], f"{path}.adapter_ref"),
        "adapter_version": _required_text(value["adapter_version"], f"{path}.adapter_version"),
        "adapter_digest": _canonical_digest(value["adapter_digest"], f"{path}.adapter_digest"),
    }
    if include_plan_class:
        normalized["plan_class"] = _required_text(value["plan_class"], f"{path}.plan_class")
    return normalized


def _normalize_components(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, Mapping) or not value:
        raise AgentRuntimeManifestValidationError("components must be a non-empty object")
    if len(value) > 64:
        raise AgentRuntimeManifestValidationError("components may contain at most 64 entries")
    normalized: dict[str, dict[str, object]] = {}
    for raw_key, raw_component in value.items():
        key = str(raw_key)
        path = f"components.{key}"
        if not _COMPONENT_KEY.fullmatch(key):
            raise AgentRuntimeManifestValidationError(f"{path} is not a valid component key")
        if not isinstance(raw_component, Mapping):
            raise AgentRuntimeManifestValidationError(f"{path} must be an object")
        if set(raw_component) != {"runtime_mode", "configuration", "adapter"}:
            raise AgentRuntimeManifestValidationError(
                f"{path} must contain runtime_mode, configuration, and adapter"
            )
        runtime_mode = _required_text(raw_component["runtime_mode"], f"{path}.runtime_mode")
        if runtime_mode not in {"execute", "descriptive_only"}:
            raise AgentRuntimeManifestValidationError(f"{path}.runtime_mode is unsupported")
        configuration = raw_component["configuration"]
        if not isinstance(configuration, Mapping):
            raise AgentRuntimeManifestValidationError(f"{path}.configuration must be an object")
        configuration = json.loads(_canonical_bytes(configuration))
        adapter_value = raw_component["adapter"]
        if runtime_mode == "descriptive_only":
            if adapter_value is not None:
                raise AgentRuntimeManifestValidationError(
                    f"{path}.adapter must be null for descriptive_only"
                )
            adapter = None
        else:
            adapter = _normalize_adapter(
                adapter_value,
                path=f"{path}.adapter",
                expected_kind="component",
                include_plan_class=False,
            )
        normalized[key] = {
            "runtime_mode": runtime_mode,
            "configuration": configuration,
            "adapter": adapter,
        }
    return normalized


def _normalize_references(value: object) -> dict[str, list[str]]:
    if not isinstance(value, Mapping) or set(value) != _REFERENCE_FIELDS:
        raise AgentRuntimeManifestValidationError(
            f"requested_references must contain exactly {sorted(_REFERENCE_FIELDS)}"
        )
    normalized: dict[str, list[str]] = {}
    for field in sorted(_REFERENCE_FIELDS):
        raw_values = value[field]
        if not isinstance(raw_values, list):
            raise AgentRuntimeManifestValidationError(
                f"requested_references.{field} must be a list"
            )
        normalized[field] = sorted(
            {_required_text(item, f"requested_references.{field}") for item in raw_values}
        )
    return normalized


def _normalize_budgets(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise AgentRuntimeManifestValidationError("budgets must be an object")
    normalized: dict[str, int] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        if not _BUDGET_KEY.fullmatch(key):
            raise AgentRuntimeManifestValidationError(f"budgets.{key} is not a valid dimension")
        if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value < 0:
            raise AgentRuntimeManifestValidationError(f"budgets.{key} must be an integer >= 0")
        normalized[key] = raw_value
    return normalized


@dataclass(frozen=True, slots=True)
class AgentRuntimeManifestInput:
    """Validated canonical compiler output, before identity and persistence."""

    _canonical_json: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "AgentRuntimeManifestInput":
        if not isinstance(payload, Mapping):
            raise AgentRuntimeManifestValidationError("manifest input must be an object")
        if set(payload) != _TOP_LEVEL_FIELDS:
            unknown = sorted(set(payload) - _TOP_LEVEL_FIELDS)
            missing = sorted(_TOP_LEVEL_FIELDS - set(payload))
            raise AgentRuntimeManifestValidationError(
                f"manifest fields do not match contract; missing={missing}, unknown={unknown}"
            )
        schema_version = payload["schema_version"]
        if schema_version != AGENT_RUNTIME_MANIFEST_SCHEMA_VERSION:
            raise AgentRuntimeManifestValidationError("schema_version is not supported")
        revision = payload["binding_revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise AgentRuntimeManifestValidationError("binding_revision must be an integer >= 1")
        fingerprint = _required_text(payload["definition_fingerprint"], "definition_fingerprint")
        if not _CONTENT_FINGERPRINT.fullmatch(fingerprint):
            raise AgentRuntimeManifestValidationError(
                "definition_fingerprint must be 64 lowercase hex characters"
            )
        execution_plan = payload["execution_plan"]
        if not isinstance(execution_plan, Mapping) or not execution_plan:
            raise AgentRuntimeManifestValidationError("execution_plan must be a non-empty object")
        normalized: dict[str, object] = {
            "schema_version": AGENT_RUNTIME_MANIFEST_SCHEMA_VERSION,
            "owner_user_id": _required_text(payload["owner_user_id"], "owner_user_id"),
            "universe_id": _required_text(payload["universe_id"], "universe_id"),
            "agent_binding_id": _required_text(payload["agent_binding_id"], "agent_binding_id"),
            "binding_revision": revision,
            "binding_configuration_digest": _canonical_digest(
                payload["binding_configuration_digest"],
                "binding_configuration_digest",
            ),
            "agent_definition_id": _required_text(
                payload["agent_definition_id"], "agent_definition_id"
            ),
            "definition_fingerprint": fingerprint,
            "components": _normalize_components(payload["components"]),
            "plan_adapter": _normalize_adapter(
                payload["plan_adapter"],
                path="plan_adapter",
                expected_kind="plan",
                include_plan_class=True,
            ),
            "execution_plan": json.loads(_canonical_bytes(execution_plan)),
            "requested_references": _normalize_references(payload["requested_references"]),
            "budgets": _normalize_budgets(payload["budgets"]),
            "compiler_contract_version": _required_text(
                payload["compiler_contract_version"],
                "compiler_contract_version",
            ),
        }
        normalized_plan = normalized["execution_plan"]
        normalized_plan_adapter = normalized["plan_adapter"]
        if not isinstance(normalized_plan, Mapping) or not isinstance(
            normalized_plan_adapter, Mapping
        ):
            raise AgentRuntimeManifestValidationError("normalized plan is invalid")
        if normalized_plan.get("plan_class") != normalized_plan_adapter.get("plan_class"):
            raise AgentRuntimeManifestValidationError(
                "execution_plan.plan_class must match plan_adapter.plan_class"
            )
        _reject_private_content(normalized)
        canonical = _canonical_bytes(normalized)
        if len(canonical) > MAX_AGENT_RUNTIME_MANIFEST_BYTES:
            raise AgentRuntimeManifestValidationError(
                f"manifest content exceeds {MAX_AGENT_RUNTIME_MANIFEST_BYTES} bytes"
            )
        return cls(canonical.decode("utf-8"))

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def input_digest(self) -> str:
        return f"sha256:{hashlib.sha256(self._canonical_json.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class AgentRuntimeManifest:
    manifest_id: str
    manifest_digest: str
    manifest_input: AgentRuntimeManifestInput
    created_at: str

    def __post_init__(self) -> None:
        if not self.manifest_id.startswith("agent_manifest_"):
            raise AgentRuntimeManifestIntegrityError("manifest_id is invalid")
        if self.manifest_digest != self.manifest_input.input_digest:
            raise AgentRuntimeManifestIntegrityError("manifest digest does not match content")
        _required_text(self.created_at, "created_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "manifest_digest": self.manifest_digest,
            "created_at": self.created_at,
            **self.manifest_input.to_dict(),
        }


__all__ = [
    "AGENT_RUNTIME_MANIFEST_SCHEMA_VERSION",
    "MAX_AGENT_RUNTIME_MANIFEST_BYTES",
    "AgentRuntimeManifest",
    "AgentRuntimeManifestConflict",
    "AgentRuntimeManifestInput",
    "AgentRuntimeManifestIntegrityError",
    "AgentRuntimeManifestValidationError",
    "canonical_content_digest",
]
