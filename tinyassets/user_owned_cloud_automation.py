"""Inert contracts for a user-authored repository-to-spec composition.

The immutable definition carries no runtime authority. Admission is a pure
validation step, and projections are derived from records owned elsewhere.
This module performs no persistence, queue mutation, provider call, tenant
code execution, credential lookup, or external effect.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Collection

from tinyassets.evaluation.scenario_runner import AcceptanceScenario

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _sha256(value: Any, name: str) -> str:
    value = _text(value, name)
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a sha256 digest")
    return value


def _positive_int(value: Any, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class RepositorySpecWorkDefinition:
    """Immutable inputs for one ordinary Branch composition."""

    schema_version: int
    principal_id: str
    universe_id: str
    repository: str
    accepted_spec_ref: str
    accepted_spec_digest: str
    branch_def_id: str
    branch_version_id: str
    branch_content_digest: str
    acceptance_scenario_id: str
    acceptance_scenario_digest: str
    input_artifact_digests: tuple[str, ...]
    provider_binding_id: str
    destination_grant_id: str
    destination_purpose: str
    max_attempts: int
    max_wall_time_seconds: int
    max_tokens: int
    max_cost_microunits: int

    _FIELD_ORDER = (
        "schema_version",
        "principal_id",
        "universe_id",
        "repository",
        "accepted_spec_ref",
        "accepted_spec_digest",
        "branch_def_id",
        "branch_version_id",
        "branch_content_digest",
        "acceptance_scenario_id",
        "acceptance_scenario_digest",
        "input_artifact_digests",
        "provider_binding_id",
        "destination_grant_id",
        "destination_purpose",
        "max_attempts",
        "max_wall_time_seconds",
        "max_tokens",
        "max_cost_microunits",
    )
    _FIELDS = frozenset(_FIELD_ORDER)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        for name in (
            "principal_id",
            "universe_id",
            "accepted_spec_ref",
            "branch_def_id",
            "branch_version_id",
            "acceptance_scenario_id",
            "provider_binding_id",
            "destination_grant_id",
        ):
            _text(getattr(self, name), name)
        if not _REPOSITORY_RE.fullmatch(self.repository):
            raise ValueError("repository must be an exact owner/name")
        for name in (
            "accepted_spec_digest",
            "branch_content_digest",
            "acceptance_scenario_digest",
        ):
            _sha256(getattr(self, name), name)
        digests = tuple(
            _sha256(value, "input_artifact_digests")
            for value in self.input_artifact_digests
        )
        if not digests or len(set(digests)) != len(digests):
            raise ValueError("input_artifact_digests must be non-empty and unique")
        object.__setattr__(self, "input_artifact_digests", digests)
        if self.destination_purpose != "pull_request":
            raise ValueError("destination_purpose must be pull_request")
        attempts = _positive_int(self.max_attempts, "max_attempts")
        if attempts > 2:
            raise ValueError("max_attempts must be <= 2")
        _positive_int(self.max_wall_time_seconds, "max_wall_time_seconds")
        _positive_int(self.max_tokens, "max_tokens")
        _positive_int(
            self.max_cost_microunits,
            "max_cost_microunits",
            minimum=0,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepositorySpecWorkDefinition:
        if not isinstance(data, dict):
            raise ValueError("RepositorySpecWorkDefinition must be an object")
        unknown = sorted(set(data) - cls._FIELDS)
        missing = sorted(cls._FIELDS - set(data))
        if unknown:
            raise ValueError(f"RepositorySpecWorkDefinition unknown fields: {unknown}")
        if missing:
            raise ValueError(f"RepositorySpecWorkDefinition missing fields: {missing}")
        values = dict(data)
        raw_digests = values["input_artifact_digests"]
        if not isinstance(raw_digests, (list, tuple)):
            raise ValueError("input_artifact_digests must be a list")
        values["input_artifact_digests"] = tuple(raw_digests)
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        result = {name: getattr(self, name) for name in self._FIELD_ORDER}
        result["input_artifact_digests"] = list(self.input_artifact_digests)
        return result

    @property
    def definition_digest(self) -> str:
        return _digest(self.to_dict())


class AutomationAdmissionError(ValueError):
    """Stable fail-closed result for a non-admissible work definition."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class AdmittedWorkDefinition:
    definition: RepositorySpecWorkDefinition
    acceptance_scenario_digest: str
    evaluator_chain: tuple[str, ...]
    input_artifact_digests: tuple[str, ...]
    privacy_scope: str


def acceptance_scenario_digest(scenario: AcceptanceScenario) -> str:
    if not isinstance(scenario, AcceptanceScenario):
        raise ValueError("scenario must be an AcceptanceScenario")
    return _digest(asdict(scenario))


def admit_work_definition(
    definition: RepositorySpecWorkDefinition,
    scenario: AcceptanceScenario,
    *,
    deterministic_evaluator_ids: Collection[str],
) -> AdmittedWorkDefinition:
    """Freeze a no-tenant-code evaluation policy before provider spend."""

    if scenario.scenario_id != definition.acceptance_scenario_id:
        raise AutomationAdmissionError("scenario_mismatch", "scenario ID changed")
    digest = acceptance_scenario_digest(scenario)
    if digest != definition.acceptance_scenario_digest:
        raise AutomationAdmissionError("scenario_mismatch", "scenario digest changed")
    admitted = frozenset(deterministic_evaluator_ids)
    unsafe = (
        bool(scenario.allowed_tools)
        or bool(scenario.setup)
        or any(evaluator not in admitted for evaluator in scenario.evaluator_chain)
    )
    if unsafe:
        raise AutomationAdmissionError(
            "sandbox_unavailable",
            "tenant-code evaluator requires production confinement",
        )
    if scenario.cost_budget["max_tokens"] > definition.max_tokens:
        raise AutomationAdmissionError(
            "budget_mismatch",
            "scenario token budget exceeds definition",
        )
    if scenario.cost_budget["max_wall_time_seconds"] > definition.max_wall_time_seconds:
        raise AutomationAdmissionError(
            "budget_mismatch",
            "scenario wall-time budget exceeds definition",
        )
    return AdmittedWorkDefinition(
        definition=definition,
        acceptance_scenario_digest=digest,
        evaluator_chain=tuple(scenario.evaluator_chain),
        input_artifact_digests=definition.input_artifact_digests,
        privacy_scope=scenario.privacy_scope,
    )


__all__ = [
    "AdmittedWorkDefinition",
    "AutomationAdmissionError",
    "RepositorySpecWorkDefinition",
    "acceptance_scenario_digest",
    "admit_work_definition",
]
