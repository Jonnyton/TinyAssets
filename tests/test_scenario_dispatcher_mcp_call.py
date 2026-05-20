"""End-to-end test for the mcp_call dispatcher (Slice 3 of the lane).

Tests the full AcceptanceScenario path against a real platform action
handler — `_action_goal_propose` from `workflow.api.market`. The
scenario specifies a Goal-propose invocation; the dispatcher invokes
the handler; the evaluator chain confirms the response shape; the
runner wraps the result into a standard EvalResult.

This is the smallest realistic end-to-end test of the AcceptanceScenario
runtime per the Slice 1 design's recommendation.
"""

from __future__ import annotations

import json

import pytest

from workflow.api.market import _action_goal_propose
from workflow.evaluation.scenario_dispatchers.mcp_call import (
    mcp_call_dispatcher,
    register as register_mcp_call_dispatcher,
)
from workflow.evaluation.scenario_runner import (
    AcceptanceScenario,
    registered_dispatchers,
    run_scenario,
    unregister_dispatcher,
)


@pytest.fixture(autouse=True)
def _clean_dispatcher_registry():
    """Each test starts + ends with an empty scenario_runner registry."""
    yield
    for target_surface in list(registered_dispatchers().keys()):
        unregister_dispatcher(target_surface)


def _goals_propose_scenario(scenario_id: str = "scenario:goals-propose-happy-path-v1") -> AcceptanceScenario:
    return AcceptanceScenario(
        scenario_id=scenario_id,
        target_surface="mcp_call",
        user_story=(
            "A user opens their MCP-connected chatbot and asks to propose "
            "a new Goal for a side project. The chatbot calls "
            "goals action=propose with a name, the platform creates the "
            "Goal record + commits it, and the response carries "
            "status=proposed plus the saved Goal data so the chatbot can "
            "confirm the proposal in plain language. The acceptance check "
            "verifies the saved record + status."
        ),
        allowed_tools=["goals", "universe"],
        evaluator_chain=["evaluator:goal-record-shape-check"],
        artifact_requirements=[
            {"kind": "packet", "scope": "final", "redact_pattern": None}
        ],
        pass_threshold={"min_score": 0.75, "score_aggregation": "mean"},
        cost_budget={"max_tokens": 4000, "max_wall_time_seconds": 60},
        privacy_scope="commons_publishable",
        idempotency_key_constructor="sha256({scenario_id}|{candidate_ref}|{date_hour})",
    )


def _goal_record_shape_evaluator(parsed_response: dict) -> dict:
    """Slice 3 evaluator: verify goals.propose returned a valid Goal record."""
    if "error" in parsed_response or parsed_response.get("status") == "rejected":
        return {
            "score": 0.0,
            "label": "goal-record-shape-check",
            "details": {"verified": False, "reason": "error_or_rejected"},
        }
    if parsed_response.get("status") != "proposed":
        return {
            "score": 0.0,
            "label": "goal-record-shape-check",
            "details": {
                "verified": False,
                "reason": f"unexpected status {parsed_response.get('status')!r}",
            },
        }
    goal = parsed_response.get("goal") or {}
    has_required_fields = bool(goal.get("name")) and "visibility" in goal
    return {
        "score": 1.0 if has_required_fields else 0.5,
        "label": "goal-record-shape-check",
        "details": {
            "verified": has_required_fields,
            "name_present": bool(goal.get("name")),
            "visibility_present": "visibility" in goal,
        },
    }


def test_register_helper_populates_runner_registry() -> None:
    register_mcp_call_dispatcher()
    assert "mcp_call" in registered_dispatchers()
    assert registered_dispatchers()["mcp_call"] is mcp_call_dispatcher


def test_dispatcher_rejects_wrong_target_surface() -> None:
    # Construct a scenario with a different target_surface but try to call
    # the mcp_call dispatcher directly with it.
    scenario = _goals_propose_scenario()
    scenario_with_wrong_surface = AcceptanceScenario(
        scenario_id="scenario:bogus-v1",
        target_surface="branch_run",
        user_story=scenario.user_story,
        allowed_tools=scenario.allowed_tools,
        evaluator_chain=scenario.evaluator_chain,
        artifact_requirements=scenario.artifact_requirements,
        pass_threshold=scenario.pass_threshold,
        cost_budget=scenario.cost_budget,
        privacy_scope=scenario.privacy_scope,
        idempotency_key_constructor=scenario.idempotency_key_constructor,
    )

    with pytest.raises(ValueError, match="unsupported target_surface"):
        mcp_call_dispatcher(
            scenario_with_wrong_surface,
            candidate_ref="goals.propose",
            action_handler=_action_goal_propose,
            invocation_kwargs={"name": "Test"},
        )


def test_dispatcher_requires_action_handler() -> None:
    scenario = _goals_propose_scenario()
    with pytest.raises(ValueError, match="action_handler"):
        mcp_call_dispatcher(
            scenario,
            candidate_ref="goals.propose",
            invocation_kwargs={"name": "Test"},
        )


