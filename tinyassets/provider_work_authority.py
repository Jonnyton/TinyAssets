"""Dark, non-bearer authority for requester-owned provider work.

The binding records server-owned authorization intent only.  Its identifier,
digest, or serialized fields cannot launch a provider, resolve a credential,
or authorize quota.  JIT receipts and provider invocation remain owned by the
later provider-work authority slices.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
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
    return value


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
        values["allowed_operations"] = tuple(values["allowed_operations"])
        values["allowed_roles"] = tuple(values["allowed_roles"])
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


@runtime_checkable
class ProviderWorkAuthorityStore(Protocol):
    def transaction(self) -> ContextManager[Any]: ...

    def get(self, binding_id: str) -> ProviderWorkBinding | None: ...


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
    """Revoke persisted bindings; production issuance is deliberately absent."""

    def __init__(self, store: Any) -> None:
        required = ("transaction", "timestamp")
        if any(not callable(getattr(store, name, None)) for name in required):
            raise ValueError("store must implement provider authority persistence")
        self._store = store

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


__all__ = [
    "ProviderWorkAuthorityStore",
    "ProviderWorkAuthorityWriteOutcome",
    "ProviderWorkBinding",
    "ProviderWorkBindingFence",
    "ProviderWorkBindingSeed",
    "ProviderWorkBindingService",
    "ProviderWorkBindingState",
    "ProviderWorkBindingWriteResult",
    "provider_work_binding_id",
]
