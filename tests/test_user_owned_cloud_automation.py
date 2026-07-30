from __future__ import annotations

import importlib
from dataclasses import FrozenInstanceError

import pytest

from tinyassets.background_branch_authority import (
    BackgroundBranchAttempt,
    BackgroundBranchAttemptLifecycle,
    BackgroundBranchBinding,
    BackgroundBranchBindingStatus,
    BackgroundBranchChildDelegation,
    BackgroundBranchExecutorAudience,
    BackgroundBranchExecutorClass,
    BackgroundBranchOperation,
    BackgroundBranchProvenance,
    BackgroundBranchReceiptRefs,
    BackgroundBranchSourceKind,
    BackgroundBranchTargetMode,
)
from tinyassets.evaluation.scenario_runner import AcceptanceScenario


def _automation():
    return importlib.import_module("tinyassets.user_owned_cloud_automation")


def _definition_payload() -> dict[str, object]:
    return {
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
        "input_artifact_digests": [
            f"sha256:{'d' * 64}",
            f"sha256:{'e' * 64}",
        ],
        "provider_binding_id": "provider_binding_alice",
        "destination_grant_id": "destination_grant_project",
        "destination_purpose": "pull_request",
        "max_attempts": 2,
        "max_wall_time_seconds": 3600,
        "max_tokens": 100_000,
        "max_cost_microunits": 5_000_000,
    }


def _scenario(**overrides: object) -> AcceptanceScenario:
    payload: dict[str, object] = {
        "scenario_id": "scenario:repo-spec-baseline-v1",
        "target_surface": "session_trace_summary",
        "user_story": (
            "A repository owner needs a deterministic preflight that checks "
            "immutable repository and OpenSpec evidence before any provider "
            "or GitHub effect is authorized. The preflight must be safe for "
            "multi-tenant cloud execution and preserve exact evidence."
        ),
        "allowed_tools": [],
        "evaluator_chain": ["evaluator:artifact-digest-v1"],
        "artifact_requirements": [{"kind": "content_digest", "required": True}],
        "pass_threshold": {"min_score": 1.0},
        "cost_budget": {"max_tokens": 0, "max_wall_time_seconds": 10},
        "privacy_scope": "universe_only",
        "idempotency_key_constructor": "scenario+candidate+artifact-digests",
        "setup": [],
    }
    payload.update(overrides)
    return AcceptanceScenario(**payload)  # type: ignore[arg-type]


def _binding_and_attempt() -> tuple[BackgroundBranchBinding, BackgroundBranchAttempt]:
    receipts = BackgroundBranchReceiptRefs(
        b2_execution_grant_id=None,
        provider_work_receipt_id="pwr_01",
        provider_attempt_receipt_id="pat_01",
        payment_receipt_id=None,
        effect_receipt_id="eff_01",
    )
    binding = BackgroundBranchBinding(
        schema_version=1,
        binding_id="bnd_01",
        status=BackgroundBranchBindingStatus.ACTIVE,
        generation=3,
        binding_digest=f"sha256:{'f' * 64}",
        authorizing_principal_id="acct_alice",
        universe_id="universe_alice",
        branch_def_id="branch_repo_spec_loop",
        operation=BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
        source_kind=BackgroundBranchSourceKind.REQUEST_ADMISSION,
        source_id="request_17",
        source_revision="4",
        source_digest=f"sha256:{'1' * 64}",
        revocation_generation=0,
        target_mode=BackgroundBranchTargetMode.PINNED_VERSION,
        pinned_branch_version_id="branch_repo_spec_loop@abc12345",
        permitted_executor_classes=(BackgroundBranchExecutorClass.CLOUD,),
        daemon_id=None,
        runtime_id=None,
        expires_at=None,
        max_attempts=2,
        remaining_depth=0,
        remaining_count=1,
        remaining_cost_microunits=5_000_000,
        child_delegation=BackgroundBranchChildDelegation(
            allowed_branch_def_ids=(),
            allowed_operations=(),
            max_depth=0,
            max_count=0,
            max_cost_microunits=0,
        ),
    )
    audience = BackgroundBranchExecutorAudience(
        executor_class=BackgroundBranchExecutorClass.CLOUD,
        daemon_id=None,
        runtime_id="runtime_cloud_1",
        worker_id="worker_1",
    )
    provenance = BackgroundBranchProvenance(
        authorizing_principal_id="acct_alice",
        source_kind=BackgroundBranchSourceKind.REQUEST_ADMISSION,
        source_id="request_17",
        executor_class=BackgroundBranchExecutorClass.CLOUD,
        daemon_id=None,
        runtime_id="runtime_cloud_1",
        worker_id="worker_1",
        parent_attempt_id=None,
        origin_attempt_id="att_01",
        audit_correlation_ids=("trace:17",),
        receipt_refs=receipts,
    )
    attempt = BackgroundBranchAttempt(
        schema_version=1,
        attempt_id="att_01",
        logical_attempt_key="request:17:g4",
        binding_id=binding.binding_id,
        binding_digest=binding.binding_digest,
        binding_generation=binding.generation,
        authorizing_principal_id="acct_alice",
        universe_id="universe_alice",
        branch_def_id="branch_repo_spec_loop",
        branch_version_id="branch_repo_spec_loop@abc12345",
        branch_content_digest=f"sha256:{'b' * 64}",
        operation=BackgroundBranchOperation.INVOKE_BRANCH_VERSION,
        source_kind=BackgroundBranchSourceKind.REQUEST_ADMISSION,
        source_id="request_17",
        source_generation=4,
        executor_audience=audience,
        claim_generation=2,
        lease_generation=5,
        lease_expires_at="2026-07-31T00:00:00Z",
        remaining_depth=0,
        remaining_count=1,
        remaining_cost_microunits=5_000_000,
        lifecycle=BackgroundBranchAttemptLifecycle.CLAIMED,
        hold_reason=None,
        terminal_reason=None,
        created_at="2026-07-30T20:00:00Z",
        updated_at="2026-07-30T20:01:00Z",
        provenance=provenance,
    )
    return binding, attempt


