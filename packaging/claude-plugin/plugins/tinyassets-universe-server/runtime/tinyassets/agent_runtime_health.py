"""Private, non-authorizing useful-progress health for custom-agent work."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum


class AgentRuntimeHealthState(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    STALLED = "stalled"
    TERMINAL = "terminal"


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class AgentRuntimeNoProgressAlarm:
    alarm_id: str
    invocation_id: str
    useful_progress_digest: str
    useful_milestone: str
    useful_progress_at: str
    threshold_seconds: int
    raised_at: str

    def __post_init__(self) -> None:
        for name in (
            "alarm_id",
            "invocation_id",
            "useful_milestone",
            "useful_progress_at",
            "raised_at",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not self.alarm_id.startswith("agent_no_progress_"):
            raise ValueError("alarm_id is invalid")
        if (
            not isinstance(self.useful_progress_digest, str)
            or len(self.useful_progress_digest) != 71
            or not self.useful_progress_digest.startswith("sha256:")
        ):
            raise ValueError("useful_progress_digest must be canonical")
        if (
            isinstance(self.threshold_seconds, bool)
            or not isinstance(self.threshold_seconds, int)
            or self.threshold_seconds < 1
        ):
            raise ValueError("threshold_seconds must be an integer >= 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "alarm_id": self.alarm_id,
            "invocation_id": self.invocation_id,
            "useful_progress_digest": self.useful_progress_digest,
            "useful_milestone": self.useful_milestone,
            "useful_progress_at": self.useful_progress_at,
            "threshold_seconds": self.threshold_seconds,
            "raised_at": self.raised_at,
        }


@dataclass(frozen=True, slots=True)
class AgentRuntimeUsefulProgressHealth:
    invocation_id: str
    state: AgentRuntimeHealthState
    useful_milestone: str
    useful_record_digest: str
    useful_progress_digest: str
    useful_progress_at: str
    observed_at: str
    no_progress_seconds: int
    authority_current: bool
    terminal_outcome_state: str | None
    alarm: AgentRuntimeNoProgressAlarm | None

    def __post_init__(self) -> None:
        if not isinstance(self.state, AgentRuntimeHealthState):
            raise ValueError("health state must be typed")
        if (
            isinstance(self.no_progress_seconds, bool)
            or not isinstance(self.no_progress_seconds, int)
            or self.no_progress_seconds < 0
        ):
            raise ValueError("no_progress_seconds must be an integer >= 0")
        if not isinstance(self.authority_current, bool):
            raise ValueError("authority_current must be boolean")

    @classmethod
    def build(
        cls,
        *,
        invocation_id: str,
        state: AgentRuntimeHealthState,
        useful_milestone: str,
        useful_record_digest: str,
        useful_progress_at: str,
        observed_at: str,
        no_progress_seconds: int,
        authority_current: bool,
        terminal_outcome_state: str | None,
        alarm: AgentRuntimeNoProgressAlarm | None,
    ) -> "AgentRuntimeUsefulProgressHealth":
        progress_digest = _digest(
            {
                "invocation_id": invocation_id,
                "useful_milestone": useful_milestone,
                "useful_record_digest": useful_record_digest,
                "useful_progress_at": useful_progress_at,
            }
        )
        return cls(
            invocation_id=invocation_id,
            state=state,
            useful_milestone=useful_milestone,
            useful_record_digest=useful_record_digest,
            useful_progress_digest=progress_digest,
            useful_progress_at=useful_progress_at,
            observed_at=observed_at,
            no_progress_seconds=no_progress_seconds,
            authority_current=authority_current,
            terminal_outcome_state=terminal_outcome_state,
            alarm=alarm,
        )


def agent_runtime_alarm_id(
    invocation_id: str,
    progress_digest: str,
    threshold_seconds: int,
) -> str:
    digest = _digest(
        {
            "invocation_id": invocation_id,
            "useful_progress_digest": progress_digest,
            "threshold_seconds": threshold_seconds,
        }
    )
    return f"agent_no_progress_{digest.removeprefix('sha256:')[:32]}"


__all__ = [
    "AgentRuntimeHealthState",
    "AgentRuntimeNoProgressAlarm",
    "AgentRuntimeUsefulProgressHealth",
    "agent_runtime_alarm_id",
]
