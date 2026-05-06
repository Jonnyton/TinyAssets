"""Tests for the confidence_threshold node primitive."""

from __future__ import annotations

import pytest

from workflow.branches import (
    BranchDefinition,
    ConditionalEdge,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from workflow.graph_compiler import (
    CompilerError,
    compile_branch,
    compile_confidence_threshold_spec,
)


def _branch() -> BranchDefinition:
    gate = NodeDefinition(
        node_id="gate",
        display_name="Confidence Gate",
        output_keys=["route", "question", "learning_signal"],
        confidence_threshold_spec={
            "confidence_key": "confidence",
            "threshold": 0.8,
            "route_key": "route",
            "process_route": "process",
            "ask_route": "ask_user",
            "answer_key": "user_answer",
            "question_key": "question",
            "question_template": "Should I process {candidate}?",
            "learn_key": "learning_signal",
        },
    )
    process = NodeDefinition(
        node_id="process",
        display_name="Process",
        prompt_template="process",
        output_keys=["processed"],
    )
    ask = NodeDefinition(
        node_id="ask",
        display_name="Ask",
        prompt_template="ask",
        output_keys=["asked"],
    )
    return BranchDefinition(
        branch_def_id="confidence-gate-test",
        name="Confidence Gate Test",
        graph_nodes=[
            GraphNodeRef(id="gate", node_def_id="gate"),
            GraphNodeRef(id="process", node_def_id="process"),
            GraphNodeRef(id="ask", node_def_id="ask"),
        ],
        node_defs=[gate, process, ask],
        edges=[
            EdgeDefinition(from_node="process", to_node="END"),
            EdgeDefinition(from_node="ask", to_node="END"),
        ],
        conditional_edges=[
            ConditionalEdge(
                from_node="gate",
                conditions={"process": "process", "ask_user": "ask"},
            ),
        ],
        entry_point="gate",
        state_schema=[
            {"name": "confidence", "type": "float"},
            {"name": "candidate", "type": "str"},
            {"name": "user_answer", "type": "str"},
            {"name": "route", "type": "str"},
            {"name": "question", "type": "str"},
            {"name": "learning_signal", "type": "dict"},
            {"name": "processed", "type": "str"},
            {"name": "asked", "type": "str"},
        ],
    )


def test_confident_node_routes_to_process() -> None:
    compiled = compile_branch(_branch())

    result = compiled.graph.compile().invoke({
        "confidence": 0.91,
        "candidate": "the patch",
    })

    assert result["route"] == "process"
    assert result["processed"] == "[Mock response for process]"
    assert "asked" not in result
    assert "question" not in result


def test_uncertain_node_routes_to_ask_with_question() -> None:
    compiled = compile_branch(_branch())

    result = compiled.graph.compile().invoke({
        "confidence": 0.41,
        "candidate": "the patch",
    })

    assert result["route"] == "ask_user"
    assert result["question"] == "Should I process the patch?"
    assert result["asked"] == "[Mock response for ask]"
    assert "processed" not in result


def test_user_answer_routes_to_process_and_emits_learning_signal() -> None:
    compiled = compile_branch(_branch())

    result = compiled.graph.compile().invoke({
        "confidence": 0.41,
        "candidate": "the patch",
        "user_answer": "Yes, apply it.",
    })

    assert result["route"] == "process"
    assert result["processed"] == "[Mock response for process]"
    assert result["learning_signal"] == {
        "answer": "Yes, apply it.",
        "confidence": 0.41,
        "threshold": 0.8,
        "confidence_key": "confidence",
        "route": "process",
    }


def test_confidence_threshold_spec_validates_threshold() -> None:
    with pytest.raises(CompilerError, match="between 0 and 1"):
        compile_confidence_threshold_spec(
            {"confidence": 0.5},
            {"confidence_key": "confidence", "threshold": 1.2},
        )


def test_branch_validation_rejects_missing_confidence_key() -> None:
    branch = _branch()
    branch.node_defs[0].confidence_threshold_spec = {"threshold": 0.8}

    errors = branch.validate()

    assert any("confidence_threshold_spec missing 'confidence_key'" in e for e in errors)