def test_work_definition_is_generic_immutable_and_content_addressed() -> None:
    automation = _automation()
    payload = _definition_payload()

    definition = automation.RepositorySpecWorkDefinition.from_dict(payload)

    assert definition.to_dict() == payload
    assert definition.definition_digest.startswith("sha256:")
    assert automation.RepositorySpecWorkDefinition.from_dict(payload) == definition
    with pytest.raises(FrozenInstanceError):
        definition.repository = "other/project"


@pytest.mark.parametrize(
    "runtime_field",
    [
        "activation_epoch",
        "lease_generation",
        "attempt_state",
        "provider_reservation_id",
        "effect_reservation_id",
        "terminal_state",
    ],
)
def test_work_definition_rejects_user_authored_runtime_authority(
    runtime_field: str,
) -> None:
    automation = _automation()
    payload = _definition_payload()
    payload[runtime_field] = "caller-controlled"

    with pytest.raises(ValueError, match="unknown fields"):
        automation.RepositorySpecWorkDefinition.from_dict(payload)


def test_admission_fails_closed_when_evaluator_can_execute_tenant_code() -> None:
    automation = _automation()
    scenario = _scenario(
        allowed_tools=["shell"],
        evaluator_chain=["evaluator:repository-tests-v1"],
    )
    payload = _definition_payload()
    payload["acceptance_scenario_digest"] = automation.acceptance_scenario_digest(
        scenario
    )
    definition = automation.RepositorySpecWorkDefinition.from_dict(payload)

    with pytest.raises(
        automation.AutomationAdmissionError,
        match="sandbox_unavailable",
    ) as exc_info:
        automation.admit_work_definition(
            definition,
            scenario,
            deterministic_evaluator_ids={"evaluator:artifact-digest-v1"},
        )

    assert exc_info.value.code == "sandbox_unavailable"


def test_admission_freezes_typed_deterministic_scenario() -> None:
    automation = _automation()
    scenario = _scenario()
    payload = _definition_payload()
    payload["acceptance_scenario_digest"] = automation.acceptance_scenario_digest(
        scenario
    )
    definition = automation.RepositorySpecWorkDefinition.from_dict(payload)

    admitted = automation.admit_work_definition(
        definition,
        scenario,
        deterministic_evaluator_ids={"evaluator:artifact-digest-v1"},
    )
    scenario.evaluator_chain.append("evaluator:mutated")

    assert admitted.definition == definition
    assert admitted.evaluator_chain == ("evaluator:artifact-digest-v1",)
    assert admitted.acceptance_scenario_digest == (
        definition.acceptance_scenario_digest
    )


def test_operational_projection_is_derived_and_read_only() -> None:
    automation = _automation()
    definition = automation.RepositorySpecWorkDefinition.from_dict(
        _definition_payload()
    )
    binding, attempt = _binding_and_attempt()

    projection = automation.project_operational_state(
        definition,
        binding=binding,
        attempt=attempt,
    )

    assert projection.definition_digest == definition.definition_digest
    assert projection.binding_generation == 3
    assert projection.binding_status == "active"
    assert projection.source_generation == 4
    assert projection.claim_generation == 2
    assert projection.lease_generation == 5
    assert projection.attempt_lifecycle == "claimed"
    assert projection.provider_work_receipt_id == "pwr_01"
    assert projection.provider_attempt_receipt_id == "pat_01"
    assert projection.effect_receipt_id == "eff_01"
    with pytest.raises(FrozenInstanceError):
        projection.binding_generation = 4


def test_operational_projection_can_show_inactive_definition() -> None:
    automation = _automation()
    definition = automation.RepositorySpecWorkDefinition.from_dict(
        _definition_payload()
    )

    projection = automation.project_operational_state(definition)

    assert projection.binding_id is None
    assert projection.attempt_id is None
    assert projection.binding_status == "inactive"


def test_operational_projection_rejects_cross_definition_attempt() -> None:
    automation = _automation()
    payload = _definition_payload()
    payload["principal_id"] = "acct_other"
    definition = automation.RepositorySpecWorkDefinition.from_dict(payload)
    binding, attempt = _binding_and_attempt()

    with pytest.raises(
        automation.AutomationProjectionError,
        match="principal",
    ):
        automation.project_operational_state(
            definition,
            binding=binding,
            attempt=attempt,
        )


def test_operational_projection_requires_binding_for_attempt() -> None:
    automation = _automation()
    definition = automation.RepositorySpecWorkDefinition.from_dict(
        _definition_payload()
    )
    _binding, attempt = _binding_and_attempt()

    with pytest.raises(
        automation.AutomationProjectionError,
        match="binding",
    ):
        automation.project_operational_state(definition, attempt=attempt)
