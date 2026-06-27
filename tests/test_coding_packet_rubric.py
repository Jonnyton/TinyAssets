"""Tests for deterministic coding_packet rubric validation."""

from __future__ import annotations

from tinyassets.coding_packet_rubric import validate_coding_packet_rubric


def _keep_packet(**overrides) -> dict:
    packet = {
        "child_run_status": "completed",
        "attached_child_evidence_handle": "run-attachment:parent:child:abc123",
        "child_candidate_patch_packet": {"changed_paths": ["docs/x.md"]},
        "release_score": 9.5,
        "release_evidence_bundle_complete": True,
        "release_gate_result": "APPROVE_AUTO_SHIP",
        "coding_packet": {"status": "KEEP_READY"},
        "automation_claim_status": "child_attached_with_handle",
    }
    packet.update(overrides)
    return packet


def _rule_ids(result: dict) -> set[str]:
    return {v["rule_id"] for v in result["violations"]}


def test_clean_keep_packet_passes_rubric() -> None:
    result = validate_coding_packet_rubric(_keep_packet())

    assert result["validation_result"] == "passed"
    assert result["rubric_violation_count"] == 0
    assert result["violations"] == []


def test_recursion_limit_empty_output_cannot_claim_keep() -> None:
    result = validate_coding_packet_rubric(
        _keep_packet(
            child_output={},
            __system__={"recursion_limit_applied": True},
        )
    )

    assert result["validation_result"] == "blocked"
    assert "recursion_limit_keep_claim" in _rule_ids(result)
    assert all(v["event"] == "rubric_violation" for v in result["violations"])


def test_contradictory_child_claim_and_downgrade_reason_is_violation() -> None:
    result = validate_coding_packet_rubric(
        _keep_packet(
            automation_claim_status="child_invoked_with_handle",
            reason_for_downgrade="BUG-045 cannot invoke or attach child packet",
        )
    )

    assert result["validation_result"] == "blocked"
    assert "contradictory_child_claim" in _rule_ids(result)
    violation = result["violations"][0]
    assert violation["event"] == "rubric_violation"
    assert violation["field"] == "automation_claim_status"


def test_keep_claim_requires_completed_child_run_and_evidence_bundle() -> None:
    result = validate_coding_packet_rubric(
        _keep_packet(
            child_run_status="interrupted",
            attached_child_evidence_handle="",
            child_candidate_patch_packet=None,
            release_evidence_bundle_complete=False,
        )
    )

    rule_ids = _rule_ids(result)
    assert "child_run_not_completed_for_keep" in rule_ids
    assert "child_output_evidence_missing" in rule_ids
    assert "release_evidence_bundle_incomplete" in rule_ids


def test_keep_claim_requires_release_score_threshold() -> None:
    result = validate_coding_packet_rubric(_keep_packet(release_score=8.9))

    assert "release_score_below_keep_threshold" in _rule_ids(result)


def test_shipped_claim_requires_repo_handle() -> None:
    result = validate_coding_packet_rubric(_keep_packet(outcome_label="shipped"))

    assert "shipped_without_repo_handle" in _rule_ids(result)
