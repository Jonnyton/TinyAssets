"""Assigned-provider authority for daemon-owned background Branch execution."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from tinyassets.background_branch_authority import (
    BackgroundBranchAttemptLifecycle,
    BackgroundBranchBindingStatus,
    BackgroundBranchExecutorClass,
)
from tinyassets.branch_tasks_v2 import AssignedConsumerLease, Epoch2BranchTask
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.provider_assignment import (
    load_provider_assignment_in_transaction,
    provider_assignment_admission,
)
from tinyassets.provider_work_authority import (
    ProviderInvocationCarrier,
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkRoot,
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBindingFence,
    ProviderWorkBindingRoot,
    ProviderWorkBindingSeed,
    ProviderWorkBindingService,
    ProviderWorkBindingState,
)
from tinyassets.runtime.claimed_branch_execution import ClaimedBranchExecutorIdentity

BACKGROUND_BRANCH_RUN_OPERATION = "background_branch_run"
_DEFAULT_MAX_INVOCATIONS = 64
_DEFAULT_MAX_TOKENS = 250_000
_DEFAULT_MAX_COST_MICROUNITS = 25_000_000
_SUPPORTED_BRANCH_ROLES = frozenset({"writer", "judge", "extract", "embed"})
logger = logging.getLogger(__name__)


class BackgroundExecutorIdentityError(PermissionError):
    """A claimed task has no current owner-authorized executor identity."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def load_background_executor_identity(
    base_path: str | Path,
    claimed_task: Epoch2BranchTask,
    consumer_lease: AssignedConsumerLease,
    *,
    heartbeat: Callable[[], None] | None = None,
) -> ClaimedBranchExecutorIdentity:
    """Reuse the daemon/runtime identity authorized by the background binding."""

    from tinyassets.cloud_automation_continuation import build_request_task_attempt_key
    from tinyassets.storage.background_branch_authority import (
        SQLiteBackgroundBranchAuthorityStore,
    )
    from tinyassets.storage.request_admissions import RequestAdmissionStore

    if claimed_task.claimed_by != consumer_lease.consumer_id:
        raise BackgroundExecutorIdentityError("background_consumer_lease_mismatch")
    root = Path(base_path)
    admission_store = RequestAdmissionStore(root)
    background_store = SQLiteBackgroundBranchAuthorityStore(root)
    with admission_store.connection() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            """
            SELECT body_digest, grant_generation
            FROM request_admissions
            WHERE admission_id = ? AND request_id = ? AND branch_task_id = ?
            """,
            (
                claimed_task.admission_id,
                claimed_task.request_id,
                claimed_task.branch_task_id,
            ),
        ).fetchone()
        if row is None:
            conn.rollback()
            raise BackgroundExecutorIdentityError("background_binding_absent")
        logical_key = build_request_task_attempt_key(
            tenant_id=claimed_task.actor_id,
            request_id=claimed_task.request_id,
            admission_id=claimed_task.admission_id,
            task_id=claimed_task.branch_task_id,
            body_digest=str(row["body_digest"]),
            admission_generation=int(row["grant_generation"]),
        )
        authority = background_store.read_authority_in_transaction(
            conn,
            logical_attempt_key=logical_key,
        )
        conn.rollback()
    if authority is None:
        raise BackgroundExecutorIdentityError("background_binding_absent")
    binding, attempt = authority
    now = datetime.now(timezone.utc)
    if binding.status is not BackgroundBranchBindingStatus.ACTIVE:
        raise BackgroundExecutorIdentityError("background_binding_inactive")
    if binding.expires_at is None or _utc(binding.expires_at) <= now:
        raise BackgroundExecutorIdentityError("background_binding_expired")
    if attempt.lifecycle not in {
        BackgroundBranchAttemptLifecycle.CLAIMED,
        BackgroundBranchAttemptLifecycle.RUNNING,
    }:
        raise BackgroundExecutorIdentityError("background_attempt_inactive")
    if attempt.lease_expires_at is None or _utc(attempt.lease_expires_at) <= now:
        raise BackgroundExecutorIdentityError("background_attempt_lease_expired")
    if (
        binding.universe_id != claimed_task.universe_id
        or binding.branch_def_id != claimed_task.branch_def_id
        or binding.pinned_branch_version_id != claimed_task.automation_branch_version
    ):
        raise BackgroundExecutorIdentityError("background_binding_target_mismatch")
    if binding.authorizing_principal_id != claimed_task.actor_id:
        raise BackgroundExecutorIdentityError("background_binding_principal_mismatch")
    if BackgroundBranchExecutorClass.CLOUD not in binding.permitted_executor_classes:
        raise BackgroundExecutorIdentityError("background_binding_executor_class_unavailable")
    if not binding.daemon_id or not binding.runtime_id:
        raise BackgroundExecutorIdentityError("background_binding_executor_identity_missing")
    return ClaimedBranchExecutorIdentity(
        daemon_id=binding.daemon_id,
        worker_id=consumer_lease.consumer_id,
        runtime_instance_id=binding.runtime_id,
        heartbeat=heartbeat,
    )

