"""Tests for the coding-lane trajectory (process) evaluator.

Covers the fail-open contract (absent data never fails), per-dimension scoring
from real coding-lane signals, the inconclusive/skip path, EvalResult mapping,
and the two source normalizers.
"""

from __future__ import annotations

from tinyassets.evaluation import (
    CodingTrajectoryEvaluation,
    coding_trajectory_from_packet,
    coding_trajectory_from_run,
    evaluate_coding_trajectory,
)
from tinyassets.evaluation.coding_process import MIN_APPLICABLE_CHECKS

# ── Fail-open / inconclusive contract ───────────────────────────────────────────


def test_empty_trajectory_is_inconclusive_not_fail():
    result = evaluate_coding_trajectory({})
    assert result.verdict == "skip"
    assert result.conclusive is False
    # No applicable checks -> no failing checks.
    assert result.failing_checks == []
    assert result.applicable_checks == []


def test_non_dict_input_is_inconclusive():
    assert evaluate_coding_trajectory(None).verdict == "skip"  # type: ignore[arg-type]
    assert evaluate_coding_trajectory("nope").verdict == "skip"  # type: ignore[arg-type]


def test_run_status_alone_makes_two_checks_applicable():
    # run_status is a run-level signal, so it makes BOTH terminal_health and
    # recursion_discipline applicable -> at/above the conclusive floor.
    result = evaluate_coding_trajectory({"run_status": "completed"})
    # run_status makes terminal_health AND recursion_discipline applicable
    # (recursion is a run-level signal), so this is actually conclusive.
    assert len(result.applicable_checks) >= MIN_APPLICABLE_CHECKS
    assert result.conclusive is True
    assert result.verdict == "pass"


def test_absent_negative_signal_does_not_fail():
    # A healthy completed run with no recursion limit: recursion_discipline is
    # applicable (run-level signal present) and passes because absence is good.
    result = evaluate_coding_trajectory({"run_status": "completed"})
    recursion = next(c for c in result.checks if c.name == "recursion_discipline")
    assert recursion.applicable is True
    assert recursion.passed is True
    assert recursion.score == 1.0


# ── Healthy path ─────────────────────────────────────────────────────────────────


def test_clean_run_passes():
    trajectory = {
        "run_status": "completed",
        "provider_calls": [
            {"node_id": "a", "attempts": 1, "degraded": False},
            {"node_id": "b", "attempts": 1, "degraded": False},
        ],
        "child_failures": [],
        "child_attached": True,
        "node_events": [
            {"node_id": "a", "status": "ran"},
            {"node_id": "b", "status": "ran"},
        ],
    }
    result = evaluate_coding_trajectory(trajectory)
    assert result.verdict == "pass"
    assert result.aggregate_score >= result.pass_threshold
    assert result.failing_checks == []


def test_clean_nonsuccess_status_is_sound():
    # review_ready is a clean refusal, not a failure.
    result = evaluate_coding_trajectory({"run_status": "review_ready"})
    terminal = next(c for c in result.checks if c.name == "terminal_health")
    assert terminal.passed is True
    assert terminal.score == 0.7


# ── Terminal health ──────────────────────────────────────────────────────────────


def test_provider_exhausted_fails_terminal_health():
    result = evaluate_coding_trajectory(
        {"run_status": "failed", "failure_class": "provider_exhausted"}
    )
    terminal = next(c for c in result.checks if c.name == "terminal_health")
    assert terminal.applicable is True
    assert terminal.passed is False
    assert terminal.score <= 0.2
    assert "infrastructure" in terminal.observation.lower()


def test_interrupted_run_fails_terminal_health():
    result = evaluate_coding_trajectory({"run_status": "interrupted"})
    terminal = next(c for c in result.checks if c.name == "terminal_health")
    assert terminal.passed is False
    assert terminal.score == 0.4


# ── Critical-fail offset resistance (Codex ADAPT #1) ─────────────────────────────


def test_terminal_failure_cannot_be_offset_to_pass():
    # Terminal failure (0.3) + four perfect checks averages 0.825 >= 0.8, which
    # would spuriously pass on aggregate alone. terminal_health is critical.
    trajectory = {
        "run_status": "failed",
        "failure_class": "error",
        "provider_calls": [{"node_id": "a", "attempts": 1, "degraded": False}],
        "child_failures": [],
        "child_attached": True,
        "node_events": [{"node_id": "a", "status": "ran"}],
    }
    result = evaluate_coding_trajectory(trajectory)
    assert result.aggregate_score >= 0.8  # would pass on aggregate alone
    assert result.verdict == "fail"  # critical-fail rule overrides


def test_child_timeout_cannot_be_offset_to_pass():
    # child_timeout (0.2) + clean everything else lands at exactly 0.8.
    # child_integrity is critical, so it must fail.
    trajectory = {
        "run_status": "completed",
        "provider_calls": [{"node_id": "a", "attempts": 1, "degraded": False}],
        "child_failures": [{"failure_class": "child_timeout"}],
        "node_events": [{"node_id": "a", "status": "ran"}],
    }
    result = evaluate_coding_trajectory(trajectory)
    assert result.aggregate_score >= 0.8
    assert result.verdict == "fail"


