from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from tinyassets.cloud_automation_control import (
    CloudAutomationTerminalKind,
    CloudAutomationTerminalRequest,
    CloudAutomationTriggerFence,
    CloudAutomationTriggerStatus,
)
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.storage.automation_activations import (
    AutomationActivationExecutor,
    AutomationActivationStore,
)
from tinyassets.storage.cloud_automation_control import CloudAutomationControlStore
from tinyassets.user_owned_cloud_automation import RepositorySpecWorkDefinition

NOW = datetime(2026, 8, 3, 23, 0, tzinfo=timezone.utc)


def _definition() -> RepositorySpecWorkDefinition:
    return RepositorySpecWorkDefinition.from_dict(
        {
            "schema_version": 1,
            "principal_id": "acct_alice",
            "universe_id": "universe_alice",
            "repository": "example/project",
            "accepted_spec_ref": "openspec/specs/example/spec.md",
            "accepted_spec_digest": f"sha256:{'a' * 64}",
            "branch_def_id": "branch_repo_spec_loop",
            "branch_version_id": "branch_repo_spec_loop@abc12345",
            "branch_content_digest": f"sha256:{'b' * 64}",
            "acceptance_scenario_id": "scenario:repo-spec-baseline-v1",
            "acceptance_scenario_digest": f"sha256:{'c' * 64}",
            "input_artifact_digests": [f"sha256:{'d' * 64}"],
            "provider_binding_id": "pwb_11111111111111111111111111111111",
            "destination_grant_id": "destination_grant_project",
            "destination_purpose": "pull_request",
            "max_attempts": 2,
            "max_provider_invocations": 4,
            "max_wall_time_seconds": 3600,
            "max_tokens": 100_000,
            "max_cost_microunits": 5_000_000,
        }
    )


def _active(tmp_path, *, clock=lambda: NOW):
    definition = _definition()
    activations = AutomationActivationStore(tmp_path, clock=clock)
    stopped = activations.create_stopped(
        universe_id=definition.universe_id,
        automation_id="automation_spec_drain",
    )
    active = activations.activate(
        expected=stopped,
        executor_class=AutomationActivationExecutor.CLOUD,
        subject=ExecutionSubject(
            kind=ExecutionSubjectKind.BRANCH_VERSION,
            ref=definition.branch_version_id,
            digest=definition.branch_content_digest,
        ),
        lease_id="lease_cloud_spec_drain",
    )
    assert active is not None
    return definition, activations, active


def test_initial_trigger_is_durable_and_definition_bound(tmp_path) -> None:
    definition, _activations, active = _active(tmp_path)
    store = CloudAutomationControlStore(tmp_path, clock=lambda: NOW)

    created = store.schedule_initial(
        definition,
        automation_id="automation_spec_drain",
        activation=active,
        cadence_seconds=300,
        due_at=NOW,
    )
    replayed = store.schedule_initial(
        definition,
        automation_id="automation_spec_drain",
        activation=active,
        cadence_seconds=300,
        due_at=NOW,
    )

    assert created == replayed
    assert created.status is CloudAutomationTriggerStatus.PENDING
    assert created.slice_ordinal == 1
    assert created.activation_epoch == active.epoch
    assert created.definition_digest == definition.definition_digest
    assert created.definition == definition
    assert store.get_trigger(created.trigger_id) == created


def test_initial_trigger_rejects_stale_or_mismatched_activation(tmp_path) -> None:
    definition, activations, active = _active(tmp_path)
    stopped = activations.stop(expected=active)
    assert stopped is not None
    store = CloudAutomationControlStore(tmp_path, clock=lambda: NOW)

    with pytest.raises(PermissionError, match="activation_not_current"):
        store.schedule_initial(
            definition,
            automation_id="automation_spec_drain",
            activation=active,
            cadence_seconds=300,
            due_at=NOW,
        )


def test_concurrent_trigger_claim_has_one_winner(tmp_path) -> None:
    definition, _activations, active = _active(tmp_path)
    store = CloudAutomationControlStore(tmp_path, clock=lambda: NOW)
    pending = store.schedule_initial(
        definition,
        automation_id="automation_spec_drain",
        activation=active,
        cadence_seconds=300,
        due_at=NOW,
    )

    def claim(index: int):
        return CloudAutomationControlStore(tmp_path, clock=lambda: NOW).claim_due(
            universe_id=definition.universe_id,
            automation_id="automation_spec_drain",
            claimed_by=f"cloud-worker-{index}",
            lease_seconds=120,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))

    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    winner = winners[0]
    assert winner.trigger_id == pending.trigger_id
    assert winner.status is CloudAutomationTriggerStatus.CLAIMED
    assert winner.claimed_by.startswith("cloud-worker-")
    assert winner.claim_expires_at == "2026-08-03T23:02:00Z"