def _hold_background_authority(base_path: Path, task: Epoch2BranchTask) -> None:
    """Project the exact queue authority owner to a retryable held state."""

    from tinyassets.background_branch_authority import BackgroundBranchBindingStatus
    from tinyassets.background_branch_authority_service import (
        BackgroundBranchAuthorityFailureKind,
        BackgroundBranchAuthorityHoldService,
        BackgroundBranchAuthorityOwnerFence,
        BackgroundBranchAuthorityOwnerKind,
        BackgroundBranchAuthorityOwnerState,
    )
    from tinyassets.storage.background_branch_authority import (
        SQLiteBackgroundBranchAuthorityStore,
    )

    class _ExitResolver:
        def resolve(self, _request: Any) -> None:
            return None

    store = SQLiteBackgroundBranchAuthorityStore(base_path)
    owner = store.get_owner(
        owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
        owner_id=task.branch_task_id,
    )
    if owner is None or (owner.state is BackgroundBranchAuthorityOwnerState.TARGET_AUTHORITY_HELD):
        return
    failure = BackgroundBranchAuthorityFailureKind.UNAUTHORIZED
    binding = owner.binding.expected_record if owner.binding is not None else None
    held_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if binding is None:
        failure = BackgroundBranchAuthorityFailureKind.MISSING
    elif binding.status is BackgroundBranchBindingStatus.REVOKED:
        failure = BackgroundBranchAuthorityFailureKind.REVOKED
    elif binding.status is BackgroundBranchBindingStatus.EXHAUSTED:
        failure = BackgroundBranchAuthorityFailureKind.EXHAUSTED
    elif (
        binding.status is BackgroundBranchBindingStatus.EXPIRED
        or binding.expires_at is not None
        and _utc(binding.expires_at) <= _utc(held_at)
    ):
        failure = BackgroundBranchAuthorityFailureKind.EXPIRED
    service = BackgroundBranchAuthorityHoldService(store, _ExitResolver())
    service.hold(
        expected=BackgroundBranchAuthorityOwnerFence(owner),
        failure=failure,
        held_at=held_at,
    )


def _positive_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _background_timestamp(value: str | datetime, *after: str) -> str:
    parsed = value if isinstance(value, datetime) else _utc(value)
    parsed = parsed.astimezone(timezone.utc)
    for prior in after:
        prior_value = _utc(prior)
        if parsed <= prior_value:
            parsed = prior_value + timedelta(microseconds=1)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def claim_background_queue_authority_in_transaction(
    conn: sqlite3.Connection,
    task: Epoch2BranchTask,
    consumer_lease: AssignedConsumerLease,
    *,
    claimed_at: str,
    lease_expires_at: str,
) -> bool:
    """Claim the canonical attempt and create its queue owner with the task CAS."""

    reason = explain_background_queue_authority_in_transaction(
        conn,
        task,
        consumer_lease,
        claimed_at=claimed_at,
        lease_expires_at=lease_expires_at,
    )
    if reason is not None:
        return False

    from tinyassets.background_branch_authority import (
        BackgroundBranchAttemptFence,
        BackgroundBranchBindingFence,
    )
    from tinyassets.background_branch_authority_service import (
        BackgroundBranchAuthorityOwnerKind,
        BackgroundBranchAuthorityOwnerRecord,
        BackgroundBranchAuthorityOwnerState,
    )
    from tinyassets.cloud_automation_continuation import build_request_task_attempt_key
    from tinyassets.storage.background_branch_authority import (
        SQLiteBackgroundBranchAuthorityStore,
        _SQLiteBackgroundBranchAuthorityTransaction,
    )

    row = conn.execute(
        """
        SELECT body_digest, grant_generation, actor_id
        FROM request_admissions
        WHERE admission_id = ? AND request_id = ? AND branch_task_id = ?
        """,
        (task.admission_id, task.request_id, task.branch_task_id),
    ).fetchone()
    assert row is not None
    logical_key = build_request_task_attempt_key(
        tenant_id=str(row["actor_id"]),
        request_id=task.request_id,
        admission_id=task.admission_id,
        task_id=task.branch_task_id,
        body_digest=str(row["body_digest"]),
        admission_generation=int(row["grant_generation"]),
    )
    try:
        authority = SQLiteBackgroundBranchAuthorityStore.read_authority_in_transaction(
            conn,
            logical_attempt_key=logical_key,
        )
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise
        authority = None
    assert authority is not None
    binding, attempt = authority
    transaction = _SQLiteBackgroundBranchAuthorityTransaction(conn)
    transitioned_at = _background_timestamp(claimed_at, attempt.updated_at)
    claimed_attempt = replace(
        attempt,
        lease_generation=attempt.lease_generation + 1,
        lease_expires_at=_background_timestamp(lease_expires_at),
        lifecycle=BackgroundBranchAttemptLifecycle.CLAIMED,
        updated_at=transitioned_at,
    )
    attempt_result = transaction.compare_and_swap_attempt(
        attempt_id=attempt.attempt_id,
        expected=BackgroundBranchAttemptFence(attempt),
        replacement=claimed_attempt,
    )
    if attempt_result.record != claimed_attempt:
        return False
    owner = BackgroundBranchAuthorityOwnerRecord(
        owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
        owner_id=task.branch_task_id,
        universe_id=binding.universe_id,
        authorizing_principal_id=binding.authorizing_principal_id,
        source_generation=attempt.source_generation,
        transition_generation=1,
        state=BackgroundBranchAuthorityOwnerState.PENDING,
        binding=BackgroundBranchBindingFence(binding),
        attempt=BackgroundBranchAttemptFence(claimed_attempt),
        hold_reason=None,
        updated_at=transitioned_at,
    )
    return transaction.insert_owner(owner).record == owner


