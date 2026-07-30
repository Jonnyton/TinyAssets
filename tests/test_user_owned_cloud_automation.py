from __future__ import annotations

import importlib
from dataclasses import FrozenInstanceError

import pytest

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
