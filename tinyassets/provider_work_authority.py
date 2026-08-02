"""Dark, non-bearer authority for requester-owned provider work.

Bindings record server-owned intent. Receipts, execution claims, and invocation
reservations remain inert ledger records: none can launch a provider, resolve a
credential, authorize quota, or enable provider-authority V2 by itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any, ContextManager, Protocol, runtime_checkable

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,254}$")
_PLACEHOLDER_DIGEST = f"sha256:{'0' * 64}"


def _required(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _reference(value: object, name: str) -> str:
    value = _required(value, name)
    if _REFERENCE_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical reference")
    return value


def _digest(value: object, name: str) -> str:
    value = _required(value, name)
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical sha256 digest")
    return value


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _timestamp(value: object, name: str) -> str:
    value = _required(value, name)
    if not value.endswith("Z") or "T" not in value:
        raise ValueError(f"{name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} must be a canonical UTC timestamp") from exc
    if parsed.utcoffset() is None:
        raise ValueError(f"{name} must be a canonical UTC timestamp")
    return value


def _parsed_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def _closed_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{name} must be a sequence")
    items = tuple(_reference(item, name) for item in value)
    if not items:
        raise ValueError(f"{name} must not be empty")
    if len(set(items)) != len(items):
        raise ValueError(f"{name} must not contain duplicates")
    return items


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _content_digest(value: object) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"


class ProviderWorkBindingState(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ProviderWorkAuthorityWriteOutcome(str, Enum):
    APPLIED = "applied"
    REPLAYED = "replayed"
    MISSING = "missing"
    GENERATION_MISMATCH = "generation_mismatch"
    CONFLICT = "conflict"
    STALE = "stale"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class ProviderWorkBindingRoot:
    """Non-authorizing lookup key for a server-owned provider assignment."""

    owner_user_id: str
    universe_id: str
    provider: str

    def __post_init__(self) -> None:
        for name in ("owner_user_id", "universe_id", "provider"):
            _reference(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ProviderWorkBindingSeed:
    """Fresh, secret-free assignment facts from a trusted server resolver."""

    owner_user_id: str
    universe_id: str
    provider: str
    credential_reference_digest: str
    allowed_operations: tuple[str, ...]
    allowed_roles: tuple[str, ...]
    assignment_generation: int
    assignment_digest: str
    max_invocations: int
    max_tokens: int
    max_cost_microunits: int
    expires_at: str

    def __post_init__(self) -> None:
        for name in ("owner_user_id", "universe_id", "provider"):
            _reference(getattr(self, name), name)
        _digest(self.credential_reference_digest, "credential_reference_digest")
        _digest(self.assignment_digest, "assignment_digest")
        object.__setattr__(
            self,
            "allowed_operations",
            _closed_tuple(self.allowed_operations, "allowed_operations"),
        )
        object.__setattr__(
            self,
            "allowed_roles",
            _closed_tuple(self.allowed_roles, "allowed_roles"),
        )
        _integer(self.assignment_generation, "assignment_generation", minimum=1)
        _integer(self.max_invocations, "max_invocations", minimum=1)
        _integer(self.max_tokens, "max_tokens", minimum=0)
        _integer(self.max_cost_microunits, "max_cost_microunits", minimum=0)
        _timestamp(self.expires_at, "expires_at")


@runtime_checkable
class ProviderWorkBindingResolver(Protocol):
    """Resolve a binding seed from the canonical assignment/custody owner."""

    def resolve(
        self,
        root: ProviderWorkBindingRoot,
    ) -> ProviderWorkBindingSeed | None: ...


@dataclass(frozen=True, slots=True)
class ProviderWorkBinding:
    schema_version: int
    binding_id: str
    generation: int
    binding_digest: str
    state: ProviderWorkBindingState
    owner_user_id: str
    universe_id: str
    provider: str
    credential_reference_digest: str
    allowed_operations: tuple[str, ...]
    allowed_roles: tuple[str, ...]
    assignment_generation: int
    assignment_digest: str
    revocation_generation: int
    max_invocations: int
    max_tokens: int
    max_cost_microunits: int
    expires_at: str
    created_at: str
    updated_at: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "binding_id",
            "generation",
            "binding_digest",
            "state",
            "owner_user_id",
            "universe_id",
            "provider",
            "credential_reference_digest",
            "allowed_operations",
            "allowed_roles",
            "assignment_generation",
            "assignment_digest",
            "revocation_generation",
            "max_invocations",
            "max_tokens",
            "max_cost_microunits",
            "expires_at",
            "created_at",
            "updated_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        for name in ("binding_id", "owner_user_id", "universe_id", "provider"):
            _reference(getattr(self, name), name)
        _integer(self.generation, "generation", minimum=1)
        _digest(self.binding_digest, "binding_digest")
        if not isinstance(self.state, ProviderWorkBindingState):
            raise ValueError("state must be typed")
        _digest(self.credential_reference_digest, "credential_reference_digest")
        object.__setattr__(
            self,
            "allowed_operations",
            _closed_tuple(self.allowed_operations, "allowed_operations"),
        )
        object.__setattr__(
            self,
            "allowed_roles",
            _closed_tuple(self.allowed_roles, "allowed_roles"),
        )
        _integer(self.assignment_generation, "assignment_generation", minimum=1)
        _digest(self.assignment_digest, "assignment_digest")
        _integer(self.revocation_generation, "revocation_generation", minimum=0)
        _integer(self.max_invocations, "max_invocations", minimum=1)
        _integer(self.max_tokens, "max_tokens", minimum=0)
        _integer(self.max_cost_microunits, "max_cost_microunits", minimum=0)
        _timestamp(self.expires_at, "expires_at")
        _timestamp(self.created_at, "created_at")
        _timestamp(self.updated_at, "updated_at")
        if self.state is ProviderWorkBindingState.ACTIVE:
            if self.revocation_generation != 0:
                raise ValueError("active binding cannot carry revocation")
        elif self.revocation_generation < 1:
            raise ValueError("revoked binding requires revocation generation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "binding_id": self.binding_id,
            "generation": self.generation,
            "binding_digest": self.binding_digest,
            "state": self.state.value,
            "owner_user_id": self.owner_user_id,
            "universe_id": self.universe_id,
            "provider": self.provider,
            "credential_reference_digest": self.credential_reference_digest,
            "allowed_operations": list(self.allowed_operations),
            "allowed_roles": list(self.allowed_roles),
            "assignment_generation": self.assignment_generation,
            "assignment_digest": self.assignment_digest,
            "revocation_generation": self.revocation_generation,
            "max_invocations": self.max_invocations,
            "max_tokens": self.max_tokens,
            "max_cost_microunits": self.max_cost_microunits,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderWorkBinding:
        if not isinstance(data, dict) or set(data) != cls._FIELDS:
            raise ValueError("ProviderWorkBinding fields do not match schema")
        values = dict(data)
        values["state"] = ProviderWorkBindingState(values["state"])
        return cls(**values)

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["binding_digest"]
        return _content_digest(payload)


@dataclass(frozen=True, slots=True)
class ProviderWorkBindingFence:
    expected_record: ProviderWorkBinding

    def __post_init__(self) -> None:
        if not isinstance(self.expected_record, ProviderWorkBinding):
            raise ValueError("expected_record must be a ProviderWorkBinding")


@dataclass(frozen=True, slots=True)
class ProviderWorkBindingWriteResult:
    outcome: ProviderWorkAuthorityWriteOutcome
    record: ProviderWorkBinding | None


class ProviderWorkReceiptState(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    FENCED = "fenced"


class ProviderWorkExecutionClaimState(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    INVALIDATED = "invalidated"


class ProviderInvocationReservationState(str, Enum):
    RESERVED = "reserved"
    LAUNCH_STARTED = "launch_started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED_BEFORE_LAUNCH = "cancelled_before_launch"
    INDETERMINATE = "indeterminate"


_WORK_ITEM_KINDS = frozenset({"background_attempt", "branch_task", "run"})


@dataclass(frozen=True, slots=True)
class ProviderUniverseWorkRoot:
    work_item_kind: str
    work_item_id: str

    def __post_init__(self) -> None:
        if self.work_item_kind not in _WORK_ITEM_KINDS:
            raise ValueError("work_item_kind is not server-classified")
        _reference(self.work_item_id, "work_item_id")


@dataclass(frozen=True, slots=True)
class ProviderUniverseWorkAuthority:
    """Transient facts returned only by a trusted server-owned resolver."""

    root: ProviderUniverseWorkRoot
    binding: ProviderWorkBinding
    actor_id: str
    branch_def_id: str
    branch_version_id: str
    operation: str
    role: str
    executor_class: str
    max_invocations: int
    max_tokens: int
    max_cost_microunits: int
    expires_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, ProviderUniverseWorkRoot):
            raise ValueError("root must be a ProviderUniverseWorkRoot")
        if not isinstance(self.binding, ProviderWorkBinding):
            raise ValueError("binding must be a ProviderWorkBinding")
        for name in (
            "actor_id",
            "branch_def_id",
            "branch_version_id",
            "operation",
            "role",
        ):
            _reference(getattr(self, name), name)
        if self.executor_class != "cloud":
            raise ValueError("executor_class must be cloud")
        _integer(self.max_invocations, "max_invocations", minimum=1)
        _integer(self.max_tokens, "max_tokens", minimum=0)
        _integer(
            self.max_cost_microunits,
            "max_cost_microunits",
            minimum=0,
        )
        _timestamp(self.expires_at, "expires_at")


@runtime_checkable
class ProviderUniverseWorkResolver(Protocol):
    def resolve(
        self,
        root: ProviderUniverseWorkRoot,
    ) -> ProviderUniverseWorkAuthority | None: ...


@dataclass(frozen=True, slots=True)
class ProviderUniverseWorkReceipt:
    schema_version: int
    receipt_id: str
    receipt_digest: str
    generation: int
    state: ProviderWorkReceiptState
    work_item_kind: str
    work_item_id: str
    binding_id: str
    binding_generation: int
    binding_digest: str
    binding_revocation_generation: int
    principal_id: str
    actor_id: str
    universe_id: str
    branch_def_id: str
    branch_version_id: str
    provider: str
    credential_reference_digest: str
    assignment_generation: int
    assignment_digest: str
    executor_class: str
    allowed_operations: tuple[str, ...]
    allowed_roles: tuple[str, ...]
    max_invocations: int
    max_tokens: int
    max_cost_microunits: int
    expires_at: str
    created_at: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "receipt_id",
            "receipt_digest",
            "generation",
            "state",
            "work_item_kind",
            "work_item_id",
            "binding_id",
            "binding_generation",
            "binding_digest",
            "binding_revocation_generation",
            "principal_id",
            "actor_id",
            "universe_id",
            "branch_def_id",
            "branch_version_id",
            "provider",
            "credential_reference_digest",
            "assignment_generation",
            "assignment_digest",
            "executor_class",
            "allowed_operations",
            "allowed_roles",
            "max_invocations",
            "max_tokens",
            "max_cost_microunits",
            "expires_at",
            "created_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        if not isinstance(self.state, ProviderWorkReceiptState):
            raise ValueError("state must be typed")
        if self.work_item_kind not in _WORK_ITEM_KINDS:
            raise ValueError("work_item_kind is not server-classified")
        for name in (
            "receipt_id",
            "work_item_id",
            "binding_id",
            "principal_id",
            "actor_id",
            "universe_id",
            "branch_def_id",
            "branch_version_id",
            "provider",
        ):
            _reference(getattr(self, name), name)
        _digest(self.receipt_digest, "receipt_digest")
        _integer(self.generation, "generation", minimum=1)
        _integer(self.binding_generation, "binding_generation", minimum=1)
        _digest(self.binding_digest, "binding_digest")
        _integer(
            self.binding_revocation_generation,
            "binding_revocation_generation",
            minimum=0,
        )
        _digest(
            self.credential_reference_digest,
            "credential_reference_digest",
        )
        _integer(self.assignment_generation, "assignment_generation", minimum=1)
        _digest(self.assignment_digest, "assignment_digest")
        if self.executor_class != "cloud":
            raise ValueError("executor_class must be cloud")
        object.__setattr__(
            self,
            "allowed_operations",
            _closed_tuple(self.allowed_operations, "allowed_operations"),
        )
        object.__setattr__(
            self,
            "allowed_roles",
            _closed_tuple(self.allowed_roles, "allowed_roles"),
        )
        _integer(self.max_invocations, "max_invocations", minimum=1)
        _integer(self.max_tokens, "max_tokens", minimum=0)
        _integer(
            self.max_cost_microunits,
            "max_cost_microunits",
            minimum=0,
        )
        _timestamp(self.expires_at, "expires_at")
        _timestamp(self.created_at, "created_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "receipt_digest": self.receipt_digest,
            "generation": self.generation,
            "state": self.state.value,
            "work_item_kind": self.work_item_kind,
            "work_item_id": self.work_item_id,
            "binding_id": self.binding_id,
            "binding_generation": self.binding_generation,
            "binding_digest": self.binding_digest,
            "binding_revocation_generation": self.binding_revocation_generation,
            "principal_id": self.principal_id,
            "actor_id": self.actor_id,
            "universe_id": self.universe_id,
            "branch_def_id": self.branch_def_id,
            "branch_version_id": self.branch_version_id,
            "provider": self.provider,
            "credential_reference_digest": self.credential_reference_digest,
            "assignment_generation": self.assignment_generation,
            "assignment_digest": self.assignment_digest,
            "executor_class": self.executor_class,
            "allowed_operations": list(self.allowed_operations),
            "allowed_roles": list(self.allowed_roles),
            "max_invocations": self.max_invocations,
            "max_tokens": self.max_tokens,
            "max_cost_microunits": self.max_cost_microunits,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderUniverseWorkReceipt:
        if not isinstance(data, dict) or set(data) != cls._FIELDS:
            raise ValueError("ProviderUniverseWorkReceipt fields do not match schema")
        values = dict(data)
        values["state"] = ProviderWorkReceiptState(values["state"])
        values["allowed_operations"] = tuple(values["allowed_operations"])
        values["allowed_roles"] = tuple(values["allowed_roles"])
        return cls(**values)

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["receipt_digest"]
        return _content_digest(payload)


@dataclass(frozen=True, slots=True)
class ProviderWorkReceiptWriteResult:
    outcome: ProviderWorkAuthorityWriteOutcome
    record: ProviderUniverseWorkReceipt | None


@dataclass(frozen=True, slots=True)
class ProviderWorkExecutionClaimRequest:
    receipt_id: str
    receipt_digest: str
    worker_id: str
    runtime_id: str
    claim_nonce_digest: str
    lease_seconds: int

    def __post_init__(self) -> None:
        for name in ("receipt_id", "worker_id", "runtime_id"):
            _reference(getattr(self, name), name)
        _digest(self.receipt_digest, "receipt_digest")
        _digest(self.claim_nonce_digest, "claim_nonce_digest")
        seconds = _integer(self.lease_seconds, "lease_seconds", minimum=1)
        if seconds > 3600:
            raise ValueError("lease_seconds must be <= 3600")


@dataclass(frozen=True, slots=True)
class ProviderWorkExecutionClaim:
    schema_version: int
    claim_id: str
    claim_digest: str
    generation: int
    state: ProviderWorkExecutionClaimState
    receipt_id: str
    receipt_digest: str
    worker_id: str
    runtime_id: str
    claim_nonce_digest: str
    lease_expires_at: str
    created_at: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "claim_id",
            "claim_digest",
            "generation",
            "state",
            "receipt_id",
            "receipt_digest",
            "worker_id",
            "runtime_id",
            "claim_nonce_digest",
            "lease_expires_at",
            "created_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        if not isinstance(self.state, ProviderWorkExecutionClaimState):
            raise ValueError("state must be typed")
        for name in ("claim_id", "receipt_id", "worker_id", "runtime_id"):
            _reference(getattr(self, name), name)
        _digest(self.claim_digest, "claim_digest")
        _integer(self.generation, "generation", minimum=1)
        _digest(self.receipt_digest, "receipt_digest")
        _digest(self.claim_nonce_digest, "claim_nonce_digest")
        _timestamp(self.lease_expires_at, "lease_expires_at")
        _timestamp(self.created_at, "created_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "claim_id": self.claim_id,
            "claim_digest": self.claim_digest,
            "generation": self.generation,
            "state": self.state.value,
            "receipt_id": self.receipt_id,
            "receipt_digest": self.receipt_digest,
            "worker_id": self.worker_id,
            "runtime_id": self.runtime_id,
            "claim_nonce_digest": self.claim_nonce_digest,
            "lease_expires_at": self.lease_expires_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderWorkExecutionClaim:
        if not isinstance(data, dict) or set(data) != cls._FIELDS:
            raise ValueError("ProviderWorkExecutionClaim fields do not match schema")
        values = dict(data)
        values["state"] = ProviderWorkExecutionClaimState(values["state"])
        return cls(**values)

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["claim_digest"]
        return _content_digest(payload)


@dataclass(frozen=True, slots=True)
class ProviderWorkExecutionClaimWriteResult:
    outcome: ProviderWorkAuthorityWriteOutcome
    record: ProviderWorkExecutionClaim | None


@dataclass(frozen=True, slots=True)
class ProviderInvocationReservationRequest:
    receipt_id: str
    receipt_digest: str
    claim_id: str
    claim_digest: str
    claim_generation: int
    invocation_key: str
    operation: str
    role: str
    max_tokens: int
    max_cost_microunits: int

    def __post_init__(self) -> None:
        for name in (
            "receipt_id",
            "claim_id",
            "invocation_key",
            "operation",
            "role",
        ):
            _reference(getattr(self, name), name)
        _digest(self.receipt_digest, "receipt_digest")
        _digest(self.claim_digest, "claim_digest")
        _integer(self.claim_generation, "claim_generation", minimum=1)
        _integer(self.max_tokens, "max_tokens", minimum=0)
        _integer(
            self.max_cost_microunits,
            "max_cost_microunits",
            minimum=0,
        )


@dataclass(frozen=True, slots=True)
class ProviderInvocationReservation:
    schema_version: int
    reservation_id: str
    reservation_digest: str
    state: ProviderInvocationReservationState
    receipt_id: str
    receipt_digest: str
    claim_id: str
    claim_digest: str
    claim_generation: int
    invocation_key: str
    ordinal: int
    operation: str
    role: str
    max_tokens: int
    max_cost_microunits: int
    created_at: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "reservation_id",
            "reservation_digest",
            "state",
            "receipt_id",
            "receipt_digest",
            "claim_id",
            "claim_digest",
            "claim_generation",
            "invocation_key",
            "ordinal",
            "operation",
            "role",
            "max_tokens",
            "max_cost_microunits",
            "created_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        if not isinstance(self.state, ProviderInvocationReservationState):
            raise ValueError("state must be typed")
        for name in (
            "reservation_id",
            "receipt_id",
            "claim_id",
            "invocation_key",
            "operation",
            "role",
        ):
            _reference(getattr(self, name), name)
        _digest(self.reservation_digest, "reservation_digest")
        _digest(self.receipt_digest, "receipt_digest")
        _digest(self.claim_digest, "claim_digest")
        _integer(self.claim_generation, "claim_generation", minimum=1)
        _integer(self.ordinal, "ordinal", minimum=1)
        _integer(self.max_tokens, "max_tokens", minimum=0)
        _integer(
            self.max_cost_microunits,
            "max_cost_microunits",
            minimum=0,
        )
        _timestamp(self.created_at, "created_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reservation_id": self.reservation_id,
            "reservation_digest": self.reservation_digest,
            "state": self.state.value,
            "receipt_id": self.receipt_id,
            "receipt_digest": self.receipt_digest,
            "claim_id": self.claim_id,
            "claim_digest": self.claim_digest,
            "claim_generation": self.claim_generation,
            "invocation_key": self.invocation_key,
            "ordinal": self.ordinal,
            "operation": self.operation,
            "role": self.role,
            "max_tokens": self.max_tokens,
            "max_cost_microunits": self.max_cost_microunits,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderInvocationReservation:
        if not isinstance(data, dict) or set(data) != cls._FIELDS:
            raise ValueError("ProviderInvocationReservation fields do not match schema")
        values = dict(data)
        values["state"] = ProviderInvocationReservationState(values["state"])
        return cls(**values)

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["reservation_digest"]
        return _content_digest(payload)


@dataclass(frozen=True, slots=True)
class ProviderInvocationReservationWriteResult:
    outcome: ProviderWorkAuthorityWriteOutcome
    record: ProviderInvocationReservation | None


@dataclass(frozen=True, slots=True)
class ProviderInvocationLaunchRequest:
    reservation_id: str
    reserved_digest: str
    receipt_id: str
    receipt_digest: str
    claim_id: str
    claim_digest: str
    claim_generation: int
    invocation_key: str

    def __post_init__(self) -> None:
        for name in (
            "reservation_id",
            "receipt_id",
            "claim_id",
            "invocation_key",
        ):
            _reference(getattr(self, name), name)
        _digest(self.reserved_digest, "reserved_digest")
        _digest(self.receipt_digest, "receipt_digest")
        _digest(self.claim_digest, "claim_digest")
        _integer(self.claim_generation, "claim_generation", minimum=1)

    @classmethod
    def from_reservation(
        cls,
        reservation: ProviderInvocationReservation,
    ) -> ProviderInvocationLaunchRequest:
        if not isinstance(reservation, ProviderInvocationReservation):
            raise ValueError("reservation must be a ProviderInvocationReservation")
        if reservation.state is not ProviderInvocationReservationState.RESERVED:
            raise ValueError("reservation must be reserved")
        return cls(
            reservation_id=reservation.reservation_id,
            reserved_digest=reservation.reservation_digest,
            receipt_id=reservation.receipt_id,
            receipt_digest=reservation.receipt_digest,
            claim_id=reservation.claim_id,
            claim_digest=reservation.claim_digest,
            claim_generation=reservation.claim_generation,
            invocation_key=reservation.invocation_key,
        )


def _reservation_with_state(
    reservation: ProviderInvocationReservation,
    state: ProviderInvocationReservationState,
) -> ProviderInvocationReservation:
    transitioned = replace(
        reservation,
        state=state,
        reservation_digest=_PLACEHOLDER_DIGEST,
    )
    return replace(transitioned, reservation_digest=transitioned.expected_digest())


def provider_work_receipt_id(
    *,
    universe_id: str,
    root: ProviderUniverseWorkRoot,
) -> str:
    identity = {
        "schema_version": 1,
        "universe_id": _reference(universe_id, "universe_id"),
        "work_item_id": root.work_item_id,
        "work_item_kind": root.work_item_kind,
    }
    return f"pwr_{_content_digest(identity).removeprefix('sha256:')[:32]}"


def provider_work_claim_id(receipt_id: str) -> str:
    identity = {
        "receipt_id": _reference(receipt_id, "receipt_id"),
        "schema_version": 1,
    }
    return f"pwc_{_content_digest(identity).removeprefix('sha256:')[:32]}"


def provider_invocation_reservation_id(
    *,
    receipt_id: str,
    invocation_key: str,
) -> str:
    identity = {
        "invocation_key": _reference(invocation_key, "invocation_key"),
        "receipt_id": _reference(receipt_id, "receipt_id"),
        "schema_version": 1,
    }
    return f"pir_{_content_digest(identity).removeprefix('sha256:')[:32]}"


def _receipt_from_authority(
    authority: ProviderUniverseWorkAuthority,
    *,
    created_at: str,
) -> ProviderUniverseWorkReceipt:
    binding = authority.binding
    provisional = ProviderUniverseWorkReceipt(
        schema_version=1,
        receipt_id=provider_work_receipt_id(
            universe_id=binding.universe_id,
            root=authority.root,
        ),
        receipt_digest=_PLACEHOLDER_DIGEST,
        generation=1,
        state=ProviderWorkReceiptState.ACTIVE,
        work_item_kind=authority.root.work_item_kind,
        work_item_id=authority.root.work_item_id,
        binding_id=binding.binding_id,
        binding_generation=binding.generation,
        binding_digest=binding.binding_digest,
        binding_revocation_generation=binding.revocation_generation,
        principal_id=binding.owner_user_id,
        actor_id=authority.actor_id,
        universe_id=binding.universe_id,
        branch_def_id=authority.branch_def_id,
        branch_version_id=authority.branch_version_id,
        provider=binding.provider,
        credential_reference_digest=binding.credential_reference_digest,
        assignment_generation=binding.assignment_generation,
        assignment_digest=binding.assignment_digest,
        executor_class=authority.executor_class,
        allowed_operations=(authority.operation,),
        allowed_roles=(authority.role,),
        max_invocations=authority.max_invocations,
        max_tokens=authority.max_tokens,
        max_cost_microunits=authority.max_cost_microunits,
        expires_at=authority.expires_at,
        created_at=created_at,
    )
    return replace(
        provisional,
        receipt_digest=provisional.expected_digest(),
    )


def _claim_from_request(
    request: ProviderWorkExecutionClaimRequest,
    *,
    created_at: str,
    lease_expires_at: str,
) -> ProviderWorkExecutionClaim:
    provisional = ProviderWorkExecutionClaim(
        schema_version=1,
        claim_id=provider_work_claim_id(request.receipt_id),
        claim_digest=_PLACEHOLDER_DIGEST,
        generation=1,
        state=ProviderWorkExecutionClaimState.ACTIVE,
        receipt_id=request.receipt_id,
        receipt_digest=request.receipt_digest,
        worker_id=request.worker_id,
        runtime_id=request.runtime_id,
        claim_nonce_digest=request.claim_nonce_digest,
        lease_expires_at=lease_expires_at,
        created_at=created_at,
    )
    return replace(provisional, claim_digest=provisional.expected_digest())


def _reservation_from_request(
    request: ProviderInvocationReservationRequest,
    *,
    ordinal: int,
    created_at: str,
) -> ProviderInvocationReservation:
    provisional = ProviderInvocationReservation(
        schema_version=1,
        reservation_id=provider_invocation_reservation_id(
            receipt_id=request.receipt_id,
            invocation_key=request.invocation_key,
        ),
        reservation_digest=_PLACEHOLDER_DIGEST,
        state=ProviderInvocationReservationState.RESERVED,
        receipt_id=request.receipt_id,
        receipt_digest=request.receipt_digest,
        claim_id=request.claim_id,
        claim_digest=request.claim_digest,
        claim_generation=request.claim_generation,
        invocation_key=request.invocation_key,
        ordinal=ordinal,
        operation=request.operation,
        role=request.role,
        max_tokens=request.max_tokens,
        max_cost_microunits=request.max_cost_microunits,
        created_at=created_at,
    )
    return replace(
        provisional,
        reservation_digest=provisional.expected_digest(),
    )


@runtime_checkable
class ProviderWorkAuthorityStore(Protocol):
    def transaction(self) -> ContextManager[Any]: ...

    def get(self, binding_id: str) -> ProviderWorkBinding | None: ...

    def claim(
        self,
        request: ProviderWorkExecutionClaimRequest,
    ) -> ProviderWorkExecutionClaimWriteResult: ...

    def reserve(
        self,
        request: ProviderInvocationReservationRequest,
    ) -> ProviderInvocationReservationWriteResult: ...

    def arm_launch(
        self,
        request: ProviderInvocationLaunchRequest,
    ) -> ProviderInvocationReservationWriteResult: ...


def provider_work_binding_id(
    *,
    owner_user_id: str,
    universe_id: str,
    provider: str,
) -> str:
    identity = {
        "owner_user_id": _reference(owner_user_id, "owner_user_id"),
        "provider": _reference(provider, "provider"),
        "schema_version": 1,
        "universe_id": _reference(universe_id, "universe_id"),
    }
    return f"pwb_{_content_digest(identity).removeprefix('sha256:')[:32]}"


def _from_seed(seed: ProviderWorkBindingSeed, *, created_at: str) -> ProviderWorkBinding:
    provisional = ProviderWorkBinding(
        schema_version=1,
        binding_id=provider_work_binding_id(
            owner_user_id=seed.owner_user_id,
            universe_id=seed.universe_id,
            provider=seed.provider,
        ),
        generation=1,
        binding_digest=_PLACEHOLDER_DIGEST,
        state=ProviderWorkBindingState.ACTIVE,
        owner_user_id=seed.owner_user_id,
        universe_id=seed.universe_id,
        provider=seed.provider,
        credential_reference_digest=seed.credential_reference_digest,
        allowed_operations=seed.allowed_operations,
        allowed_roles=seed.allowed_roles,
        assignment_generation=seed.assignment_generation,
        assignment_digest=seed.assignment_digest,
        revocation_generation=0,
        max_invocations=seed.max_invocations,
        max_tokens=seed.max_tokens,
        max_cost_microunits=seed.max_cost_microunits,
        expires_at=seed.expires_at,
        created_at=created_at,
        updated_at=created_at,
    )
    return replace(provisional, binding_digest=provisional.expected_digest())


class ProviderWorkBindingService:
    """Issue from a trusted assignment resolver and revoke exact bindings."""

    def __init__(
        self,
        store: Any,
        resolver: ProviderWorkBindingResolver | None = None,
    ) -> None:
        required = ("transaction", "timestamp")
        if any(not callable(getattr(store, name, None)) for name in required):
            raise ValueError("store must implement provider authority persistence")
        if resolver is not None and not isinstance(
            resolver,
            ProviderWorkBindingResolver,
        ):
            raise ValueError("resolver must implement ProviderWorkBindingResolver")
        self._store = store
        self._resolver = resolver

    def issue(
        self,
        root: ProviderWorkBindingRoot,
    ) -> ProviderWorkBindingWriteResult:
        if not isinstance(root, ProviderWorkBindingRoot):
            raise ValueError("root must be a ProviderWorkBindingRoot")
        if self._resolver is None:
            raise PermissionError("server-owned provider assignment is unavailable")
        seed = self._resolver.resolve(root)
        exact_root = (
            isinstance(seed, ProviderWorkBindingSeed),
            isinstance(seed, ProviderWorkBindingSeed) and seed.owner_user_id == root.owner_user_id,
            isinstance(seed, ProviderWorkBindingSeed) and seed.universe_id == root.universe_id,
            isinstance(seed, ProviderWorkBindingSeed) and seed.provider == root.provider,
        )
        if not all(exact_root) or seed is None:
            raise PermissionError("server-owned provider assignment is unavailable")
        issue = getattr(self._store, "_issue_binding", None)
        if not callable(issue):
            raise ValueError("store must implement binding issuance persistence")
        return issue(seed)

    def revoke(self, expected: ProviderWorkBindingFence) -> ProviderWorkBindingWriteResult:
        if not isinstance(expected, ProviderWorkBindingFence):
            raise ValueError("expected must be a ProviderWorkBindingFence")
        current = expected.expected_record
        if current.state is not ProviderWorkBindingState.ACTIVE:
            return ProviderWorkBindingWriteResult(
                ProviderWorkAuthorityWriteOutcome.CONFLICT,
                current,
            )
        provisional = replace(
            current,
            generation=current.generation + 1,
            binding_digest=_PLACEHOLDER_DIGEST,
            state=ProviderWorkBindingState.REVOKED,
            revocation_generation=current.revocation_generation + 1,
            updated_at=self._store.timestamp(),
        )
        replacement = replace(
            provisional,
            binding_digest=provisional.expected_digest(),
        )
        with self._store.transaction() as transaction:
            return transaction.compare_and_swap(expected, replacement)


class ProviderWorkReceiptService:
    """Issue inert receipts only from a trusted server-owned resolver."""

    def __init__(
        self,
        store: Any,
        resolver: ProviderUniverseWorkResolver,
    ) -> None:
        if not callable(getattr(store, "_issue_universe_receipt", None)):
            raise ValueError("store must implement receipt persistence")
        if not isinstance(resolver, ProviderUniverseWorkResolver):
            raise ValueError("resolver must implement ProviderUniverseWorkResolver")
        self._store = store
        self._resolver = resolver

    def issue(
        self,
        root: ProviderUniverseWorkRoot,
    ) -> ProviderWorkReceiptWriteResult:
        if not isinstance(root, ProviderUniverseWorkRoot):
            raise ValueError("root must be a ProviderUniverseWorkRoot")
        authority = self._resolver.resolve(root)
        if not isinstance(authority, ProviderUniverseWorkAuthority) or authority.root != root:
            raise PermissionError("server-owned provider authority is unavailable")
        binding = authority.binding
        exact = (
            binding.state is ProviderWorkBindingState.ACTIVE,
            authority.operation in binding.allowed_operations,
            authority.role in binding.allowed_roles,
            authority.executor_class == "cloud",
            authority.max_invocations <= binding.max_invocations,
            authority.max_tokens <= binding.max_tokens,
            authority.max_cost_microunits <= binding.max_cost_microunits,
            _parsed_timestamp(authority.expires_at) <= _parsed_timestamp(binding.expires_at),
        )
        if not all(exact):
            raise PermissionError("resolved provider authority exceeds binding")
        return self._store._issue_universe_receipt(authority)


__all__ = [
    "ProviderInvocationReservation",
    "ProviderInvocationLaunchRequest",
    "ProviderInvocationReservationRequest",
    "ProviderInvocationReservationState",
    "ProviderInvocationReservationWriteResult",
    "ProviderWorkAuthorityStore",
    "ProviderWorkAuthorityWriteOutcome",
    "ProviderWorkBinding",
    "ProviderWorkBindingFence",
    "ProviderWorkBindingResolver",
    "ProviderWorkBindingRoot",
    "ProviderWorkBindingSeed",
    "ProviderWorkBindingService",
    "ProviderWorkBindingState",
    "ProviderWorkBindingWriteResult",
    "ProviderWorkExecutionClaim",
    "ProviderWorkExecutionClaimRequest",
    "ProviderWorkExecutionClaimState",
    "ProviderWorkExecutionClaimWriteResult",
    "ProviderWorkReceiptService",
    "ProviderWorkReceiptState",
    "ProviderWorkReceiptWriteResult",
    "ProviderUniverseWorkAuthority",
    "ProviderUniverseWorkReceipt",
    "ProviderUniverseWorkResolver",
    "ProviderUniverseWorkRoot",
    "provider_work_binding_id",
]