def explain_background_queue_authority_in_transaction(
    conn: sqlite3.Connection,
    task: Epoch2BranchTask,
    consumer_lease: AssignedConsumerLease,
    *,
    claimed_at: str,
    lease_expires_at: str,
) -> str | None:
    """Return the first queue-authority claim predicate without writing."""

    from tinyassets.background_branch_authority_service import (
        BackgroundBranchAuthorityOwnerKind,
    )
    from tinyassets.cloud_automation_continuation import build_request_task_attempt_key
    from tinyassets.storage.background_branch_authority import (
        SQLiteBackgroundBranchAuthorityStore,
    )

    if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
        raise ValueError("background queue authority explain requires a transaction")
    if task.claimed_by:
        return "task_already_claimed"
    row = conn.execute(
        """
        SELECT body_digest, grant_generation, actor_id
        FROM request_admissions
        WHERE admission_id = ? AND request_id = ? AND branch_task_id = ?
        """,
        (task.admission_id, task.request_id, task.branch_task_id),
    ).fetchone()
    if row is None:
        return "no_admission_row"
    logical_key = build_request_task_attempt_key(
        tenant_id=str(row["actor_id"]),
        request_id=task.request_id,
        admission_id=task.admission_id,
        task_id=task.branch_task_id,
        body_digest=str(row["body_digest"]),
        admission_generation=int(row["grant_generation"]),
    )
    authority = SQLiteBackgroundBranchAuthorityStore.read_authority_in_transaction(
        conn,
        logical_attempt_key=logical_key,
    )
    if authority is None:
        return "no_background_authority"
    binding, attempt = authority
    now = _utc(claimed_at)
    lease_expiry = _utc(lease_expires_at)
    predicates = (
        (binding.status is BackgroundBranchBindingStatus.ACTIVE, "binding_not_active"),
        (binding.expires_at is not None, "binding_expired"),
        (
            binding.expires_at is not None and _utc(binding.expires_at) > now,
            "binding_expired",
        ),
        (
            binding.expires_at is not None and lease_expiry <= _utc(binding.expires_at),
            "binding_lease_too_short",
        ),
        (
            binding.authorizing_principal_id == str(row["actor_id"]),
            "binding_principal_mismatch",
        ),
        (binding.universe_id == task.universe_id, "binding_universe_mismatch"),
        (binding.branch_def_id == task.branch_def_id, "binding_branch_mismatch"),
        (
            binding.pinned_branch_version_id == task.automation_branch_version,
            "binding_version_mismatch",
        ),
        (
            BackgroundBranchExecutorClass.CLOUD in binding.permitted_executor_classes,
            "binding_executor_class_missing",
        ),
        (bool(binding.daemon_id), "binding_daemon_missing"),
        (bool(binding.runtime_id), "binding_runtime_missing"),
        (
            attempt.lifecycle is BackgroundBranchAttemptLifecycle.RESERVED,
            "attempt_not_reserved",
        ),
        (attempt.lease_expires_at is None, "attempt_lease_present"),
        (
            attempt.branch_version_id == task.automation_branch_version,
            "attempt_version_mismatch",
        ),
        (
            attempt.branch_content_digest == task.automation_subject_digest,
            "attempt_digest_mismatch",
        ),
        (
            attempt.executor_audience.daemon_id == binding.daemon_id,
            "attempt_daemon_mismatch",
        ),
        (
            attempt.executor_audience.runtime_id == binding.runtime_id,
            "attempt_runtime_mismatch",
        ),
        (lease_expiry > now, "claim_lease_invalid"),
        (
            consumer_lease.consumer_id.startswith(
                ("assigned-consumer:", "worker_assigned_")
            ),
            "consumer_identity_invalid",
        ),
        (
            _utc(consumer_lease.expires_at) >= lease_expiry,
            "consumer_lease_too_short",
        ),
    )
    for allowed, reason in predicates:
        if not allowed:
            return reason
    owner = SQLiteBackgroundBranchAuthorityStore.read_queue_owner_in_transaction(
        conn,
        owner_id=task.branch_task_id,
    )
    if owner is not None and owner.owner_kind is BackgroundBranchAuthorityOwnerKind.QUEUE_TASK:
        return "queue_owner_exists"
    return None


