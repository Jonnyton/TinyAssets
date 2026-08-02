"""Non-authorizing typed outcomes for one admitted agent provider call."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

MAX_AGENT_PROVIDER_OUTPUT_BYTES = 32 * 1024


class AgentProviderOutcomeState(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INDETERMINATE = "indeterminate"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return f"sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def _text(value: object, name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    if len(value) > maximum:
        raise ValueError(f"{name} is too long")
    return value


def _digest_value(value: object, name: str) -> str:
    text = _text(value, name)
    if len(text) != 71 or not text.startswith("sha256:"):
        raise ValueError(f"{name} must be a sha256 digest")
    try:
        int(text[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a sha256 digest") from exc
    return text


@dataclass(frozen=True, slots=True)
class AgentInvocationProviderOutcome:
    """One terminal, inert result bound to the exact launched reservation."""

    schema_version: int
    outcome_id: str
    outcome_digest: str
    state: AgentProviderOutcomeState
    invocation_id: str
    continuation_id: str
    continuation_digest: str
    reservation_id: str
    launch_reservation_digest: str
    terminal_reservation_digest: str
    typed_input_digest: str
    provider: str
    model: str
    family: str
    latency_ms: float | None
    typed_output: dict[str, Any] | None
    blocker_code: str | None
    blocker_detail: str | None
    created_at: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "outcome_id",
            "outcome_digest",
            "state",
            "invocation_id",
            "continuation_id",
            "continuation_digest",
            "reservation_id",
            "launch_reservation_digest",
            "terminal_reservation_digest",
            "typed_input_digest",
            "provider",
            "model",
            "family",
            "latency_ms",
            "typed_output",
            "blocker_code",
            "blocker_detail",
            "created_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported outcome schema_version")
        if not isinstance(self.state, AgentProviderOutcomeState):
            raise ValueError("outcome state must be typed")
        for name in (
            "outcome_id",
            "invocation_id",
            "continuation_id",
            "reservation_id",
            "provider",
            "created_at",
        ):
            _text(getattr(self, name), name)
        for name in (
            "outcome_digest",
            "continuation_digest",
            "launch_reservation_digest",
            "terminal_reservation_digest",
            "typed_input_digest",
        ):
            _digest_value(getattr(self, name), name)
        if self.latency_ms is not None and (
            isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, (int, float))
            or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be non-negative")
        if self.state is AgentProviderOutcomeState.SUCCEEDED:
            if not isinstance(self.typed_output, dict):
                raise ValueError("successful outcome requires typed_output")
            if set(self.typed_output) != {"kind", "text"}:
                raise ValueError("typed_output fields do not match provider_text")
            if self.typed_output.get("kind") != "provider_text" or not isinstance(
                self.typed_output.get("text"), str
            ):
                raise ValueError("typed_output must be provider_text")
            if self.blocker_code is not None or self.blocker_detail is not None:
                raise ValueError("successful outcome cannot carry a blocker")
            _text(self.model, "model")
            _text(self.family, "family")
            if len(_canonical(self.typed_output)) > MAX_AGENT_PROVIDER_OUTPUT_BYTES:
                raise ValueError("typed_output exceeds bounded storage")
        else:
            if self.typed_output is not None:
                raise ValueError("blocked outcome cannot carry typed_output")
            _text(self.blocker_code, "blocker_code", maximum=128)
            _text(self.blocker_detail, "blocker_detail", maximum=512)
        if self.outcome_digest != self.expected_digest():
            raise ValueError("outcome_digest does not match content")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome_id": self.outcome_id,
            "outcome_digest": self.outcome_digest,
            "state": self.state.value,
            "invocation_id": self.invocation_id,
            "continuation_id": self.continuation_id,
            "continuation_digest": self.continuation_digest,
            "reservation_id": self.reservation_id,
            "launch_reservation_digest": self.launch_reservation_digest,
            "terminal_reservation_digest": self.terminal_reservation_digest,
            "typed_input_digest": self.typed_input_digest,
            "provider": self.provider,
            "model": self.model,
            "family": self.family,
            "latency_ms": self.latency_ms,
            "typed_output": self.typed_output,
            "blocker_code": self.blocker_code,
            "blocker_detail": self.blocker_detail,
            "created_at": self.created_at,
        }

    @classmethod
    def build(cls, **values: Any) -> "AgentInvocationProviderOutcome":
        if "outcome_digest" in values:
            raise ValueError("outcome_digest is server-computed")
        provisional = object.__new__(cls)
        expected = cls._FIELDS - {"outcome_digest"}
        if set(values) != expected:
            raise ValueError("outcome fields do not match schema")
        for name in expected:
            value = values[name]
            if name == "typed_output" and value is not None:
                value = json.loads(_canonical(value))
            object.__setattr__(provisional, name, value)
        object.__setattr__(provisional, "outcome_digest", f"sha256:{'0' * 64}")
        object.__setattr__(provisional, "outcome_digest", provisional.expected_digest())
        provisional.__post_init__()
        return provisional

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "AgentInvocationProviderOutcome":
        if not isinstance(value, Mapping) or set(value) != cls._FIELDS:
            raise ValueError("outcome fields do not match schema")
        payload = dict(value)
        payload["state"] = AgentProviderOutcomeState(payload["state"])
        output = payload["typed_output"]
        if output is not None:
            if not isinstance(output, dict):
                raise ValueError("typed_output must be an object")
            payload["typed_output"] = json.loads(_canonical(output))
        return cls(**payload)  # type: ignore[arg-type]

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["outcome_digest"]
        return _digest(payload)


__all__ = [
    "MAX_AGENT_PROVIDER_OUTPUT_BYTES",
    "AgentInvocationProviderOutcome",
    "AgentProviderOutcomeState",
]
