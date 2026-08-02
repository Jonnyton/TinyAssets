"""Immutable records for the dark custom-agent invocation command source."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.storage.automation_activations import AutomationActivationExecutor

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SQLITE_INTEGER_MAX = (1 << 63) - 1


class AgentInvocationCommandIntegrityError(RuntimeError):
    """Persisted invocation-command evidence failed closed."""


def _text(value: object, name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    clean = value.strip()
    if len(clean) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return clean


def _bounded_integer(
    value: object,
    name: str,
    *,
    minimum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > _SQLITE_INTEGER_MAX
    ):
        qualifier = "positive" if minimum == 1 else "non-negative"
        raise ValueError(f"{name} must be a bounded {qualifier} integer")
    return value


def _positive(value: object, name: str) -> int:
    return _bounded_integer(value, name, minimum=1)


def _nonnegative(value: object, name: str) -> int:
    return _bounded_integer(value, name, minimum=0)


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
class AgentInvocationBudgetEnvelope:
    """Typed upper bounds pinned into one invocation command."""

    max_invocations: int
    max_tokens: int
    max_cost_microunits: int
    max_turns: int
    expires_at: str
    budget_digest: str

    _FIELDS = frozenset(
        {
            "max_invocations",
            "max_tokens",
            "max_cost_microunits",
            "max_turns",
            "expires_at",
            "budget_digest",
        }
    )

    def __post_init__(self) -> None:
        _positive(self.max_invocations, "max_invocations")
        _nonnegative(self.max_tokens, "max_tokens")
        _nonnegative(self.max_cost_microunits, "max_cost_microunits")
        _positive(self.max_turns, "max_turns")
        _timestamp(self.expires_at, "expires_at")
        _digest(self.budget_digest, "budget_digest")
        if self.budget_digest != self.computed_digest:
            raise ValueError("budget_digest does not match canonical content")

    def _content_dict(self) -> dict[str, object]:
        return {
            "max_invocations": self.max_invocations,
            "max_tokens": self.max_tokens,
            "max_cost_microunits": self.max_cost_microunits,
            "max_turns": self.max_turns,
            "expires_at": self.expires_at,
        }

    @property
    def computed_digest(self) -> str:
        return _content_digest(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "budget_digest": self.budget_digest}

    @classmethod
    def build(cls, **values: Any) -> AgentInvocationBudgetEnvelope:
        if "budget_digest" in values:
            raise ValueError("budget_digest is server-computed")
        expected = cls._FIELDS - {"budget_digest"}
        if set(values) != expected:
            raise ValueError("budget fields do not match schema")
        provisional = object.__new__(cls)
        for field_name in expected:
            object.__setattr__(provisional, field_name, values[field_name])
        object.__setattr__(provisional, "budget_digest", provisional.computed_digest)
        provisional.__post_init__()
        return provisional

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentInvocationBudgetEnvelope:
        if not isinstance(data, dict) or set(data) != cls._FIELDS:
            raise ValueError("budget fields do not match schema")
        return cls(**data)


@dataclass(frozen=True, slots=True)
class AgentInvocationCommand:
    """Immutable, non-authorizing request prepared for future admission."""

    schema_version: int
    command_id: str
    generation: int
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
    provider_work_binding_id: str
    provider_work_binding_generation: int
    provider_work_binding_digest: str
    idempotency_key_digest: str
    request_digest: str
    budget: AgentInvocationBudgetEnvelope
    admission_witness_id: str
    admission_witness_digest: str
    created_at: str
    command_digest: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "command_id",
            "generation",
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
            "provider_work_binding_id",
            "provider_work_binding_generation",
            "provider_work_binding_digest",
            "idempotency_key_digest",
            "request_digest",
            "budget",
            "budget_digest",
            "admission_witness_id",
            "admission_witness_digest",
            "created_at",
            "command_digest",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        for name in (
            "command_id",
            "invocation_id",
            "authorizing_subject_id",
            "universe_id",
            "agent_binding_id",
            "activation_automation_id",
            "lease_id",
            "provider_work_binding_id",
            "admission_witness_id",
        ):
            _text(getattr(self, name), name)
        if not self.command_id.startswith("agent_invocation_command_"):
            raise ValueError("command_id is not an agent invocation command")
        if not self.invocation_id.startswith("agent_invocation_"):
            raise ValueError("invocation_id is not an agent invocation")
        if re.fullmatch(r"pwb_[0-9a-f]{32}", self.provider_work_binding_id) is None:
            raise ValueError("provider_work_binding_id is not canonical")
        if not self.admission_witness_id.startswith("agent_invocation_admission_"):
            raise ValueError("admission_witness_id is not canonical")
        for name in (
            "generation",
            "authorizing_grant_generation",
            "binding_revision",
            "activation_epoch",
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
        if not isinstance(self.budget, AgentInvocationBudgetEnvelope):
            raise ValueError("budget must be a typed invocation budget envelope")
        for name in (
            "typed_input_digest",
            "provider_work_binding_digest",
            "idempotency_key_digest",
            "request_digest",
            "admission_witness_digest",
            "command_digest",
        ):
            _digest(getattr(self, name), name)
        _timestamp(self.created_at, "created_at")
        if self.command_digest != self.computed_digest:
            raise ValueError("command_digest does not match canonical content")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "command_id": self.command_id,
            "generation": self.generation,
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
            "provider_work_binding_id": self.provider_work_binding_id,
            "provider_work_binding_generation": self.provider_work_binding_generation,
            "provider_work_binding_digest": self.provider_work_binding_digest,
            "idempotency_key_digest": self.idempotency_key_digest,
            "request_digest": self.request_digest,
            "budget": self.budget.to_dict(),
            "budget_digest": self.budget.budget_digest,
            "admission_witness_id": self.admission_witness_id,
            "admission_witness_digest": self.admission_witness_digest,
            "created_at": self.created_at,
        }

    @property
    def computed_digest(self) -> str:
        return _content_digest(self._content_dict())

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "command_digest": self.command_digest}

    @classmethod
    def build(cls, **values: Any) -> AgentInvocationCommand:
        if "command_digest" in values or "budget_digest" in values:
            raise ValueError("computed digests cannot be supplied")
        expected = cls._FIELDS - {"command_digest", "budget_digest"}
        if set(values) != expected:
            raise ValueError("command fields do not match schema")
        provisional = object.__new__(cls)
        for field_name in expected:
            object.__setattr__(provisional, field_name, values[field_name])
        object.__setattr__(provisional, "command_digest", provisional.computed_digest)
        provisional.__post_init__()
        return provisional

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentInvocationCommand:
        if not isinstance(data, dict) or set(data) != cls._FIELDS:
            raise ValueError("command fields do not match schema")
        values = dict(data)
        budget_digest = values.pop("budget_digest")
        values["execution_subject"] = _subject_from_dict(values["execution_subject"])
        values["executor_class"] = AutomationActivationExecutor(values["executor_class"])
        values["budget"] = AgentInvocationBudgetEnvelope.from_dict(values["budget"])
        if values["budget"].budget_digest != budget_digest:
            raise ValueError("budget_digest does not match typed budget")
        return cls(**values)


__all__ = [
    "AgentInvocationBudgetEnvelope",
    "AgentInvocationCommand",
    "AgentInvocationCommandIntegrityError",
]
