"""Typed trigger and terminal-receipt records for user-owned cloud automations.

This module owns no queue task, provider call, credential, or external effect.
It freezes the data-bound definition used by one generic Trigger and records
the terminal evidence needed to decide whether another bounded slice is due.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from tinyassets.user_owned_cloud_automation import (
    RepositorySpecWorkDefinition,
    admit_work_definition,
    repository_spec_baseline_scenario,
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _digest(value: object, name: str) -> str:
    clean = _text(value, name)
    if _DIGEST_RE.fullmatch(clean) is None:
        raise ValueError(f"{name} must be a sha256 digest")
    return clean


def _integer(value: object, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def parse_timestamp(value: object, name: str) -> datetime:
    clean = _text(value, name)
    try:
        parsed = datetime.fromisoformat(clean.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _construct_with_digest(cls: type[Any], payload: dict[str, Any], field: str):
    """Construct a frozen record only after deriving its content digest."""

    provisional = object.__new__(cls)
    for name, value in payload.items():
        object.__setattr__(provisional, name, value)
    payload[field] = provisional.expected_digest()
    return cls(**payload)


def _baseline_evaluation_receipt(
    definition: RepositorySpecWorkDefinition,
) -> dict[str, Any]:
    scenario = repository_spec_baseline_scenario()
    admitted = admit_work_definition(definition, scenario)
    body = {
        "schema_version": 1,
        "status": "admitted",
        "definition_digest": definition.definition_digest,
        "scenario_id": scenario.scenario_id,
        "scenario_digest": admitted.acceptance_scenario_digest,
        "scenario_json": admitted.acceptance_scenario_json,
        "evaluator_chain": list(admitted.evaluator_chain),
        "input_artifact_digests": list(admitted.input_artifact_digests),
        "privacy_scope": admitted.privacy_scope,
        "accepted_spec_ref": definition.accepted_spec_ref,
        "accepted_spec_digest": definition.accepted_spec_digest,
        "branch_version_id": definition.branch_version_id,
        "branch_content_digest": definition.branch_content_digest,
        "max_tokens": admitted.scenario_max_tokens,
        "max_wall_time_seconds": admitted.scenario_max_wall_time_seconds,
    }
    return {**body, "receipt_digest": content_digest(body)}


class CloudAutomationTriggerStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    ADMITTED = "admitted"
    EMITTED = "emitted"


@dataclass(frozen=True, slots=True)
class CloudAutomationProviderClaimFence:
    """Exact requester-provider and physical-worker identity for Trigger claim."""

    provider_binding_id: str
    provider_binding_generation: int
    provider_binding_digest: str
    daemon_id: str
    runtime_id: str
    worker_id: str

    def __post_init__(self) -> None:
        for name in (
            "provider_binding_id",
            "daemon_id",
            "runtime_id",
            "worker_id",
        ):
            _text(getattr(self, name), name)
        _integer(
            self.provider_binding_generation,
            "provider_binding_generation",
            minimum=1,
        )
        _digest(self.provider_binding_digest, "provider_binding_digest")


class CloudAutomationTerminalKind(str, Enum):
    MERGED = "merged"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"
    IDLE = "idle"


class CloudAutomationDesiredState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class CloudAutomationControl:
    """Owner-bound desired state for one recurring cloud automation."""

    schema_version: int
    universe_id: str
    automation_id: str
    principal_id: str
    definition_json: str
    definition_digest: str
    baseline_evaluation_json: str
    cadence_seconds: int
    revision: int
    desired_state: CloudAutomationDesiredState
    updated_at: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "universe_id",
            "automation_id",
            "principal_id",
            "definition_json",
            "definition_digest",
            "baseline_evaluation_json",
            "cadence_seconds",
            "revision",
            "desired_state",
            "updated_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        for name in ("universe_id", "automation_id", "principal_id"):
            _text(getattr(self, name), name)
        try:
            definition = RepositorySpecWorkDefinition.from_dict(
                json.loads(self.definition_json)
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("definition_json is invalid") from exc
        if not all(
            (
                self.definition_json == _canonical_json(definition.to_dict()),
                self.definition_digest == definition.definition_digest,
                self.principal_id == definition.principal_id,
                self.universe_id == definition.universe_id,
            )
        ):
            raise ValueError("control definition does not match its owner")
        baseline = _baseline_evaluation_receipt(definition)
        if self.baseline_evaluation_json != _canonical_json(baseline):
            raise ValueError("control baseline evaluation receipt is invalid")
        _integer(self.cadence_seconds, "cadence_seconds")
        _integer(self.revision, "revision")
        if not isinstance(self.desired_state, CloudAutomationDesiredState):
            raise ValueError("desired_state must be typed")
        parse_timestamp(self.updated_at, "updated_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "universe_id": self.universe_id,
            "automation_id": self.automation_id,
            "principal_id": self.principal_id,
            "definition_json": self.definition_json,
            "definition_digest": self.definition_digest,
            "baseline_evaluation_json": self.baseline_evaluation_json,
            "cadence_seconds": self.cadence_seconds,
            "revision": self.revision,
            "desired_state": self.desired_state.value,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CloudAutomationControl:
        if not isinstance(value, dict) or set(value) != cls._FIELDS:
            raise ValueError("CloudAutomationControl fields do not match schema")
        payload = dict(value)
        payload["desired_state"] = CloudAutomationDesiredState(
            payload["desired_state"]
        )
        return cls(**payload)

    @classmethod
    def create(
        cls,
        *,
        automation_id: str,
        definition: RepositorySpecWorkDefinition,
        cadence_seconds: int,
        updated_at: str,
    ) -> CloudAutomationControl:
        if not isinstance(definition, RepositorySpecWorkDefinition):
            raise ValueError("definition must be a RepositorySpecWorkDefinition")
        return cls(
            schema_version=1,
            universe_id=definition.universe_id,
            automation_id=automation_id,
            principal_id=definition.principal_id,
            definition_json=_canonical_json(definition.to_dict()),
            definition_digest=definition.definition_digest,
            baseline_evaluation_json=_canonical_json(
                _baseline_evaluation_receipt(definition)
            ),
            cadence_seconds=_integer(cadence_seconds, "cadence_seconds"),
            revision=1,
            desired_state=CloudAutomationDesiredState.ACTIVE,
            updated_at=timestamp(parse_timestamp(updated_at, "updated_at")),
        )

    def transition(
        self,
        desired_state: CloudAutomationDesiredState,
        *,
        updated_at: str,
    ) -> CloudAutomationControl:
        if not isinstance(desired_state, CloudAutomationDesiredState):
            raise ValueError("desired_state must be typed")
        if self.desired_state is CloudAutomationDesiredState.STOPPED:
            raise ValueError("stopped automation requires a new activation bind")
        if desired_state is self.desired_state:
            return self
        return CloudAutomationControl(
            schema_version=self.schema_version,
            universe_id=self.universe_id,
            automation_id=self.automation_id,
            principal_id=self.principal_id,
            definition_json=self.definition_json,
            definition_digest=self.definition_digest,
            baseline_evaluation_json=self.baseline_evaluation_json,
            cadence_seconds=self.cadence_seconds,
            revision=self.revision + 1,
            desired_state=desired_state,
            updated_at=timestamp(parse_timestamp(updated_at, "updated_at")),
        )

    def rebind(
        self,
        definition: RepositorySpecWorkDefinition,
        *,
        updated_at: str,
    ) -> CloudAutomationControl:
        """Bind a stopped control to another immutable version."""
        if self.desired_state is not CloudAutomationDesiredState.STOPPED:
            raise ValueError("automation must be stopped before rebind")
        if not isinstance(definition, RepositorySpecWorkDefinition):
            raise ValueError("definition must be a RepositorySpecWorkDefinition")
        if (
            definition.principal_id != self.principal_id
            or definition.universe_id != self.universe_id
            or definition.branch_def_id != self.definition.branch_def_id
        ):
            raise ValueError("rebind definition changes automation ownership or lineage")
        return CloudAutomationControl(
            schema_version=self.schema_version,
            universe_id=self.universe_id,
            automation_id=self.automation_id,
            principal_id=self.principal_id,
            definition_json=_canonical_json(definition.to_dict()),
            definition_digest=definition.definition_digest,
            baseline_evaluation_json=_canonical_json(
                _baseline_evaluation_receipt(definition)
            ),
            cadence_seconds=self.cadence_seconds,
            revision=self.revision + 1,
            desired_state=CloudAutomationDesiredState.ACTIVE,
            updated_at=timestamp(parse_timestamp(updated_at, "updated_at")),
        )

    @property
    def definition(self) -> RepositorySpecWorkDefinition:
        return RepositorySpecWorkDefinition.from_dict(json.loads(self.definition_json))

    @property
    def baseline_evaluation(self) -> dict[str, Any]:
        return json.loads(self.baseline_evaluation_json)


@dataclass(frozen=True, slots=True)
class CloudAutomationSliceTrigger:
    schema_version: int
    trigger_id: str
    generation: int
    trigger_digest: str
    status: CloudAutomationTriggerStatus
    principal_id: str
    universe_id: str
    automation_id: str
    activation_epoch: int
    activation_subject_ref: str
    activation_subject_digest: str
    definition_json: str
    definition_digest: str
    slice_ordinal: int
    cadence_seconds: int
    due_at: str
    claim_id: str | None
    claimed_by: str | None
    claim_expires_at: str | None
    request_id: str | None
    admission_id: str | None
    branch_task_id: str | None
    previous_terminal_receipt_id: str | None
    created_at: str
    updated_at: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "trigger_id",
            "generation",
            "trigger_digest",
            "status",
            "principal_id",
            "universe_id",
            "automation_id",
            "activation_epoch",
            "activation_subject_ref",
            "activation_subject_digest",
            "definition_json",
            "definition_digest",
            "slice_ordinal",
            "cadence_seconds",
            "due_at",
            "claim_id",
            "claimed_by",
            "claim_expires_at",
            "request_id",
            "admission_id",
            "branch_task_id",
            "previous_terminal_receipt_id",
            "created_at",
            "updated_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        if not isinstance(self.status, CloudAutomationTriggerStatus):
            raise ValueError("status must be typed")
        for name in (
            "trigger_id",
            "principal_id",
            "universe_id",
            "automation_id",
            "activation_subject_ref",
        ):
            _text(getattr(self, name), name)
        if not self.trigger_id.startswith("cloud_trigger_"):
            raise ValueError("trigger_id is not canonical")
        _integer(self.generation, "generation")
        _integer(self.activation_epoch, "activation_epoch", minimum=0)
        _integer(self.slice_ordinal, "slice_ordinal")
        _integer(self.cadence_seconds, "cadence_seconds")
        _digest(self.trigger_digest, "trigger_digest")
        _digest(self.activation_subject_digest, "activation_subject_digest")
        _digest(self.definition_digest, "definition_digest")
        parse_timestamp(self.due_at, "due_at")
        parse_timestamp(self.created_at, "created_at")
        parse_timestamp(self.updated_at, "updated_at")
        try:
            raw_definition = json.loads(self.definition_json)
        except json.JSONDecodeError as exc:
            raise ValueError("definition_json is invalid") from exc
        definition = RepositorySpecWorkDefinition.from_dict(raw_definition)
        exact_definition = (
            self.definition_json == _canonical_json(definition.to_dict()),
            definition.definition_digest == self.definition_digest,
            definition.principal_id == self.principal_id,
            definition.universe_id == self.universe_id,
            definition.branch_version_id == self.activation_subject_ref,
            definition.branch_content_digest == self.activation_subject_digest,
        )
        if not all(exact_definition):
            raise ValueError("trigger definition does not match its frozen identity")
        claimed_fields = (self.claim_id, self.claimed_by, self.claim_expires_at)
        admission_fields = (self.request_id, self.admission_id, self.branch_task_id)
        if self.status is CloudAutomationTriggerStatus.PENDING:
            if any(value is not None for value in claimed_fields):
                raise ValueError("pending trigger cannot carry a claim")
            if any(value is not None for value in admission_fields):
                raise ValueError("pending trigger cannot carry an admission")
        else:
            for name, value in zip(
                ("claim_id", "claimed_by", "claim_expires_at"),
                claimed_fields,
                strict=True,
            ):
                _text(value, name)
            parse_timestamp(self.claim_expires_at, "claim_expires_at")
            if self.status is CloudAutomationTriggerStatus.CLAIMED:
                if any(value is not None for value in admission_fields):
                    raise ValueError("claimed trigger cannot carry an admission")
            else:
                for name, value in zip(
                    ("request_id", "admission_id", "branch_task_id"),
                    admission_fields,
                    strict=True,
                ):
                    _text(value, name)
        if self.previous_terminal_receipt_id is not None:
            _text(self.previous_terminal_receipt_id, "previous_terminal_receipt_id")
        if self.trigger_digest != self.expected_digest():
            raise ValueError("trigger_digest does not match content")

    @property
    def definition(self) -> RepositorySpecWorkDefinition:
        return RepositorySpecWorkDefinition.from_dict(json.loads(self.definition_json))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trigger_id": self.trigger_id,
            "generation": self.generation,
            "trigger_digest": self.trigger_digest,
            "status": self.status.value,
            "principal_id": self.principal_id,
            "universe_id": self.universe_id,
            "automation_id": self.automation_id,
            "activation_epoch": self.activation_epoch,
            "activation_subject_ref": self.activation_subject_ref,
            "activation_subject_digest": self.activation_subject_digest,
            "definition_json": self.definition_json,
            "definition_digest": self.definition_digest,
            "slice_ordinal": self.slice_ordinal,
            "cadence_seconds": self.cadence_seconds,
            "due_at": self.due_at,
            "claim_id": self.claim_id,
            "claimed_by": self.claimed_by,
            "claim_expires_at": self.claim_expires_at,
            "request_id": self.request_id,
            "admission_id": self.admission_id,
            "branch_task_id": self.branch_task_id,
            "previous_terminal_receipt_id": self.previous_terminal_receipt_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CloudAutomationSliceTrigger:
        if not isinstance(value, dict) or set(value) != cls._FIELDS:
            raise ValueError("CloudAutomationSliceTrigger fields do not match schema")
        payload = dict(value)
        payload["status"] = CloudAutomationTriggerStatus(payload["status"])
        return cls(**payload)

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["trigger_digest"]
        return content_digest(payload)

    def claim(
        self,
        *,
        claimed_by: str,
        claim_expires_at: str,
        updated_at: str,
        generation: int | None = None,
    ) -> CloudAutomationSliceTrigger:
        if self.status is CloudAutomationTriggerStatus.EMITTED:
            raise ValueError("emitted trigger cannot be claimed")
        next_generation = self.generation if generation is None else generation
        at = timestamp(parse_timestamp(updated_at, "updated_at"))
        identity = {
            "claimed_by": _text(claimed_by, "claimed_by"),
            "generation": _integer(next_generation, "generation"),
            "trigger_id": self.trigger_id,
            "updated_at": at,
        }
        payload = self.to_dict()
        payload.update(
            {
                "generation": next_generation,
                "trigger_digest": "",
                "status": CloudAutomationTriggerStatus.CLAIMED,
                "claim_id": (
                    "cloud_trigger_claim_" + content_digest(identity).removeprefix("sha256:")[:32]
                ),
                "claimed_by": identity["claimed_by"],
                "claim_expires_at": timestamp(
                    parse_timestamp(claim_expires_at, "claim_expires_at")
                ),
                "updated_at": at,
            }
        )
        return _construct_with_digest(type(self), payload, "trigger_digest")

    def emit(self, *, updated_at: str) -> CloudAutomationSliceTrigger:
        if self.status is not CloudAutomationTriggerStatus.ADMITTED:
            raise ValueError("only an admitted trigger can be emitted")
        payload = self.to_dict()
        payload.update(
            {
                "trigger_digest": "",
                "status": CloudAutomationTriggerStatus.EMITTED,
                "updated_at": timestamp(parse_timestamp(updated_at, "updated_at")),
            }
        )
        return _construct_with_digest(type(self), payload, "trigger_digest")

    def admit(
        self,
        *,
        request_id: str,
        admission_id: str,
        branch_task_id: str,
        updated_at: str,
    ) -> CloudAutomationSliceTrigger:
        if self.status is not CloudAutomationTriggerStatus.CLAIMED:
            raise ValueError("only a claimed trigger can be admitted")
        payload = self.to_dict()
        payload.update(
            {
                "trigger_digest": "",
                "status": CloudAutomationTriggerStatus.ADMITTED,
                "request_id": _text(request_id, "request_id"),
                "admission_id": _text(admission_id, "admission_id"),
                "branch_task_id": _text(branch_task_id, "branch_task_id"),
                "updated_at": timestamp(parse_timestamp(updated_at, "updated_at")),
            }
        )
        return _construct_with_digest(type(self), payload, "trigger_digest")

    @classmethod
    def pending(
        cls,
        definition: RepositorySpecWorkDefinition,
        *,
        automation_id: str,
        activation_epoch: int,
        slice_ordinal: int,
        cadence_seconds: int,
        due_at: str,
        previous_terminal_receipt_id: str | None,
        created_at: str,
    ) -> CloudAutomationSliceTrigger:
        identity = {
            "activation_epoch": activation_epoch,
            "automation_id": automation_id,
            "slice_ordinal": slice_ordinal,
            "universe_id": definition.universe_id,
        }
        payload: dict[str, Any] = {
            "schema_version": 1,
            "trigger_id": (
                "cloud_trigger_" + content_digest(identity).removeprefix("sha256:")[:32]
            ),
            "generation": 1,
            "trigger_digest": "",
            "status": CloudAutomationTriggerStatus.PENDING,
            "principal_id": definition.principal_id,
            "universe_id": definition.universe_id,
            "automation_id": _text(automation_id, "automation_id"),
            "activation_epoch": _integer(activation_epoch, "activation_epoch", minimum=0),
            "activation_subject_ref": definition.branch_version_id,
            "activation_subject_digest": definition.branch_content_digest,
            "definition_json": _canonical_json(definition.to_dict()),
            "definition_digest": definition.definition_digest,
            "slice_ordinal": _integer(slice_ordinal, "slice_ordinal"),
            "cadence_seconds": _integer(cadence_seconds, "cadence_seconds"),
            "due_at": timestamp(parse_timestamp(due_at, "due_at")),
            "claim_id": None,
            "claimed_by": None,
            "claim_expires_at": None,
            "request_id": None,
            "admission_id": None,
            "branch_task_id": None,
            "previous_terminal_receipt_id": previous_terminal_receipt_id,
            "created_at": timestamp(parse_timestamp(created_at, "created_at")),
            "updated_at": timestamp(parse_timestamp(created_at, "created_at")),
        }
        return _construct_with_digest(cls, payload, "trigger_digest")


@dataclass(frozen=True, slots=True)
class CloudAutomationTriggerFence:
    expected: CloudAutomationSliceTrigger

    def __post_init__(self) -> None:
        if not isinstance(self.expected, CloudAutomationSliceTrigger):
            raise ValueError("expected must be a CloudAutomationSliceTrigger")


@dataclass(frozen=True, slots=True)
class CloudAutomationTerminalRequest:
    terminal_kind: CloudAutomationTerminalKind
    branch_task_id: str
    run_id: str
    claim_id: str
    attempt_id: str
    evidence_handles: tuple[str, ...]
    completed_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.terminal_kind, CloudAutomationTerminalKind):
            raise ValueError("terminal_kind must be typed")
        for name in ("branch_task_id", "run_id", "claim_id", "attempt_id"):
            _text(getattr(self, name), name)
        handles = tuple(_text(value, "evidence_handles") for value in self.evidence_handles)
        if len(set(handles)) != len(handles):
            raise ValueError("evidence_handles must be unique")
        object.__setattr__(self, "evidence_handles", handles)
        parse_timestamp(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class CloudAutomationTerminalReceipt:
    schema_version: int
    receipt_id: str
    receipt_digest: str
    trigger_id: str
    trigger_generation: int
    principal_id: str
    universe_id: str
    automation_id: str
    activation_epoch: int
    slice_ordinal: int
    branch_version_id: str
    branch_content_digest: str
    provider_binding_id: str
    destination_grant_id: str
    terminal_kind: CloudAutomationTerminalKind
    branch_task_id: str
    run_id: str
    claim_id: str
    attempt_id: str
    evidence_handles: tuple[str, ...]
    next_action: str
    completed_at: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "receipt_id",
            "receipt_digest",
            "trigger_id",
            "trigger_generation",
            "principal_id",
            "universe_id",
            "automation_id",
            "activation_epoch",
            "slice_ordinal",
            "branch_version_id",
            "branch_content_digest",
            "provider_binding_id",
            "destination_grant_id",
            "terminal_kind",
            "branch_task_id",
            "run_id",
            "claim_id",
            "attempt_id",
            "evidence_handles",
            "next_action",
            "completed_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        if not isinstance(self.terminal_kind, CloudAutomationTerminalKind):
            raise ValueError("terminal_kind must be typed")
        for name in (
            "receipt_id",
            "trigger_id",
            "principal_id",
            "universe_id",
            "automation_id",
            "branch_version_id",
            "provider_binding_id",
            "destination_grant_id",
            "branch_task_id",
            "run_id",
            "claim_id",
            "attempt_id",
            "next_action",
        ):
            _text(getattr(self, name), name)
        if not self.receipt_id.startswith("cloud_terminal_"):
            raise ValueError("receipt_id is not canonical")
        _digest(self.receipt_digest, "receipt_digest")
        _digest(self.branch_content_digest, "branch_content_digest")
        _integer(self.trigger_generation, "trigger_generation")
        _integer(self.activation_epoch, "activation_epoch", minimum=0)
        _integer(self.slice_ordinal, "slice_ordinal")
        handles = tuple(_text(value, "evidence_handles") for value in self.evidence_handles)
        object.__setattr__(self, "evidence_handles", handles)
        parse_timestamp(self.completed_at, "completed_at")
        if self.receipt_digest != self.expected_digest():
            raise ValueError("receipt_digest does not match content")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "receipt_digest": self.receipt_digest,
            "trigger_id": self.trigger_id,
            "trigger_generation": self.trigger_generation,
            "principal_id": self.principal_id,
            "universe_id": self.universe_id,
            "automation_id": self.automation_id,
            "activation_epoch": self.activation_epoch,
            "slice_ordinal": self.slice_ordinal,
            "branch_version_id": self.branch_version_id,
            "branch_content_digest": self.branch_content_digest,
            "provider_binding_id": self.provider_binding_id,
            "destination_grant_id": self.destination_grant_id,
            "terminal_kind": self.terminal_kind.value,
            "branch_task_id": self.branch_task_id,
            "run_id": self.run_id,
            "claim_id": self.claim_id,
            "attempt_id": self.attempt_id,
            "evidence_handles": list(self.evidence_handles),
            "next_action": self.next_action,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CloudAutomationTerminalReceipt:
        if not isinstance(value, dict) or set(value) != cls._FIELDS:
            raise ValueError("CloudAutomationTerminalReceipt fields do not match schema")
        payload = dict(value)
        payload["terminal_kind"] = CloudAutomationTerminalKind(payload["terminal_kind"])
        payload["evidence_handles"] = tuple(payload["evidence_handles"])
        return cls(**payload)

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["receipt_digest"]
        return content_digest(payload)

    @classmethod
    def create(
        cls,
        trigger: CloudAutomationSliceTrigger,
        request: CloudAutomationTerminalRequest,
        *,
        next_action: str,
    ) -> CloudAutomationTerminalReceipt:
        if trigger.status is not CloudAutomationTriggerStatus.ADMITTED:
            raise ValueError("terminal receipt requires an admitted trigger")
        definition = trigger.definition
        identity = {
            "trigger_id": trigger.trigger_id,
            "trigger_generation": trigger.generation,
        }
        payload: dict[str, Any] = {
            "schema_version": 1,
            "receipt_id": (
                "cloud_terminal_" + content_digest(identity).removeprefix("sha256:")[:32]
            ),
            "receipt_digest": "",
            "trigger_id": trigger.trigger_id,
            "trigger_generation": trigger.generation,
            "principal_id": trigger.principal_id,
            "universe_id": trigger.universe_id,
            "automation_id": trigger.automation_id,
            "activation_epoch": trigger.activation_epoch,
            "slice_ordinal": trigger.slice_ordinal,
            "branch_version_id": trigger.activation_subject_ref,
            "branch_content_digest": trigger.activation_subject_digest,
            "provider_binding_id": definition.provider_binding_id,
            "destination_grant_id": definition.destination_grant_id,
            "terminal_kind": request.terminal_kind,
            "branch_task_id": request.branch_task_id,
            "run_id": request.run_id,
            "claim_id": request.claim_id,
            "attempt_id": request.attempt_id,
            "evidence_handles": request.evidence_handles,
            "next_action": _text(next_action, "next_action"),
            "completed_at": timestamp(parse_timestamp(request.completed_at, "completed_at")),
        }
        return _construct_with_digest(cls, payload, "receipt_digest")

    def matches_request(self, request: CloudAutomationTerminalRequest) -> bool:
        return (
            self.terminal_kind is request.terminal_kind
            and self.branch_task_id == request.branch_task_id
            and self.run_id == request.run_id
            and self.claim_id == request.claim_id
            and self.attempt_id == request.attempt_id
            and self.evidence_handles == request.evidence_handles
            and self.completed_at
            == timestamp(parse_timestamp(request.completed_at, "completed_at"))
        )


@dataclass(frozen=True, slots=True)
class CloudAutomationTerminalWriteResult:
    completed_trigger: CloudAutomationSliceTrigger
    receipt: CloudAutomationTerminalReceipt
    next_trigger: CloudAutomationSliceTrigger | None


@dataclass(frozen=True, slots=True)
class CloudAutomationHealth:
    state: str
    last_useful_progress_at: str | None
    no_progress_alarm: bool
    alarm_after: str | None
    current_claim: dict[str, Any] | None
    retry_at: str | None
    blocker: str | None
    next_action: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "last_useful_progress_at": self.last_useful_progress_at,
            "no_progress_alarm": self.no_progress_alarm,
            "alarm_after": self.alarm_after,
            "current_claim": self.current_claim,
            "retry_at": self.retry_at,
            "blocker": self.blocker,
            "next_action": self.next_action,
        }


def project_cloud_automation_health(
    control: CloudAutomationControl,
    *,
    activation: Any,
    triggers: list[CloudAutomationSliceTrigger],
    receipts: list[CloudAutomationTerminalReceipt],
    now: datetime,
) -> CloudAutomationHealth:
    """Derive cloud-authoritative health only from durable typed records."""

    if not isinstance(control, CloudAutomationControl):
        raise ValueError("control must be a CloudAutomationControl")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    ordered_triggers = sorted(
        triggers,
        key=lambda value: (value.activation_epoch, value.slice_ordinal),
    )
    ordered_receipts = sorted(
        receipts,
        key=lambda value: (value.activation_epoch, value.slice_ordinal),
    )
    current = next(
        (
            value
            for value in reversed(ordered_triggers)
            if value.status is not CloudAutomationTriggerStatus.EMITTED
        ),
        None,
    )
    useful = [
        value
        for value in ordered_receipts
        if value.terminal_kind
        in {CloudAutomationTerminalKind.MERGED, CloudAutomationTerminalKind.PARTIAL}
        and value.evidence_handles
    ]
    latest_useful = useful[-1] if useful else None
    latest_receipt = ordered_receipts[-1] if ordered_receipts else None
    baseline = (
        parse_timestamp(latest_useful.completed_at, "completed_at")
        if latest_useful is not None
        else parse_timestamp(ordered_triggers[0].created_at, "created_at")
        if ordered_triggers
        else None
    )
    definition = ordered_triggers[-1].definition if ordered_triggers else None
    alarm_after_dt = None
    if baseline is not None and definition is not None:
        cadence = ordered_triggers[-1].cadence_seconds
        allowance = max(900, definition.max_wall_time_seconds + (cadence * 2))
        alarm_after_dt = baseline + timedelta(seconds=allowance)
    activation_active = bool(
        activation is not None
        and getattr(getattr(activation, "state", None), "value", None) == "active"
        and getattr(getattr(activation, "executor_class", None), "value", None) == "cloud"
    )
    no_progress_alarm = bool(
        control.desired_state is CloudAutomationDesiredState.ACTIVE
        and activation_active
        and alarm_after_dt is not None
        and now.astimezone(timezone.utc) > alarm_after_dt
    )
    blocker = None
    if latest_receipt is not None and latest_receipt not in useful:
        if latest_receipt.terminal_kind in {
            CloudAutomationTerminalKind.BLOCKED,
            CloudAutomationTerminalKind.FAILED,
            CloudAutomationTerminalKind.IDLE,
        }:
            blocker = latest_receipt.terminal_kind.value
    if control.desired_state is CloudAutomationDesiredState.STOPPED:
        state = "stopped"
    elif control.desired_state is CloudAutomationDesiredState.PAUSED:
        state = "paused"
    elif not activation_active:
        state = "activation_stopped"
    elif no_progress_alarm:
        state = "no_progress"
    elif current is not None and current.status in {
        CloudAutomationTriggerStatus.CLAIMED,
        CloudAutomationTriggerStatus.ADMITTED,
    }:
        state = "running"
    else:
        state = "waiting"
    return CloudAutomationHealth(
        state=state,
        last_useful_progress_at=(
            latest_useful.completed_at if latest_useful is not None else None
        ),
        no_progress_alarm=no_progress_alarm,
        alarm_after=(timestamp(alarm_after_dt) if alarm_after_dt is not None else None),
        current_claim=(
            {
                "trigger_id": current.trigger_id,
                "status": current.status.value,
                "claim_id": current.claim_id,
                "claimed_by": current.claimed_by,
                "claim_expires_at": current.claim_expires_at,
                "branch_task_id": current.branch_task_id,
            }
            if current is not None
            and current.status
            in {CloudAutomationTriggerStatus.CLAIMED, CloudAutomationTriggerStatus.ADMITTED}
            else None
        ),
        retry_at=(
            current.due_at
            if current is not None
            and current.status is CloudAutomationTriggerStatus.PENDING
            else current.claim_expires_at
            if current is not None
            and current.status is CloudAutomationTriggerStatus.CLAIMED
            else None
        ),
        blocker=blocker,
        next_action=(latest_receipt.next_action if latest_receipt is not None else None),
    )


__all__ = [
    "CloudAutomationControl",
    "CloudAutomationDesiredState",
    "CloudAutomationHealth",
    "CloudAutomationProviderClaimFence",
    "CloudAutomationSliceTrigger",
    "CloudAutomationTerminalKind",
    "CloudAutomationTerminalReceipt",
    "CloudAutomationTerminalRequest",
    "CloudAutomationTerminalWriteResult",
    "CloudAutomationTriggerFence",
    "CloudAutomationTriggerStatus",
    "content_digest",
    "parse_timestamp",
    "project_cloud_automation_health",
    "timestamp",
]
