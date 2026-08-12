"""User-owned preparation for an ordinary recurring cloud Branch."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import rfc8785

from tinyassets.background_branch_authority import (
    BackgroundBranchChildDelegation,
    BackgroundBranchExecutorClass,
    BackgroundBranchOperation,
    BackgroundBranchSourceKind,
    BackgroundBranchTargetMode,
)
from tinyassets.background_branch_authority_service import (
    BackgroundBranchBindingRoot,
    BackgroundBranchBindingSeed,
    BackgroundBranchBindingTransitionService,
)
from tinyassets.cloud_automation_continuation import (
    CloudContinuationWriteOutcome,
    CloudContinuationWriteResult,
    PreparedCloudContinuationRequest,
    prepare_inactive_cloud_continuation,
)
from tinyassets.cloud_automation_control import CloudAutomationControl
from tinyassets.daemon_registry import create_daemon, select_project_loop_daemon
from tinyassets.storage.automation_activations import AutomationActivationStore
from tinyassets.storage.background_branch_authority import (
    SQLiteBackgroundBranchAuthorityStore,
)
from tinyassets.storage.cloud_automation_continuation import (
    SQLiteCloudAutomationContinuationStore,
)
from tinyassets.storage.cloud_automation_control import CloudAutomationControlStore
from tinyassets.storage.cloud_automation_inputs import load_accepted_spec
from tinyassets.storage.outbound_connections import ConnectionLedger
from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore
from tinyassets.user_owned_cloud_automation import (
    RepositorySpecWorkDefinition,
    admit_work_definition,
    repository_spec_baseline_scenario,
    resolve_inactive_cloud_authority,
)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _request_id(definition: RepositorySpecWorkDefinition, automation_id: str) -> str:
    payload = rfc8785.dumps(
        {
            "domain": "cloud-automation-initial-request-v1",
            "automation_id": automation_id,
            "definition_digest": definition.definition_digest,
            "universe_id": definition.universe_id,
        }
    )
    return f"req_{hashlib.sha256(payload).hexdigest()[:32]}"


def _admission_body(
    definition: RepositorySpecWorkDefinition,
    *,
    daemon_id: str,
) -> dict[str, Any]:
    return {
        "branch_id": definition.branch_def_id,
        "directed_daemon_id": daemon_id,
        "directed_daemon_instruction": "",
        "pickup_incentive": "",
        "priority_weight": 100,
        "request_type": "run_branch",
        "schema_version": "request-admission-v2",
        "text": "Continue the accepted repository specification.",
        "universe_id": definition.universe_id,
    }


@dataclass(frozen=True, slots=True)
class CloudAutomationSetupResult:
    control: CloudAutomationControl
    daemon_id: str
    continuation_id: str
    background_binding_id: str
    activation_epoch: int


def prepare_cloud_automation(
    base_path: str | Path,
    definition: RepositorySpecWorkDefinition,
    *,
    automation_id: str,
    cadence_seconds: int,
    operator_display_name: str,
    operator_soul_text: str,
    expected_control: CloudAutomationControl | None = None,
    clock: Callable[[], datetime] | None = None,
) -> CloudAutomationSetupResult:
    """Prepare a stopped activation for the universe's assigned executor."""

    if not isinstance(definition, RepositorySpecWorkDefinition):
        raise ValueError("definition must be a RepositorySpecWorkDefinition")
    clean_automation_id = automation_id.strip()
    if not clean_automation_id:
        raise ValueError("automation_id is required")
    if not isinstance(cadence_seconds, int) or isinstance(cadence_seconds, bool):
        raise ValueError("cadence_seconds must be an integer")
    if cadence_seconds < 60:
        raise ValueError("cadence_seconds must be at least 60")
    if expected_control is not None:
        if not isinstance(expected_control, CloudAutomationControl):
            raise ValueError("expected_control must be a CloudAutomationControl")
        if (
            expected_control.automation_id != clean_automation_id
            or expected_control.universe_id != definition.universe_id
            or expected_control.principal_id != definition.principal_id
            or expected_control.desired_state.value != "stopped"
        ):
            raise ValueError("automation must be stopped by its owner before rebind")
        cadence_seconds = expected_control.cadence_seconds
    root = Path(base_path)
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    now = now.astimezone(timezone.utc)

    load_accepted_spec(
        root,
        accepted_spec_ref=definition.accepted_spec_ref,
        expected_digest=definition.accepted_spec_digest,
    )
    admit_work_definition(definition, repository_spec_baseline_scenario())

    provider_store = SQLiteProviderWorkAuthorityStore(root, clock=lambda: now)
    ledger = ConnectionLedger(
        root / "outbound.db",
        verify_authenticated_principal=lambda: definition.principal_id,
    )
    resolve_inactive_cloud_authority(
        definition,
        provider_store=provider_store,
        connection_ledger=ledger,
    )
    from tinyassets.branch_versions import get_branch_version

    branch_version = get_branch_version(root, definition.branch_version_id)
    if branch_version is None:
        raise ValueError("immutable Branch version does not exist")
    if not all(
        (
            branch_version.branch_def_id == definition.branch_def_id,
            branch_version.status == "active",
            f"sha256:{branch_version.content_hash}" == definition.branch_content_digest,
        )
    ):
        raise ValueError("immutable Branch version does not match the definition")
    snapshot = branch_version.snapshot
    version_author = (snapshot.get("author") or "").strip()
    version_visibility = (snapshot.get("visibility") or "").strip()
    if not version_author or version_visibility not in {"public", "private"}:
        # Pre-authority snapshots cannot prove who may execute their contents.
        # Republish them with an authority-bearing immutable snapshot instead of
        # consulting a mutable current Branch definition.
        raise ValueError("immutable Branch version does not exist")
    if version_visibility == "private" and version_author != definition.principal_id:
        raise ValueError("immutable Branch version does not exist")

    daemon = select_project_loop_daemon(
        root,
        universe_id=definition.universe_id,
        owner_user_id=definition.principal_id,
    )
    if daemon is None:
        soul_text = operator_soul_text.strip()
        if not soul_text:
            raise ValueError("operator.soul_text is required for the first universe loop")
        daemon = create_daemon(
            root,
            display_name=(
                operator_display_name.strip()
                or f"{definition.universe_id} cloud workflow operator"
            ),
            created_by=definition.principal_id,
            soul_mode="soul",
            soul_text=soul_text,
            domain_claims=["user-authored-workflows"],
            metadata={
                "project_loop_default": True,
                "universe_id": definition.universe_id,
                "cloud_user_owned": True,
            },
        )
    daemon_id = str(daemon["daemon_id"])

    activation_store = AutomationActivationStore(root, clock=lambda: now)
    activation = activation_store.create_stopped(
        universe_id=definition.universe_id,
        automation_id=clean_automation_id,
    )
    if activation.state.value != "stopped":
        raise ValueError("automation is already active")

    request_id = _request_id(definition, clean_automation_id)
    body = _admission_body(definition, daemon_id=daemon_id)
    body_digest = f"sha256:{hashlib.sha256(rfc8785.dumps(body)).hexdigest()}"
    expires_at = _timestamp(
        now + timedelta(seconds=max(86_400, definition.max_wall_time_seconds + 900))
    )

    class _InitialBindingResolver:
        def resolve(self, source: BackgroundBranchBindingRoot):
            if (
                source.source_kind is not BackgroundBranchSourceKind.REQUEST_ADMISSION
                or source.source_id != request_id
            ):
                return None
            return BackgroundBranchBindingSeed(
                authorizing_principal_id=definition.principal_id,
                universe_id=definition.universe_id,
                branch_def_id=definition.branch_def_id,
                operation=BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
                source_kind=BackgroundBranchSourceKind.REQUEST_ADMISSION,
                source_id=request_id,
                source_revision="1",
                source_digest=body_digest,
                target_mode=BackgroundBranchTargetMode.PINNED_VERSION,
                pinned_branch_version_id=definition.branch_version_id,
                permitted_executor_classes=(BackgroundBranchExecutorClass.CLOUD,),
                daemon_id=daemon_id,
                runtime_id=None,
                expires_at=expires_at,
                max_attempts=definition.max_attempts,
                remaining_depth=1,
                remaining_count=definition.max_attempts,
                remaining_cost_microunits=definition.max_cost_microunits,
                child_delegation=BackgroundBranchChildDelegation(
                    allowed_branch_def_ids=(),
                    allowed_operations=(),
                    max_depth=0,
                    max_count=0,
                    max_cost_microunits=0,
                ),
            )

    background_store = SQLiteBackgroundBranchAuthorityStore(root)
    binding_result = BackgroundBranchBindingTransitionService(
        background_store,
        _InitialBindingResolver(),
    ).create(
        BackgroundBranchBindingRoot(
            source_kind=BackgroundBranchSourceKind.REQUEST_ADMISSION,
            source_id=request_id,
        )
    )
    binding = binding_result.record
    if binding is None:
        raise RuntimeError("cloud automation background binding was not created")
    continuation_store = SQLiteCloudAutomationContinuationStore(root, clock=lambda: now)
    current_continuation = continuation_store.get(
        universe_id=definition.universe_id,
        automation_id=clean_automation_id,
    )
    if (
        expected_control is not None
        and current_continuation is not None
        and current_continuation.definition_digest
        != expected_control.definition_digest
        and (
            current_continuation.definition_digest != definition.definition_digest
            or current_continuation.branch_version_id != definition.branch_version_id
        )
    ):
        raise PermissionError("a different immutable rebind is already prepared")
    if (
        expected_control is not None
        and current_continuation is not None
        and current_continuation.definition_digest == definition.definition_digest
        and current_continuation.branch_version_id == definition.branch_version_id
    ):
        prepared = CloudContinuationWriteResult(
            CloudContinuationWriteOutcome.REPLAYED,
            current_continuation,
        )
    else:
        prepared = prepare_inactive_cloud_continuation(
            definition,
            request=PreparedCloudContinuationRequest(
                automation_id=clean_automation_id,
                background_binding_id=binding.binding_id,
            ),
            activation_store=activation_store,
            background_store=background_store,
            provider_store=provider_store,
            connection_ledger=ledger,
            continuation_store=continuation_store,
            expected_current=(
                current_continuation if expected_control is not None else None
            ),
            clock=lambda: now,
        )
    if prepared.outcome not in {
        CloudContinuationWriteOutcome.APPLIED,
        CloudContinuationWriteOutcome.REPLAYED,
    } or prepared.record is None:
        raise ValueError("cloud automation continuation conflicts with existing setup")
    control_store = CloudAutomationControlStore(root, clock=lambda: now)
    control = (
        control_store.create_control(
            definition,
            automation_id=clean_automation_id,
            cadence_seconds=cadence_seconds,
        )
        if expected_control is None
        else control_store.rebind_control(
            expected=expected_control,
            definition=definition,
        )
    )
    return CloudAutomationSetupResult(
        control=control,
        daemon_id=daemon_id,
        continuation_id=prepared.record.continuation_id,
        background_binding_id=binding.binding_id,
        activation_epoch=activation.epoch,
    )


__all__ = ["CloudAutomationSetupResult", "prepare_cloud_automation"]