def test_noncritical_failure_is_still_offset_to_pass():
    # The critical rule is targeted, not blanket: a lone provider blemish on an
    # otherwise-clean path is correctly offset and still passes.
    trajectory = {
        "run_status": "completed",
        "provider_calls": [
            {"node_id": "a", "attempts": 1, "degraded": True},
            {"node_id": "b", "attempts": 1, "degraded": False},
            {"node_id": "c", "attempts": 1, "degraded": False},
            {"node_id": "d", "attempts": 1, "degraded": False},
        ],
        "child_failures": [],
        "child_attached": True,
        "node_events": [{"node_id": "a", "status": "ran"}],
    }
    result = evaluate_coding_trajectory(trajectory)
    efficiency = next(c for c in result.checks if c.name == "provider_efficiency")
    assert efficiency.passed is False  # the blemish is recorded
    assert result.verdict == "pass"  # but it does not force a fail


def test_receipt_waiting_only_on_real_status():
    # Codex ADAPT #3: a gate dict with a non-waiting status is NOT receipt-waiting.
    resolved = coding_trajectory_from_packet(
        {
            "child_run_status": "completed",
            "child_invocation_receipt_gate": {"status": "resolved"},
        }
    )
    assert "receipt_waiting" not in resolved
    waiting = coding_trajectory_from_packet(
        {
            "child_run_status": "completed",
            "child_invocation_receipt_gate": {"status": "receipt_waiting"},
        }
    )
    assert waiting["receipt_waiting"] is True
    via_parent = coding_trajectory_from_packet(
        {"child_run_status": "completed", "parent_loop_status": "receipt_waiting"}
    )
    assert via_parent["receipt_waiting"] is True


# ── Provider efficiency ──────────────────────────────────────────────────────────


def test_degraded_providers_fail_efficiency():
    trajectory = {
        "run_status": "completed",
        "provider_calls": [
            {"node_id": "a", "attempts": 3, "degraded": True},
            {"node_id": "b", "attempts": 1, "degraded": False},
        ],
    }
    result = evaluate_coding_trajectory(trajectory)
    efficiency = next(c for c in result.checks if c.name == "provider_efficiency")
    assert efficiency.applicable is True
    assert efficiency.passed is False
    assert efficiency.score < 1.0
    assert efficiency.details["degraded"] == 1
    assert efficiency.details["retried"] == 1


def test_no_provider_calls_is_not_applicable():
    result = evaluate_coding_trajectory({"run_status": "completed"})
    efficiency = next(c for c in result.checks if c.name == "provider_efficiency")
    assert efficiency.applicable is False


# ── Recursion discipline ─────────────────────────────────────────────────────────


def test_recursion_limit_with_empty_output_scores_zero():
    result = evaluate_coding_trajectory(
        {
            "run_status": "completed",
            "recursion_limit_applied": True,
            "recursion_limit_empty_output": True,
        }
    )
    recursion = next(c for c in result.checks if c.name == "recursion_discipline")
    assert recursion.passed is False
    assert recursion.score == 0.0


def test_recursion_limit_with_output_is_partial():
    result = evaluate_coding_trajectory(
        {"run_status": "completed", "recursion_limit_applied": True}
    )
    recursion = next(c for c in result.checks if c.name == "recursion_discipline")
    assert recursion.passed is False
    assert recursion.score == 0.4


# ── Child integrity ──────────────────────────────────────────────────────────────


def test_child_failure_fails_integrity():
    trajectory = {
        "run_status": "completed",
        "child_failures": [{"failure_class": "child_failed"}],
    }
    result = evaluate_coding_trajectory(trajectory)
    child = next(c for c in result.checks if c.name == "child_integrity")
    assert child.applicable is True
    assert child.passed is False
    assert child.score == 0.0
    assert "child_failed" in child.details["failure_classes"]


def test_receipt_waiting_fails_integrity():
    result = evaluate_coding_trajectory(
        {"run_status": "completed", "receipt_waiting": True}
    )
    child = next(c for c in result.checks if c.name == "child_integrity")
    assert child.applicable is True
    assert child.passed is False
    assert child.score == 0.3


def test_no_child_dimension_is_not_applicable():
    result = evaluate_coding_trajectory({"run_status": "completed"})
    child = next(c for c in result.checks if c.name == "child_integrity")
    assert child.applicable is False


def test_clean_child_attachment_passes():
    result = evaluate_coding_trajectory(
        {"run_status": "completed", "child_failures": [], "child_attached": True}
    )
    child = next(c for c in result.checks if c.name == "child_integrity")
    assert child.applicable is True
    assert child.passed is True
    assert child.score == 1.0


# ── Node progression ─────────────────────────────────────────────────────────────


