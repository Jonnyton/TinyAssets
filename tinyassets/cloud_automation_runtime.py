"""Runtime bridge from generic persisted Triggers to bounded cloud slices."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from tinyassets.background_branch_authority import (
    BackgroundBranchExecutorAudience,
    BackgroundBranchExecutorClass,
)
from tinyassets.cloud_automation_continuation import (
    CloudContinuationActivationRequest,
    CloudContinuationWriteOutcome,
    PreparedCloudContinuationActivationService,
    advance_active_cloud_continuation,
)
from tinyassets.cloud_automation_control import (
    CloudAutomationDesiredState,
    CloudAutomationProviderClaimFence,
    CloudAutomationSliceTrigger,
    CloudAutomationTerminalKind,
    CloudAutomationTerminalRequest,
    CloudAutomationTerminalWriteResult,
    CloudAutomationTriggerFence,
    CloudAutomationTriggerStatus,
)
from tinyassets.storage.automation_activations import (
    AutomationActivationState,
    AutomationActivationStore,
)
from tinyassets.storage.background_branch_authority import (
    SQLiteBackgroundBranchAuthorityStore,
)
from tinyassets.storage.cloud_automation_continuation import (
    SQLiteCloudAutomationContinuationStore,
)
from tinyassets.storage.cloud_automation_control import CloudAutomationControlStore
from tinyassets.storage.outbound_connections import ConnectionLedger
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
)
from tinyassets.storage.request_admissions import RequestAdmissionStore


@dataclass(frozen=True, slots=True)
class CloudAutomationSliceProduction:
    trigger: CloudAutomationSliceTrigger
    request_id: str
    admission_id: str
    branch_task_id: str
    continuation_generation: int


def _terminal_kind(*, success: bool, error: str) -> CloudAutomationTerminalKind:
    lowered = error.lower()
    if success:
        return CloudAutomationTerminalKind.PARTIAL
    if "idle" in lowered or "no_work" in lowered:
        return CloudAutomationTerminalKind.IDLE
    if any(
        marker in lowered
        for marker in (
            "authority",
            "sandbox",
            "unavailable",
            "cancel_requested",
            "blocked",
        )
    ):
        return CloudAutomationTerminalKind.BLOCKED
    return CloudAutomationTerminalKind.FAILED


def record_cloud_automation_terminal(
    base_path: str | Path,
    *,
    branch_task_id: str,
    success: bool,
    error: str,
    run_id: str = "",
    evidence_handles: tuple[str, ...] = (),
    clock: Callable[[], datetime] | None = None,
) -> CloudAutomationTerminalWriteResult | None:
    """Settle an admitted Trigger after its epoch-2 task becomes terminal."""

    now_clock = clock or (lambda: datetime.now(timezone.utc))
    root = Path(base_path)
    controls = CloudAutomationControlStore(root, clock=now_clock)
    trigger = controls.get_trigger_for_task(branch_task_id)
    if trigger is None:
        return None
    exact_run_id = run_id.strip() or f"run_not_started_{branch_task_id}"
    handles = tuple(dict.fromkeys(value.strip() for value in evidence_handles if value.strip()))
    if run_id.strip():
        handles = tuple(dict.fromkeys((*handles, f"run:{run_id.strip()}")))
    if trigger.status is CloudAutomationTriggerStatus.EMITTED:
        receipt = controls.get_receipt_for_trigger(trigger.trigger_id)
        if receipt is None:
            raise RuntimeError("emitted trigger is missing terminal receipt")
        return controls.record_terminal(
            CloudAutomationTriggerFence(trigger),
            CloudAutomationTerminalRequest(
                terminal_kind=_terminal_kind(success=success, error=error),
                branch_task_id=branch_task_id,
                run_id=exact_run_id,
                claim_id=str(trigger.claim_id),
                attempt_id=receipt.attempt_id,
                evidence_handles=handles,
                completed_at=receipt.completed_at,
            ),
        )
    continuation = SQLiteCloudAutomationContinuationStore(root).get(
        universe_id=trigger.universe_id,
        automation_id=trigger.automation_id,
    )
    if continuation is None:
        raise PermissionError("prepared cloud continuation is unavailable")
    attempts = (
        SQLiteBackgroundBranchAuthorityStore(root)
        .list_attempts(
            binding_id=continuation.background_binding_id,
            after=None,
            limit=10,
        )
        .items
    )
    attempt = next(
        (
            value
            for value in attempts
            if value.source_id == trigger.request_id and value.universe_id == trigger.universe_id
        ),
        None,
    )
    if attempt is None:
        raise PermissionError("cloud background attempt is unavailable")
    now = now_clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return controls.record_terminal(
        CloudAutomationTriggerFence(trigger),
        CloudAutomationTerminalRequest(
            terminal_kind=_terminal_kind(success=success, error=error),
            branch_task_id=branch_task_id,
            run_id=exact_run_id,
            claim_id=str(trigger.claim_id),
            attempt_id=attempt.attempt_id,
            evidence_handles=handles,
            completed_at=now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        ),
    )


def reconcile_one_terminal_cloud_automation(
    base_path: str | Path,
    *,
    universe_id: str,
    clock: Callable[[], datetime] | None = None,
) -> CloudAutomationTerminalWriteResult | None:
    """Recover a task-terminal/Trigger-terminal crash window."""

    from tinyassets.runs import RUN_STATUS_COMPLETED, get_run_by_branch_task_id

    root = Path(base_path)
    controls = CloudAutomationControlStore(root, clock=clock)
    admissions = RequestAdmissionStore(root, clock=clock)
    for trigger in controls.list_admitted_triggers(
        universe_id=universe_id,
        limit=100,
    ):
        assert trigger.branch_task_id is not None
        task = admissions.get_v2_task(trigger.branch_task_id)
        if task is None or task.get("status") not in {
            "succeeded",
            "failed",
            "cancelled",
        }:
            continue
        run = get_run_by_branch_task_id(root, branch_task_id=trigger.branch_task_id)
        run_id = str((run or {}).get("run_id") or "")
        run_status = str((run or {}).get("status") or "")
        success = task["status"] == "succeeded" and run_status == RUN_STATUS_COMPLETED
        detail = task.get("detail") if isinstance(task.get("detail"), dict) else {}
        error = str(detail.get("error") or "")
        if not success and not error:
            error = f"branch_task_status:{task['status']}"
        return record_cloud_automation_terminal(
            root,
            branch_task_id=trigger.branch_task_id,
            success=success,
            error=error,
            run_id=run_id,
            clock=clock,
        )
    return None


class _ExactAudienceResolver:
    def __init__(
        self,
        audience: BackgroundBranchExecutorAudience,
        *,
        base_path: Path,
        provider_store: SQLiteProviderWorkAuthorityStore,
        universe_id: str,
    ) -> None:
        self._audience = audience
        self._base_path = base_path
        self._provider_store = provider_store
        self._universe_id = universe_id

    def resolve(self, *, continuation, branch_task_id: str):
        if continuation.universe_id != self._universe_id:
            return None
        if not branch_task_id:
            return None
        binding = self._provider_store.get(continuation.provider_binding_id)
        if binding is None:
            return None
        from tinyassets.daemon_registry import runtime_matches_worker_provider

        if not runtime_matches_worker_provider(
            self._base_path,
            universe_id=self._universe_id,
            runtime_instance_id=self._audience.runtime_id,
            daemon_id=self._audience.daemon_id,
            worker_id=self._audience.worker_id,
            provider_name=binding.provider,
        ):
            return None
        return self._audience

def produce_one_due_cloud_automation_slice(
    base_path: str | Path,
    *,
    universe_id: str,
    audience: BackgroundBranchExecutorAudience,
    principal_id: str = "",
    claim_lease_seconds: int = 120,
    clock: Callable[[], datetime] | None = None,
) -> CloudAutomationSliceProduction | None:
    """Claim and materialize at most one due Trigger for one cloud worker."""

    if not isinstance(audience, BackgroundBranchExecutorAudience):
        raise ValueError("audience must be a BackgroundBranchExecutorAudience")
    if audience.executor_class is not BackgroundBranchExecutorClass.CLOUD:
        raise ValueError("audience must be a cloud executor")
    now_clock = clock or (lambda: datetime.now(timezone.utc))
    root = Path(base_path)
    controls = CloudAutomationControlStore(root, clock=now_clock)
    provider_store = SQLiteProviderWorkAuthorityStore(root, clock=now_clock)
    continuation_store = SQLiteCloudAutomationContinuationStore(
        root,
        clock=now_clock,
    )
    automation_ids = controls.list_claimable_automation_ids(
        universe_id=universe_id,
        principal_id=principal_id,
        limit=100,
    )
    if not automation_ids:
        return None
    trigger = None
    continuation = None
    for automation_id in automation_ids:
        candidate = continuation_store.get(
            universe_id=universe_id,
            automation_id=automation_id,
        )
        if candidate is None:
            continue
        if (
            _ExactAudienceResolver(
                audience,
                base_path=root,
                provider_store=provider_store,
                universe_id=universe_id,
            ).resolve(
                continuation=candidate,
                branch_task_id="pre_claim_provider_fence",
            )
            is None
        ):
            continue
        trigger = controls.claim_due_for_worker(
            universe_id=universe_id,
            automation_id=automation_id,
            claimed_by=audience.worker_id,
            lease_seconds=claim_lease_seconds,
            provider_fence=CloudAutomationProviderClaimFence(
                provider_binding_id=candidate.provider_binding_id,
                provider_binding_generation=candidate.provider_binding_generation,
                provider_binding_digest=candidate.provider_binding_digest,
                daemon_id=audience.daemon_id,
                runtime_id=audience.runtime_id,
                worker_id=audience.worker_id,
            ),
        )
        if trigger is not None:
            continuation = candidate
            break
    if trigger is None:
        return None

    definition = trigger.definition
    activation_store = AutomationActivationStore(root, clock=now_clock)
    background_store = SQLiteBackgroundBranchAuthorityStore(root)
    if continuation is None:
        raise PermissionError("prepared cloud continuation is unavailable")
    binding = background_store.get_binding(continuation.background_binding_id)
    if binding is None or binding.daemon_id != audience.daemon_id:
        raise PermissionError("cloud worker audience does not own the continuation")
    ledger = ConnectionLedger(
        root / "outbound.db",
        verify_authenticated_principal=lambda: continuation.principal_id,
    )
    if continuation.generation + 1 == trigger.slice_ordinal:
        advanced = advance_active_cloud_continuation(
            definition,
            trigger=trigger,
            activation_store=activation_store,
            background_store=background_store,
            provider_store=provider_store,
            connection_ledger=ledger,
            continuation_store=continuation_store,
            clock=now_clock,
        )
        if (
            advanced.outcome
            not in {
                CloudContinuationWriteOutcome.APPLIED,
                CloudContinuationWriteOutcome.REPLAYED,
            }
            or advanced.record is None
        ):
            raise PermissionError("next cloud continuation could not advance")
        continuation = advanced.record
    elif continuation.generation != trigger.slice_ordinal:
        raise PermissionError("Trigger ordinal does not match continuation generation")

    activation = activation_store.get(trigger.universe_id, trigger.automation_id)
    if activation is None or activation.lease_id is None:
        raise PermissionError("cloud automation activation is unavailable")
    result = PreparedCloudContinuationActivationService(
        definition,
        continuation=continuation,
        activation_store=activation_store,
        background_store=background_store,
        provider_store=provider_store,
        connection_ledger=ledger,
        continuation_store=continuation_store,
        request_admission_store=RequestAdmissionStore(root, clock=now_clock),
        audience_resolver=_ExactAudienceResolver(
            audience,
            base_path=root,
            provider_store=provider_store,
            universe_id=trigger.universe_id,
        ),
        clock=now_clock,
    ).activate(CloudContinuationActivationRequest(lease_id=activation.lease_id))
    admitted = controls.bind_admission(
        CloudAutomationTriggerFence(trigger),
        request_id=result.request_id,
        admission_id=result.admission_id,
        branch_task_id=result.branch_task_id,
    )
    return CloudAutomationSliceProduction(
        trigger=admitted,
        request_id=result.request_id,
        admission_id=result.admission_id,
        branch_task_id=result.branch_task_id,
        continuation_generation=continuation.generation,
    )


def activate_one_requested_cloud_automation(
    base_path: str | Path,
    *,
    universe_id: str,
    audience: BackgroundBranchExecutorAudience,
    principal_id: str = "",
    claim_lease_seconds: int = 120,
    clock: Callable[[], datetime] | None = None,
) -> CloudAutomationSliceProduction | None:
    """Converge one prepared owner request into its first admitted cloud slice."""

    if not isinstance(audience, BackgroundBranchExecutorAudience):
        raise ValueError("audience must be a BackgroundBranchExecutorAudience")
    if audience.executor_class is not BackgroundBranchExecutorClass.CLOUD:
        raise ValueError("audience must be a cloud executor")
    now_clock = clock or (lambda: datetime.now(timezone.utc))
    root = Path(base_path)
    controls = CloudAutomationControlStore(root, clock=now_clock)
    activation_store = AutomationActivationStore(root, clock=now_clock)
    background_store = SQLiteBackgroundBranchAuthorityStore(root)
    provider_store = SQLiteProviderWorkAuthorityStore(root, clock=now_clock)
    continuation_store = SQLiteCloudAutomationContinuationStore(root, clock=now_clock)
    admission_store = RequestAdmissionStore(root, clock=now_clock)
    for control in controls.list_controls(universe_id=universe_id, limit=100):
        if principal_id and control.principal_id != principal_id:
            continue
        if control.desired_state is not CloudAutomationDesiredState.ACTIVE:
            continue
        current_control = controls.get_control(
            universe_id=universe_id,
            automation_id=control.automation_id,
        )
        if (
            current_control != control
            or current_control.desired_state is not CloudAutomationDesiredState.ACTIVE
        ):
            continue
        continuation = continuation_store.get(
            universe_id=universe_id,
            automation_id=control.automation_id,
        )
        if continuation is None:
            continue
        binding = background_store.get_binding(continuation.background_binding_id)
        if binding is None or binding.daemon_id != audience.daemon_id:
            continue
        triggers = controls.list_triggers(
            automation_id=control.automation_id,
            limit=100,
        )
        initial = next(
            (
                value
                for value in triggers
                if value.slice_ordinal == 1
                and value.activation_epoch == continuation.activation_epoch + 1
            ),
            None,
        )
        activation = activation_store.get(universe_id, control.automation_id)
        if activation is None:
            continue
        if (
            activation.state is AutomationActivationState.ACTIVE
            and activation.lease_id is not None
        ):
            lease_id = activation.lease_id
        else:
            lease_seed = (
                f"{universe_id}:{control.automation_id}:{activation.epoch + 1}:"
                f"{control.definition_digest}"
            )
            lease_id = (
                "lease_cloud_"
                + hashlib.sha256(lease_seed.encode("utf-8")).hexdigest()[:32]
            )
        ledger = ConnectionLedger(
            root / "outbound.db",
            verify_authenticated_principal=lambda: control.principal_id,
        )
        result = PreparedCloudContinuationActivationService(
            control.definition,
            continuation=continuation,
            activation_store=activation_store,
            background_store=background_store,
            provider_store=provider_store,
            connection_ledger=ledger,
            continuation_store=continuation_store,
            request_admission_store=admission_store,
            audience_resolver=_ExactAudienceResolver(
                audience,
                base_path=root,
                provider_store=provider_store,
                universe_id=universe_id,
            ),
            clock=now_clock,
        ).activate(CloudContinuationActivationRequest(lease_id=lease_id))
        if initial is None:
            initial = controls.schedule_initial(
                control.definition,
                automation_id=control.automation_id,
                activation=result.activation,
                cadence_seconds=control.cadence_seconds,
                due_at=now_clock(),
            )
        if initial.status is CloudAutomationTriggerStatus.PENDING:
            initial = controls.claim_due_for_worker(
                universe_id=universe_id,
                automation_id=control.automation_id,
                claimed_by=audience.worker_id,
                lease_seconds=claim_lease_seconds,
                provider_fence=CloudAutomationProviderClaimFence(
                    provider_binding_id=continuation.provider_binding_id,
                    provider_binding_generation=continuation.provider_binding_generation,
                    provider_binding_digest=continuation.provider_binding_digest,
                    daemon_id=audience.daemon_id,
                    runtime_id=audience.runtime_id,
                    worker_id=audience.worker_id,
                ),
            )
        if initial is None:
            continue
        if initial.status is CloudAutomationTriggerStatus.CLAIMED:
            if initial.claimed_by != audience.worker_id:
                continue
            initial = controls.bind_admission(
                CloudAutomationTriggerFence(initial),
                request_id=result.request_id,
                admission_id=result.admission_id,
                branch_task_id=result.branch_task_id,
            )
        if initial.status is not CloudAutomationTriggerStatus.ADMITTED:
            continue
        return CloudAutomationSliceProduction(
            trigger=initial,
            request_id=result.request_id,
            admission_id=result.admission_id,
            branch_task_id=result.branch_task_id,
            continuation_generation=continuation.generation,
        )
    return None


__all__ = [
    "activate_one_requested_cloud_automation",
    "CloudAutomationSliceProduction",
    "produce_one_due_cloud_automation_slice",
    "reconcile_one_terminal_cloud_automation",
    "record_cloud_automation_terminal",
]
