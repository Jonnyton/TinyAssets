"""Assigned-provider authority for daemon-owned background Branch execution."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from tinyassets.background_branch_authority import BackgroundBranchBindingStatus
from tinyassets.branch_tasks_v2 import AssignedConsumerLease, Epoch2BranchTask
from tinyassets.provider_assignment import (
    ServedProviderAuthority,
    load_provider_assignment_in_transaction,
    provider_assignment_admission,
)
from tinyassets.provider_work_authority import (
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBindingFence,
    ProviderWorkBindingRoot,
    ProviderWorkBindingSeed,
    ProviderWorkBindingService,
    ProviderWorkBindingState,
)

BACKGROUND_BRANCH_RUN_OPERATION = "background_branch_run"
_DEFAULT_MAX_INVOCATIONS = 64
_DEFAULT_MAX_TOKENS = 250_000
_DEFAULT_MAX_COST_MICROUNITS = 25_000_000
_SUPPORTED_BRANCH_ROLES = frozenset({"writer", "judge", "extract", "embed"})
logger = logging.getLogger(__name__)


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


def _ensure_reservation_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assigned_queue_provider_reservations (
            reservation_id TEXT PRIMARY KEY,
            branch_task_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            budget_owner TEXT NOT NULL,
            provider_binding_id TEXT NOT NULL,
            provider_binding_generation INTEGER NOT NULL,
            provider_binding_digest TEXT NOT NULL,
            operation TEXT NOT NULL,
            role TEXT NOT NULL,
            max_tokens INTEGER NOT NULL,
            max_cost_microunits INTEGER NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(branch_task_id, reservation_id)
        )
        """
    )


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
            ) as authority:
                from tinyassets.config import load_universe_config
                from tinyassets.providers.base import UniverseContext

                universe_dir = self._base_path / self._task.universe_id
                call_kwargs = dict(kwargs)
                call_kwargs.update(
                    operation=BACKGROUND_BRANCH_RUN_OPERATION,
                    universe_context=UniverseContext(
                        universe_dir=universe_dir,
                        config=load_universe_config(universe_dir),
                        served_provider=authority,
                    ),
                )
                result = self._provider_call(
                    prompt, system, role=role, config=config, **call_kwargs
                )
                self._call_index = invocation_index
                return result, authority.provider

    def _arm_launch(
        self,
        *,
        reservation_id: str,
        logical_attempt_key: str,
        expected_attempt: Any,
        expected_binding: Any,
        expected_provider_binding: Any,
        expected_assignment: Any,
        expected_custody: Any,
        agent: dict[str, Any],
        role: str,
    ) -> None:
        """Final exact CAS immediately before the provider boundary."""

        from tinyassets.provider_assignment import load_provider_assignment_in_transaction
        from tinyassets.provider_serving_binding import _current_serving_authority
        from tinyassets.storage.background_branch_authority import (
            SQLiteBackgroundBranchAuthorityStore,
        )
        from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore
        from tinyassets.storage.request_admissions import RequestAdmissionStore

        admission_store = RequestAdmissionStore(self._base_path)
        provider_store = SQLiteProviderWorkAuthorityStore(self._base_path)
        universe_dir = self._base_path / self._task.universe_id
        with admission_store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                task = conn.execute(
                    "SELECT * FROM branch_tasks_v2 WHERE branch_task_id=? LIMIT 1",
                    (self._task.branch_task_id,),
                ).fetchone()
                if task is None or not all(
                    (
                        task["status"] in {"running", "cancel_requested"},
                        task["claimed_by"] == self._consumer_lease.consumer_id,
                        task["claimed_at"] == self._task.claimed_at,
                        _utc(str(task["lease_expires_at"])) > datetime.now(timezone.utc),
                        task["automation_activation_epoch"]
                        == self._task.automation_activation_epoch,
                        task["automation_subject_ref"] == self._task.automation_subject_ref,
                        task["automation_subject_digest"] == self._task.automation_subject_digest,
                    )
                ):
                    raise PermissionError("task authority changed before launch")
                activation = conn.execute(
                    "SELECT * FROM automation_activations "
                    "WHERE universe_id=? AND automation_id=? LIMIT 1",
                    (self._task.universe_id, self._task.automation_id),
                ).fetchone()
                if activation is None or not all(
                    (
                        activation["state"] == "active",
                        activation["epoch"] == self._task.automation_activation_epoch,
                        activation["subject_ref"] == self._task.automation_subject_ref,
                        activation["subject_digest"] == self._task.automation_subject_digest,
                        activation["immutable_branch_version"]
                        == self._task.automation_branch_version,
                        activation["lease_id"] == self._task.automation_lease_id,
                    )
                ):
                    raise PermissionError("automation authority changed before launch")
                # Re-validate the immutable Branch version at the launch fence (Codex #3,
                # #2516). branch_versions lives in a SEPARATE DB (runs_db) from this
                # admission CAS, so it cannot be locked in the same transaction — but
                # re-reading it HERE, in the before_provider_launch fence, narrows the
                # rollback TOCTOU from the whole snapshot-creation window to this fence: a
                # version concurrently flipped to rolled_back (or a digest/branch change)
                # fails closed before the provider is launched, instead of the earlier
                # one-time check going stale.
                _branch_roles(self._base_path, self._task)
                assignment = load_provider_assignment_in_transaction(
                    conn, universe_id=self._task.universe_id
                )
                current_assignment, _serving_binding, custody = _current_serving_authority(
                    conn,
                    store=provider_store,
                    universe_dir=universe_dir,
                    owner_user_id=expected_assignment.owner_user_id,
                    universe_id=self._task.universe_id,
                    agent=agent,
                )
                background = SQLiteBackgroundBranchAuthorityStore.read_authority_in_transaction(
                    conn, logical_attempt_key=logical_attempt_key
                )
                authority_owner = (
                    SQLiteBackgroundBranchAuthorityStore.read_queue_owner_in_transaction(
                        conn, owner_id=self._task.branch_task_id
                    )
                )
                if (
                    assignment != expected_assignment
                    or current_assignment != expected_assignment
                    or custody != expected_custody
                    or background != (expected_binding, expected_attempt)
                    or authority_owner is None
                    or authority_owner.state.value == "target_authority_held"
                    or authority_owner.binding is None
                    or authority_owner.attempt is None
                    or authority_owner.binding.expected_record != expected_binding
                    or authority_owner.attempt.expected_record != expected_attempt
                    or not provider_store.validate_in_transaction(
                        conn,
                        binding_id=expected_provider_binding.binding_id,
                        binding_generation=expected_provider_binding.generation,
                        binding_digest=expected_provider_binding.binding_digest,
                        owner_user_id=expected_assignment.owner_user_id,
                        universe_id=self._task.universe_id,
                        provider=expected_assignment.provider,
                        operation=BACKGROUND_BRANCH_RUN_OPERATION,
                        role=role,
                    )
                ):
                    raise PermissionError("provider authority changed before launch")
                cursor = conn.execute(
                    "UPDATE assigned_queue_provider_reservations "
                    "SET state='launch_started' WHERE reservation_id=? "
                    "AND state='reserved'",
                    (reservation_id,),
                )
                if cursor.rowcount != 1:
                    raise PermissionError("provider reservation is not launchable")
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _arm_launch_or_hold(self, **kwargs: Any) -> None:
        from tinyassets.exceptions import ProviderAuthorityHeldError

        try:
            self._arm_launch(**kwargs)
        except Exception as exc:
            try:
                _hold_background_authority(self._base_path, self._task)
            except Exception:  # noqa: BLE001 - retain the original authority failure
                logger.exception("background authority hold projection failed")
            raise ProviderAuthorityHeldError(
                "Assigned background provider authority changed before launch."
            ) from exc

    @contextmanager
    def _authorize_launch(
        self,
        *,
        role: str,
        prompt: str,
        system: str,
        invocation_index: int,
        declared_providers: set[str],
    ) -> Iterator[ServedProviderAuthority]:
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
        authority = None
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
                        authority_owner = background_store.read_queue_owner_in_transaction(
                            conn, owner_id=self._task.branch_task_id
                        )
                        if (
                            authority_owner is None
                            or authority_owner.state.value == "target_authority_held"
                            or authority_owner.binding is None
                            or authority_owner.attempt is None
                            or authority_owner.binding.expected_record != binding
                            or authority_owner.attempt.expected_record != attempt
                        ):
                            raise PermissionError("background queue authority is held or stale")
                        if not all(
                            (
                                binding.status is BackgroundBranchBindingStatus.ACTIVE,
                                attempt.binding_id == binding.binding_id,
                                attempt.binding_generation == binding.generation,
                                attempt.binding_digest == binding.binding_digest,
                                attempt.authorizing_principal_id == assignment.owner_user_id,
                                attempt.universe_id == self._task.universe_id,
                                attempt.branch_def_id == self._task.branch_def_id,
                                attempt.branch_version_id == self._task.automation_branch_version,
                                attempt.branch_content_digest
                                == self._task.automation_subject_digest,
                                attempt.lifecycle.value
                                not in {
                                    "authority_held",
                                    "target_authority_held",
                                    "revoked",
                                    "expired",
                                    "succeeded",
                                    "failed",
                                    "cancelled",
                                },
                                attempt.lease_expires_at is None
                                or _utc(attempt.lease_expires_at) > now,
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
                        _ensure_reservation_schema(conn)
                        prompt_digest = hashlib.sha256(
                            json.dumps([role, prompt, system], ensure_ascii=False).encode("utf-8")
                        ).hexdigest()
                        reservation_id = (
                            f"aqpr_{self._task.branch_task_id}_{invocation_index}_"
                            f"{prompt_digest[:16]}"
                        )
                        budget_owner = (
                            f"universe:{self._task.universe_id}:{BACKGROUND_BRANCH_RUN_OPERATION}"
                        )
                        token_share = max(1, max_tokens // max_invocations)
                        cost_share = max(1, max_cost // max_invocations)
                        existing = conn.execute(
                            "SELECT state FROM assigned_queue_provider_reservations "
                            "WHERE reservation_id=?",
                            (reservation_id,),
                        ).fetchone()
                        if existing is not None and existing["state"] != "reserved":
                            raise PermissionError("background provider launch is already armed")
                        if existing is not None:
                            conn.execute(
                                "DELETE FROM assigned_queue_provider_reservations "
                                "WHERE reservation_id=? AND state='reserved'",
                                (reservation_id,),
                            )
                        totals = conn.execute(
                            """
                            SELECT COUNT(*), COALESCE(SUM(max_tokens),0),
                                   COALESCE(SUM(max_cost_microunits),0)
                            FROM assigned_queue_provider_reservations
                            WHERE budget_owner=? AND operation=?
                            """,
                            (budget_owner, BACKGROUND_BRANCH_RUN_OPERATION),
                        ).fetchone()
                        if (
                            int(totals[0]) >= max_invocations
                            or int(totals[1]) + token_share > max_tokens
                            or int(totals[2]) + cost_share > max_cost
                        ):
                            raise PermissionError("background provider budget is exhausted")
                        conn.execute(
                            """
                            INSERT INTO assigned_queue_provider_reservations VALUES
                            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?)
                            """,
                            (
                                reservation_id,
                                self._task.branch_task_id,
                                attempt.attempt_id,
                                budget_owner,
                                provider_binding.binding_id,
                                provider_binding.generation,
                                provider_binding.binding_digest,
                                BACKGROUND_BRANCH_RUN_OPERATION,
                                role,
                                token_share,
                                cost_share,
                                now.isoformat(),
                            ),
                        )
                        if _is_open_provider(assignment.provider):
                            snapshot = None
                            authority_kind = "connection_grant"
                            service = "http"
                            snapshot_generation = custody.generation
                            snapshot_digest = custody.reference_digest
                        else:
                            snapshot = snapshot_llm_subscription_credential(
                                universe_dir=universe_dir, custody=custody
                            )
                            authority_kind = "subscription_snapshot"
                            service = {"codex": "codex", "claude-code": "claude"}.get(
                                assignment.provider, ""
                            )
                            if not service:
                                raise PermissionError("assigned provider is unsupported")
                            snapshot_generation = snapshot.generation
                            snapshot_digest = snapshot.reference_digest
                        conn.execute(
                            "UPDATE assigned_queue_provider_reservations "
                            "SET state='launch_started' "
                            "WHERE reservation_id=? AND state='reserved'",
                            (reservation_id,),
                        )
                        conn.execute(
                            "UPDATE assigned_queue_provider_reservations "
                            "SET state='reserved' WHERE reservation_id=? "
                            "AND state='launch_started'",
                            (reservation_id,),
                        )
                        authority = ServedProviderAuthority(
                            authority_kind=authority_kind,
                            provider=assignment.provider,
                            max_invocations=max_invocations,
                            request_max_invocations=0,
                            max_tokens=token_share,
                            max_cost_microunits=cost_share,
                            owner_user_id=assignment.owner_user_id,
                            universe_id=self._task.universe_id,
                            agent_binding_id=str(agent["binding_id"]),
                            binding_revision=int(agent["revision"]),
                            binding_id=provider_binding.binding_id,
                            binding_generation=provider_binding.generation,
                            binding_digest=provider_binding.binding_digest,
                            credential_reference_id=custody.reference_id,
                            credential_reference_generation=snapshot_generation,
                            credential_reference_digest=snapshot_digest,
                            credential_service=service,
                            credential_snapshot_dir=(snapshot.directory if snapshot else None),
                            request_capability=None,
                            operation=BACKGROUND_BRANCH_RUN_OPERATION,
                            allowed_roles=roles,
                            budget_owner="background_attempt",
                            before_provider_launch=lambda: self._arm_launch_or_hold(
                                reservation_id=reservation_id,
                                logical_attempt_key=logical_key,
                                expected_attempt=attempt,
                                expected_binding=binding,
                                expected_provider_binding=provider_binding,
                                expected_assignment=assignment,
                                expected_custody=custody,
                                agent=agent,
                                role=role,
                            ),
                        )
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
                yield authority
        except ProviderAuthorityHeldError:
            raise
        except Exception as exc:
            if authority is not None:
                raise
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
    "authorize_background_served_provider_call",
]