def start_background_queue_authority(
    base_path: str | Path,
    task: Epoch2BranchTask,
    consumer_lease: AssignedConsumerLease,
) -> None:
    """CAS one claimed queue owner and attempt into their running states."""

    from tinyassets.background_branch_authority import BackgroundBranchAttemptFence
    from tinyassets.background_branch_authority_service import (
        BackgroundBranchAuthorityOwnerFence,
        BackgroundBranchAuthorityOwnerKind,
        BackgroundBranchAuthorityOwnerState,
    )
    from tinyassets.storage.background_branch_authority import (
        SQLiteBackgroundBranchAuthorityStore,
    )

    if task.claimed_by != consumer_lease.consumer_id:
        raise BackgroundExecutorIdentityError("background_consumer_lease_mismatch")
    store = SQLiteBackgroundBranchAuthorityStore(base_path)
    with store.transaction() as transaction:
        owner = transaction.get_owner(
            owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
            owner_id=task.branch_task_id,
        )
        if owner is None:
            raise BackgroundExecutorIdentityError("background_queue_owner_missing")
        if (
            owner.state is not BackgroundBranchAuthorityOwnerState.PENDING
            or owner.binding is None
            or owner.attempt is None
        ):
            raise BackgroundExecutorIdentityError("background_queue_owner_inactive")
        binding = transaction.get_binding(owner.binding.expected_record.binding_id)
        attempt = transaction.get_attempt_by_logical_key(
            owner.attempt.expected_record.logical_attempt_key
        )
        now = datetime.now(timezone.utc)
        if binding != owner.binding.expected_record:
            raise BackgroundExecutorIdentityError("background_binding_stale")
        if binding.expires_at is None or _utc(binding.expires_at) <= now:
            raise BackgroundExecutorIdentityError("background_binding_expired")
        if attempt != owner.attempt.expected_record:
            raise BackgroundExecutorIdentityError("background_attempt_stale")
        if attempt.lifecycle is not BackgroundBranchAttemptLifecycle.CLAIMED:
            raise BackgroundExecutorIdentityError("background_attempt_inactive")
        if attempt.lease_expires_at is None or _utc(attempt.lease_expires_at) <= now:
            raise BackgroundExecutorIdentityError("background_attempt_lease_expired")
        transitioned_at = _background_timestamp(now, owner.updated_at, attempt.updated_at)
        running_attempt = replace(
            attempt,
            lifecycle=BackgroundBranchAttemptLifecycle.RUNNING,
            updated_at=transitioned_at,
        )
        attempt_result = transaction.compare_and_swap_attempt(
            attempt_id=attempt.attempt_id,
            expected=BackgroundBranchAttemptFence(attempt),
            replacement=running_attempt,
        )
        if attempt_result.record != running_attempt:
            raise BackgroundExecutorIdentityError("background_attempt_stale")
        running_owner = replace(
            owner,
            transition_generation=owner.transition_generation + 1,
            state=BackgroundBranchAuthorityOwnerState.RUNNING,
            attempt=BackgroundBranchAttemptFence(running_attempt),
            updated_at=transitioned_at,
        )
        owner_result = transaction.compare_and_swap_owner(
            expected=BackgroundBranchAuthorityOwnerFence(owner),
            replacement=running_owner,
        )
        if owner_result.record != running_owner:
            raise BackgroundExecutorIdentityError("background_queue_owner_changed")


def terminalize_background_queue_authority(
    base_path: str | Path,
    task: Epoch2BranchTask,
    *,
    status: str,
    reason: str,
) -> None:
    """CAS the queue authority and its attempt to one conclusive terminal state."""

    from tinyassets.background_branch_authority import BackgroundBranchAttemptFence
    from tinyassets.background_branch_authority_service import (
        BackgroundBranchAuthorityOwnerFence,
        BackgroundBranchAuthorityOwnerKind,
        BackgroundBranchAuthorityOwnerState,
    )
    from tinyassets.storage.background_branch_authority import (
        SQLiteBackgroundBranchAuthorityStore,
    )

    owner_states = {
        "succeeded": BackgroundBranchAuthorityOwnerState.SUCCEEDED,
        "failed": BackgroundBranchAuthorityOwnerState.FAILED,
        "cancelled": BackgroundBranchAuthorityOwnerState.CANCELLED,
    }
    attempt_states = {
        "succeeded": BackgroundBranchAttemptLifecycle.SUCCEEDED,
        "failed": BackgroundBranchAttemptLifecycle.FAILED,
        "cancelled": BackgroundBranchAttemptLifecycle.CANCELLED,
    }
    if status not in owner_states or not reason.strip():
        raise ValueError("background terminal status and reason are required")
    store = SQLiteBackgroundBranchAuthorityStore(base_path)
    with store.transaction() as transaction:
        owner = transaction.get_owner(
            owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
            owner_id=task.branch_task_id,
        )
        if owner is None:
            raise BackgroundExecutorIdentityError("background_queue_owner_missing")
        if owner.state not in {
            BackgroundBranchAuthorityOwnerState.PENDING,
            BackgroundBranchAuthorityOwnerState.RUNNING,
        } or owner.attempt is None:
            raise BackgroundExecutorIdentityError("background_queue_owner_inactive")
        attempt = transaction.get_attempt_by_logical_key(
            owner.attempt.expected_record.logical_attempt_key
        )
        if attempt != owner.attempt.expected_record:
            raise BackgroundExecutorIdentityError("background_attempt_stale")
        transitioned_at = _background_timestamp(
            datetime.now(timezone.utc), owner.updated_at, attempt.updated_at
        )
        attempt_state = attempt_states[status]
        if attempt.lifecycle is BackgroundBranchAttemptLifecycle.CLAIMED:
            attempt_state = BackgroundBranchAttemptLifecycle.CANCELLED
        terminal_attempt = replace(
            attempt,
            lease_generation=attempt.lease_generation + 1,
            lease_expires_at=None,
            lifecycle=attempt_state,
            hold_reason=None,
            terminal_reason=reason,
            updated_at=transitioned_at,
        )
        attempt_result = transaction.compare_and_swap_attempt(
            attempt_id=attempt.attempt_id,
            expected=BackgroundBranchAttemptFence(attempt),
            replacement=terminal_attempt,
        )
        if attempt_result.record != terminal_attempt:
            raise BackgroundExecutorIdentityError("background_attempt_stale")
        terminal_owner = replace(
            owner,
            transition_generation=owner.transition_generation + 1,
            state=owner_states[status],
            attempt=BackgroundBranchAttemptFence(terminal_attempt),
            hold_reason=None,
            updated_at=transitioned_at,
        )
        owner_result = transaction.compare_and_swap_owner(
            expected=BackgroundBranchAuthorityOwnerFence(owner),
            replacement=terminal_owner,
        )
        if owner_result.record != terminal_owner:
            raise BackgroundExecutorIdentityError("background_queue_owner_changed")


