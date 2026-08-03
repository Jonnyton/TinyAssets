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
import sqlite3
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

import rfc8785

from tinyassets.background_branch_authority import (
    BackgroundBranchAttempt,
    BackgroundBranchAttemptFence,
    BackgroundBranchAttemptLifecycle,
    BackgroundBranchAuthorityWriteOutcome,
    BackgroundBranchBindingStatus,
    BackgroundBranchExecutorAudience,
    BackgroundBranchExecutorClass,
    BackgroundBranchOperation,
    BackgroundBranchReceiptRefs,
    BackgroundBranchSourceKind,
    BackgroundBranchTargetMode,
    build_request_task_attempt_key,
)
from tinyassets.background_branch_authority_service import (
    BackgroundBranchAttemptBoundaryState,
    BackgroundBranchAttemptClaimAction,
    BackgroundBranchAttemptClaimRequest,
    BackgroundBranchAttemptClaimResolution,
    BackgroundBranchAttemptClaimService,
    BackgroundBranchAttemptIssuanceRequest,
    BackgroundBranchAttemptIssuanceResolution,
    BackgroundBranchAttemptIssuanceService,
    BackgroundBranchAttemptPredecessorState,
)
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.provider_work_authority import (
    ProviderInvocationLaunchRequest,
    ProviderInvocationReservationRequest,
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkRoot,
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBindingState,
    ProviderWorkExecutionClaimRequest,
    ProviderWorkReceiptService,
)
from tinyassets.storage.automation_activations import (
    AutomationActivation,
    AutomationActivationExecutor,
    AutomationActivationState,
    AutomationActivationStore,
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


def _branch_execution_subject(
    definition: RepositorySpecWorkDefinition,
) -> ExecutionSubject:
    return ExecutionSubject(
        kind=ExecutionSubjectKind.BRANCH_VERSION,
        ref=definition.branch_version_id,
        digest=definition.branch_content_digest,
    )


def _continuation_execution_subject(
    continuation: PreparedCloudContinuation,
) -> ExecutionSubject:
    return ExecutionSubject(
        kind=ExecutionSubjectKind.BRANCH_VERSION,
        ref=continuation.branch_version_id,
        digest=continuation.branch_content_digest,
    )


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


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

    _FIELDS = frozenset(
        {
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
        }
    )

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
class AgentInvocationCloudContinuation:
    """Prepared canonical continuation for one admitted agent invocation."""

    schema_version: int
    work_item_kind: str
    continuation_id: str
    generation: int
    continuation_digest: str
    state: CloudContinuationState
    principal_id: str
    universe_id: str
    automation_id: str
    activation_epoch: int
    activation_lease_id: str
    execution_subject: ExecutionSubject
    command_id: str
    command_digest: str
    invocation_id: str
    invocation_generation: int
    invocation_digest: str
    provider_binding_id: str
    provider_binding_generation: int
    provider_binding_digest: str
    receipt_id: str
    receipt_digest: str
    claim_id: str
    claim_generation: int
    claim_digest: str
    reservation_id: str
    reservation_digest: str
    typed_input_digest: str
    max_tokens: int
    max_cost_microunits: int
    created_at: str
    updated_at: str

    _FIELDS = frozenset(
        {
            "schema_version",
            "work_item_kind",
            "continuation_id",
            "generation",
            "continuation_digest",
            "state",
            "principal_id",
            "universe_id",
            "automation_id",
            "activation_epoch",
            "activation_lease_id",
            "execution_subject",
            "command_id",
            "command_digest",
            "invocation_id",
            "invocation_generation",
            "invocation_digest",
            "provider_binding_id",
            "provider_binding_generation",
            "provider_binding_digest",
            "receipt_id",
            "receipt_digest",
            "claim_id",
            "claim_generation",
            "claim_digest",
            "reservation_id",
            "reservation_digest",
            "typed_input_digest",
            "max_tokens",
            "max_cost_microunits",
            "created_at",
            "updated_at",
        }
    )

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        if self.work_item_kind != "agent_invocation":
            raise ValueError("work_item_kind must be agent_invocation")
        if self.state is not CloudContinuationState.PREPARED:
            raise ValueError("agent continuation must be prepared")
        for name in (
            "continuation_id",
            "principal_id",
            "universe_id",
            "automation_id",
            "activation_lease_id",
            "command_id",
            "invocation_id",
            "provider_binding_id",
            "receipt_id",
            "claim_id",
            "reservation_id",
        ):
            _text(getattr(self, name), name)
        for name in (
            "generation",
            "activation_epoch",
            "invocation_generation",
            "provider_binding_generation",
            "claim_generation",
        ):
            _integer(getattr(self, name), name, minimum=1)
        for name in ("max_tokens", "max_cost_microunits"):
            _integer(getattr(self, name), name, minimum=0)
        if (
            not isinstance(self.execution_subject, ExecutionSubject)
            or self.execution_subject.kind
            is not ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST
        ):
            raise ValueError("execution_subject must be an agent runtime manifest")
        for name in (
            "continuation_digest",
            "command_digest",
            "invocation_digest",
            "provider_binding_digest",
            "receipt_digest",
            "claim_digest",
            "reservation_digest",
            "typed_input_digest",
        ):
            _digest(getattr(self, name), name)
        _timestamp_text(self.created_at, "created_at")
        _timestamp_text(self.updated_at, "updated_at")
        if self.continuation_digest != self.expected_digest():
            raise ValueError("continuation_digest does not match content")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "work_item_kind": self.work_item_kind,
            "continuation_id": self.continuation_id,
            "generation": self.generation,
            "continuation_digest": self.continuation_digest,
            "state": self.state.value,
            "principal_id": self.principal_id,
            "universe_id": self.universe_id,
            "automation_id": self.automation_id,
            "activation_epoch": self.activation_epoch,
            "activation_lease_id": self.activation_lease_id,
            "execution_subject": self.execution_subject.to_dict(),
            "command_id": self.command_id,
            "command_digest": self.command_digest,
            "invocation_id": self.invocation_id,
            "invocation_generation": self.invocation_generation,
            "invocation_digest": self.invocation_digest,
            "provider_binding_id": self.provider_binding_id,
            "provider_binding_generation": self.provider_binding_generation,
            "provider_binding_digest": self.provider_binding_digest,
            "receipt_id": self.receipt_id,
            "receipt_digest": self.receipt_digest,
            "claim_id": self.claim_id,
            "claim_generation": self.claim_generation,
            "claim_digest": self.claim_digest,
            "reservation_id": self.reservation_id,
            "reservation_digest": self.reservation_digest,
            "typed_input_digest": self.typed_input_digest,
            "max_tokens": self.max_tokens,
            "max_cost_microunits": self.max_cost_microunits,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def build(cls, **values: Any) -> AgentInvocationCloudContinuation:
        if "continuation_digest" in values:
            raise ValueError("continuation_digest is server-computed")
        provisional = object.__new__(cls)
        for name in cls._FIELDS - {"continuation_digest"}:
            if name not in values:
                raise ValueError(f"missing {name}")
            object.__setattr__(provisional, name, values[name])
        if set(values) != cls._FIELDS - {"continuation_digest"}:
            raise ValueError("agent continuation fields do not match schema")
        object.__setattr__(
            provisional,
            "continuation_digest",
            f"sha256:{'0' * 64}",
        )
        object.__setattr__(provisional, "continuation_digest", provisional.expected_digest())
        provisional.__post_init__()
        return provisional

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AgentInvocationCloudContinuation:
        if not isinstance(value, dict) or set(value) != cls._FIELDS:
            raise ValueError("agent continuation fields do not match schema")
        payload = dict(value)
        payload["state"] = CloudContinuationState(payload["state"])
        payload["execution_subject"] = ExecutionSubject.from_dict(
            payload["execution_subject"]
        )
        return cls(**payload)

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["continuation_digest"]
        return _content_digest(payload)

    def matches_preparation(self, other: AgentInvocationCloudContinuation) -> bool:
        if not isinstance(other, AgentInvocationCloudContinuation):
            return False
        left = self.to_dict()
        right = other.to_dict()
        for payload in (left, right):
            del payload["continuation_digest"]
            del payload["created_at"]
            del payload["updated_at"]
        return left == right

    def matches_armed_reconciliation(
        self,
        other: AgentInvocationCloudContinuation,
    ) -> bool:
        """Match immutable lineage after the reservation advances to launch-started."""
        if not isinstance(other, AgentInvocationCloudContinuation):
            return False
        left = self.to_dict()
        right = other.to_dict()
        for payload in (left, right):
            del payload["continuation_digest"]
            del payload["reservation_digest"]
            del payload["created_at"]
            del payload["updated_at"]
        return left == right


@dataclass(frozen=True, slots=True)
class CloudContinuationWriteResult:
    outcome: CloudContinuationWriteOutcome
    record: PreparedCloudContinuation | AgentInvocationCloudContinuation | None


class CloudContinuationPreparationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class CloudContinuationActivationRequest:
    """Server-selected identity for one stopped-to-cloud activation epoch."""

    lease_id: str

    def __post_init__(self) -> None:
        _text(self.lease_id, "lease_id")


@dataclass(frozen=True, slots=True)
class CloudContinuationActivationResult:
    """Converged dark runtime owners; this result grants no execution."""

    activation: AutomationActivation
    request_id: str
    admission_id: str
    branch_task_id: str
    admission_replayed: bool
    attempt: BackgroundBranchAttempt
    attempt_outcome: BackgroundBranchAuthorityWriteOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.activation, AutomationActivation):
            raise ValueError("activation must be typed")
        for name in ("request_id", "admission_id", "branch_task_id"):
            _text(getattr(self, name), name)
        if not isinstance(self.admission_replayed, bool):
            raise ValueError("admission_replayed must be boolean")
        if not isinstance(self.attempt, BackgroundBranchAttempt):
            raise ValueError("attempt must be typed")
        if not isinstance(
            self.attempt_outcome,
            BackgroundBranchAuthorityWriteOutcome,
        ):
            raise ValueError("attempt_outcome must be typed")


