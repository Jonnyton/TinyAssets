"""Immutable records for the dark custom-agent invocation authority source."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.storage.automation_activations import AutomationActivationExecutor

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class AgentInvocationIntegrityError(RuntimeError):
    """Persisted invocation authority evidence failed closed."""


class AgentInvocationEventState(str, Enum):
    ADMITTED = "admitted"
    INVALIDATED = "invalidated"


def _text(value: object, name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    clean = value.strip()
    if len(clean) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return clean


def _positive(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _digest(value: object, name: str) -> str:
    clean = _text(value, name, maximum=71)
    if _DIGEST.fullmatch(clean) is None:
        raise ValueError(f"{name} must be a sha256 digest")
    return clean


def _timestamp(value: object, name: str) -> str:
    clean = _text(value, name, maximum=64)
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return clean


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _content_digest(value: object) -> str:
    encoded = _canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _subject_to_dict(subject: ExecutionSubject) -> dict[str, object]:
    return {
        "kind": subject.kind.value,
        "ref": subject.ref,
        "digest": subject.digest,
    }


def _subject_from_dict(value: object) -> ExecutionSubject:
    if not isinstance(value, dict) or set(value) != {"kind", "ref", "digest"}:
        raise ValueError("execution_subject fields do not match schema")
    return ExecutionSubject(
        kind=ExecutionSubjectKind(value["kind"]),
        ref=value["ref"],
        digest=value["digest"],
    )


@dataclass(frozen=True, slots=True)
class AgentInvocationRoot:
    """Immutable, non-authorizing identity written only by future admission."""

    schema_version: int
    invocation_id: str
    authorizing_subject_id: str
    authorizing_grant_generation: int
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    execution_subject: ExecutionSubject
    activation_automation_id: str
    activation_epoch: int
    executor_class: AutomationActivationExecutor
    lease_id: str
    typed_input_digest: str
    command_id: str
    command_generation: int
    command_digest: str
    provider_work_binding_id: str
    provider_work_binding_generation: int
    provider_work_binding_digest: str
    idempotency_key_digest: str
    request_digest: str
    budget_digest: str
    admission_witness_id: str
    admission_witness_digest: str
    created_at: str
    root_digest: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "invocation_id",
            "authorizing_subject_id",
            "authorizing_grant_generation",
            "universe_id",
            "agent_binding_id",
            "binding_revision",
            "execution_subject",
            "activation_automation_id",
            "activation_epoch",
            "executor_class",
            "lease_id",
            "typed_input_digest",
            "command_id",
            "command_generation",
            "command_digest",
            "provider_work_binding_id",
            "provider_work_binding_generation",
            "provider_work_binding_digest",
            "idempotency_key_digest",
            "request_digest",
            "budget_digest",
            "admission_witness_id",
            "admission_witness_digest",
            "created_at",
            "root_digest",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        for name in (
            "invocation_id",
            "authorizing_subject_id",
            "universe_id",
            "agent_binding_id",
            "activation_automation_id",
            "lease_id",
            "command_id",
            "provider_work_binding_id",
            "admission_witness_id",
        ):
            _text(getattr(self, name), name)
        if not self.invocation_id.startswith("agent_invocation_"):
            raise ValueError("invocation_id is not an agent invocation")
        if not self.command_id.startswith("agent_invocation_command_"):
            raise ValueError("command_id is not an agent invocation command")
        if re.fullmatch(r"pwb_[0-9a-f]{32}", self.provider_work_binding_id) is None:
            raise ValueError("provider_work_binding_id is not canonical")
        for name in (
            "authorizing_grant_generation",
            "binding_revision",
            "activation_epoch",
            "command_generation",
            "provider_work_binding_generation",
        ):
            _positive(getattr(self, name), name)
        if (
            not isinstance(self.execution_subject, ExecutionSubject)
            or self.execution_subject.kind is not ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST
        ):
            raise ValueError("execution_subject must be an agent runtime manifest")
        if not isinstance(self.executor_class, AutomationActivationExecutor):
            raise ValueError("executor_class must be typed")
        for name in (
            "typed_input_digest",
            "command_digest",
            "provider_work_binding_digest",
            "idempotency_key_digest",
            "request_digest",
            "budget_digest",
            "admission_witness_digest",
            "root_digest",
        ):
            _digest(getattr(self, name), name)
        _timestamp(self.created_at, "created_at")
        if self.root_digest != self.computed_digest:
            raise ValueError("root_digest does not match canonical content")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "invocation_id": self.invocation_id,
            "authorizing_subject_id": self.authorizing_subject_id,
            "authorizing_grant_generation": self.authorizing_grant_generation,
            "universe_id": self.universe_id,
            "agent_binding_id": self.agent_binding_id,
            "binding_revision": self.binding_revision,
            "execution_subject": _subject_to_dict(self.execution_subject),
            "activation_automation_id": self.activation_automation_id,
            "activation_epoch": self.activation_epoch,
            "executor_class": self.executor_class.value,
            "lease_id": self.lease_id,
            "typed_input_digest": self.typed_input_digest,
            "command_id": self.command_id,
            "command_generation": self.command_generation,
            "command_digest": self.command_digest,
            "provider_work_binding_id": self.provider_work_binding_id,
            "provider_work_binding_generation": self.provider_work_binding_generation,
            "provider_work_binding_digest": self.provider_work_binding_digest,
            "idempotency_key_digest": self.idempotency_key_digest,
            "request_digest": self.request_digest,
            "budget_digest": self.budget_digest,
            "admission_witness_id": self.admission_witness_id,
            "admission_witness_digest": self.admission_witness_digest,
            "created_at": self.created_at,
        }

    @property
    def computed_digest(self) -> str:
        return _content_digest(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "root_digest": self.root_digest}

    @classmethod
    def build(cls, **values: Any) -> AgentInvocationRoot:
        if "root_digest" in values:
            raise ValueError("root_digest is server-computed")
        provisional = object.__new__(cls)
        for field_name in cls._FIELDS - {"root_digest"}:
            if field_name not in values:
                raise ValueError(f"missing {field_name}")
            object.__setattr__(provisional, field_name, values[field_name])
        extra = set(values) - (cls._FIELDS - {"root_digest"})
        if extra:
            raise ValueError("root fields do not match schema")
        object.__setattr__(provisional, "root_digest", provisional.computed_digest)
        provisional.__post_init__()
        return provisional

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentInvocationRoot:
        if not isinstance(data, dict) or set(data) != cls._FIELDS:
            raise ValueError("root fields do not match schema")
        values = dict(data)
        values["execution_subject"] = _subject_from_dict(values["execution_subject"])
        values["executor_class"] = AutomationActivationExecutor(values["executor_class"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class AgentInvocationEvent:
    """One append-only invocation lifecycle event."""

    schema_version: int
    event_id: str
    invocation_id: str
    generation: int
    state: AgentInvocationEventState
    previous_event_digest: str | None
    root_digest: str
    reason_code: str | None
    occurred_at: str
    event_digest: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "event_id",
            "invocation_id",
            "generation",
            "state",
            "previous_event_digest",
            "root_digest",
            "reason_code",
            "occurred_at",
            "event_digest",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        for name in ("event_id", "invocation_id"):
            _text(getattr(self, name), name)
        if not self.event_id.startswith("agent_invocation_event_"):
            raise ValueError("event_id is not an agent invocation event")
        if not self.invocation_id.startswith("agent_invocation_"):
            raise ValueError("invocation_id is not an agent invocation")
        _positive(self.generation, "generation")
        if not isinstance(self.state, AgentInvocationEventState):
            raise ValueError("state must be typed")
        if self.previous_event_digest is not None:
            _digest(self.previous_event_digest, "previous_event_digest")
        _digest(self.root_digest, "root_digest")
        if self.reason_code is not None:
            _text(self.reason_code, "reason_code", maximum=128)
        _timestamp(self.occurred_at, "occurred_at")
        _digest(self.event_digest, "event_digest")
        if self.event_digest != self.computed_digest:
            raise ValueError("event_digest does not match canonical content")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "invocation_id": self.invocation_id,
            "generation": self.generation,
            "state": self.state.value,
            "previous_event_digest": self.previous_event_digest,
            "root_digest": self.root_digest,
            "reason_code": self.reason_code,
            "occurred_at": self.occurred_at,
        }

    @property
    def computed_digest(self) -> str:
        return _content_digest(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "event_digest": self.event_digest}

    @classmethod
    def build(cls, **values: Any) -> AgentInvocationEvent:
        if "event_digest" in values:
            raise ValueError("event_digest is server-computed")
        provisional = object.__new__(cls)
        for field_name in cls._FIELDS - {"event_digest"}:
            if field_name not in values:
                raise ValueError(f"missing {field_name}")
            object.__setattr__(provisional, field_name, values[field_name])
        extra = set(values) - (cls._FIELDS - {"event_digest"})
        if extra:
            raise ValueError("event fields do not match schema")
        object.__setattr__(provisional, "event_digest", provisional.computed_digest)
        provisional.__post_init__()
        return provisional

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentInvocationEvent:
        if not isinstance(data, dict) or set(data) != cls._FIELDS:
            raise ValueError("event fields do not match schema")
        values = dict(data)
        values["state"] = AgentInvocationEventState(values["state"])
        return cls(**values)


__all__ = [
    "AgentInvocationEvent",
    "AgentInvocationEventState",
    "AgentInvocationIntegrityError",
    "AgentInvocationRoot",
]
