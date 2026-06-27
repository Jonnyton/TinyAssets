"""Tests for process-oriented scene evaluation."""

from __future__ import annotations

from tinyassets.evaluation.process import (
    ProcessEvaluation,
    evaluate_scene_process,
)


def _base_state() -> dict:
    return {
        "orient_result": {
            "scene_id": "test-B1-C1-S1",
            "canon_context": "Ryn serves the harbor watch.",
        },
        "plan_output": {
            "scene_id": "test-B1-C1-S1",
            "beats": [
                {"beat_number": 1, "description": "Ryn reaches the gate."},
                {"beat_number": 2, "description": "She opens it."},
            ],
        },
        "draft_output": {
            "scene_id": "test-B1-C1-S1",
            "prose": "Ryn crossed the harbor in the rain.",
            "word_count": 7,
        },
        "search_context": {
            "phase": "draft",
            "facts": [{"fact_id": "f1", "text": "Ryn serves the harbor watch."}],
            "prose_chunks": ["The harbor bells rang through the fog."],
            "community_summaries": ["Ashwater is ruled from stormglass towers."],
            "sources": ["vector", "hipporag"],
            "token_count": 42,
        },
        "retrieved_context": {
            "facts": [{"fact_id": "f1", "text": "Ryn serves the harbor watch."}],
            "canon_facts": [{"fact_id": "f1", "text": "Ryn serves the harbor watch."}],
            "prose_chunks": ["The harbor bells rang through the fog."],
            "community_summaries": ["Ashwater is ruled from stormglass towers."],
            "sources": ["vector", "hipporag"],
            "token_count": 42,
        },
        "quality_trace": [
            {
                "node": "orient",
                "scene_id": "test-B1-C1-S1",
                "action": "orient_real",
                "search_sources": ["hipporag"],
                "search_token_count": 12,
                "search_fact_count": 1,
            },
            {
                "node": "plan",
                "scene_id": "test-B1-C1-S1",
                "action": "plan_real",
                "writer_tools": ["story_search", "world_constraints"],
                "search_sources": ["raptor"],
                "search_token_count": 10,
                "search_fact_count": 1,
            },
            {
                "node": "draft",
                "scene_id": "test-B1-C1-S1",
                "action": "draft_real",
                "writer_tools": ["story_search", "recent_prose"],
                "search_sources": ["vector"],
                "search_token_count": 20,
                "search_fact_count": 1,
            },
        ],
    }


class TestProcessEvaluation:
    def test_smoke(self):
        state = _base_state()
        commit_result = {
            "structural_checks": [
                {
                    "name": "canon_breach",
                    "passed": True,
                    "score": 1.0,
                    "violations": [],
                }
            ]
        }
        commit_trace = {
            "node": "commit",
            "scene_id": "test-B1-C1-S1",
            "action": "commit_real",
            "verdict": "accept",
        }

        result = evaluate_scene_process(
            state,
            pending_trace=[commit_trace],
            verdict="accept",
            second_draft_used=False,
            commit_result=commit_result,
        )

        assert isinstance(result, ProcessEvaluation)
        assert result.aggregate_score > 0.8
        assert result.failing_checks == []

    def test_tool_use_fails_without_story_search(self):
        state = _base_state()
        state["quality_trace"][1]["writer_tools"] = ["world_constraints"]
        state["quality_trace"][2]["writer_tools"] = ["recent_prose"]

        result = evaluate_scene_process(
            state,
            verdict="accept",
            second_draft_used=False,
            commit_result={"structural_checks": []},
        )

        assert "tool_use" in result.failing_checks

    def test_stopping_behavior_fails_on_third_draft_request(self):
        state = _base_state()

        result = evaluate_scene_process(
            state,
            verdict="second_draft",
            second_draft_used=True,
            commit_result={"structural_checks": []},
        )

        assert "stopping_behavior" in result.failing_checks

    def test_trace_handoff_fails_when_plan_missing(self):
        state = _base_state()
        state["quality_trace"] = [
            entry for entry in state["quality_trace"] if entry["node"] != "plan"
        ]

        result = evaluate_scene_process(
            state,
            verdict="accept",
            second_draft_used=False,
            commit_result={"structural_checks": []},
        )

        assert "trace_handoff" in result.failing_checks
