from __future__ import annotations

from workflow.evaluation import EvalResult, ProcessCheck, ProcessEvaluation


def test_eval_result_preserves_optimization_evidence_fields() -> None:
    result = EvalResult(
        score=0.72,
        verdict="pass",
        kind="custom",
        label="holdout_eval",
        rationale="Candidate improved holdout accuracy.",
        evidence={"holdout_accuracy": 0.72},
        artifacts={"stderr": "warning: slow path"},
        evaluator_id="eval-holdout-v1",
        cost={"wall_ms": 1234, "tokens": 512},
        ran_at="2026-05-02T00:00:00Z",
        freshness={"verified_at": "2026-05-02", "environment": "unit-test"},
    )

    payload = result.to_dict()

    assert payload["evidence"]["holdout_accuracy"] == 0.72
    assert payload["artifacts"]["stderr"] == "warning: slow path"
    assert payload["evaluator_id"] == "eval-holdout-v1"
    assert payload["cost"]["wall_ms"] == 1234
    assert payload["freshness"]["environment"] == "unit-test"


def test_process_eval_result_populates_artifact_side_channel() -> None:
    process = ProcessEvaluation(
        checks=[
            ProcessCheck(
                name="trace_handoff",
                passed=False,
                score=0.0,
                observation="Trace was missing commit evidence.",
            )
        ],
        aggregate_score=0.0,
        failing_checks=["trace_handoff"],
    )

    result = process.to_eval_result()

    assert result.verdict == "fail"
    assert "trace_handoff" in result.rationale
    assert result.evidence["checks"][0]["name"] == "trace_handoff"
    assert result.artifacts["process_evaluation"]["failing_checks"] == ["trace_handoff"]