def test_failed_node_fails_progression():
    trajectory = {
        "run_status": "completed",
        "node_events": [
            {"node_id": "a", "status": "ran"},
            {"node_id": "b", "status": "failed"},
        ],
    }
    result = evaluate_coding_trajectory(trajectory)
    progression = next(c for c in result.checks if c.name == "node_progression")
    assert progression.applicable is True
    assert progression.passed is False
    assert "b" in progression.details["failed_nodes"]


# ── EvalResult mapping ───────────────────────────────────────────────────────────


def test_to_eval_result_skip_uses_reserved_score():
    result = evaluate_coding_trajectory({})
    eval_result = result.to_eval_result()
    assert eval_result.verdict == "skip"
    assert eval_result.score == -1.0
    assert eval_result.kind == "process"


def test_to_eval_result_pass_in_unit_range():
    result = evaluate_coding_trajectory(
        {"run_status": "completed", "child_failures": [], "child_attached": True}
    )
    eval_result = result.to_eval_result()
    assert eval_result.verdict == "pass"
    assert 0.0 <= eval_result.score <= 1.0


def test_to_dict_round_trips_checks():
    result = evaluate_coding_trajectory({"run_status": "completed"})
    as_dict = result.to_dict()
    assert as_dict["verdict"] == "pass"
    assert as_dict["conclusive"] is True
    names = {c["name"] for c in as_dict["checks"]}
    assert names == {
        "terminal_health",
        "provider_efficiency",
        "recursion_discipline",
        "child_integrity",
        "node_progression",
    }


# ── Normalizers ──────────────────────────────────────────────────────────────────


def test_from_packet_extracts_recursion_and_attachment():
    packet = {
        "child_run_status": "completed",
        "__system__": {"recursion_limit_applied": True},
        "child_output": {},
        "automation_claim_status": "child_attached_with_handle",
    }
    trajectory = coding_trajectory_from_packet(packet)
    assert trajectory["run_status"] == "completed"
    assert trajectory["recursion_limit_applied"] is True
    assert trajectory["recursion_limit_empty_output"] is True
    assert trajectory["child_attached"] is True


def test_from_packet_thin_packet_is_fail_open():
    # A packet with almost no trajectory signal must not manufacture failures.
    trajectory = coding_trajectory_from_packet({"some_unrelated_field": 1})
    result = evaluate_coding_trajectory(trajectory)
    assert result.verdict == "skip"


def test_from_packet_non_dict_returns_empty():
    assert coding_trajectory_from_packet(None) == {}  # type: ignore[arg-type]


def test_from_run_parses_system_events():
    # run carries only raw fields (status); provider_calls + recursion live in
    # __system__ run_events rows; node rows are non-__system__.
    run = {"status": "failed"}
    run_events = [
        {"node_id": "__system__", "status": "recursion_limit_applied", "detail": {}},
        {
            "node_id": "__system__",
            "status": "provider_calls",
            "detail": {"calls": [{"node_id": "a", "attempts": 2, "degraded": True}]},
        },
        {"node_id": "a", "status": "failed", "detail": {}},
        {"node_id": "b", "status": "ran", "detail": {}},
    ]
    trajectory = coding_trajectory_from_run(
        run,
        run_events=run_events,
        failure_class="provider_exhausted",
        child_failures=[{"failure_class": "child_timeout"}],
    )
    assert trajectory["run_status"] == "failed"
    assert trajectory["failure_class"] == "provider_exhausted"
    assert trajectory["recursion_limit_applied"] is True
    # provider_calls parsed out of the __system__ row, not the run record.
    assert trajectory["provider_calls"] == [
        {"node_id": "a", "attempts": 2, "degraded": True}
    ]
    # __system__ rows excluded from node_events.
    assert {e["node_id"] for e in trajectory["node_events"]} == {"a", "b"}
    result = evaluate_coding_trajectory(trajectory)
    assert result.verdict == "fail"
    assert len(result.applicable_checks) >= 4


def test_from_run_raw_get_run_shape_is_thin_not_failing():
    # A raw get_run record (no events, no enrichment) must NOT manufacture
    # signal. Only run_status survives; recursion defaults False (negative
    # signal absent = good), provider/node/child checks non-applicable.
    run = {"status": "completed", "last_node_id": "x", "provider_used": "claude"}
    trajectory = coding_trajectory_from_run(run)
    assert trajectory["run_status"] == "completed"
    assert "provider_calls" not in trajectory
    assert "node_events" not in trajectory
    result = evaluate_coding_trajectory(trajectory)
    # terminal_health + recursion_discipline applicable, both pass.
    assert result.verdict == "pass"


def test_from_run_non_dict_returns_empty_status_only():
    trajectory = coding_trajectory_from_run(None)  # type: ignore[arg-type]
    # run_status None is filtered out; recursion default False stays.
    assert "run_status" not in trajectory


def test_returns_evaluation_type():
    assert isinstance(evaluate_coding_trajectory({}), CodingTrajectoryEvaluation)
