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
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from tinyassets.background_branch_authority import (
    BackgroundBranchAttemptLifecycle,
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
    BackgroundBranchAttemptIssuanceRequest,
    BackgroundBranchAttemptIssuanceResolution,
)
from tinyassets.provider_work_authority import (
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkRoot,
    ProviderWorkBindingState,
)
from tinyassets.storage.automation_activations import (
    AutomationActivationExecutor,
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
class CloudContinuationWriteResult:
    outcome: CloudContinuationWriteOutcome
    record: PreparedCloudContinuation | None


class CloudContinuationPreparationError(ValueError):
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
        definition: RepositorySpecWorkDefinition,
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

        if not isinstance(definition, RepositorySpecWorkDefinition):
            raise ValueError("definition must be a RepositorySpecWorkDefinition")
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
        if continuation.definition_digest != definition.definition_digest:
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
            activation.immutable_branch_version == definition.branch_version_id,
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


class PreparedCloudContinuationProviderResolver:
    """Resolve one claimed background attempt into non-bearer provider facts.

    The returned authority is intentionally transient. Receipt persistence
    revalidates the provider binding transactionally, and a later launch owner
    must revalidate activation, attempt, assignment, and credential custody
    again before provider access.
    """

    def __init__(
        self,
        definition: RepositorySpecWorkDefinition,
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

        if not isinstance(definition, RepositorySpecWorkDefinition):
            raise ValueError("definition must be a RepositorySpecWorkDefinition")
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
        if continuation.definition_digest != definition.definition_digest:
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
            activation.immutable_branch_version == definition.branch_version_id,
            background.status is BackgroundBranchBindingStatus.ACTIVE,
            background.binding_id == continuation.background_binding_id,
            background.generation == continuation.background_binding_generation,
            background.binding_digest == continuation.background_binding_digest,
            attempt.binding_id == background.binding_id,
            attempt.binding_generation == background.generation,
            attempt.binding_digest == background.binding_digest,
            attempt.authorizing_principal_id == definition.principal_id,
            attempt.universe_id == definition.universe_id,
            attempt.branch_def_id == definition.branch_def_id,
            attempt.branch_version_id == definition.branch_version_id,
            attempt.branch_content_digest == definition.branch_content_digest,
            attempt.executor_audience.executor_class is BackgroundBranchExecutorClass.CLOUD,
            attempt.lifecycle
            in {
                BackgroundBranchAttemptLifecycle.CLAIMED,
                BackgroundBranchAttemptLifecycle.RUNNING,
            },
            lease_expiry > now,
            attempt.remaining_count > 0,
            attempt.remaining_cost_microunits >= definition.max_cost_microunits,
            provider.state is ProviderWorkBindingState.ACTIVE,
            provider.binding_id == continuation.provider_binding_id,
            provider.generation == continuation.provider_binding_generation,
            provider.binding_digest == continuation.provider_binding_digest,
            provider.owner_user_id == definition.principal_id,
            provider.universe_id == definition.universe_id,
            provider.allowed_operations == ("repository_spec_delivery",),
            provider.allowed_roles == ("writer",),
            provider.max_invocations == definition.max_attempts,
            provider.max_tokens == definition.max_tokens,
            provider.max_cost_microunits == definition.max_cost_microunits,
            provider_expiry > now,
        )
        if not all(exact):
            return None
        actor_id = attempt.executor_audience.daemon_id or attempt.executor_audience.worker_id
        expires_at = lease_expires_at if lease_expiry <= provider_expiry else provider.expires_at
        return ProviderUniverseWorkAuthority(
            root=root,
            binding=provider,
            actor_id=actor_id,
            branch_def_id=definition.branch_def_id,
            branch_version_id=definition.branch_version_id,
            operation="repository_spec_delivery",
            role="writer",
            executor_class="cloud",
            max_invocations=definition.max_attempts,
            max_tokens=definition.max_tokens,
            max_cost_microunits=definition.max_cost_microunits,
            expires_at=expires_at,
        )


__all__ = [
    "CloudContinuationAttemptAudienceResolver",
    "CloudContinuationPreparationError",
    "CloudContinuationState",
    "CloudContinuationWriteOutcome",
    "CloudContinuationWriteResult",
    "PreparedCloudContinuation",
    "PreparedCloudContinuationAttemptResolver",
    "PreparedCloudContinuationProviderResolver",
    "PreparedCloudContinuationRequest",
    "prepare_inactive_cloud_continuation",
]