def _normalize_content_digest(value: str) -> str:
    """Both forms occur: branch_versions.content_hash is bare hex, but a task's
    automation_subject_digest is `sha256:<hex>` (api/cloud_automations.py). Normalize
    to the prefixed form so the authority compare doesn't fail every real version
    (Codex #2, PR #2516). Empty stays empty so a missing digest never matches."""
    text = (value or "").strip()
    if not text:
        return ""
    return text if text.startswith("sha256:") else f"sha256:{text}"


def _branch_roles(base_path: Path, task: Epoch2BranchTask) -> tuple[str, ...]:
    from tinyassets.branch_versions import get_branch_version

    version = get_branch_version(base_path, task.automation_branch_version)
    if (
        version is None
        or version.status != "active"
        or version.branch_def_id != task.branch_def_id
        or _normalize_content_digest(version.content_hash)
        != _normalize_content_digest(task.automation_subject_digest)
    ):
        raise PermissionError("immutable Branch version is not current authority")
    node_defs = version.snapshot.get("node_defs", {})
    if isinstance(node_defs, dict):
        nodes = node_defs.values()
    elif isinstance(node_defs, list):
        nodes = node_defs
    else:
        raise PermissionError("immutable Branch node definitions are invalid")
    roles = {
        str(node.get("model_hint") or "writer").strip() or "writer"
        for node in nodes
        if isinstance(node, dict) and str(node.get("node_type") or "prompt") == "prompt"
    }
    if not roles:
        roles = {"writer"}
    if not roles.issubset(_SUPPORTED_BRANCH_ROLES):
        raise PermissionError("immutable Branch requests an unsupported provider role")
    return tuple(sorted(roles))


class _SeedResolver:
    def __init__(self, seed: ProviderWorkBindingSeed) -> None:
        self.seed = seed

    def resolve(self, root: ProviderWorkBindingRoot) -> ProviderWorkBindingSeed | None:
        return self.seed if self._matches(root) else None

    def resolve_current_in_transaction(
        self, _conn: sqlite3.Connection, root: ProviderWorkBindingRoot
    ) -> ProviderWorkBindingSeed | None:
        return self.resolve(root)

    def _matches(self, root: ProviderWorkBindingRoot) -> bool:
        return (
            root.owner_user_id == self.seed.owner_user_id
            and root.universe_id == self.seed.universe_id
            and root.provider == self.seed.provider
        )


def _current_background_binding(
    conn: sqlite3.Connection,
    *,
    provider_store: Any,
    seed: ProviderWorkBindingSeed,
) -> Any:
    root = ProviderWorkBindingRoot(
        owner_user_id=seed.owner_user_id,
        universe_id=seed.universe_id,
        provider=seed.provider,
    )
    service = ProviderWorkBindingService(provider_store, _SeedResolver(seed))
    issued = service.issue_in_transaction(conn, root)
    if (
        issued.outcome
        in {
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            ProviderWorkAuthorityWriteOutcome.REPLAYED,
        }
        and issued.record is not None
    ):
        return issued.record
    from tinyassets.provider_work_authority import provider_work_binding_id

    binding_id = provider_work_binding_id(
        owner_user_id=seed.owner_user_id,
        universe_id=seed.universe_id,
        provider=seed.provider,
        binding_class=BACKGROUND_BRANCH_RUN_OPERATION,
    )
    current = provider_store.get_binding_in_transaction(conn, binding_id=binding_id)
    if current is None:
        raise PermissionError("background provider binding is unavailable")
    exact = (
        current.state is ProviderWorkBindingState.ACTIVE,
        _utc(current.expires_at) > datetime.now(timezone.utc),
        current.credential_reference_digest == seed.credential_reference_digest,
        current.allowed_operations == seed.allowed_operations,
        current.allowed_roles == seed.allowed_roles,
        current.assignment_generation == seed.assignment_generation,
        current.assignment_digest == seed.assignment_digest,
        current.max_invocations == seed.max_invocations,
        current.max_tokens == seed.max_tokens,
        current.max_cost_microunits == seed.max_cost_microunits,
    )
    if all(exact):
        return current
    rebound = service.rebind_in_transaction(conn, ProviderWorkBindingFence(current), root)
    if rebound.outcome is not ProviderWorkAuthorityWriteOutcome.APPLIED or rebound.record is None:
        raise PermissionError("background provider binding rotation conflicted")
    return rebound.record


