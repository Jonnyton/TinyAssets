"""Prepared, non-authorizing cloud continuation contracts.

A prepared continuation is a durable snapshot of independently owned facts.
It cannot activate an automation, enqueue an epoch-2 task, issue a background
attempt, invoke a provider, resolve a credential, or authorize an effect.
Every owner must be revalidated just in time by the later cutover slice.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from tinyassets.background_branch_authority import (
    BackgroundBranchBindingStatus,
    BackgroundBranchExecutorClass,
    BackgroundBranchOperation,
    BackgroundBranchTargetMode,
)
from tinyassets.storage.automation_activations import (
    AutomationActivationState,
)
from tinyassets.user_owned_cloud_automation import (
    AutomationAdmissionError,
    RepositorySpecWorkDefinition,
    resolve_inactive_cloud_authority,
)

_PLACEHOLDER_DIGEST = f"sha256:{'0' * 64}"
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _digest(value: object, name: str) -> str:
    value = _text(value, name)
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a canonical sha256 digest")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _content_digest(value: object) -> str:
    payload = _canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _timestamp_text(value: object, name: str) -> str:
    value = _text(value, name)
    if not value.endswith("Z"):
        raise ValueError(f"{name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} must be a canonical UTC timestamp") from exc
    if _timestamp(parsed) != value:
        raise ValueError(f"{name} must be a canonical UTC timestamp")
    return value


class CloudContinuationState(str, Enum):
    PREPARED = "prepared"


class CloudContinuationWriteOutcome(str, Enum):
    APPLIED = "applied"
    REPLAYED = "replayed"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class PreparedCloudContinuationRequest:
    automation_id: str
    background_binding_id: str

    def __post_init__(self) -> None:
        _text(self.automation_id, "automation_id")
        _text(self.background_binding_id, "background_binding_id")


@dataclass(frozen=True, slots=True)
class PreparedCloudContinuation:
    schema_version: int
    continuation_id: str
    generation: int
    continuation_digest: str
    state: CloudContinuationState
    principal_id: str
    universe_id: str
    automation_id: str
    activation_epoch: int
    intended_executor_class: str
    definition_digest: str
    branch_def_id: str
    branch_version_id: str
    branch_content_digest: str
    background_binding_id: str
    background_binding_generation: int
    background_binding_digest: str
    provider_binding_id: str
    provider_binding_generation: int
    provider_binding_digest: str
    destination_grant_id: str
    destination_connection_id: str
    destination: str
    created_at: str
    updated_at: str

    _FIELDS = frozenset({
        "schema_version",
        "continuation_id",
        "generation",
        "continuation_digest",
        "state",
        "principal_id",
        "universe_id",
        "automation_id",
        "activation_epoch",
        "intended_executor_class",
        "definition_digest",
        "branch_def_id",
        "branch_version_id",
        "branch_content_digest",
        "background_binding_id",
        "background_binding_generation",
        "background_binding_digest",
        "provider_binding_id",
        "provider_binding_generation",
        "provider_binding_digest",
        "destination_grant_id",
        "destination_connection_id",
        "destination",
        "created_at",
        "updated_at",
    })

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        if not isinstance(self.state, CloudContinuationState):
            raise ValueError("state must be typed")
        for name in (
            "continuation_id",
            "principal_id",
            "universe_id",
            "automation_id",
            "branch_def_id",
            "branch_version_id",
            "background_binding_id",
            "provider_binding_id",
            "destination_grant_id",
            "destination_connection_id",
            "destination",
        ):
            _text(getattr(self, name), name)
        _timestamp_text(self.created_at, "created_at")
        _timestamp_text(self.updated_at, "updated_at")
        if self.intended_executor_class != "cloud":
            raise ValueError("intended_executor_class must be cloud")
        _integer(self.generation, "generation", minimum=1)
        _integer(self.activation_epoch, "activation_epoch", minimum=0)
        _integer(
            self.background_binding_generation,
            "background_binding_generation",
            minimum=1,
        )
        _integer(
            self.provider_binding_generation,
            "provider_binding_generation",
            minimum=1,
        )
        for name in (
            "continuation_digest",
            "definition_digest",
            "branch_content_digest",
            "background_binding_digest",
            "provider_binding_digest",
        ):
            _digest(getattr(self, name), name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "continuation_id": self.continuation_id,
            "generation": self.generation,
            "continuation_digest": self.continuation_digest,
            "state": self.state.value,
            "principal_id": self.principal_id,
            "universe_id": self.universe_id,
            "automation_id": self.automation_id,
            "activation_epoch": self.activation_epoch,
            "intended_executor_class": self.intended_executor_class,
            "definition_digest": self.definition_digest,
            "branch_def_id": self.branch_def_id,
            "branch_version_id": self.branch_version_id,
            "branch_content_digest": self.branch_content_digest,
            "background_binding_id": self.background_binding_id,
            "background_binding_generation": self.background_binding_generation,
            "background_binding_digest": self.background_binding_digest,
            "provider_binding_id": self.provider_binding_id,
            "provider_binding_generation": self.provider_binding_generation,
            "provider_binding_digest": self.provider_binding_digest,
            "destination_grant_id": self.destination_grant_id,
            "destination_connection_id": self.destination_connection_id,
            "destination": self.destination,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PreparedCloudContinuation:
        if not isinstance(value, dict) or set(value) != cls._FIELDS:
            raise ValueError("PreparedCloudContinuation fields do not match schema")
        payload = dict(value)
        payload["state"] = CloudContinuationState(payload["state"])
        return cls(**payload)

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["continuation_digest"]
        return _content_digest(payload)

    def matches_preparation(self, other: PreparedCloudContinuation) -> bool:
        """Compare the immutable request while ignoring retry timestamps."""
        if not isinstance(other, PreparedCloudContinuation):
            return False
        left = self.to_dict()
        right = other.to_dict()
        for payload in (left, right):
            del payload["continuation_digest"]
            del payload["created_at"]
            del payload["updated_at"]
        return left == right


@dataclass(frozen=True, slots=True)
class CloudContinuationWriteResult:
    outcome: CloudContinuationWriteOutcome
    record: PreparedCloudContinuation | None


class CloudContinuationPreparationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _prepared_record(
    definition: RepositorySpecWorkDefinition,
    *,
    request: PreparedCloudContinuationRequest,
    activation: Any,
    background: Any,
    provider: Any,
    destination: Any,
    created_at: str,
) -> PreparedCloudContinuation:
    identity = {
        "automation_id": request.automation_id,
        "definition_digest": definition.definition_digest,
        "schema_version": 1,
        "universe_id": definition.universe_id,
    }
    provisional = PreparedCloudContinuation(
        schema_version=1,
        continuation_id=(
            "cloud_cont_" + _content_digest(identity).removeprefix("sha256:")[:32]
        ),
        generation=1,
        continuation_digest=_PLACEHOLDER_DIGEST,
        state=CloudContinuationState.PREPARED,
        principal_id=definition.principal_id,
        universe_id=definition.universe_id,
        automation_id=request.automation_id,
        activation_epoch=activation.epoch,
        intended_executor_class="cloud",
        definition_digest=definition.definition_digest,
        branch_def_id=definition.branch_def_id,
        branch_version_id=definition.branch_version_id,
        branch_content_digest=definition.branch_content_digest,
        background_binding_id=background.binding_id,
        background_binding_generation=background.generation,
        background_binding_digest=background.binding_digest,
        provider_binding_id=provider.provider_binding_id,
        provider_binding_generation=provider.provider_binding_generation,
        provider_binding_digest=provider.provider_binding_digest,
        destination_grant_id=destination.destination_grant_id,
        destination_connection_id=destination.destination_connection_id,
        destination=destination.destination,
        created_at=created_at,
        updated_at=created_at,
    )
    return replace(
        provisional,
        continuation_digest=provisional.expected_digest(),
    )


def prepare_inactive_cloud_continuation(
    definition: RepositorySpecWorkDefinition,
    *,
    request: PreparedCloudContinuationRequest,
    activation_store: Any,
    background_store: Any,
    provider_store: Any,
    connection_ledger: Any,
    continuation_store: Any,
    clock: Callable[[], datetime] | None = None,
) -> CloudContinuationWriteResult:
    """Persist one exact prepared continuation without granting execution."""
    from tinyassets.storage.automation_activations import AutomationActivationStore
    from tinyassets.storage.background_branch_authority import (
        SQLiteBackgroundBranchAuthorityStore,
    )
    from tinyassets.storage.cloud_automation_continuation import (
        SQLiteCloudAutomationContinuationStore,
    )
    from tinyassets.storage.outbound_connections import ConnectionLedger
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )

    if not isinstance(definition, RepositorySpecWorkDefinition):
        raise ValueError("definition must be a RepositorySpecWorkDefinition")
    if not isinstance(request, PreparedCloudContinuationRequest):
        raise ValueError("request must be a PreparedCloudContinuationRequest")
    stores = (
        (activation_store, AutomationActivationStore),
        (background_store, SQLiteBackgroundBranchAuthorityStore),
        (provider_store, SQLiteProviderWorkAuthorityStore),
        (continuation_store, SQLiteCloudAutomationContinuationStore),
    )
    if any(not isinstance(store, expected) for store, expected in stores):
        raise ValueError("cloud continuation stores must use canonical owners")
    if not isinstance(connection_ledger, ConnectionLedger):
        raise ValueError("connection_ledger must be a ConnectionLedger")
    control_paths = {
        Path(store.base_path).resolve() for store, _expected in stores
    }
    if len(control_paths) != 1:
        raise CloudContinuationPreparationError(
            "control_plane_mismatch",
            "canonical stores do not share one control-plane path",
        )

    activation = activation_store.get(definition.universe_id, request.automation_id)
    if activation is None:
        raise CloudContinuationPreparationError(
            "activation_missing",
            "server-authoritative activation does not exist",
        )
    if activation.state is not AutomationActivationState.STOPPED:
        raise CloudContinuationPreparationError(
            "activation_not_stopped",
            "prepared continuation requires a stopped activation",
        )

    background = background_store.get_binding(request.background_binding_id)
    if background is None or background.status is not BackgroundBranchBindingStatus.ACTIVE:
        raise CloudContinuationPreparationError(
            "background_binding_unavailable",
            "background Branch binding is missing or inactive",
        )
    exact_background = (
        background.authorizing_principal_id == definition.principal_id,
        background.universe_id == definition.universe_id,
        background.branch_def_id == definition.branch_def_id,
        background.operation is BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
        background.target_mode is BackgroundBranchTargetMode.PINNED_VERSION,
        background.pinned_branch_version_id == definition.branch_version_id,
        background.permitted_executor_classes
        == (BackgroundBranchExecutorClass.CLOUD,),
        background.max_attempts <= definition.max_attempts,
        0 < background.remaining_count <= definition.max_attempts,
        0
        < background.remaining_cost_microunits
        <= definition.max_cost_microunits,
    )
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    if background.expires_at is not None:
        expires_at = datetime.fromisoformat(
            background.expires_at.removesuffix("Z") + "+00:00"
        )
        exact_background += (expires_at > now.astimezone(timezone.utc),)
    if not all(exact_background):
        raise CloudContinuationPreparationError(
            "background_binding_mismatch",
            "background Branch binding does not match the immutable definition",
        )

    try:
        authority = resolve_inactive_cloud_authority(
            definition,
            provider_store=provider_store,
            connection_ledger=connection_ledger,
        )
    except AutomationAdmissionError as exc:
        raise CloudContinuationPreparationError(exc.code, str(exc)) from exc
    provider_binding = provider_store.get(authority.provider_binding_id)
    exact_provider_snapshot = (
        provider_binding is not None,
        provider_binding is not None
        and provider_binding.generation == authority.provider_binding_generation,
        provider_binding is not None
        and provider_binding.binding_digest == authority.provider_binding_digest,
    )
    if not all(exact_provider_snapshot) or provider_binding is None:
        raise CloudContinuationPreparationError(
            "provider_binding_unavailable",
            "requester-owned provider binding changed during preparation",
        )

    created_at = _timestamp(now)
    record = _prepared_record(
        definition,
        request=request,
        activation=activation,
        background=background,
        provider=authority,
        destination=authority,
        created_at=created_at,
    )
    try:
        return continuation_store.prepare(
            record,
            expected_activation=activation,
            expected_background=background,
            expected_provider=provider_binding,
        )
    except PermissionError as exc:
        code = {
            "background_binding_not_current": "background_binding_mismatch",
            "provider_binding_not_current": "provider_binding_unavailable",
        }.get(str(exc), "activation_not_stopped")
        raise CloudContinuationPreparationError(
            code,
            "control-plane authority changed during continuation preparation",
        ) from exc


__all__ = [
    "CloudContinuationPreparationError",
    "CloudContinuationState",
    "CloudContinuationWriteOutcome",
    "CloudContinuationWriteResult",
    "PreparedCloudContinuation",
    "PreparedCloudContinuationRequest",
    "prepare_inactive_cloud_continuation",
]