def test_terminal_receipt_schedules_exactly_one_next_trigger(tmp_path) -> None:
    definition, _activations, active = _active(tmp_path)
    store = CloudAutomationControlStore(tmp_path, clock=lambda: NOW)
    initial = store.schedule_initial(
        definition,
        automation_id="automation_spec_drain",
        activation=active,
        cadence_seconds=300,
        due_at=NOW,
    )
    claimed = store.claim_due(
        universe_id=definition.universe_id,
        automation_id="automation_spec_drain",
        claimed_by="cloud-worker-1",
        lease_seconds=120,
    )
    assert claimed is not None
    request = CloudAutomationTerminalRequest(
        terminal_kind=CloudAutomationTerminalKind.MERGED,
        branch_task_id="bt2_11111111111111111111111111111111",
        run_id="run_cloud_slice_1",
        claim_id="pwc_11111111111111111111111111111111",
        attempt_id="att_11111111111111111111111111111111",
        evidence_handles=("https://github.com/example/project/pull/1",),
        completed_at="2026-08-03T23:01:00Z",
    )

    result = store.record_terminal(CloudAutomationTriggerFence(claimed), request)
    replay = store.record_terminal(CloudAutomationTriggerFence(claimed), request)

    assert replay == result
    assert result.receipt.terminal_kind is CloudAutomationTerminalKind.MERGED
    assert result.receipt.next_action == "scheduled"
    assert result.next_trigger is not None
    assert result.next_trigger.slice_ordinal == initial.slice_ordinal + 1
    assert result.next_trigger.due_at == "2026-08-03T23:06:00Z"
    assert result.next_trigger.previous_terminal_receipt_id == result.receipt.receipt_id
    assert len(store.list_receipts(automation_id="automation_spec_drain", limit=10)) == 1
    assert len(store.list_triggers(automation_id="automation_spec_drain", limit=10)) == 2


def test_terminal_after_pause_is_recorded_without_scheduling(tmp_path) -> None:
    definition, activations, active = _active(tmp_path)
    store = CloudAutomationControlStore(tmp_path, clock=lambda: NOW)
    store.schedule_initial(
        definition,
        automation_id="automation_spec_drain",
        activation=active,
        cadence_seconds=300,
        due_at=NOW,
    )
    claimed = store.claim_due(
        universe_id=definition.universe_id,
        automation_id="automation_spec_drain",
        claimed_by="cloud-worker-1",
        lease_seconds=120,
    )
    assert claimed is not None
    stopped = activations.stop(expected=active)
    assert stopped is not None

    result = store.record_terminal(
        CloudAutomationTriggerFence(claimed),
        CloudAutomationTerminalRequest(
            terminal_kind=CloudAutomationTerminalKind.PARTIAL,
            branch_task_id="bt2_11111111111111111111111111111111",
            run_id="run_cloud_slice_1",
            claim_id="pwc_11111111111111111111111111111111",
            attempt_id="att_11111111111111111111111111111111",
            evidence_handles=("effect:already-committed",),
            completed_at="2026-08-03T23:01:00Z",
        ),
    )

    assert result.receipt.next_action == "activation_stopped"
    assert result.next_trigger is None
    assert store.list_triggers(automation_id="automation_spec_drain", limit=10) == [
        result.completed_trigger
    ]


def test_claim_refuses_expired_due_trigger_after_activation_changes(tmp_path) -> None:
    definition, activations, active = _active(tmp_path)
    store = CloudAutomationControlStore(tmp_path, clock=lambda: NOW)
    store.schedule_initial(
        definition,
        automation_id="automation_spec_drain",
        activation=active,
        cadence_seconds=300,
        due_at=NOW,
    )
    assert activations.stop(expected=active) is not None

    assert (
        store.claim_due(
            universe_id=definition.universe_id,
            automation_id="automation_spec_drain",
            claimed_by="cloud-worker-1",
            lease_seconds=120,
        )
        is None
    )


def test_claimed_trigger_can_be_reclaimed_only_after_lease_expiry(tmp_path) -> None:
    clock_now = [NOW]
    definition, _activations, active = _active(tmp_path, clock=lambda: clock_now[0])
    store = CloudAutomationControlStore(tmp_path, clock=lambda: clock_now[0])
    store.schedule_initial(
        definition,
        automation_id="automation_spec_drain",
        activation=active,
        cadence_seconds=300,
        due_at=NOW,
    )
    first = store.claim_due(
        universe_id=definition.universe_id,
        automation_id="automation_spec_drain",
        claimed_by="cloud-worker-1",
        lease_seconds=60,
    )
    assert first is not None
    assert (
        store.claim_due(
            universe_id=definition.universe_id,
            automation_id="automation_spec_drain",
            claimed_by="cloud-worker-2",
            lease_seconds=60,
        )
        is None
    )

    clock_now[0] = NOW + timedelta(seconds=61)
    reclaimed = store.claim_due(
        universe_id=definition.universe_id,
        automation_id="automation_spec_drain",
        claimed_by="cloud-worker-2",
        lease_seconds=60,
    )
    assert reclaimed is not None
    assert reclaimed.trigger_id == first.trigger_id
    assert reclaimed.generation == first.generation + 1
    assert reclaimed.claimed_by == "cloud-worker-2"
