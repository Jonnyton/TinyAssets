"""CI acceptance-suite eval (R1 / S1): a rubric'd, *gating* output-eval for the
coding loop, run as a normal pytest so it gates in CI with no workflow change.

This is the "set the bar at the eval, not the demo" beachhead from
docs/design-notes/2026-06-24-coding-loop-eval-gate-wiring.md (S1). It reuses the
existing AcceptanceScenario machinery but raises the bar: ``min_score=0.9`` with
``"min"`` aggregation (any single failing rubric dimension blocks — failures are
not averaged away), and an explicit task-success evaluator chain.

Dispatcher registration is SUITE-LOCAL (registered in a fixture, torn down
after), so it never mutates the production ``_DISPATCHERS`` registry —
``run_scenario`` still returns ``skip`` in production. That is the
zero-production-behavior-change anchor the Codex review required.

Rubric dimensions (whitepaper p44): this slice scores **task success**.
tool-use quality / trajectory compliance / hallucination / response quality are
added as the suite grows (later slices).
"""

from __future__ import annotations

import pytest

from tinyassets.api.market import _action_goal_propose
from tinyassets.evaluation.scenario_dispatchers.mcp_call import (
    register as register_mcp_call_dispatcher,
)
from tinyassets.evaluation.scenario_runner import (
    AcceptanceScenario,
    registered_dispatchers,
    run_scenario,
    unregister_dispatcher,
)


@pytest.fixture(autouse=True)
def _suite_local_dispatcher(tmp_path, monkeypatch):
    """Register the mcp_call dispatcher for this suite only; isolate storage.

    Suite-local register + teardown keeps the production registry empty, so the
    daemon's ``run_scenario`` still returns ``skip`` outside CI.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    # sqlite_only is the explicit, fully-isolated backend (no YAML writes); the
    # bare "sqlite" value is NOT recognized by the factory and falls through to
    # git auto-probe, which is not guaranteed isolated (Codex review 2026-06-25).
    monkeypatch.setenv("TINYASSETS_STORAGE_BACKEND", "sqlite_only")
    register_mcp_call_dispatcher()
    yield
    for target_surface in list(registered_dispatchers().keys()):
        unregister_dispatcher(target_surface)


_USER_STORY = (
    "A user opens their MCP-connected chatbot and asks to propose a new Goal "
    "for a side project. The chatbot calls goals action=propose with a name; "
    "the platform creates the Goal record, commits it, and returns "
    "status=proposed plus the saved Goal so the chatbot can confirm in plain "
    "language. The CI acceptance gate asserts task success: the call did not "
    "error, the response status is proposed, and the saved Goal record carries "
    "a name and a visibility field. This is the smallest real output-eval of "
    "the coding-loop gate, scored at min aggregation so any single failing "
    "rubric dimension blocks the suite rather than averaging a real failure away."
)


def _scenario(scenario_id: str = "scenario:ci-goals-propose-task-success-v1") -> AcceptanceScenario:
    return AcceptanceScenario(
        scenario_id=scenario_id,
        target_surface="mcp_call",
        user_story=_USER_STORY,
        allowed_tools=["goals", "universe"],
        evaluator_chain=[
            "evaluator:task-success-no-error",
            "evaluator:goal-record-shape-check",
        ],
        artifact_requirements=[{"kind": "packet", "scope": "final", "redact_pattern": None}],
        pass_threshold={"min_score": 0.9, "score_aggregation": "min"},
        cost_budget={"max_tokens": 4000, "max_wall_time_seconds": 60},
        privacy_scope="commons_publishable",
        idempotency_key_constructor="sha256({scenario_id}|{candidate_ref}|{date_hour})",
    )


def task_success_no_error(parsed_response: dict) -> dict:
    """Rubric dimension: task success — the call must not error / reject."""
    status = parsed_response.get("status", "")
    errored = "error" in parsed_response or status in {"rejected", "error", "failed"}
    return {
        "score": 0.0 if errored else 1.0,
        "label": "task-success-no-error",
        "details": {"status": status, "errored": errored},
    }


def goal_record_shape_check(parsed_response: dict) -> dict:
    """Task success cont. — the side effect (Goal record) actually landed."""
    if "error" in parsed_response or parsed_response.get("status") != "proposed":
        return {
            "score": 0.0,
            "label": "goal-record-shape-check",
            "details": {"verified": False, "status": parsed_response.get("status")},
        }
    goal = parsed_response.get("goal") or {}
    ok = bool(goal.get("name")) and "visibility" in goal
    return {
        "score": 1.0 if ok else 0.5,
        "label": "goal-record-shape-check",
        "details": {
            "verified": ok,
            "name_present": bool(goal.get("name")),
            "visibility_present": "visibility" in goal,
        },
    }


_EVALUATORS = [task_success_no_error, goal_record_shape_check]


def test_user_story_within_length_bound():
    """Guard the scenario contract itself (200-2000 chars)."""
    assert 200 <= len(_USER_STORY) <= 2000, len(_USER_STORY)


def test_acceptance_suite_goals_propose_passes():
    """A well-formed goals.propose call passes the rubric'd gate (score >= 0.9)."""
    result = run_scenario(
        _scenario(),
        candidate_ref="goals.propose",
        action_handler=_action_goal_propose,
        invocation_kwargs={"name": "CI acceptance probe goal", "description": "eval"},
        evaluators=_EVALUATORS,
    )
    assert result.verdict == "pass", result.details
    assert result.score >= 0.9, result.score
    assert result.label == "mcp_call:goals.propose"


def test_acceptance_suite_gate_catches_failure():
    """The gate actually blocks: a propose call missing required input must NOT
    pass. Proves the bar is at the eval, not a happy-path demo."""
    result = run_scenario(
        _scenario("scenario:ci-goals-propose-failure-v1"),
        candidate_ref="goals.propose",
        action_handler=_action_goal_propose,
        invocation_kwargs={},  # missing name -> handler rejects
        evaluators=_EVALUATORS,
    )
    assert result.verdict != "pass", result.details
    assert result.score < 0.9, result.score
