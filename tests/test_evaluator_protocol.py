"""Tests for the unified Evaluator protocol and EvalResult.

Covers:
  * EvalResult dataclass: field defaults, score-range invariants.
  * Evaluator Protocol: isinstance check via runtime_checkable.
  * ProcessEvaluation.to_eval_result(): roundtrip, verdict mapping.
  * NumericEvaluator fixture: minimal Protocol-conforming implementation.
"""

from __future__ import annotations

from typing import Any

import pytest

from tinyassets.evaluation import (
    EvalResult,
    Evaluator,
    EvalVerdict,
    ProcessCheck,
    ProcessEvaluation,
)

# ── EvalResult ────────────────────────────────────────────────────────────────

class TestEvalResult:
    def test_defaults(self):
        r = EvalResult(score=0.5, verdict="pass", kind="numeric")
        assert r.label == ""
        assert r.details == {}

    def test_score_lower_bound_accepted(self):
        r = EvalResult(score=-1.0, verdict="skip", kind="custom")
        assert r.score == -1.0

    def test_score_upper_bound_accepted(self):
        r = EvalResult(score=1.0, verdict="pass", kind="structural")
        assert r.score == 1.0

    def test_score_above_range_raises(self):
        with pytest.raises(ValueError, match="EvalResult.score"):
            EvalResult(score=1.001, verdict="pass", kind="numeric")

    def test_score_below_range_raises(self):
        with pytest.raises(ValueError, match="EvalResult.score"):
            EvalResult(score=-1.001, verdict="fail", kind="editorial")

    def test_details_stored(self):
        r = EvalResult(score=0.0, verdict="error", kind="process", details={"k": "v"})
        assert r.details["k"] == "v"

    def test_label_stored(self):
        r = EvalResult(score=0.8, verdict="pass", kind="numeric", label="my_check")
        assert r.label == "my_check"

    def test_not_applicable_score(self):
        r = EvalResult(score=-1.0, verdict="skip", kind="custom", label="n/a")
        assert r.score == -1.0

    def test_verdict_values_accepted(self):
        for v in ("pass", "fail", "skip", "error"):
            r = EvalResult(score=0.0, verdict=v, kind="numeric")  # type: ignore[arg-type]
            assert r.verdict == v


# ── Evaluator Protocol ────────────────────────────────────────────────────────

class NumericEvaluator:
    """Minimal Protocol-conforming evaluator for testing."""

    def evaluate(self, state: dict[str, Any]) -> EvalResult:
        score = float(state.get("score", 0.0))
        score = max(-1.0, min(1.0, score))
        verdict: EvalVerdict = "pass" if score >= 0.5 else "fail"
        return EvalResult(score=score, verdict=verdict, kind="numeric", label="test_numeric")


class NoEvaluateMethod:
    """Does NOT satisfy the Evaluator protocol."""

    def run(self, state: dict[str, Any]) -> EvalResult:  # wrong method name
        return EvalResult(score=0.0, verdict="pass", kind="numeric")


class TestEvaluatorProtocol:
    def test_numeric_evaluator_satisfies_protocol(self):
        e = NumericEvaluator()
        assert isinstance(e, Evaluator)

    def test_missing_method_fails_protocol(self):
        assert not isinstance(NoEvaluateMethod(), Evaluator)

    def test_numeric_evaluator_returns_eval_result(self):
        e = NumericEvaluator()
        result = e.evaluate({"score": 0.7})
        assert isinstance(result, EvalResult)
        assert result.verdict == "pass"
        assert result.score == pytest.approx(0.7)

    def test_numeric_evaluator_fail_verdict(self):
        e = NumericEvaluator()
        result = e.evaluate({"score": 0.3})
        assert result.verdict == "fail"

    def test_numeric_evaluator_clamps_score(self):
        e = NumericEvaluator()
        result = e.evaluate({"score": 99.0})
        assert result.score == pytest.approx(1.0)

    def test_protocol_satisfied_by_lambda_class(self):
        class LambdaEvaluator:
            def evaluate(self, state: dict[str, Any]) -> EvalResult:
                return EvalResult(score=0.0, verdict="skip", kind="custom")

        assert isinstance(LambdaEvaluator(), Evaluator)

    def test_structural_evaluator_satisfies_protocol(self):
        from tinyassets.evaluation import StructuralEvaluator

        class WrappedStructural:
            def __init__(self) -> None:
                self._inner = StructuralEvaluator()

            def evaluate(self, state: dict[str, Any]) -> EvalResult:
                result = self._inner.evaluate(state)
                verdict: EvalVerdict = "fail" if result.hard_failure else "pass"
                return EvalResult(
                    score=result.aggregate_score,
                    verdict=verdict,
                    kind="structural",
                    label="structural_eval",
                )

        assert isinstance(WrappedStructural(), Evaluator)


# ── ProcessEvaluation.to_eval_result ─────────────────────────────────────────

class TestProcessEvaluationToEvalResult:
    def _make_process_evaluation(self, *, score: float, failing: list[str]) -> ProcessEvaluation:
        checks = [
            ProcessCheck(
                name=name,
                passed=(name not in failing),
                score=1.0 if name not in failing else 0.0,
            )
            for name in ["trace_handoff", "tool_use"]
        ]
        return ProcessEvaluation(
            checks=checks,
            aggregate_score=score,
            failing_checks=list(failing),
        )

    def test_returns_eval_result(self):
        pe = self._make_process_evaluation(score=0.9, failing=[])
        result = pe.to_eval_result()
        assert isinstance(result, EvalResult)

    def test_kind_is_process(self):
        pe = self._make_process_evaluation(score=0.5, failing=[])
        assert pe.to_eval_result().kind == "process"

    def test_pass_verdict_when_no_failures(self):
        pe = self._make_process_evaluation(score=0.8, failing=[])
        assert pe.to_eval_result().verdict == "pass"

    def test_fail_verdict_when_checks_fail(self):
        pe = self._make_process_evaluation(score=0.4, failing=["trace_handoff"])
        assert pe.to_eval_result().verdict == "fail"

    def test_score_preserved(self):
        pe = self._make_process_evaluation(score=0.75, failing=[])
        assert pe.to_eval_result().score == pytest.approx(0.75)

    def test_score_clamped_to_range(self):
        pe = ProcessEvaluation(checks=[], aggregate_score=1.5, failing_checks=[])
        result = pe.to_eval_result()
        assert result.score <= 1.0

    def test_details_include_failing_checks(self):
        pe = self._make_process_evaluation(score=0.3, failing=["tool_use"])
        result = pe.to_eval_result()
        assert "tool_use" in result.details.get("failing_checks", [])

    def test_label_set(self):
        pe = self._make_process_evaluation(score=1.0, failing=[])
        assert pe.to_eval_result().label == "process_evaluation"


# ── Score-range invariants ────────────────────────────────────────────────────

class TestScoreRangeInvariants:
    @pytest.mark.parametrize("score", [-1.0, -0.5, 0.0, 0.5, 1.0])
    def test_valid_scores_accepted(self, score: float):
        r = EvalResult(score=score, verdict="pass", kind="numeric")
        assert r.score == pytest.approx(score)

    @pytest.mark.parametrize("score", [-1.001, 1.001, -2.0, 2.0, float("inf")])
    def test_out_of_range_scores_rejected(self, score: float):
        with pytest.raises(ValueError):
            EvalResult(score=score, verdict="pass", kind="numeric")
