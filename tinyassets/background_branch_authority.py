"""Dark typed contracts for server-owned background Branch authority.

These records are deliberately inert.  They carry no bearer capability and
perform no persistence, queue mutation, credential lookup, or Branch run.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any


class BackgroundBranchBindingStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    REVOKED = "revoked"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"


class BackgroundBranchSourceKind(str, Enum):
    SCHEDULE = "schedule"
    SUBSCRIPTION = "subscription"
    PINNED_SOUL = "pinned_soul"
    ROOT_RUN = "root_run"
    REQUEST_ADMISSION = "request_admission"
    PRODUCER_SUBSCRIPTION = "producer_subscription"
    ACCEPTED_MARKET_CONTRACT = "accepted_market_contract"
    RESUMED_RUN = "resumed_run"
    CLAIMED_TASK = "claimed_task"
    DIRECT_CHILD = "direct_child"
    PARENT_ATTEMPT = "parent_attempt"


class BackgroundBranchTargetMode(str, Enum):
    LIVE_AT_ATTEMPT = "live_at_attempt"
    PINNED_VERSION = "pinned_version"


class BackgroundBranchAttemptLifecycle(str, Enum):
    RESERVED = "reserved"
    CLAIMED = "claimed"
    RUNNING = "running"
    TARGET_AUTHORITY_HELD = "target_authority_held"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundBranchHoldReason(str, Enum):
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    TARGET_CHANGED = "target_changed"
    PRINCIPAL_REVOKED = "principal_revoked"
    SOURCE_GENERATION_MISMATCH = "source_generation_mismatch"
    INDETERMINATE_PRIOR_ATTEMPT = "indeterminate_prior_attempt"
    BINDING_MISSING = "binding_missing"
    BINDING_REVOKED = "binding_revoked"
    BINDING_EXPIRED = "binding_expired"
    BINDING_EXHAUSTED = "binding_exhausted"
    TARGET_UNAUTHORIZED = "target_unauthorized"
    EXECUTOR_MISMATCH = "executor_mismatch"


def _strict_fields(
    data: dict[str, Any],
    expected: frozenset[str],
    *,
    record_name: str,
) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{record_name} must be an object")
    unknown = sorted(set(data) - expected)
    if unknown:
        raise ValueError(f"{record_name} unknown fields: {unknown}")
    missing = sorted(expected - set(data))
    if missing:
        raise ValueError(f"{record_name} missing fields: {missing}")


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _integer(value: Any, field_name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field_name} must be an integer >= {minimum}")
    return value


def _enum_value(enum_type: type[Enum], value: Any, field_name: str) -> Any:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} has unsupported value {value!r}") from exc


def _text_tuple(value: Any, field_name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    items = tuple(_text(item, field_name) for item in value)
    if not allow_empty and not items:
        raise ValueError(f"{field_name} must not be empty")
    if len(set(items)) != len(items):
        raise ValueError(f"{field_name} must not contain duplicates")
    return items


def _json_object(
    value: Any,
    field_name: str,
    *,
    non_empty_values: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    for key, item in value.items():
        _text(key, f"{field_name} key")
        if non_empty_values:
            _text(item, f"{field_name}.{key}")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain JSON values") from exc
    return copy.deepcopy(value)


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class BackgroundBranchProvenance:
    authorizing_principal_id: str
    source_kind: BackgroundBranchSourceKind
    source_id: str
    executor_class: str
    daemon_id: str | None
    runtime_id: str | None
    worker_id: str | None
    parent_attempt_id: str | None
    origin_attempt_id: str
    audit_correlation_ids: tuple[str, ...]
    receipt_refs: Mapping[str, str]

    _FIELDS = frozenset(
        {
            "authorizing_principal_id",
            "source_kind",
            "source_id",
            "executor_class",
            "daemon_id",
            "runtime_id",
            "worker_id",
            "parent_attempt_id",
            "origin_attempt_id",
            "audit_correlation_ids",
            "receipt_refs",
        }
    )

    def __post_init__(self) -> None:
        _text(self.authorizing_principal_id, "authorizing_principal_id")
        if not isinstance(self.source_kind, BackgroundBranchSourceKind):
            raise ValueError("source_kind must be typed")
        _text(self.source_id, "source_id")
        _text(self.executor_class, "executor_class")
        for name in ("daemon_id", "runtime_id", "worker_id", "parent_attempt_id"):
            _optional_text(getattr(self, name), name)
        _text(self.origin_attempt_id, "origin_attempt_id")
        if not self.audit_correlation_ids:
            raise ValueError("audit_correlation_ids must not be empty")
        for value in self.audit_correlation_ids:
            _text(value, "audit_correlation_ids")
        if len(set(self.audit_correlation_ids)) != len(self.audit_correlation_ids):
            raise ValueError("audit_correlation_ids must not contain duplicates")
        receipt_refs = _json_object(dict(self.receipt_refs), "receipt_refs", non_empty_values=True)
        object.__setattr__(self, "receipt_refs", _freeze_json(receipt_refs))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackgroundBranchProvenance:
        _strict_fields(data, cls._FIELDS, record_name=cls.__name__)
        return cls(
            authorizing_principal_id=_text(
                data["authorizing_principal_id"], "authorizing_principal_id"
            ),
            source_kind=_enum_value(BackgroundBranchSourceKind, data["source_kind"], "source_kind"),
            source_id=_text(data["source_id"], "source_id"),
            executor_class=_text(data["executor_class"], "executor_class"),
            daemon_id=_optional_text(data["daemon_id"], "daemon_id"),
            runtime_id=_optional_text(data["runtime_id"], "runtime_id"),
            worker_id=_optional_text(data["worker_id"], "worker_id"),
            parent_attempt_id=_optional_text(data["parent_attempt_id"], "parent_attempt_id"),
            origin_attempt_id=_text(data["origin_attempt_id"], "origin_attempt_id"),
            audit_correlation_ids=_text_tuple(
                data["audit_correlation_ids"], "audit_correlation_ids"
            ),
            receipt_refs=_json_object(data["receipt_refs"], "receipt_refs", non_empty_values=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorizing_principal_id": self.authorizing_principal_id,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "executor_class": self.executor_class,
            "daemon_id": self.daemon_id,
            "runtime_id": self.runtime_id,
            "worker_id": self.worker_id,
            "parent_attempt_id": self.parent_attempt_id,
            "origin_attempt_id": self.origin_attempt_id,
            "audit_correlation_ids": list(self.audit_correlation_ids),
            "receipt_refs": _thaw_json(self.receipt_refs),
        }


@dataclass(frozen=True, slots=True)
class BackgroundBranchBinding:
    schema_version: int
    binding_id: str
    status: BackgroundBranchBindingStatus
    generation: int
    binding_digest: str
    authorizing_principal_id: str
    universe_id: str
    branch_def_id: str
    operation: str
    source_kind: BackgroundBranchSourceKind
    source_id: str
    source_revision: str
    source_digest: str
    revocation_generation: int
    target_mode: BackgroundBranchTargetMode
    pinned_branch_version_id: str | None
    permitted_executor_classes: tuple[str, ...]
    daemon_id: str | None
    runtime_id: str | None
    expires_at: str | None
    max_attempts: int
    remaining_depth: int
    remaining_count: int
    remaining_cost_microunits: int
    child_delegation: Mapping[str, Any]

    _FIELDS = frozenset(
        {
            "schema_version",
            "binding_id",
            "status",
            "generation",
            "binding_digest",
            "authorizing_principal_id",
            "universe_id",
            "branch_def_id",
            "operation",
            "source_kind",
            "source_id",
            "source_revision",
            "source_digest",
            "revocation_generation",
            "target_mode",
            "pinned_branch_version_id",
            "permitted_executor_classes",
            "daemon_id",
            "runtime_id",
            "expires_at",
            "max_attempts",
            "remaining_depth",
            "remaining_count",
            "remaining_cost_microunits",
            "child_delegation",
        }
    )

    def __post_init__(self) -> None:
        _integer(self.schema_version, "schema_version", minimum=1)
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        for name in (
            "binding_id",
            "binding_digest",
            "authorizing_principal_id",
            "universe_id",
            "branch_def_id",
            "operation",
            "source_id",
            "source_revision",
            "source_digest",
        ):
            _text(getattr(self, name), name)
        if not isinstance(self.status, BackgroundBranchBindingStatus):
            raise ValueError("status must be typed")
        if not isinstance(self.source_kind, BackgroundBranchSourceKind):
            raise ValueError("source_kind must be typed")
        if not isinstance(self.target_mode, BackgroundBranchTargetMode):
            raise ValueError("target_mode must be typed")
        _integer(self.generation, "generation", minimum=1)
        _integer(self.revocation_generation, "revocation_generation", minimum=0)
        _optional_text(self.pinned_branch_version_id, "pinned_branch_version_id")
        if self.target_mode is BackgroundBranchTargetMode.PINNED_VERSION:
            if self.pinned_branch_version_id is None:
                raise ValueError("pinned_version requires pinned_branch_version_id")
        elif self.pinned_branch_version_id is not None:
            raise ValueError("live_at_attempt forbids pinned_branch_version_id")
        if not self.permitted_executor_classes:
            raise ValueError("permitted_executor_classes must not be empty")
        for value in self.permitted_executor_classes:
            _text(value, "permitted_executor_classes")
        if len(set(self.permitted_executor_classes)) != len(self.permitted_executor_classes):
            raise ValueError("permitted_executor_classes must not contain duplicates")
        _optional_text(self.daemon_id, "daemon_id")
        _optional_text(self.runtime_id, "runtime_id")
        _optional_text(self.expires_at, "expires_at")
        _integer(self.max_attempts, "max_attempts", minimum=1)
        _integer(self.remaining_depth, "remaining_depth", minimum=0)
        _integer(self.remaining_count, "remaining_count", minimum=0)
        _integer(
            self.remaining_cost_microunits,
            "remaining_cost_microunits",
            minimum=0,
        )
        child_delegation = _json_object(_thaw_json(self.child_delegation), "child_delegation")
        object.__setattr__(self, "child_delegation", _freeze_json(child_delegation))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackgroundBranchBinding:
        _strict_fields(data, cls._FIELDS, record_name=cls.__name__)
        return cls(
            schema_version=_integer(data["schema_version"], "schema_version", minimum=1),
            binding_id=_text(data["binding_id"], "binding_id"),
            status=_enum_value(BackgroundBranchBindingStatus, data["status"], "status"),
            generation=_integer(data["generation"], "generation", minimum=1),
            binding_digest=_text(data["binding_digest"], "binding_digest"),
            authorizing_principal_id=_text(
                data["authorizing_principal_id"], "authorizing_principal_id"
            ),
            universe_id=_text(data["universe_id"], "universe_id"),
            branch_def_id=_text(data["branch_def_id"], "branch_def_id"),
            operation=_text(data["operation"], "operation"),
            source_kind=_enum_value(BackgroundBranchSourceKind, data["source_kind"], "source_kind"),
            source_id=_text(data["source_id"], "source_id"),
            source_revision=_text(data["source_revision"], "source_revision"),
            source_digest=_text(data["source_digest"], "source_digest"),
            revocation_generation=_integer(
                data["revocation_generation"], "revocation_generation", minimum=0
            ),
            target_mode=_enum_value(BackgroundBranchTargetMode, data["target_mode"], "target_mode"),
            pinned_branch_version_id=_optional_text(
                data["pinned_branch_version_id"], "pinned_branch_version_id"
            ),
            permitted_executor_classes=_text_tuple(
                data["permitted_executor_classes"], "permitted_executor_classes"
            ),
            daemon_id=_optional_text(data["daemon_id"], "daemon_id"),
            runtime_id=_optional_text(data["runtime_id"], "runtime_id"),
            expires_at=_optional_text(data["expires_at"], "expires_at"),
            max_attempts=_integer(data["max_attempts"], "max_attempts", minimum=1),
            remaining_depth=_integer(data["remaining_depth"], "remaining_depth", minimum=0),
            remaining_count=_integer(data["remaining_count"], "remaining_count", minimum=0),
            remaining_cost_microunits=_integer(
                data["remaining_cost_microunits"],
                "remaining_cost_microunits",
                minimum=0,
            ),
            child_delegation=_json_object(data["child_delegation"], "child_delegation"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "binding_id": self.binding_id,
            "status": self.status.value,
            "generation": self.generation,
            "binding_digest": self.binding_digest,
            "authorizing_principal_id": self.authorizing_principal_id,
            "universe_id": self.universe_id,
            "branch_def_id": self.branch_def_id,
            "operation": self.operation,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "source_digest": self.source_digest,
            "revocation_generation": self.revocation_generation,
            "target_mode": self.target_mode.value,
            "pinned_branch_version_id": self.pinned_branch_version_id,
            "permitted_executor_classes": list(self.permitted_executor_classes),
            "daemon_id": self.daemon_id,
            "runtime_id": self.runtime_id,
            "expires_at": self.expires_at,
            "max_attempts": self.max_attempts,
            "remaining_depth": self.remaining_depth,
            "remaining_count": self.remaining_count,
            "remaining_cost_microunits": self.remaining_cost_microunits,
            "child_delegation": _thaw_json(self.child_delegation),
        }


@dataclass(frozen=True, slots=True)
class BackgroundBranchAttempt:
    schema_version: int
    attempt_id: str
    logical_attempt_key: str
    binding_id: str
    binding_digest: str
    binding_generation: int
    authorizing_principal_id: str
    universe_id: str
    branch_def_id: str
    branch_version_id: str
    branch_content_digest: str
    operation: str
    source_kind: BackgroundBranchSourceKind
    source_id: str
    source_generation: int
    executor_audience: str
    claim_generation: int
    lease_generation: int
    lease_expires_at: str | None
    remaining_depth: int
    remaining_count: int
    remaining_cost_microunits: int
    lifecycle: BackgroundBranchAttemptLifecycle
    hold_reason: BackgroundBranchHoldReason | None
    terminal_reason: str | None
    created_at: str
    updated_at: str
    provenance: BackgroundBranchProvenance

    _FIELDS = frozenset(
        {
            "schema_version",
            "attempt_id",
            "logical_attempt_key",
            "binding_id",
            "binding_digest",
            "binding_generation",
            "authorizing_principal_id",
            "universe_id",
            "branch_def_id",
            "branch_version_id",
            "branch_content_digest",
            "operation",
            "source_kind",
            "source_id",
            "source_generation",
            "executor_audience",
            "claim_generation",
            "lease_generation",
            "lease_expires_at",
            "remaining_depth",
            "remaining_count",
            "remaining_cost_microunits",
            "lifecycle",
            "hold_reason",
            "terminal_reason",
            "created_at",
            "updated_at",
            "provenance",
        }
    )
    _TERMINAL = frozenset(
        {
            BackgroundBranchAttemptLifecycle.SUCCEEDED,
            BackgroundBranchAttemptLifecycle.FAILED,
            BackgroundBranchAttemptLifecycle.CANCELLED,
        }
    )

    def __post_init__(self) -> None:
        _integer(self.schema_version, "schema_version", minimum=1)
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        for name in (
            "attempt_id",
            "logical_attempt_key",
            "binding_id",
            "binding_digest",
            "authorizing_principal_id",
            "universe_id",
            "branch_def_id",
            "branch_version_id",
            "branch_content_digest",
            "operation",
            "source_id",
            "executor_audience",
            "created_at",
            "updated_at",
        ):
            _text(getattr(self, name), name)
        if not isinstance(self.source_kind, BackgroundBranchSourceKind):
            raise ValueError("source_kind must be typed")
        if not isinstance(self.lifecycle, BackgroundBranchAttemptLifecycle):
            raise ValueError("lifecycle must be typed")
        if self.hold_reason is not None and not isinstance(
            self.hold_reason, BackgroundBranchHoldReason
        ):
            raise ValueError("hold_reason must be typed")
        _integer(self.binding_generation, "binding_generation", minimum=1)
        _integer(self.source_generation, "source_generation", minimum=0)
        _integer(self.claim_generation, "claim_generation", minimum=1)
        _integer(self.lease_generation, "lease_generation", minimum=1)
        _optional_text(self.lease_expires_at, "lease_expires_at")
        _integer(self.remaining_depth, "remaining_depth", minimum=0)
        _integer(self.remaining_count, "remaining_count", minimum=0)
        _integer(
            self.remaining_cost_microunits,
            "remaining_cost_microunits",
            minimum=0,
        )
        _optional_text(self.terminal_reason, "terminal_reason")
        held = self.lifecycle is BackgroundBranchAttemptLifecycle.TARGET_AUTHORITY_HELD
        if held != (self.hold_reason is not None):
            raise ValueError("hold_reason is required only for held attempts")
        terminal = self.lifecycle in self._TERMINAL
        if terminal != (self.terminal_reason is not None):
            raise ValueError("terminal_reason is required only for terminal attempts")
        if (held or terminal) and self.lease_expires_at is not None:
            raise ValueError("held or terminal attempts cannot retain a lease")
        if (
            self.lifecycle
            in {
                BackgroundBranchAttemptLifecycle.CLAIMED,
                BackgroundBranchAttemptLifecycle.RUNNING,
            }
            and self.lease_expires_at is None
        ):
            raise ValueError("claimed or running attempts require a lease")
        if not isinstance(self.provenance, BackgroundBranchProvenance):
            raise ValueError("provenance must be typed")
        if self.provenance.authorizing_principal_id != self.authorizing_principal_id:
            raise ValueError("provenance authorizer must match attempt authorizer")
        if self.provenance.source_kind is not self.source_kind:
            raise ValueError("provenance source_kind must match attempt source_kind")
        if self.provenance.source_id != self.source_id:
            raise ValueError("provenance source_id must match attempt source_id")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackgroundBranchAttempt:
        _strict_fields(data, cls._FIELDS, record_name=cls.__name__)
        raw_hold_reason = data["hold_reason"]
        return cls(
            schema_version=_integer(data["schema_version"], "schema_version", minimum=1),
            attempt_id=_text(data["attempt_id"], "attempt_id"),
            logical_attempt_key=_text(data["logical_attempt_key"], "logical_attempt_key"),
            binding_id=_text(data["binding_id"], "binding_id"),
            binding_digest=_text(data["binding_digest"], "binding_digest"),
            binding_generation=_integer(
                data["binding_generation"], "binding_generation", minimum=1
            ),
            authorizing_principal_id=_text(
                data["authorizing_principal_id"], "authorizing_principal_id"
            ),
            universe_id=_text(data["universe_id"], "universe_id"),
            branch_def_id=_text(data["branch_def_id"], "branch_def_id"),
            branch_version_id=_text(data["branch_version_id"], "branch_version_id"),
            branch_content_digest=_text(data["branch_content_digest"], "branch_content_digest"),
            operation=_text(data["operation"], "operation"),
            source_kind=_enum_value(BackgroundBranchSourceKind, data["source_kind"], "source_kind"),
            source_id=_text(data["source_id"], "source_id"),
            source_generation=_integer(data["source_generation"], "source_generation", minimum=0),
            executor_audience=_text(data["executor_audience"], "executor_audience"),
            claim_generation=_integer(data["claim_generation"], "claim_generation", minimum=1),
            lease_generation=_integer(data["lease_generation"], "lease_generation", minimum=1),
            lease_expires_at=_optional_text(data["lease_expires_at"], "lease_expires_at"),
            remaining_depth=_integer(data["remaining_depth"], "remaining_depth", minimum=0),
            remaining_count=_integer(data["remaining_count"], "remaining_count", minimum=0),
            remaining_cost_microunits=_integer(
                data["remaining_cost_microunits"],
                "remaining_cost_microunits",
                minimum=0,
            ),
            lifecycle=_enum_value(BackgroundBranchAttemptLifecycle, data["lifecycle"], "lifecycle"),
            hold_reason=(
                None
                if raw_hold_reason is None
                else _enum_value(BackgroundBranchHoldReason, raw_hold_reason, "hold_reason")
            ),
            terminal_reason=_optional_text(data["terminal_reason"], "terminal_reason"),
            created_at=_text(data["created_at"], "created_at"),
            updated_at=_text(data["updated_at"], "updated_at"),
            provenance=BackgroundBranchProvenance.from_dict(data["provenance"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "logical_attempt_key": self.logical_attempt_key,
            "binding_id": self.binding_id,
            "binding_digest": self.binding_digest,
            "binding_generation": self.binding_generation,
            "authorizing_principal_id": self.authorizing_principal_id,
            "universe_id": self.universe_id,
            "branch_def_id": self.branch_def_id,
            "branch_version_id": self.branch_version_id,
            "branch_content_digest": self.branch_content_digest,
            "operation": self.operation,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "executor_audience": self.executor_audience,
            "claim_generation": self.claim_generation,
            "lease_generation": self.lease_generation,
            "lease_expires_at": self.lease_expires_at,
            "remaining_depth": self.remaining_depth,
            "remaining_count": self.remaining_count,
            "remaining_cost_microunits": self.remaining_cost_microunits,
            "lifecycle": self.lifecycle.value,
            "hold_reason": (self.hold_reason.value if self.hold_reason is not None else None),
            "terminal_reason": self.terminal_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provenance": self.provenance.to_dict(),
        }