class _BackgroundAssignedProviderSession:
    def __init__(
        self,
        base_path: Path,
        task: Epoch2BranchTask,
        consumer_lease: AssignedConsumerLease,
        provider_call: Callable[..., str],
    ) -> None:
        self._base_path = base_path
        self._task = task
        self._consumer_lease = consumer_lease
        self._provider_call = provider_call
        self._call_index = 0
        self._lock = threading.Lock()

    @staticmethod
    def _declared_policy_providers(policy: dict[str, Any] | None) -> set[str]:
        providers: set[str] = set()
        if not policy:
            return providers
        for value in policy.values():
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                use = entry.get("use") if isinstance(entry, dict) else None
                candidate = use if isinstance(use, dict) else entry
                if isinstance(candidate, dict) and candidate.get("provider"):
                    providers.add(str(candidate["provider"]))
        return providers

    def call_with_policy_sync(
        self,
        role: str,
        prompt: str,
        system: str,
        policy: dict[str, Any] | None,
        config: Any = None,
        difficulty: str = "",
        **kwargs: Any,
    ) -> tuple[str, str, dict[str, Any]]:
        del difficulty
        response, provider = self._call(role, prompt, system, config, policy, kwargs)
        return response, provider, {"authority": BACKGROUND_BRANCH_RUN_OPERATION, "attempts": 1}

    def __call__(
        self, prompt: str, system: str = "", *, role: str = "writer", **kwargs: Any
    ) -> str:
        config = kwargs.pop("config", None)
        policy = kwargs.pop("policy", None)
        response, _provider = self._call(role, prompt, system, config, policy, kwargs)
        return response

    def _call(
        self,
        role: str,
        prompt: str,
        system: str,
        config: Any,
        policy: dict[str, Any] | None,
        kwargs: dict[str, Any],
    ) -> tuple[str, str]:
        supplied_operation = kwargs.pop("operation", BACKGROUND_BRANCH_RUN_OPERATION)
        supplied_context = kwargs.pop("universe_context", None)
        if supplied_operation != BACKGROUND_BRANCH_RUN_OPERATION:
            raise PermissionError("background provider operation cannot be substituted")
        if (
            supplied_context is not None
            and Path(supplied_context.universe_dir).name != self._task.universe_id
        ):
            raise PermissionError("background provider universe cannot be substituted")
        declared_providers = self._declared_policy_providers(policy)
        with self._lock:
            invocation_index = self._call_index + 1
            with self._authorize_launch(
                role=role,
                prompt=prompt,
                system=system,
                invocation_index=invocation_index,
                declared_providers=declared_providers,
            ) as launch:
                from tinyassets.config import load_universe_config
                from tinyassets.providers.base import ModelConfig, UniverseContext

                carrier, snapshot_dir, provider = launch
                universe_dir = self._base_path / self._task.universe_id
                call_kwargs = dict(kwargs)
                call_config = config
                if snapshot_dir is not None:
                    if call_config is None:
                        call_config = ModelConfig()
                    if not isinstance(call_config, ModelConfig):
                        raise TypeError("background provider config must be a ModelConfig")
                    call_config = replace(
                        call_config,
                        credential_snapshot_dir=snapshot_dir,
                    )
                call_kwargs.update(
                    operation=BACKGROUND_BRANCH_RUN_OPERATION,
                    universe_context=UniverseContext(
                        universe_dir=universe_dir,
                        config=load_universe_config(universe_dir),
                        provider_invocation=carrier,
                    ),
                )
                result = self._provider_call(
                    prompt, system, role=role, config=call_config, **call_kwargs
                )
                self._call_index = invocation_index
                return result, provider

    @contextmanager
    def _authorize_launch(
        self,
        *,
        role: str,
        prompt: str,
        system: str,
        invocation_index: int,
        declared_providers: set[str],
    ) -> Iterator[tuple[ProviderInvocationCarrier, Path | None, str]]:
        from tinyassets.cloud_automation_continuation import build_request_task_attempt_key
        from tinyassets.credential_vault import snapshot_llm_subscription_credential
        from tinyassets.exceptions import ProviderAuthorityHeldError
        from tinyassets.provider_serving_binding import (
            _current_serving_authority,
            _is_open_provider,
            resolve_serving_agent_binding,
        )
        from tinyassets.storage.background_branch_authority import (
            SQLiteBackgroundBranchAuthorityStore,
        )
        from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore
        from tinyassets.storage.request_admissions import RequestAdmissionStore

        held = "Assigned background provider authority is unavailable; retry after repair."
        universe_dir = self._base_path / self._task.universe_id
        snapshot = None
        carrier = None
        try:
            roles = _branch_roles(self._base_path, self._task)
            if role not in roles:
                raise PermissionError("provider role is outside immutable Branch authority")
            admission_store = RequestAdmissionStore(self._base_path)
            provider_store = SQLiteProviderWorkAuthorityStore(self._base_path)
            background_store = SQLiteBackgroundBranchAuthorityStore(self._base_path)
            with provider_assignment_admission().shared(universe_dir):
                with admission_store.connection() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        row = conn.execute(
                            """
                            SELECT t.*, a.actor_id, a.body_digest, a.grant_generation
                            FROM branch_tasks_v2 AS t JOIN request_admissions AS a
                              ON a.admission_id=t.admission_id AND a.request_id=t.request_id
                             AND a.branch_task_id=t.branch_task_id
                            WHERE t.branch_task_id=? LIMIT 1
                            """,
                            (self._task.branch_task_id,),
                        ).fetchone()
                        if row is None:
                            raise PermissionError("task admission is unavailable")
                        now = datetime.now(timezone.utc)
                        exact_task = (
                            row["status"] in {"running", "cancel_requested"},
                            row["claimed_by"] == self._consumer_lease.consumer_id,
                            row["claimed_at"] == self._task.claimed_at,
                            _utc(str(row["lease_expires_at"])) > now,
                            _utc(self._consumer_lease.expires_at) > now,
                            row["universe_id"] == self._task.universe_id,
                            row["automation_activation_epoch"]
                            == self._task.automation_activation_epoch,
                            row["automation_subject_ref"] == self._task.automation_subject_ref,
                            row["automation_subject_digest"]
                            == self._task.automation_subject_digest,
                            row["automation_branch_version"]
                            == self._task.automation_branch_version,
                        )
                        if not all(exact_task):
                            raise PermissionError("task lease or immutable target changed")
                        activation = conn.execute(
                            """
                            SELECT * FROM automation_activations
                            WHERE universe_id=? AND automation_id=? LIMIT 1
                            """,
                            (self._task.universe_id, self._task.automation_id),
                        ).fetchone()
                        if activation is None or not all(
                            (
                                activation["state"] == "active",
                                activation["epoch"] == self._task.automation_activation_epoch,
                                activation["subject_ref"] == self._task.automation_subject_ref,
                                activation["subject_digest"]
                                == self._task.automation_subject_digest,
                                activation["immutable_branch_version"]
                                == self._task.automation_branch_version,
                                activation["lease_id"] == self._task.automation_lease_id,
                            )
                        ):
                            raise PermissionError("automation activation changed")
                        assignment = load_provider_assignment_in_transaction(
                            conn, universe_id=self._task.universe_id
                        )
                        if assignment is None or assignment.state != "ready":
                            raise PermissionError("assigned provider is unavailable")
                        if declared_providers - {assignment.provider}:
                            raise PermissionError(
                                "background policy provider is outside assigned authority"
                            )
                        agent = resolve_serving_agent_binding(
                            self._base_path,
                            universe_id=self._task.universe_id,
                            owner_user_id=assignment.owner_user_id,
                        )
                        current_assignment, serving_binding, custody = _current_serving_authority(
                            conn,
                            store=provider_store,
                            universe_dir=universe_dir,
                            owner_user_id=assignment.owner_user_id,
                            universe_id=self._task.universe_id,
                            agent=agent,
                        )
                        if current_assignment != assignment:
                            raise PermissionError("assigned provider rotated")
                        logical_key = build_request_task_attempt_key(
                            tenant_id=assignment.owner_user_id,
                            request_id=self._task.request_id,
                            admission_id=self._task.admission_id,
                            task_id=self._task.branch_task_id,
                            body_digest=str(row["body_digest"]),
                            admission_generation=int(row["grant_generation"]),
                        )
                        background_authority = background_store.read_authority_in_transaction(
                            conn, logical_attempt_key=logical_key
                        )
                        if background_authority is None:
                            raise PermissionError("background Branch attempt is unavailable")
                        binding, attempt = background_authority
                        if binding.status is BackgroundBranchBindingStatus.ACTIVE and (
                            binding.expires_at is None or _utc(binding.expires_at) <= now
                        ):
                            raise BackgroundExecutorIdentityError(
                                "background_binding_expired"
                            )
                        if not all(
                            (
                                binding.status is BackgroundBranchBindingStatus.ACTIVE,
                                binding.expires_at is not None,
                                binding.expires_at is not None
                                and _utc(binding.expires_at) > now,
                                binding.authorizing_principal_id
                                == assignment.owner_user_id,
                                binding.universe_id == self._task.universe_id,
                                binding.branch_def_id == self._task.branch_def_id,
                                binding.pinned_branch_version_id
                                == self._task.automation_branch_version,
                                BackgroundBranchExecutorClass.CLOUD
                                in binding.permitted_executor_classes,
                                bool(binding.daemon_id),
                                bool(binding.runtime_id),
                                attempt.binding_id == binding.binding_id,
                                attempt.binding_generation == binding.generation,
                                attempt.binding_digest == binding.binding_digest,
                                attempt.authorizing_principal_id == assignment.owner_user_id,
                                attempt.universe_id == self._task.universe_id,
                                attempt.branch_def_id == self._task.branch_def_id,
                                attempt.branch_version_id == self._task.automation_branch_version,
                                attempt.branch_content_digest
                                == self._task.automation_subject_digest,
                                attempt.lifecycle
                                in {
                                    BackgroundBranchAttemptLifecycle.CLAIMED,
                                    BackgroundBranchAttemptLifecycle.RUNNING,
                                },
                                attempt.lease_expires_at is not None,
                                attempt.lease_expires_at is not None
                                and _utc(attempt.lease_expires_at) > now,
                                attempt.remaining_count > 0,
                                attempt.remaining_cost_microunits > 0,
                            )
                        ):
                            raise PermissionError("background Branch attempt is unavailable")
                        max_invocations = min(
                            attempt.remaining_count,
                            _positive_env(
                                "TINYASSETS_ASSIGNED_QUEUE_UNIVERSE_MAX_INVOCATIONS",
                                _DEFAULT_MAX_INVOCATIONS,
                            ),
                        )
                        max_tokens = _positive_env(
                            "TINYASSETS_ASSIGNED_QUEUE_UNIVERSE_MAX_TOKENS", _DEFAULT_MAX_TOKENS
                        )
                        max_cost = min(
                            attempt.remaining_cost_microunits,
                            _positive_env(
                                "TINYASSETS_ASSIGNED_QUEUE_UNIVERSE_MAX_COST_MICROUNITS",
                                _DEFAULT_MAX_COST_MICROUNITS,
                            ),
                        )
                        attempt_expiry = _utc(
                            attempt.lease_expires_at or str(row["lease_expires_at"])
                        )
                        expires_at = (
                            min(attempt_expiry, _utc(serving_binding.expires_at))
                            .isoformat()
                            .replace("+00:00", "Z")
                        )
                        seed = ProviderWorkBindingSeed(
                            owner_user_id=assignment.owner_user_id,
                            universe_id=self._task.universe_id,
                            provider=assignment.provider,
                            credential_reference_digest=custody.reference_digest,
                            allowed_operations=(BACKGROUND_BRANCH_RUN_OPERATION,),
                            allowed_roles=roles,
                            assignment_generation=assignment.generation,
                            assignment_digest=assignment.assignment_digest,
                            max_invocations=max_invocations,
                            max_tokens=max_tokens,
                            max_cost_microunits=max_cost,
                            expires_at=expires_at,
                        )
                        provider_binding = _current_background_binding(
                            conn, provider_store=provider_store, seed=seed
                        )
                        if _is_open_provider(assignment.provider):
                            snapshot = None
                        else:
                            snapshot = snapshot_llm_subscription_credential(
                                universe_dir=universe_dir,
                                custody=custody,
                            )
                        authority = ProviderUniverseWorkAuthority(
                            root=ProviderUniverseWorkRoot(
                                work_item_kind="background_attempt",
                                work_item_id=attempt.attempt_id,
                            ),
                            binding=provider_binding,
                            principal_id=binding.authorizing_principal_id,
                            actor_id=str(binding.daemon_id),
                            operation=BACKGROUND_BRANCH_RUN_OPERATION,
                            role=role,
                            allowed_roles=roles,
                            executor_class="cloud",
                            max_invocations=max_invocations,
                            max_tokens=max_tokens,
                            max_cost_microunits=max_cost,
                            expires_at=provider_binding.expires_at,
                            execution_subject=ExecutionSubject(
                                kind=ExecutionSubjectKind.BRANCH_VERSION,
                                ref=self._task.automation_branch_version,
                                digest=self._task.automation_subject_digest,
                            ),
                            branch_def_id=self._task.branch_def_id,
                            branch_version_id=self._task.automation_branch_version,
                        )
                        prompt_digest = hashlib.sha256(
                            json.dumps(
                                [role, prompt, system],
                                ensure_ascii=False,
                            ).encode("utf-8")
                        ).hexdigest()
                        invocation_key = (
                            f"background-branch:{self._task.branch_task_id}:"
                            f"{invocation_index}:{prompt_digest}"
                        )
                        token_base, token_remainder = divmod(
                            max_tokens,
                            max_invocations,
                        )
                        cost_base, cost_remainder = divmod(
                            max_cost,
                            max_invocations,
                        )
                        token_share = token_base + int(
                            invocation_index <= token_remainder
                        )
                        cost_share = cost_base + int(
                            invocation_index <= cost_remainder
                        )
                        if token_share < 1 or cost_share < 1:
                            raise PermissionError(
                                "background provider invocation budget is exhausted"
                            )
                        claim_nonce_digest = "sha256:" + hashlib.sha256(
                            json.dumps(
                                [
                                    binding.binding_id,
                                    binding.binding_digest,
                                    attempt.attempt_id,
                                    provider_binding.binding_id,
                                    self._task.branch_task_id,
                                ],
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest()
                        lease_seconds = min(
                            3600,
                            int(
                                (
                                    _utc(str(row["lease_expires_at"])) - now
                                ).total_seconds()
                            ),
                        )
                        if lease_seconds < 1:
                            raise PermissionError(
                                "background provider claim lease is expired"
                            )
                        carrier = (
                            provider_store
                            ._reserve_and_arm_background_branch_carrier_in_transaction(
                                conn,
                                authority=authority,
                                worker_id=str(binding.daemon_id),
                                runtime_id=str(binding.runtime_id),
                                claim_nonce_digest=claim_nonce_digest,
                                lease_seconds=lease_seconds,
                                invocation_key=invocation_key,
                                role=role,
                                max_tokens=token_share,
                                max_cost_microunits=cost_share,
                            )
                        )
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
                assert carrier is not None
                yield carrier, snapshot.directory if snapshot else None, assignment.provider
        except ProviderAuthorityHeldError:
            raise
        except Exception as exc:
            if carrier is not None:
                raise
            if isinstance(exc, BackgroundExecutorIdentityError):
                try:
                    terminalize_background_queue_authority(
                        self._base_path,
                        self._task,
                        status="failed",
                        reason=exc.reason,
                    )
                except Exception:  # noqa: BLE001 - preserve the primary failure reason
                    logger.exception("background authority terminal projection failed")
            else:
                try:
                    _hold_background_authority(self._base_path, self._task)
                except Exception:  # noqa: BLE001 - preserve the primary hold reason
                    logger.exception("background authority hold projection failed")
            raise ProviderAuthorityHeldError(held) from exc
        finally:
            from tinyassets.credential_vault import cleanup_llm_credential_snapshot

            cleanup_llm_credential_snapshot(snapshot)


def authorize_background_served_provider_call(
    base_path: str | Path,
    claimed_task: Epoch2BranchTask,
    consumer_lease: AssignedConsumerLease,
) -> Any:
    """Return an exact-universe provider call; actual authority is fenced per call."""

    if not isinstance(claimed_task, Epoch2BranchTask):
        raise ValueError("claimed_task must be an Epoch2BranchTask")
    if not isinstance(consumer_lease, AssignedConsumerLease):
        raise ValueError("consumer_lease must be an AssignedConsumerLease")
    if claimed_task.claimed_by != consumer_lease.consumer_id:
        raise PermissionError("consumer lease does not own the claimed task")
    try:
        from domains.fantasy_daemon.phases._provider_stub import call_provider
    except ImportError as exc:
        raise PermissionError("provider bridge is unavailable") from exc
    from tinyassets.config import load_universe_config
    from tinyassets.providers.base import UniverseContext
    from tinyassets.providers.call import UniverseBoundProviderCall

    root = Path(base_path)
    universe_dir = root / claimed_task.universe_id
    session = _BackgroundAssignedProviderSession(root, claimed_task, consumer_lease, call_provider)
    return UniverseBoundProviderCall(
        session,
        UniverseContext(
            universe_dir=universe_dir,
            config=load_universe_config(universe_dir),
        ),
        BACKGROUND_BRANCH_RUN_OPERATION,
    )


__all__ = [
    "BACKGROUND_BRANCH_RUN_OPERATION",
    "BackgroundExecutorIdentityError",
    "authorize_background_served_provider_call",
    "load_background_executor_identity",
]