def test_dispatcher_uses_default_status_check_when_no_evaluators(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_STORAGE_BACKEND", "sqlite")

    scenario = _goals_propose_scenario()
    raw = mcp_call_dispatcher(
        scenario,
        candidate_ref="goals.propose",
        action_handler=_action_goal_propose,
        invocation_kwargs={"name": "Default Eval Project"},
        # evaluators omitted → default status check kicks in
    )

    assert raw["score"] == 1.0
    er = raw["details"]["evaluator_results"]
    assert len(er) == 1
    assert er[0]["label"] == "default_status_check"
    assert er[0]["details"]["status"] == "proposed"


def test_dispatcher_rejects_missing_name_via_evaluator(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_STORAGE_BACKEND", "sqlite")

    scenario = _goals_propose_scenario(scenario_id="scenario:goals-propose-missing-name-v1")
    raw = mcp_call_dispatcher(
        scenario,
        candidate_ref="goals.propose",
        action_handler=_action_goal_propose,
        invocation_kwargs={},  # missing name → handler returns error
        evaluators=[_goal_record_shape_evaluator],
    )

    # Evaluator should catch the rejected response and score 0.
    assert raw["score"] == 0.0
    assert raw["details"]["evaluator_results"][0]["details"]["verified"] is False


def test_end_to_end_goals_propose_passes(tmp_path, monkeypatch) -> None:
    """The full Slice 3 path: scenario + dispatcher + evaluator + runner.

    Verifies that AcceptanceScenario actually exercises a real platform
    action and produces a standard EvalResult with PASS verdict.
    """
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_STORAGE_BACKEND", "sqlite")

    # Universe-side startup: register the dispatcher.
    register_mcp_call_dispatcher()

    # A real platform action invocation passed as kwargs.
    scenario = _goals_propose_scenario()
    result = run_scenario(
        scenario,
        candidate_ref="goals.propose",
        action_handler=_action_goal_propose,
        invocation_kwargs={"name": "Slice 3 End-to-End Test Project"},
        evaluators=[_goal_record_shape_evaluator],
    )

    # Standard EvalResult shape, PASS verdict, correct score.
    assert result.verdict == "pass"
    assert result.kind == "custom"
    assert result.label == "mcp_call:goals.propose"
    assert result.score == 1.0

    # Evidence captured: raw response + evaluator outcome + cost.
    assert "raw_response_text" in result.details
    parsed = result.details["parsed_response"]
    assert parsed["status"] == "proposed"
    assert parsed["goal"]["name"] == "Slice 3 End-to-End Test Project"

    eval_results = result.details["evaluator_results"]
    assert len(eval_results) == 1
    assert eval_results[0]["label"] == "goal-record-shape-check"
    assert eval_results[0]["details"]["verified"] is True

    # Runner-injected defaults present (per scenario_runner contract).
    assert result.details["scenario_id"] == scenario.scenario_id
    assert result.details["target_surface"] == "mcp_call"
    assert result.details["privacy_scope"] == "commons_publishable"

    # Wall-time budget honored (real handler completes well under the cap).
    assert result.details["wall_time_seconds"] < scenario.cost_budget["max_wall_time_seconds"]
    assert "over_budget" not in result.details


def test_end_to_end_goals_propose_fails_on_missing_name(tmp_path, monkeypatch) -> None:
    """The same scenario but with a malformed invocation: must FAIL cleanly."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_STORAGE_BACKEND", "sqlite")

    register_mcp_call_dispatcher()
    scenario = _goals_propose_scenario(scenario_id="scenario:goals-propose-fail-v1")
    result = run_scenario(
        scenario,
        candidate_ref="goals.propose",
        action_handler=_action_goal_propose,
        invocation_kwargs={},  # missing required `name`
        evaluators=[_goal_record_shape_evaluator],
    )

    assert result.verdict == "fail"
    assert result.score == 0.0
    parsed = result.details["parsed_response"]
    assert "error" in parsed
    assert "name is required" in parsed["error"]


def test_dispatcher_records_handler_exception_as_minus_one(tmp_path, monkeypatch) -> None:
    """When the action handler itself raises, score is -1.0 and reason is recorded."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))

    scenario = _goals_propose_scenario(scenario_id="scenario:goals-propose-crash-v1")

    def crashing_handler(_kwargs):
        raise RuntimeError("simulated handler crash")

    raw = mcp_call_dispatcher(
        scenario,
        candidate_ref="goals.propose",
        action_handler=crashing_handler,
        invocation_kwargs={"name": "Crash Test"},
        evaluators=[_goal_record_shape_evaluator],
    )

    assert raw["score"] == -1.0
    assert "handler_exception" in raw["details"]
    assert "simulated handler crash" in raw["details"]["handler_exception"]