class CloudContinuationActivationError(ValueError):
    """Stable fail-closed result for dark cloud runtime composition."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@runtime_checkable
class CloudContinuationAttemptAudienceResolver(Protocol):
    """Trusted server adapter for the worker assigned to one epoch-2 task."""

    def resolve(
        self,
        *,
        continuation: PreparedCloudContinuation,
        branch_task_id: str,
    ) -> BackgroundBranchExecutorAudience | None:
        """Return the current server-owned audience, or no assignment."""


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
        continuation_id=("cloud_cont_" + _content_digest(identity).removeprefix("sha256:")[:32]),
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
    control_paths = {Path(store.base_path).resolve() for store, _expected in stores}
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
        background.permitted_executor_classes == (BackgroundBranchExecutorClass.CLOUD,),
        background.max_attempts <= definition.max_attempts,
        0 < background.remaining_count <= definition.max_attempts,
        0 < background.remaining_cost_microunits <= definition.max_cost_microunits,
    )
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    if background.expires_at is not None:
        expires_at = datetime.fromisoformat(background.expires_at.removesuffix("Z") + "+00:00")
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


class PreparedCloudContinuationAttemptResolver:
    """Bind one current epoch-2 task to one background-attempt reservation.

    The caller supplies only non-authorizing task and attempt references. This
    adapter rereads the prepared continuation, active cloud epoch, exact queue
    task, background binding, and server-selected worker before the background
    authority owner may reserve an attempt.
    """

    def __init__(
        self,
        definition: RepositorySpecWorkDefinition | None,
        *,
        continuation: PreparedCloudContinuation,
        admission: Mapping[str, object],
        activation_store: Any,
        background_store: Any,
        continuation_store: Any,
        request_admission_store: Any,
        audience_resolver: CloudContinuationAttemptAudienceResolver,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        from tinyassets.storage.automation_activations import (
            AutomationActivationStore,
        )
        from tinyassets.storage.background_branch_authority import (
            SQLiteBackgroundBranchAuthorityStore,
        )
        from tinyassets.storage.cloud_automation_continuation import (
            SQLiteCloudAutomationContinuationStore,
        )
        from tinyassets.storage.request_admissions import RequestAdmissionStore

        if definition is not None and not isinstance(
            definition,
            RepositorySpecWorkDefinition,
        ):
            raise ValueError("definition must be a RepositorySpecWorkDefinition or None")
        if not isinstance(continuation, PreparedCloudContinuation):
            raise ValueError("continuation must be a PreparedCloudContinuation")
        if not isinstance(admission, Mapping):
            raise ValueError("admission must be a mapping")
        stores = (
            (activation_store, AutomationActivationStore),
            (background_store, SQLiteBackgroundBranchAuthorityStore),
            (continuation_store, SQLiteCloudAutomationContinuationStore),
            (request_admission_store, RequestAdmissionStore),
        )
        if any(not isinstance(store, expected) for store, expected in stores):
            raise ValueError("cloud attempt resolver requires canonical stores")
        if len({Path(store.base_path).resolve() for store, _expected in stores}) != 1:
            raise ValueError("cloud attempt resolver stores must share one control plane")
        if not isinstance(
            audience_resolver,
            CloudContinuationAttemptAudienceResolver,
        ):
            raise ValueError(
                "audience_resolver must implement CloudContinuationAttemptAudienceResolver"
            )
        if (
            definition is not None
            and continuation.definition_digest != definition.definition_digest
        ):
            raise ValueError("continuation does not match the immutable definition")
        self._definition = definition
        self._continuation = continuation
        self._admission_id = _text(admission.get("admission_id"), "admission_id")
        self._request_id = _text(admission.get("request_id"), "request_id")
        self._branch_task_id = _text(
            admission.get("branch_task_id"),
            "branch_task_id",
        )
        self._activation_store = activation_store
        self._background_store = background_store
        self._continuation_store = continuation_store
        self._request_admission_store = request_admission_store
        self._audience_resolver = audience_resolver
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve(
        self,
        request: BackgroundBranchAttemptIssuanceRequest,
    ) -> BackgroundBranchAttemptIssuanceResolution | None:
        if not isinstance(request, BackgroundBranchAttemptIssuanceRequest):
            raise ValueError("request must be a BackgroundBranchAttemptIssuanceRequest")
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        resolved_at = (
            now.astimezone(timezone.utc)
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        )
        continuation = self._continuation
        definition = self._definition
        if definition is None:
            return None
        try:
            current_continuation = self._continuation_store.get(
                universe_id=continuation.universe_id,
                automation_id=continuation.automation_id,
            )
            activation = self._activation_store.get(
                continuation.universe_id,
                continuation.automation_id,
            )
            binding = self._background_store.get_binding(continuation.background_binding_id)
            with self._request_admission_store.connection() as conn:
                task = conn.execute(
                    """
                    SELECT
                        a.tenant_id, a.actor_id, a.universe_id,
                        a.body_digest, a.grant_generation,
                        t.branch_task_id, t.admission_id, t.request_id,
                        t.branch_def_id, t.directed_daemon_id,
                        t.automation_id, t.automation_activation_epoch,
                        t.automation_executor_class,
                        t.automation_branch_version,
                        t.automation_lease_id, t.status,
                        t.queue_epoch, t.protocol_version
                    FROM request_admissions AS a
                    JOIN branch_tasks_v2 AS t
                      ON t.admission_id = a.admission_id
                     AND t.request_id = a.request_id
                     AND t.branch_task_id = a.branch_task_id
                    WHERE a.admission_id = ?
                      AND a.request_id = ?
                      AND a.branch_task_id = ?
                    LIMIT 1
                    """,
                    (
                        self._admission_id,
                        self._request_id,
                        self._branch_task_id,
                    ),
                ).fetchone()
            audience = self._audience_resolver.resolve(
                continuation=continuation,
                branch_task_id=self._branch_task_id,
            )
        except (OSError, sqlite3.Error, ValueError):
            return None
        if any(
            value is None
            for value in (
                current_continuation,
                activation,
                binding,
                task,
                audience,
            )
        ):
            return None
        assert current_continuation is not None
        assert activation is not None
        assert binding is not None
        assert task is not None
        assert isinstance(audience, BackgroundBranchExecutorAudience)
        try:
            expected_logical_key = build_request_task_attempt_key(
                tenant_id=str(task["tenant_id"]),
                request_id=str(task["request_id"]),
                admission_id=str(task["admission_id"]),
                task_id=str(task["branch_task_id"]),
                body_digest=str(task["body_digest"]),
                admission_generation=int(task["grant_generation"]),
            )
            source_generation = int(binding.source_revision)
            binding_expiry = (
                datetime.fromisoformat(binding.expires_at.removesuffix("Z") + "+00:00")
                if binding.expires_at is not None
                else None
            )
        except (TypeError, ValueError):
            return None
        exact = (
            current_continuation == continuation,
            continuation.state is CloudContinuationState.PREPARED,
            continuation.principal_id == definition.principal_id,
            continuation.universe_id == definition.universe_id,
            continuation.branch_def_id == definition.branch_def_id,
            continuation.branch_version_id == definition.branch_version_id,
            continuation.branch_content_digest == definition.branch_content_digest,
            activation.state is AutomationActivationState.ACTIVE,
            activation.executor_class is AutomationActivationExecutor.CLOUD,
            activation.epoch == continuation.activation_epoch + 1,
            activation.subject == _branch_execution_subject(definition),
            task["tenant_id"] == definition.principal_id,
            task["actor_id"] == definition.principal_id,
            task["universe_id"] == definition.universe_id,
            task["branch_def_id"] == definition.branch_def_id,
            task["directed_daemon_id"] == audience.daemon_id,
            task["automation_id"] == continuation.automation_id,
            task["automation_activation_epoch"] == activation.epoch,
            task["automation_executor_class"] == "cloud",
            task["automation_branch_version"] == definition.branch_version_id,
            task["automation_lease_id"] == activation.lease_id,
            task["status"] == "pending",
            task["queue_epoch"] == 2,
            task["protocol_version"] == 2,
            binding.status is BackgroundBranchBindingStatus.ACTIVE,
            binding.binding_id == continuation.background_binding_id,
            binding.generation == continuation.background_binding_generation,
            binding.binding_digest == continuation.background_binding_digest,
            binding.authorizing_principal_id == definition.principal_id,
            binding.universe_id == definition.universe_id,
            binding.branch_def_id == definition.branch_def_id,
            binding.operation is BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
            binding.source_kind is BackgroundBranchSourceKind.REQUEST_ADMISSION,
            binding.source_id == self._request_id,
            binding.source_revision == str(task["grant_generation"]),
            binding.target_mode is BackgroundBranchTargetMode.PINNED_VERSION,
            binding.pinned_branch_version_id == definition.branch_version_id,
            binding.permitted_executor_classes == (BackgroundBranchExecutorClass.CLOUD,),
            binding.max_attempts <= definition.max_attempts,
            0 < binding.remaining_count <= definition.max_attempts,
            binding.remaining_cost_microunits >= definition.max_cost_microunits,
            binding_expiry is None or binding_expiry > now.astimezone(timezone.utc),
            request.binding_id == binding.binding_id,
            request.binding_generation == binding.generation,
            request.binding_digest == binding.binding_digest,
            request.logical_attempt_key == expected_logical_key,
            request.physical_universe_id == definition.universe_id,
            request.executor_audience == audience,
        )
        if not all(exact):
            return None
        return BackgroundBranchAttemptIssuanceResolution(
            binding=binding,
            branch_version_id=definition.branch_version_id,
            branch_content_digest=definition.branch_content_digest,
            source_generation=source_generation,
            executor_audience=audience,
            resolved_at=resolved_at,
            parent_attempt_id=None,
            origin_attempt_id=None,
            audit_correlation_ids=(
                f"audit:continuation:{continuation.continuation_id}",
                f"task:{self._branch_task_id}",
            ),
            receipt_refs=BackgroundBranchReceiptRefs(
                b2_execution_grant_id=None,
                provider_work_receipt_id=None,
                provider_attempt_receipt_id=None,
                payment_receipt_id=None,
                effect_receipt_id=None,
            ),
        )


class PreparedCloudContinuationActivationService:
    """Converge prepared authority into one dark epoch-2 runtime lane.

    Every step is independently durable. A restart accepts only the exact
    activation epoch and lease requested by the original invocation, replays
    the admission by a server-derived idempotency identity, and replays the
    same logical background attempt. The epoch-2 consumer remains dark.
    """

    _REQUEST_TEXT = "Continue the accepted repository specification."
    _POLICY_VERSION = "operator-priority-v1"
    _TRIGGER_SOURCE = "owner_queued"
    _PRIORITY_WEIGHT = 100

    def __init__(
        self,
        definition: RepositorySpecWorkDefinition,
        *,
        continuation: PreparedCloudContinuation,
        activation_store: Any,
        background_store: Any,
        provider_store: Any,
        connection_ledger: Any,
        continuation_store: Any,
        request_admission_store: Any,
        audience_resolver: CloudContinuationAttemptAudienceResolver,
        clock: Callable[[], datetime] | None = None,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
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
        from tinyassets.storage.request_admissions import RequestAdmissionStore

        if not isinstance(definition, RepositorySpecWorkDefinition):
            raise ValueError("definition must be a RepositorySpecWorkDefinition")
        if not isinstance(continuation, PreparedCloudContinuation):
            raise ValueError("continuation must be a PreparedCloudContinuation")
        stores = (
            (activation_store, AutomationActivationStore),
            (background_store, SQLiteBackgroundBranchAuthorityStore),
            (provider_store, SQLiteProviderWorkAuthorityStore),
            (continuation_store, SQLiteCloudAutomationContinuationStore),
            (request_admission_store, RequestAdmissionStore),
        )
        if any(not isinstance(store, expected) for store, expected in stores):
            raise ValueError("cloud activation service requires canonical stores")
        if not isinstance(connection_ledger, ConnectionLedger):
            raise ValueError("connection_ledger must be a ConnectionLedger")
        if len({Path(store.base_path).resolve() for store, _expected in stores}) != 1:
            raise ValueError("cloud activation stores must share one control plane")
        if not isinstance(audience_resolver, CloudContinuationAttemptAudienceResolver):
            raise ValueError(
                "audience_resolver must implement CloudContinuationAttemptAudienceResolver"
            )
        if continuation.definition_digest != definition.definition_digest:
            raise ValueError("continuation does not match the immutable definition")
        self._definition = definition
        self._continuation = continuation
        self._activation_store = activation_store
        self._background_store = background_store
        self._provider_store = provider_store
        self._connection_ledger = connection_ledger
        self._continuation_store = continuation_store
        self._request_admission_store = request_admission_store
        self._audience_resolver = audience_resolver
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._fault_injector = fault_injector

    def activate(
        self,
        request: CloudContinuationActivationRequest,
    ) -> CloudContinuationActivationResult:
        from tinyassets.daemon_registry import get_daemon
        from tinyassets.storage.request_admissions import RequestAdmissionStore

        if not isinstance(request, CloudContinuationActivationRequest):
            raise ValueError("request must be a CloudContinuationActivationRequest")
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        continuation = self._continuation
        definition = self._definition
        current_continuation = self._continuation_store.get(
            universe_id=continuation.universe_id,
            automation_id=continuation.automation_id,
        )
        binding = self._background_store.get_binding(continuation.background_binding_id)
        if current_continuation != continuation or binding is None:
            self._fail(
                "continuation_authority_changed",
                "prepared continuation or background binding is no longer current",
            )
        assert binding is not None
        try:
            authority = resolve_inactive_cloud_authority(
                definition,
                provider_store=self._provider_store,
                connection_ledger=self._connection_ledger,
            )
        except AutomationAdmissionError as exc:
            self._fail(exc.code, str(exc))
        binding_expiry = (
            datetime.fromisoformat(binding.expires_at.removesuffix("Z") + "+00:00")
            if binding.expires_at is not None
            else None
        )
        exact_authority = (
            authority.provider_binding_id == continuation.provider_binding_id,
            authority.provider_binding_generation == continuation.provider_binding_generation,
            authority.provider_binding_digest == continuation.provider_binding_digest,
            authority.destination_grant_id == continuation.destination_grant_id,
            authority.destination_connection_id == continuation.destination_connection_id,
            authority.destination == continuation.destination,
        )
        exact_binding = (
            binding.status is BackgroundBranchBindingStatus.ACTIVE,
            binding.generation == continuation.background_binding_generation,
            binding.binding_digest == continuation.background_binding_digest,
            binding.authorizing_principal_id == definition.principal_id,
            binding.universe_id == definition.universe_id,
            binding.branch_def_id == definition.branch_def_id,
            binding.operation is BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
            binding.source_kind is BackgroundBranchSourceKind.REQUEST_ADMISSION,
            binding.source_id.startswith("req_"),
            binding.target_mode is BackgroundBranchTargetMode.PINNED_VERSION,
            binding.pinned_branch_version_id == definition.branch_version_id,
            binding.permitted_executor_classes == (BackgroundBranchExecutorClass.CLOUD,),
            binding.daemon_id is not None,
            binding.max_attempts <= definition.max_attempts,
            0 < binding.remaining_count <= definition.max_attempts,
            binding.remaining_cost_microunits >= definition.max_cost_microunits,
            binding_expiry is None or binding_expiry > now.astimezone(timezone.utc),
        )
        if not all((*exact_authority, *exact_binding)):
            self._fail(
                "continuation_authority_changed",
                "current authority no longer matches the prepared continuation",
            )
        try:
            grant_generation = int(binding.source_revision)
        except (TypeError, ValueError):
            self._fail(
                "binding_source_generation_invalid",
                "background binding source revision is not an admission generation",
            )
        if grant_generation < 1:
            self._fail(
                "binding_source_generation_invalid",
                "background binding source revision must be positive",
            )

        assert binding.daemon_id is not None
        try:
            daemon = get_daemon(
                self._request_admission_store.base_path,
                daemon_id=binding.daemon_id,
            )
        except (KeyError, LookupError, OSError, RuntimeError, ValueError) as exc:
            raise CloudContinuationActivationError(
                "directed_daemon_unavailable",
                "the server-selected daemon is missing or unreadable",
            ) from exc
        if not (
            daemon.get("daemon_id") == binding.daemon_id
            and daemon.get("owner_user_id") == definition.principal_id
            and daemon.get("tenant_id") == definition.principal_id
            and isinstance(daemon.get("soul_hash"), str)
            and bool(str(daemon["soul_hash"]))
        ):
            self._fail(
                "directed_daemon_mismatch",
                "server-selected daemon does not belong to the automation principal",
            )

        body = {
            "branch_id": definition.branch_def_id,
            "directed_daemon_id": binding.daemon_id,
            "directed_daemon_instruction": "",
            "pickup_incentive": "",
            "priority_weight": self._PRIORITY_WEIGHT,
            "request_type": "run_branch",
            "schema_version": "request-admission-v2",
            "text": self._REQUEST_TEXT,
            "universe_id": definition.universe_id,
        }
        body_digest = f"sha256:{hashlib.sha256(rfc8785.dumps(body)).hexdigest()}"
        if binding.source_digest != body_digest:
            self._fail(
                "binding_source_digest_mismatch",
                "background binding does not authorize the canonical admission body",
            )

        activation = self._converge_activation(request)
        self._inject("activation_committed")
        identifier_seed = {
            "schema_version": 1,
            "continuation_id": continuation.continuation_id,
            "continuation_generation": continuation.generation,
            "activation_epoch": activation.epoch,
            "activation_lease_id": activation.lease_id,
        }
        ids = {
            "req": binding.source_id,
            **{
                prefix: self._derived_id(prefix, identifier_seed)
                for prefix in ("adm", "bt2", "evt")
            },
        }
        admission_store = RequestAdmissionStore(
            self._request_admission_store.base_path,
            id_factory=lambda prefix: ids[prefix],
            clock=self._clock,
        )
        admission = admission_store.commit_admission(
            tenant_id=definition.principal_id,
            actor_id=definition.principal_id,
            universe_id=definition.universe_id,
            idempotency_key_hash=_content_digest(
                {
                    "domain": "cloud-continuation-admission-v1",
                    **identifier_seed,
                }
            ),
            body_digest=body_digest,
            body_digest_version="rfc8785-v1",
            request_type="run_branch",
            text=self._REQUEST_TEXT,
            branch_id=definition.branch_def_id,
            branch_def_id=definition.branch_def_id,
            trigger_source=self._TRIGGER_SOURCE,
            accepted_priority_weight=self._PRIORITY_WEIGHT,
            policy_version=self._POLICY_VERSION,
            grant_generation=grant_generation,
            receipt={
                "authority": "request-local",
                "branch_def_id": definition.branch_def_id,
                "continuation_id": continuation.continuation_id,
                "grant_generation": grant_generation,
                "priority_policy_version": self._POLICY_VERSION,
                "directed_assignment": {
                    "daemon_id": binding.daemon_id,
                    "daemon_soul_hash": str(daemon["soul_hash"]),
                    "authority_scope": "owner",
                },
            },
            directed_daemon_id=binding.daemon_id,
            created_at=_timestamp(now),
            automation_activation=activation,
        )
        if admission.get("request_id") != binding.source_id:
            self._fail(
                "admission_source_mismatch",
                "idempotent admission does not match the prepared source identity",
            )
        self._inject("admission_committed")

        audience = self._audience_resolver.resolve(
            continuation=continuation,
            branch_task_id=str(admission["branch_task_id"]),
        )
        if not (
            isinstance(audience, BackgroundBranchExecutorAudience)
            and audience.executor_class is BackgroundBranchExecutorClass.CLOUD
            and audience.daemon_id == binding.daemon_id
        ):
            self._fail(
                "executor_audience_unavailable",
                "trusted cloud worker assignment is absent or mismatched",
            )
        logical_attempt_key = build_request_task_attempt_key(
            tenant_id=definition.principal_id,
            request_id=str(admission["request_id"]),
            admission_id=str(admission["admission_id"]),
            task_id=str(admission["branch_task_id"]),
            body_digest=body_digest,
            admission_generation=grant_generation,
        )
        resolver = PreparedCloudContinuationAttemptResolver(
            definition,
            continuation=continuation,
            admission={**admission, "body_digest": body_digest},
            activation_store=self._activation_store,
            background_store=self._background_store,
            continuation_store=self._continuation_store,
            request_admission_store=admission_store,
            audience_resolver=self._audience_resolver,
            clock=self._clock,
        )
        attempt_result = BackgroundBranchAttemptIssuanceService(
            self._background_store,
            resolver,
        ).issue(
            BackgroundBranchAttemptIssuanceRequest(
                binding_id=binding.binding_id,
                binding_generation=binding.generation,
                binding_digest=binding.binding_digest,
                logical_attempt_key=logical_attempt_key,
                physical_universe_id=definition.universe_id,
                executor_audience=audience,
            )
        )
        if attempt_result.record is None:
            self._fail(
                "background_attempt_missing",
                "background attempt reservation did not produce a record",
            )
        self._inject("attempt_committed")
        assert attempt_result.record is not None
        return CloudContinuationActivationResult(
            activation=activation,
            request_id=str(admission["request_id"]),
            admission_id=str(admission["admission_id"]),
            branch_task_id=str(admission["branch_task_id"]),
            admission_replayed=bool(admission["idempotent_replay"]),
            attempt=attempt_result.record,
            attempt_outcome=attempt_result.outcome,
        )

    def _converge_activation(
        self,
        request: CloudContinuationActivationRequest,
    ) -> AutomationActivation:
        continuation = self._continuation
        current = self._activation_store.get(
            continuation.universe_id,
            continuation.automation_id,
        )
        if current is None:
            self._fail("activation_missing", "automation activation is missing")
        assert current is not None
        if (
            current.state is AutomationActivationState.STOPPED
            and current.epoch == continuation.activation_epoch
        ):
            activated = self._activation_store.activate(
                expected=current,
                executor_class=AutomationActivationExecutor.CLOUD,
                subject=_branch_execution_subject(self._definition),
                lease_id=request.lease_id,
            )
            current = activated or self._activation_store.get(
                continuation.universe_id,
                continuation.automation_id,
            )
        exact = (
            current is not None,
            current is not None and current.state is AutomationActivationState.ACTIVE,
            current is not None and current.executor_class is AutomationActivationExecutor.CLOUD,
            current is not None and current.epoch == continuation.activation_epoch + 1,
            current is not None and current.subject == _branch_execution_subject(self._definition),
            current is not None and current.lease_id == request.lease_id,
        )
        if not all(exact):
            self._fail(
                "activation_conflict",
                "current activation does not match the requested cloud epoch",
            )
        assert current is not None
        return current

    def _inject(self, phase: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(phase)

    @staticmethod
    def _derived_id(prefix: str, seed: Mapping[str, object]) -> str:
        identity = {"domain": f"cloud-continuation-{prefix}-v1", **seed}
        return f"{prefix}_{_content_digest(identity).removeprefix('sha256:')[:32]}"

    @staticmethod
    def _fail(code: str, detail: str) -> None:
        raise CloudContinuationActivationError(code, detail)


class PreparedCloudContinuationClaimResolver(PreparedCloudContinuationAttemptResolver):
    """Bind one reserved attempt to its exact claimed epoch-2 task custody."""

    def resolve(
        self,
        request: BackgroundBranchAttemptClaimRequest,
    ) -> BackgroundBranchAttemptClaimResolution | None:
        if not isinstance(request, BackgroundBranchAttemptClaimRequest):
            raise ValueError("request must be a BackgroundBranchAttemptClaimRequest")
        if request.action is not BackgroundBranchAttemptClaimAction.CLAIM:
            return None
        requested_lease = request.requested_lease_expires_at
        if requested_lease is None:
            return None
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        now = now.astimezone(timezone.utc)
        continuation = self._continuation
        definition = self._definition
        definition_exact = definition is None or (
            continuation.definition_digest == definition.definition_digest
            and continuation.principal_id == definition.principal_id
            and continuation.universe_id == definition.universe_id
            and continuation.branch_def_id == definition.branch_def_id
            and continuation.branch_version_id == definition.branch_version_id
            and continuation.branch_content_digest == definition.branch_content_digest
        )
        attempt = request.attempt
        try:
            current_continuation = self._continuation_store.get(
                universe_id=continuation.universe_id,
                automation_id=continuation.automation_id,
            )
            activation = self._activation_store.get(
                continuation.universe_id,
                continuation.automation_id,
            )
            binding = self._background_store.get_binding(continuation.background_binding_id)
            with self._request_admission_store.connection() as conn:
                task = conn.execute(
                    """
                    SELECT
                        a.tenant_id, a.actor_id, a.universe_id,
                        a.body_digest, a.grant_generation,
                        t.branch_task_id, t.admission_id, t.request_id,
                        t.branch_def_id, t.directed_daemon_id,
                        t.automation_id, t.automation_activation_epoch,
                        t.automation_executor_class,
                        t.automation_branch_version,
                        t.automation_lease_id, t.status,
                        t.queue_epoch, t.protocol_version,
                        t.claimed_by, t.claimed_at, t.heartbeat_at,
                        t.lease_expires_at, t.disabled
                    FROM request_admissions AS a
                    JOIN branch_tasks_v2 AS t
                      ON t.admission_id = a.admission_id
                     AND t.request_id = a.request_id
                     AND t.branch_task_id = a.branch_task_id
                    WHERE a.admission_id = ?
                      AND a.request_id = ?
                      AND a.branch_task_id = ?
                    LIMIT 1
                    """,
                    (
                        self._admission_id,
                        self._request_id,
                        self._branch_task_id,
                    ),
                ).fetchone()
            audience = self._audience_resolver.resolve(
                continuation=continuation,
                branch_task_id=self._branch_task_id,
            )
        except (OSError, sqlite3.Error, ValueError):
            return None
        if any(
            value is None
            for value in (
                current_continuation,
                activation,
                binding,
                task,
                audience,
            )
        ):
            return None
        assert current_continuation is not None
        assert activation is not None
        assert binding is not None
        assert task is not None
        assert isinstance(audience, BackgroundBranchExecutorAudience)
        try:
            claimed_at = datetime.fromisoformat(str(task["claimed_at"]))
            heartbeat_at = datetime.fromisoformat(str(task["heartbeat_at"]))
            task_lease = datetime.fromisoformat(str(task["lease_expires_at"]))
            transitioned_at = datetime.fromisoformat(
                request.transitioned_at.removesuffix("Z") + "+00:00"
            )
            requested_lease_at = datetime.fromisoformat(
                requested_lease.removesuffix("Z") + "+00:00"
            )
            expected_logical_key = build_request_task_attempt_key(
                tenant_id=str(task["tenant_id"]),
                request_id=str(task["request_id"]),
                admission_id=str(task["admission_id"]),
                task_id=str(task["branch_task_id"]),
                body_digest=str(task["body_digest"]),
                admission_generation=int(task["grant_generation"]),
            )
            source_generation = int(binding.source_revision)
        except (TypeError, ValueError):
            return None
        claimed_at = claimed_at.astimezone(timezone.utc)
        heartbeat_at = heartbeat_at.astimezone(timezone.utc)
        task_lease = task_lease.astimezone(timezone.utc)
        exact = (
            definition_exact,
            current_continuation == continuation,
            continuation.state is CloudContinuationState.PREPARED,
            activation.state is AutomationActivationState.ACTIVE,
            activation.executor_class is AutomationActivationExecutor.CLOUD,
            activation.epoch == continuation.activation_epoch + 1,
            activation.subject == _continuation_execution_subject(continuation),
            task["tenant_id"] == continuation.principal_id,
            task["actor_id"] == continuation.principal_id,
            task["universe_id"] == continuation.universe_id,
            task["branch_def_id"] == continuation.branch_def_id,
            task["directed_daemon_id"] == audience.daemon_id,
            task["automation_id"] == continuation.automation_id,
            task["automation_activation_epoch"] == activation.epoch,
            task["automation_executor_class"] == "cloud",
            task["automation_branch_version"] == continuation.branch_version_id,
            task["automation_lease_id"] == activation.lease_id,
            task["status"] == "running",
            task["queue_epoch"] == 2,
            task["protocol_version"] == 2,
            task["disabled"] == 0,
            task["claimed_by"] == audience.worker_id,
            claimed_at == transitioned_at,
            heartbeat_at == claimed_at,
            task_lease == requested_lease_at,
            task_lease > now,
            binding.status is BackgroundBranchBindingStatus.ACTIVE,
            binding.binding_id == continuation.background_binding_id,
            binding.generation == continuation.background_binding_generation,
            binding.binding_digest == continuation.background_binding_digest,
            binding.authorizing_principal_id == continuation.principal_id,
            binding.universe_id == continuation.universe_id,
            binding.branch_def_id == continuation.branch_def_id,
            binding.operation is BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
            binding.source_kind is BackgroundBranchSourceKind.REQUEST_ADMISSION,
            binding.source_id == self._request_id,
            binding.source_revision == str(task["grant_generation"]),
            binding.target_mode is BackgroundBranchTargetMode.PINNED_VERSION,
            binding.pinned_branch_version_id == continuation.branch_version_id,
            binding.permitted_executor_classes == (BackgroundBranchExecutorClass.CLOUD,),
            attempt.lifecycle is BackgroundBranchAttemptLifecycle.RESERVED,
            attempt.binding_id == binding.binding_id,
            attempt.binding_generation == binding.generation,
            attempt.binding_digest == binding.binding_digest,
            attempt.logical_attempt_key == expected_logical_key,
            attempt.authorizing_principal_id == continuation.principal_id,
            attempt.universe_id == continuation.universe_id,
            attempt.branch_def_id == continuation.branch_def_id,
            attempt.branch_version_id == continuation.branch_version_id,
            attempt.branch_content_digest == continuation.branch_content_digest,
            attempt.operation is BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
            attempt.source_kind is BackgroundBranchSourceKind.REQUEST_ADMISSION,
            attempt.source_id == self._request_id,
            attempt.source_generation == source_generation,
            attempt.executor_audience == audience,
            request.requested_audience == audience,
        )
        if not all(exact):
            return None
        return BackgroundBranchAttemptClaimResolution(
            binding=binding,
            executor_audience=audience,
            predecessor=BackgroundBranchAttemptPredecessorState.UNKNOWN,
            boundary=BackgroundBranchAttemptBoundaryState.NOT_CROSSED,
            resolved_at=request.transitioned_at,
        )


class PreparedCloudContinuationProviderResolver:
    """Resolve one claimed background attempt into non-bearer provider facts.

    The returned authority is intentionally transient. Receipt persistence
    revalidates the provider binding transactionally, and a later launch owner
    must revalidate activation, attempt, assignment, and credential custody
    again before provider access.
    """

    def __init__(
        self,
        definition: RepositorySpecWorkDefinition | None,
        *,
        continuation: PreparedCloudContinuation,
        activation_store: Any,
        background_store: Any,
        provider_store: Any,
        continuation_store: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        from tinyassets.storage.automation_activations import (
            AutomationActivationStore,
        )
        from tinyassets.storage.background_branch_authority import (
            SQLiteBackgroundBranchAuthorityStore,
        )
        from tinyassets.storage.cloud_automation_continuation import (
            SQLiteCloudAutomationContinuationStore,
        )
        from tinyassets.storage.provider_work_authority import (
            SQLiteProviderWorkAuthorityStore,
        )

        if definition is not None and not isinstance(
            definition,
            RepositorySpecWorkDefinition,
        ):
            raise ValueError("definition must be a RepositorySpecWorkDefinition or None")
        if not isinstance(continuation, PreparedCloudContinuation):
            raise ValueError("continuation must be a PreparedCloudContinuation")
        stores = (
            (activation_store, AutomationActivationStore),
            (background_store, SQLiteBackgroundBranchAuthorityStore),
            (provider_store, SQLiteProviderWorkAuthorityStore),
            (continuation_store, SQLiteCloudAutomationContinuationStore),
        )
        if any(not isinstance(store, expected) for store, expected in stores):
            raise ValueError("cloud provider resolver requires canonical stores")
        if len({Path(store.base_path).resolve() for store, _expected in stores}) != 1:
            raise ValueError("cloud provider resolver stores must share one control plane")
        if (
            definition is not None
            and continuation.definition_digest != definition.definition_digest
        ):
            raise ValueError("continuation does not match the immutable definition")
        self._definition = definition
        self._continuation = continuation
        self._activation_store = activation_store
        self._background_store = background_store
        self._provider_store = provider_store
        self._continuation_store = continuation_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve(
        self,
        root: ProviderUniverseWorkRoot,
    ) -> ProviderUniverseWorkAuthority | None:
        if not isinstance(root, ProviderUniverseWorkRoot):
            raise ValueError("root must be a ProviderUniverseWorkRoot")
        if root.work_item_kind != "background_attempt":
            return None
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        now = now.astimezone(timezone.utc)
        definition = self._definition
        continuation = self._continuation

        try:
            current_continuation = self._continuation_store.get(
                universe_id=continuation.universe_id,
                automation_id=continuation.automation_id,
            )
            activation = self._activation_store.get(
                continuation.universe_id,
                continuation.automation_id,
            )
            attempt = self._background_store.get_attempt(root.work_item_id)
            background = self._background_store.get_binding(continuation.background_binding_id)
            provider = self._provider_store.get(continuation.provider_binding_id)
        except (OSError, ValueError):
            return None
        if any(
            value is None
            for value in (
                current_continuation,
                activation,
                attempt,
                background,
                provider,
            )
        ):
            return None
        assert current_continuation is not None
        assert activation is not None
        assert attempt is not None
        assert background is not None
        assert provider is not None

        definition_exact = definition is None or (
            continuation.definition_digest == definition.definition_digest
            and continuation.principal_id == definition.principal_id
            and continuation.universe_id == definition.universe_id
            and continuation.branch_def_id == definition.branch_def_id
            and continuation.branch_version_id == definition.branch_version_id
            and continuation.branch_content_digest == definition.branch_content_digest
            and provider.max_invocations == definition.max_attempts
            and provider.max_tokens == definition.max_tokens
            and provider.max_cost_microunits == definition.max_cost_microunits
        )
        max_invocations = (
            definition.max_attempts
            if definition is not None
            else min(provider.max_invocations, attempt.remaining_count)
        )
        max_tokens = definition.max_tokens if definition is not None else provider.max_tokens
        max_cost_microunits = (
            definition.max_cost_microunits
            if definition is not None
            else min(provider.max_cost_microunits, attempt.remaining_cost_microunits)
        )

        lease_expires_at = attempt.lease_expires_at
        if lease_expires_at is None:
            return None
        try:
            lease_expiry = datetime.fromisoformat(lease_expires_at.removesuffix("Z") + "+00:00")
            provider_expiry = datetime.fromisoformat(
                provider.expires_at.removesuffix("Z") + "+00:00"
            )
        except ValueError:
            return None
        exact = (
            definition_exact,
            current_continuation == continuation,
            continuation.state is CloudContinuationState.PREPARED,
            activation.state is AutomationActivationState.ACTIVE,
            activation.executor_class is AutomationActivationExecutor.CLOUD,
            activation.epoch == continuation.activation_epoch + 1,
            activation.subject == _continuation_execution_subject(continuation),
            background.status is BackgroundBranchBindingStatus.ACTIVE,
            background.binding_id == continuation.background_binding_id,
            background.generation == continuation.background_binding_generation,
            background.binding_digest == continuation.background_binding_digest,
            attempt.binding_id == background.binding_id,
            attempt.binding_generation == background.generation,
            attempt.binding_digest == background.binding_digest,
            attempt.authorizing_principal_id == continuation.principal_id,
            attempt.universe_id == continuation.universe_id,
            attempt.branch_def_id == continuation.branch_def_id,
            attempt.branch_version_id == continuation.branch_version_id,
            attempt.branch_content_digest == continuation.branch_content_digest,
            attempt.executor_audience.executor_class is BackgroundBranchExecutorClass.CLOUD,
            attempt.lifecycle
            in {
                BackgroundBranchAttemptLifecycle.CLAIMED,
                BackgroundBranchAttemptLifecycle.RUNNING,
            },
            lease_expiry > now,
            max_invocations > 0,
            attempt.remaining_cost_microunits >= max_cost_microunits,
            provider.state is ProviderWorkBindingState.ACTIVE,
            provider.binding_id == continuation.provider_binding_id,
            provider.generation == continuation.provider_binding_generation,
            provider.binding_digest == continuation.provider_binding_digest,
            provider.owner_user_id == continuation.principal_id,
            provider.universe_id == continuation.universe_id,
            provider.allowed_operations == ("repository_spec_delivery",),
            provider.allowed_roles == ("writer",),
            provider_expiry > now,
        )
        if not all(exact):
            return None
        actor_id = attempt.executor_audience.daemon_id or attempt.executor_audience.worker_id
        expires_at = lease_expires_at if lease_expiry <= provider_expiry else provider.expires_at
        return ProviderUniverseWorkAuthority(
            root=root,
            binding=provider,
            principal_id=continuation.principal_id,
            actor_id=actor_id,
            execution_subject=_continuation_execution_subject(continuation),
            branch_def_id=continuation.branch_def_id,
            branch_version_id=continuation.branch_version_id,
            operation="repository_spec_delivery",
            role="writer",
            executor_class="cloud",
            max_invocations=max_invocations,
            max_tokens=max_tokens,
            max_cost_microunits=max_cost_microunits,
            expires_at=expires_at,
        )


class _ClaimedCloudProviderSession:
    """Process-local provider call owner for one claimed cloud Branch task."""

    _OPERATION = "repository_spec_delivery"
    _ROLE = "writer"

    def __init__(
        self,
        *,
        base_path: Path,
        continuation: PreparedCloudContinuation,
        branch_task_id: str,
        receipt: Any,
        claim: Any,
        provider_store: Any,
        provider_call: Callable[..., str],
    ) -> None:
        self._base_path = base_path
        self._continuation = continuation
        self._branch_task_id = branch_task_id
        self._receipt = receipt
        self._claim = claim
        self._provider_store = provider_store
        self._provider_call = provider_call
        self._call_ordinal = 0
        self._lock = threading.Lock()

    def __call__(
        self,
        prompt: str,
        system: str = "",
        *,
        role: str = _ROLE,
        **kwargs: Any,
    ) -> str:
        from tinyassets.config import load_universe_config
        from tinyassets.providers.base import UniverseContext

        if role != self._ROLE:
            raise PermissionError("cloud provider role is outside prepared authority")
        with self._lock:
            self._call_ordinal += 1
            ordinal = self._call_ordinal
        invocation_key = (
            f"cloud-branch:{self._branch_task_id}:{ordinal}:"
            f"{_content_digest({'prompt': prompt, 'system': system})}"
        )
        max_tokens = self._receipt.max_tokens // self._receipt.max_invocations
        max_cost = (
            self._receipt.max_cost_microunits // self._receipt.max_invocations
        )
        reserved = self._provider_store.reserve(
            ProviderInvocationReservationRequest(
                receipt_id=self._receipt.receipt_id,
                receipt_digest=self._receipt.receipt_digest,
                claim_id=self._claim.claim_id,
                claim_digest=self._claim.claim_digest,
                claim_generation=self._claim.generation,
                invocation_key=invocation_key,
                operation=self._OPERATION,
                role=self._ROLE,
                max_tokens=max_tokens,
                max_cost_microunits=max_cost,
            )
        ).record
        if reserved is None:
            raise PermissionError("provider invocation budget or authority is unavailable")
        carrier = self._provider_store.arm_launch_carrier(
            ProviderInvocationLaunchRequest.from_reservation(reserved)
        )
        universe_dir = self._base_path / self._continuation.universe_id
        universe_config = load_universe_config(universe_dir)
        call_kwargs = dict(kwargs)
        call_kwargs.update(
            operation=self._OPERATION,
            universe_context=UniverseContext(
                universe_dir=universe_dir,
                config=universe_config,
                provider_invocation=carrier,
            ),
        )
        return self._provider_call(
            prompt,
            system,
            role=role,
            **call_kwargs,
        )


def prepare_claimed_cloud_provider_call(
    base_path: str | Path,
    *,
    claimed_task: Any,
    daemon_id: str,
    provider_call: Callable[..., str],
    clock: Callable[[], datetime] | None = None,
) -> Callable[..., str] | None:
    """Claim exact background/provider authority for one cloud queue task.

    Returns ``None`` for ordinary non-automation tasks. Cloud automation tasks
    fail closed when any prepared, queue, attempt, activation, or provider
    authority record is absent or stale.
    """
    from tinyassets.storage.background_branch_authority import (
        SQLiteBackgroundBranchAuthorityStore,
    )
    from tinyassets.storage.cloud_automation_continuation import (
        SQLiteCloudAutomationContinuationStore,
    )
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )
    from tinyassets.storage.request_admissions import RequestAdmissionStore

    automation_id = str(getattr(claimed_task, "automation_id", "") or "").strip()
    if not automation_id:
        return None
    if str(getattr(claimed_task, "automation_executor_class", "") or "") != "cloud":
        raise PermissionError("cloud automation task has the wrong executor class")
    now_clock = clock or (lambda: datetime.now(timezone.utc))
    now = now_clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    now = now.astimezone(timezone.utc)
    root_path = Path(base_path)
    universe_id = _text(getattr(claimed_task, "universe_id", None), "universe_id")
    branch_task_id = _text(
        getattr(claimed_task, "branch_task_id", None),
        "branch_task_id",
    )
    admission_id = _text(getattr(claimed_task, "admission_id", None), "admission_id")
    request_id = _text(getattr(claimed_task, "request_id", None), "request_id")
    worker_id = _text(
        getattr(claimed_task, "executor_worker_id", None),
        "executor_worker_id",
    )
    runtime_id = _text(
        getattr(claimed_task, "executor_runtime_id", None),
        "executor_runtime_id",
    )
    daemon_id = _text(daemon_id, "daemon_id")
    admission_store = RequestAdmissionStore(root_path, clock=now_clock)
    with admission_store.connection() as conn:
        admission_row = conn.execute(
            """
            SELECT a.body_digest, a.grant_generation,
                   a.receipt_json, t.claimed_at, t.lease_expires_at
            FROM request_admissions AS a
            JOIN branch_tasks_v2 AS t
              ON t.admission_id = a.admission_id
             AND t.request_id = a.request_id
             AND t.branch_task_id = a.branch_task_id
            WHERE a.admission_id = ? AND a.request_id = ? AND a.branch_task_id = ?
            LIMIT 1
            """,
            (admission_id, request_id, branch_task_id),
        ).fetchone()
    if admission_row is None:
        raise PermissionError("cloud task admission is unavailable")
    try:
        admission_receipt = json.loads(str(admission_row["receipt_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PermissionError("cloud task admission receipt is invalid") from exc
    continuation_id = str(admission_receipt.get("continuation_id") or "").strip()
    if not continuation_id:
        return None
    continuation_store = SQLiteCloudAutomationContinuationStore(
        root_path,
        clock=now_clock,
    )
    continuation = continuation_store.get(
        universe_id=universe_id,
        automation_id=automation_id,
    )
    if continuation is None or continuation.continuation_id != continuation_id:
        raise PermissionError("prepared cloud continuation is unavailable")
    audience = BackgroundBranchExecutorAudience(
        executor_class=BackgroundBranchExecutorClass.CLOUD,
        daemon_id=daemon_id,
        runtime_id=runtime_id,
        worker_id=worker_id,
    )

    class _AudienceResolver:
        def resolve(self, *, continuation: Any, branch_task_id: str):
            if continuation != expected_continuation or branch_task_id != expected_task_id:
                return None
            return audience

    expected_continuation = continuation
    expected_task_id = branch_task_id
    logical_key = build_request_task_attempt_key(
        tenant_id=continuation.principal_id,
        request_id=request_id,
        admission_id=admission_id,
        task_id=branch_task_id,
        body_digest=str(admission_row["body_digest"]),
        admission_generation=int(admission_row["grant_generation"]),
    )
    background_store = SQLiteBackgroundBranchAuthorityStore(root_path)
    attempt = background_store.get_attempt_by_logical_key(logical_key)
    if attempt is None:
        raise PermissionError("cloud background attempt is unavailable")
    def canonical_task_timestamp(value: object, name: str) -> str:
        raw = _text(value, name)
        parsed = datetime.fromisoformat(
            raw.removesuffix("Z") + "+00:00" if raw.endswith("Z") else raw
        )
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{name} must include a timezone")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    claimed_at = canonical_task_timestamp(admission_row["claimed_at"], "claimed_at")
    lease_expires_at = canonical_task_timestamp(
        admission_row["lease_expires_at"],
        "lease_expires_at",
    )
    claim_resolver = PreparedCloudContinuationClaimResolver(
        None,
        continuation=continuation,
        admission={
            "admission_id": admission_id,
            "request_id": request_id,
            "branch_task_id": branch_task_id,
        },
        activation_store=AutomationActivationStore(root_path, clock=now_clock),
        background_store=background_store,
        continuation_store=continuation_store,
        request_admission_store=admission_store,
        audience_resolver=_AudienceResolver(),
        clock=now_clock,
    )
    if attempt.lifecycle is BackgroundBranchAttemptLifecycle.RESERVED:
        attempt = BackgroundBranchAttemptClaimService(
            background_store,
            claim_resolver,
        ).claim(
            expected=BackgroundBranchAttemptFence(attempt),
            executor_audience=audience,
            claimed_at=claimed_at,
            lease_expires_at=lease_expires_at,
        ).record
    elif not (
        attempt.lifecycle
        in {
            BackgroundBranchAttemptLifecycle.CLAIMED,
            BackgroundBranchAttemptLifecycle.RUNNING,
        }
        and attempt.executor_audience == audience
        and attempt.lease_expires_at == lease_expires_at
    ):
        raise PermissionError("cloud background attempt custody is stale")
    if attempt is None:
        raise PermissionError("cloud background attempt claim failed")
    provider_store = SQLiteProviderWorkAuthorityStore(root_path, clock=now_clock)
    receipt = ProviderWorkReceiptService(
        provider_store,
        PreparedCloudContinuationProviderResolver(
            None,
            continuation=continuation,
            activation_store=AutomationActivationStore(root_path, clock=now_clock),
            background_store=background_store,
            provider_store=provider_store,
            continuation_store=continuation_store,
            clock=now_clock,
        ),
    ).issue(
        ProviderUniverseWorkRoot(
            work_item_kind="background_attempt",
            work_item_id=attempt.attempt_id,
        )
    ).record
    if receipt is None:
        raise PermissionError("cloud provider receipt is unavailable")
    task_lease = datetime.fromisoformat(lease_expires_at.removesuffix("Z") + "+00:00")
    receipt_expiry = datetime.fromisoformat(receipt.expires_at.removesuffix("Z") + "+00:00")
    lease_seconds = min(3600, int((min(task_lease, receipt_expiry) - now).total_seconds()))
    if lease_seconds < 1:
        raise PermissionError("cloud provider claim lease is expired")
    provider_claim = provider_store.claim(
        ProviderWorkExecutionClaimRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            worker_id=worker_id,
            runtime_id=runtime_id,
            claim_nonce_digest=_content_digest(
                {
                    "continuation_digest": continuation.continuation_digest,
                    "domain": "cloud-branch-provider-claim-v1",
                    "runtime_id": runtime_id,
                    "task_id": branch_task_id,
                    "worker_id": worker_id,
                }
            ),
            lease_seconds=lease_seconds,
        )
    )
    if (
        provider_claim.outcome
        not in {
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            ProviderWorkAuthorityWriteOutcome.REPLAYED,
        }
        or provider_claim.record is None
    ):
        raise PermissionError("cloud provider execution claim is unavailable")
    return _ClaimedCloudProviderSession(
        base_path=root_path,
        continuation=continuation,
        branch_task_id=branch_task_id,
        receipt=receipt,
        claim=provider_claim.record,
        provider_store=provider_store,
        provider_call=provider_call,
    )


__all__ = [
    "AgentInvocationCloudContinuation",
    "CloudContinuationAttemptAudienceResolver",
    "CloudContinuationActivationError",
    "CloudContinuationActivationRequest",
    "CloudContinuationActivationResult",
    "CloudContinuationPreparationError",
    "CloudContinuationState",
    "CloudContinuationWriteOutcome",
    "CloudContinuationWriteResult",
    "PreparedCloudContinuation",
    "PreparedCloudContinuationActivationService",
    "PreparedCloudContinuationAttemptResolver",
    "PreparedCloudContinuationClaimResolver",
    "PreparedCloudContinuationProviderResolver",
    "PreparedCloudContinuationRequest",
    "prepare_claimed_cloud_provider_call",
    "prepare_inactive_cloud_continuation",
]
