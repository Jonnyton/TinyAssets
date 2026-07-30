"""Dark typed contracts for server-owned background Branch authority.

These records are deliberately inert.  They carry no bearer capability and
perform no persistence, queue mutation, credential lookup, or Branch run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
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


class BackgroundBranchOperation(str, Enum):
    INVOKE_BRANCH = "invoke_branch"
    INVOKE_BRANCH_VERSION = "invoke_branch_version"
    RESUME_RUN = "resume_run"


class BackgroundBranchExecutorClass(str, Enum):
    CLOUD = "cloud"
    HOST = "host"
    DISTRIBUTED = "distributed"


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


_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,254}$")
_SECRET_PREFIXES = (
    "bearer",
    "sk-",
    "ghp_",
    "github_pat_",
    "secret:",
    "token:",
)


def _reference(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if result.lower().startswith(_SECRET_PREFIXES) or not _REFERENCE_PATTERN.fullmatch(result):
        raise ValueError(f"{field_name} must be a non-bearer reference")
    return result


def _optional_reference(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _reference(value, field_name)


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


def _enum_tuple(
    enum_type: type[Enum],
    value: Any,
    field_name: str,
    *,
    allow_empty: bool = False,
) -> tuple[Any, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"{field_name} must be a list")
    items = tuple(_enum_value(enum_type, item, field_name) for item in value)
    if not allow_empty and not items:
        raise ValueError(f"{field_name} must not be empty")
    if len(set(items)) != len(items):
        raise ValueError(f"{field_name} must not contain duplicates")
    return items


@dataclass(frozen=True, slots=True)
class BackgroundBranchChildDelegation:
    allowed_branch_def_ids: tuple[str, ...]
    allowed_operations: tuple[BackgroundBranchOperation, ...]
    max_depth: int
    max_count: int
    max_cost_microunits: int

    _FIELDS = frozenset(
        {
            "allowed_branch_def_ids",
            "allowed_operations",
            "max_depth",
            "max_count",
            "max_cost_microunits",
        }
    )

    def __post_init__(self) -> None:
        branch_ids = tuple(
            _reference(item, "allowed_branch_def_ids") for item in self.allowed_branch_def_ids
        )
        operations = tuple(self.allowed_operations)
        if any(not isinstance(item, BackgroundBranchOperation) for item in operations):
            raise ValueError("allowed_operations must be typed")
        if len(set(branch_ids)) != len(branch_ids):
            raise ValueError("allowed_branch_def_ids must not contain duplicates")
        if len(set(operations)) != len(operations):
            raise ValueError("allowed_operations must not contain duplicates")
        object.__setattr__(self, "allowed_branch_def_ids", branch_ids)
        object.__setattr__(self, "allowed_operations", operations)
        _integer(self.max_depth, "max_depth", minimum=0)
        _integer(self.max_count, "max_count", minimum=0)
        _integer(self.max_cost_microunits, "max_cost_microunits", minimum=0)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackgroundBranchChildDelegation:
        _strict_fields(data, cls._FIELDS, record_name=cls.__name__)
        return cls(
            allowed_branch_def_ids=tuple(
                _reference(item, "allowed_branch_def_ids")
                for item in _text_tuple(
                    data["allowed_branch_def_ids"],
                    "allowed_branch_def_ids",
                    allow_empty=True,
                )
            ),
            allowed_operations=_enum_tuple(
                BackgroundBranchOperation,
                data["allowed_operations"],
                "allowed_operations",
                allow_empty=True,
            ),
            max_depth=_integer(data["max_depth"], "max_depth", minimum=0),
            max_count=_integer(data["max_count"], "max_count", minimum=0),
            max_cost_microunits=_integer(
                data["max_cost_microunits"],
                "max_cost_microunits",
                minimum=0,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_branch_def_ids": list(self.allowed_branch_def_ids),
            "allowed_operations": [item.value for item in self.allowed_operations],
            "max_depth": self.max_depth,
            "max_count": self.max_count,
            "max_cost_microunits": self.max_cost_microunits,
        }


@dataclass(frozen=True, slots=True)
class BackgroundBranchReceiptRefs:
    b2_execution_grant_id: str | None
    provider_work_receipt_id: str | None
    provider_attempt_receipt_id: str | None
    payment_receipt_id: str | None
    effect_receipt_id: str | None

    _FIELD_ORDER = (
        "b2_execution_grant_id",
        "provider_work_receipt_id",
        "provider_attempt_receipt_id",
        "payment_receipt_id",
        "effect_receipt_id",
    )
    _FIELDS = frozenset(_FIELD_ORDER)

    def __post_init__(self) -> None:
        for name in self._FIELD_ORDER:
            _optional_reference(getattr(self, name), name)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackgroundBranchReceiptRefs:
        _strict_fields(data, cls._FIELDS, record_name=cls.__name__)
        return cls(**{name: _optional_reference(data[name], name) for name in cls._FIELD_ORDER})

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._FIELD_ORDER}


@dataclass(frozen=True, slots=True)
class BackgroundBranchExecutorAudience:
    executor_class: BackgroundBranchExecutorClass
    daemon_id: str | None
    runtime_id: str | None
    worker_id: str

    _FIELDS = frozenset({"executor_class", "daemon_id", "runtime_id", "worker_id"})

    def __post_init__(self) -> None:
        if not isinstance(self.executor_class, BackgroundBranchExecutorClass):
            raise ValueError("executor_class must be typed")
        _optional_reference(self.daemon_id, "daemon_id")
        _optional_reference(self.runtime_id, "runtime_id")
        _reference(self.worker_id, "worker_id")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackgroundBranchExecutorAudience:
        _strict_fields(data, cls._FIELDS, record_name=cls.__name__)
        return cls(
            executor_class=_enum_value(
                BackgroundBranchExecutorClass,
                data["executor_class"],
                "executor_class",
            ),
            daemon_id=_optional_reference(data["daemon_id"], "daemon_id"),
            runtime_id=_optional_reference(data["runtime_id"], "runtime_id"),
            worker_id=_reference(data["worker_id"], "worker_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "executor_class": self.executor_class.value,
            "daemon_id": self.daemon_id,
            "runtime_id": self.runtime_id,
            "worker_id": self.worker_id,
        }


@dataclass(frozen=True, slots=True)
class BackgroundBranchProvenance:
    authorizing_principal_id: str
    source_kind: BackgroundBranchSourceKind
    source_id: str
    executor_class: BackgroundBranchExecutorClass
    daemon_id: str | None
    runtime_id: str | None
    worker_id: str | None
    parent_attempt_id: str | None
    origin_attempt_id: str
    audit_correlation_ids: tuple[str, ...]
    receipt_refs: BackgroundBranchReceiptRefs

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
        if not isinstance(self.executor_class, BackgroundBranchExecutorClass):
            raise ValueError("executor_class must be typed")
        for name in ("daemon_id", "runtime_id", "worker_id", "parent_attempt_id"):
            _optional_reference(getattr(self, name), name)
        _reference(self.origin_attempt_id, "origin_attempt_id")
        correlation_ids = tuple(
            _reference(value, "audit_correlation_ids") for value in self.audit_correlation_ids
        )
        if not correlation_ids:
            raise ValueError("audit_correlation_ids must not be empty")
        if len(set(correlation_ids)) != len(correlation_ids):
            raise ValueError("audit_correlation_ids must not contain duplicates")
        object.__setattr__(self, "audit_correlation_ids", correlation_ids)
        if not isinstance(self.receipt_refs, BackgroundBranchReceiptRefs):
            raise ValueError("receipt_refs must be typed")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackgroundBranchProvenance:
        _strict_fields(data, cls._FIELDS, record_name=cls.__name__)
        return cls(
            authorizing_principal_id=_text(
                data["authorizing_principal_id"], "authorizing_principal_id"
            ),
            source_kind=_enum_value(BackgroundBranchSourceKind, data["source_kind"], "source_kind"),
            source_id=_text(data["source_id"], "source_id"),
            executor_class=_enum_value(
                BackgroundBranchExecutorClass,
                data["executor_class"],
                "executor_class",
            ),
            daemon_id=_optional_reference(data["daemon_id"], "daemon_id"),
            runtime_id=_optional_reference(data["runtime_id"], "runtime_id"),
            worker_id=_optional_reference(data["worker_id"], "worker_id"),
            parent_attempt_id=_optional_reference(data["parent_attempt_id"], "parent_attempt_id"),
            origin_attempt_id=_reference(data["origin_attempt_id"], "origin_attempt_id"),
            audit_correlation_ids=_text_tuple(
                data["audit_correlation_ids"], "audit_correlation_ids"
            ),
            receipt_refs=BackgroundBranchReceiptRefs.from_dict(data["receipt_refs"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorizing_principal_id": self.authorizing_principal_id,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "executor_class": self.executor_class.value,
            "daemon_id": self.daemon_id,
            "runtime_id": self.runtime_id,
            "worker_id": self.worker_id,
            "parent_attempt_id": self.parent_attempt_id,
            "origin_attempt_id": self.origin_attempt_id,
            "audit_correlation_ids": list(self.audit_correlation_ids),
            "receipt_refs": self.receipt_refs.to_dict(),
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
    operation: BackgroundBranchOperation
    source_kind: BackgroundBranchSourceKind
    source_id: str
    source_revision: str
    source_digest: str
    revocation_generation: int
    target_mode: BackgroundBranchTargetMode
    pinned_branch_version_id: str | None
    permitted_executor_classes: tuple[BackgroundBranchExecutorClass, ...]
    daemon_id: str | None
    runtime_id: str | None
    expires_at: str | None
    max_attempts: int
    remaining_depth: int
    remaining_count: int
    remaining_cost_microunits: int
    child_delegation: BackgroundBranchChildDelegation

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
            "source_id",
            "source_revision",
            "source_digest",
        ):
            _text(getattr(self, name), name)
        if not isinstance(self.status, BackgroundBranchBindingStatus):
            raise ValueError("status must be typed")
        if not isinstance(self.source_kind, BackgroundBranchSourceKind):
            raise ValueError("source_kind must be typed")
        if not isinstance(self.operation, BackgroundBranchOperation):
            raise ValueError("operation must be typed")
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
        executor_classes = tuple(self.permitted_executor_classes)
        if not executor_classes:
            raise ValueError("permitted_executor_classes must not be empty")
        if any(not isinstance(value, BackgroundBranchExecutorClass) for value in executor_classes):
            raise ValueError("permitted_executor_classes must be typed")
        if len(set(executor_classes)) != len(executor_classes):
            raise ValueError("permitted_executor_classes must not contain duplicates")
        object.__setattr__(self, "permitted_executor_classes", executor_classes)
        _optional_reference(self.daemon_id, "daemon_id")
        _optional_reference(self.runtime_id, "runtime_id")
        _optional_text(self.expires_at, "expires_at")
        _integer(self.max_attempts, "max_attempts", minimum=1)
        _integer(self.remaining_depth, "remaining_depth", minimum=0)
        _integer(self.remaining_count, "remaining_count", minimum=0)
        _integer(
            self.remaining_cost_microunits,
            "remaining_cost_microunits",
            minimum=0,
        )
        if not isinstance(self.child_delegation, BackgroundBranchChildDelegation):
            raise ValueError("child_delegation must be typed")
        if self.remaining_count > self.max_attempts:
            raise ValueError("remaining_count exceeds max_attempts")

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
            operation=_enum_value(BackgroundBranchOperation, data["operation"], "operation"),
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
            permitted_executor_classes=_enum_tuple(
                BackgroundBranchExecutorClass,
                data["permitted_executor_classes"],
                "permitted_executor_classes",
            ),
            daemon_id=_optional_reference(data["daemon_id"], "daemon_id"),
            runtime_id=_optional_reference(data["runtime_id"], "runtime_id"),
            expires_at=_optional_text(data["expires_at"], "expires_at"),
            max_attempts=_integer(data["max_attempts"], "max_attempts", minimum=1),
            remaining_depth=_integer(data["remaining_depth"], "remaining_depth", minimum=0),
            remaining_count=_integer(data["remaining_count"], "remaining_count", minimum=0),
            remaining_cost_microunits=_integer(
                data["remaining_cost_microunits"],
                "remaining_cost_microunits",
                minimum=0,
            ),
            child_delegation=BackgroundBranchChildDelegation.from_dict(data["child_delegation"]),
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
            "operation": self.operation.value,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "source_digest": self.source_digest,
            "revocation_generation": self.revocation_generation,
            "target_mode": self.target_mode.value,
            "pinned_branch_version_id": self.pinned_branch_version_id,
            "permitted_executor_classes": [item.value for item in self.permitted_executor_classes],
            "daemon_id": self.daemon_id,
            "runtime_id": self.runtime_id,
            "expires_at": self.expires_at,
            "max_attempts": self.max_attempts,
            "remaining_depth": self.remaining_depth,
            "remaining_count": self.remaining_count,
            "remaining_cost_microunits": self.remaining_cost_microunits,
            "child_delegation": self.child_delegation.to_dict(),
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
    operation: BackgroundBranchOperation
    source_kind: BackgroundBranchSourceKind
    source_id: str
    source_generation: int
    executor_audience: BackgroundBranchExecutorAudience
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
            "source_id",
            "created_at",
            "updated_at",
        ):
            _text(getattr(self, name), name)
        if not isinstance(self.source_kind, BackgroundBranchSourceKind):
            raise ValueError("source_kind must be typed")
        if not isinstance(self.operation, BackgroundBranchOperation):
            raise ValueError("operation must be typed")
        if not isinstance(self.executor_audience, BackgroundBranchExecutorAudience):
            raise ValueError("executor_audience must be typed")
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
        if (
            self.provenance.executor_class is not self.executor_audience.executor_class
            or self.provenance.daemon_id != self.executor_audience.daemon_id
            or self.provenance.runtime_id != self.executor_audience.runtime_id
            or self.provenance.worker_id != self.executor_audience.worker_id
        ):
            raise ValueError("provenance executor must match attempt audience")
        child_source = self.source_kind in {
            BackgroundBranchSourceKind.DIRECT_CHILD,
            BackgroundBranchSourceKind.PARENT_ATTEMPT,
        }
        if child_source:
            if self.provenance.parent_attempt_id is None:
                raise ValueError("child attempt requires parent lineage")
            if self.provenance.parent_attempt_id == self.attempt_id:
                raise ValueError("child attempt cannot parent itself")
            if self.provenance.origin_attempt_id == self.attempt_id:
                raise ValueError("child attempt requires root origin lineage")
        elif self.provenance.parent_attempt_id is not None:
            raise ValueError("root attempt cannot have parent lineage")
        elif self.provenance.origin_attempt_id != self.attempt_id:
            raise ValueError("root attempt must originate from itself")

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
            operation=_enum_value(BackgroundBranchOperation, data["operation"], "operation"),
            source_kind=_enum_value(BackgroundBranchSourceKind, data["source_kind"], "source_kind"),
            source_id=_text(data["source_id"], "source_id"),
            source_generation=_integer(data["source_generation"], "source_generation", minimum=0),
            executor_audience=BackgroundBranchExecutorAudience.from_dict(data["executor_audience"]),
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
            lifecycle=_enum_value(
                BackgroundBranchAttemptLifecycle,
                data["lifecycle"],
                "lifecycle",
            ),
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
            "operation": self.operation.value,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "source_generation": self.source_generation,
            "executor_audience": self.executor_audience.to_dict(),
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
