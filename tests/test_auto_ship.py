"""Tests for ``workflow.auto_ship.validate_ship_request`` (PR #198 Phase 1).

Covers the auto-ship safety envelope from
``docs/milestones/auto-ship-canary-v0.md`` §6:
  - §6.1 required packet fields + value gates
  - §6.2 allowed ship classes + allowed/forbidden path prefixes
  - §6.3 diff-size / binary / secret checks

Phase 1 is dry-run only — ``ship_status`` is always ``"skipped"`` and
``would_open_pr`` carries the actual passed/blocked signal.
"""

from __future__ import annotations

import pytest

from workflow.auto_ship import (
    ALLOWED_SHIP_CLASSES,
    DIFF_SIZE_BYTES_MAX,
    FORBIDDEN_PATH_PREFIXES,
    KEEP_SCORE_MIN,
    validate_ship_request,
)


def _valid_packet(**overrides) -> dict:
    """Minimal packet that passes the envelope. Tests override fields to force
    specific failures."""
    base = {
        "release_gate_result": "APPROVE_AUTO_SHIP",
        "ship_class": "docs_canary",
        "child_keep_reject_decision": "KEEP",
        "coding_packet": {"status": "KEEP_READY"},
        "child_score": 9.5,
        "risk_level": "low",
        "blocked_execution_record": {},
        "stable_evidence_handle": "child_run:branch-x:run-y",
        "automation_claim_status": "child_attached_with_handle",
        "rollback_plan": "Revert commit <sha> or close PR if not merged",
        "changed_paths": ["docs/autoship-canaries/first-loop-autoship.md"],
        "diff": "+ added a timestamp\n- old timestamp\n",
    }
    base.update(overrides)
    return base


# ── Phase-1 dry-run shape contract ────────────────────────────────────────


class TestPhase1Contract:
    def test_dry_run_always_set(self):
        d = validate_ship_request(_valid_packet())
        assert d["dry_run"] is True

    def test_ship_status_always_skipped_in_phase_1(self):
        d_pass = validate_ship_request(_valid_packet())
        d_fail = validate_ship_request(_valid_packet(release_gate_result="HOLD"))
        assert d_pass["ship_status"] == "skipped"
        assert d_fail["ship_status"] == "skipped"

    def test_passed_decision_keys(self):
        d = validate_ship_request(_valid_packet())
        assert d["validation_result"] == "passed"
        assert d["would_open_pr"] is True
        assert d["violations"] == []
        assert d["rollback_handle"].startswith("revert:")

    def test_blocked_decision_keys(self):
        d = validate_ship_request(_valid_packet(release_gate_result="HOLD"))
        assert d["validation_result"] == "blocked"
        assert d["would_open_pr"] is False
        assert len(d["violations"]) >= 1
        assert d["rollback_handle"] is None


# ── Top-level packet shape ────────────────────────────────────────────────


class TestPacketShape:
    @pytest.mark.parametrize("not_a_dict", [None, "", 42, [], "{}"])
    def test_non_dict_packet_blocked(self, not_a_dict):
        d = validate_ship_request(not_a_dict)
        assert d["validation_result"] == "blocked"
        assert any(v["rule_id"] == "packet_not_dict" for v in d["violations"])

    def test_empty_packet_blocks_with_required_field_violations(self):
        d = validate_ship_request({})
        assert d["validation_result"] == "blocked"
        rule_ids = {v["rule_id"] for v in d["violations"]}
        assert any(rid.startswith("required_field_missing:") for rid in rule_ids)


# ── §6.1 required fields ──────────────────────────────────────────────────


class TestRequiredFields:
    @pytest.mark.parametrize("missing_field", [
        "release_gate_result",
        "ship_class",
        "child_keep_reject_decision",
        "child_score",
        "risk_level",
        "blocked_execution_record",
        "stable_evidence_handle",
        "automation_claim_status",
        "rollback_plan",
    ])
    def test_each_required_field_when_missing(self, missing_field):
        packet = _valid_packet()
        del packet[missing_field]
        d = validate_ship_request(packet)
        assert d["validation_result"] == "blocked"
        rule = f"required_field_missing:{missing_field}"
        assert any(v["rule_id"] == rule for v in d["violations"]), \
            f"expected violation rule_id={rule!r}; got {[v['rule_id'] for v in d['violations']]}"

    @pytest.mark.parametrize("missing_field", [
        "release_gate_result",
        "stable_evidence_handle",
        "rollback_plan",
    ])
    def test_each_required_field_when_empty_string(self, missing_field):
        d = validate_ship_request(_valid_packet(**{missing_field: ""}))
        assert d["validation_result"] == "blocked"


# ── §6.1 value gates ──────────────────────────────────────────────────────


class TestValueGates:
    def test_missing_coding_packet_status_blocked(self):
        packet = _valid_packet()
        del packet["coding_packet"]
        d = validate_ship_request(packet)
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "coding_packet_status_missing"
            for v in d["violations"]
        )

    @pytest.mark.parametrize("status", ["KEEP_READY", "AUTO_SHIP_READY"])
    def test_allowed_coding_packet_status_passes(self, status):
        d = validate_ship_request(_valid_packet(coding_packet={"status": status}))
        assert d["validation_result"] == "passed"

    def test_top_level_coding_packet_status_passes(self):
        packet = _valid_packet(coding_packet_status="KEEP_READY")
        del packet["coding_packet"]
        d = validate_ship_request(packet)
        assert d["validation_result"] == "passed"

    def test_source_packet_coding_packet_status_passes(self):
        packet = _valid_packet(source_packet={"coding_packet": {"status": "KEEP_READY"}})
        del packet["coding_packet"]
        d = validate_ship_request(packet)
        assert d["validation_result"] == "passed"

    def test_bad_coding_packet_status_blocked(self):
        d = validate_ship_request(_valid_packet(coding_packet={"status": "REVIEW_READY"}))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "coding_packet_status_not_allowed"
            for v in d["violations"]
        )

    def test_release_gate_must_be_approve_auto_ship(self):
        for verdict in ("HOLD", "REVIEW_READY", "REJECT", "APPROVE", "OBSERVE"):
            d = validate_ship_request(_valid_packet(release_gate_result=verdict))
            assert d["validation_result"] == "blocked"
            assert any(
                v["rule_id"] == "release_gate_not_approved"
                for v in d["violations"]
            )

    def test_child_decision_must_be_keep(self):
        for decision in ("REVIEW_READY", "REJECT", "SEND_BACK"):
            d = validate_ship_request(_valid_packet(child_keep_reject_decision=decision))
            assert d["validation_result"] == "blocked"
            assert any(
                v["rule_id"] == "child_decision_not_keep"
                for v in d["violations"]
            )

    def test_child_score_below_threshold_blocked(self):
        d = validate_ship_request(_valid_packet(child_score=KEEP_SCORE_MIN - 0.1))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "child_score_below_threshold"
            for v in d["violations"]
        )

    def test_child_score_at_threshold_passes(self):
        d = validate_ship_request(_valid_packet(child_score=KEEP_SCORE_MIN))
        assert d["validation_result"] == "passed"

    def test_child_score_non_numeric_blocked(self):
        d = validate_ship_request(_valid_packet(child_score="9.5"))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "child_score_not_numeric"
            for v in d["violations"]
        )

    def test_risk_level_not_low_blocked(self):
        for risk in ("medium", "high", "critical", "unknown"):
            d = validate_ship_request(_valid_packet(risk_level=risk))
            assert d["validation_result"] == "blocked"
            assert any(
                v["rule_id"] == "risk_level_not_low" for v in d["violations"]
            )

    def test_blocked_execution_record_nonempty_blocked(self):
        d = validate_ship_request(_valid_packet(blocked_execution_record={"reason": "x"}))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "blocked_execution_record_nonempty"
            for v in d["violations"]
        )

    def test_automation_claim_status_must_be_in_allowlist(self):
        for bad in ("no_execution_claim", "child_invoked_with_handle", "anything_else"):
            d = validate_ship_request(_valid_packet(automation_claim_status=bad))
            if bad == "child_invoked_with_handle":
                # child_invoked_with_handle is NOT in v0 allowlist
                # (allowlist: child_attached_with_handle,
                # parent_completed_with_handle, direct_packet_with_handle)
                assert d["validation_result"] == "blocked"
            else:
                assert d["validation_result"] == "blocked"
            assert any(
                v["rule_id"] == "automation_claim_status_not_allowed"
                for v in d["violations"]
            )


# ── §6.2 ship class allowlist ─────────────────────────────────────────────


class TestShipClass:
    @pytest.mark.parametrize("good", sorted(ALLOWED_SHIP_CLASSES))
    def test_each_allowed_ship_class_passes(self, good):
        # Need to also adjust changed_paths to match the class
        path_map = {
            "docs_canary": "docs/autoship-canaries/x.md",
            "metadata_canary": "workflow/autoship_canaries/x.json",
            "test_fixture_canary": "tests/fixtures/autoship_canaries/x.json",
        }
        d = validate_ship_request(_valid_packet(
            ship_class=good,
            changed_paths=[path_map[good]],
        ))
        assert d["validation_result"] == "passed"

    def test_runtime_ship_class_blocked(self):
        d = validate_ship_request(_valid_packet(ship_class="runtime_change"))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "ship_class_not_allowed" for v in d["violations"]
        )


# ── §6.2 path allowlist + §6.2 forbidden ──────────────────────────────────


class TestPaths:
    def test_empty_changed_paths_blocked(self):
        d = validate_ship_request(_valid_packet(changed_paths=[]))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "changed_paths_empty" for v in d["violations"]
        )

    def test_path_not_under_allowed_prefix_blocked(self):
        d = validate_ship_request(_valid_packet(
            changed_paths=["docs/random/path.md"]
        ))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "changed_path_not_allowed" for v in d["violations"]
        )

    @pytest.mark.parametrize("bad", FORBIDDEN_PATH_PREFIXES)
    def test_each_forbidden_prefix_blocked(self, bad):
        d = validate_ship_request(_valid_packet(
            changed_paths=[f"{bad}foo.py"]
        ))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "changed_path_forbidden_prefix"
            for v in d["violations"]
        )

    def test_forbidden_substring_env_blocked(self):
        d = validate_ship_request(_valid_packet(
            changed_paths=["docs/autoship-canaries/.env.example"]
        ))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "changed_path_forbidden_substring"
            for v in d["violations"]
        )

    def test_forbidden_substring_secret_blocked(self):
        d = validate_ship_request(_valid_packet(
            changed_paths=["docs/autoship-canaries/secrets-doc.md"]
        ))
        assert d["validation_result"] == "blocked"

    def test_path_normalization_does_not_let_forbidden_in(self):
        # ``./workflow/api/x`` normalizes to ``workflow/api/x`` and must be blocked
        d = validate_ship_request(_valid_packet(
            changed_paths=["./workflow/api/something.py"]
        ))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "changed_path_forbidden_prefix"
            for v in d["violations"]
        )

    def test_invalid_changed_path_entry_blocked(self):
        d = validate_ship_request(_valid_packet(changed_paths=[None, ""]))
        assert d["validation_result"] == "blocked"
        assert sum(
            1 for v in d["violations"] if v["rule_id"] == "changed_path_invalid"
        ) == 2


# ── §6.3 diff-content checks ──────────────────────────────────────────────


class TestDiffContent:
    def test_diff_under_size_cap_passes(self):
        d = validate_ship_request(_valid_packet(diff="x" * (DIFF_SIZE_BYTES_MAX - 100)))
        assert d["validation_result"] == "passed"

    def test_diff_over_size_cap_blocked(self):
        d = validate_ship_request(_valid_packet(diff="x" * (DIFF_SIZE_BYTES_MAX + 1)))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "diff_too_large" for v in d["violations"]
        )

    def test_binary_content_blocked(self):
        d = validate_ship_request(_valid_packet(diff="some text\0more text"))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "diff_binary_content" for v in d["violations"]
        )

    def test_openai_secret_in_diff_blocked(self):
        d = validate_ship_request(_valid_packet(
            diff="+ OPENAI_KEY = sk-abc1234567890def1234567890\n"
        ))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "diff_secret_pattern" for v in d["violations"]
        )

    def test_aws_secret_in_diff_blocked(self):
        d = validate_ship_request(_valid_packet(
            diff="+ AWS_ACCESS = AKIAIOSFODNN7EXAMPLE\n"
        ))
        assert d["validation_result"] == "blocked"

    def test_private_key_block_blocked(self):
        d = validate_ship_request(_valid_packet(
            diff="-----BEGIN RSA PRIVATE KEY-----\nfake\n"
        ))
        assert d["validation_result"] == "blocked"

    def test_diff_non_string_blocked(self):
        d = validate_ship_request(_valid_packet(diff=42))
        assert d["validation_result"] == "blocked"
        assert any(
            v["rule_id"] == "diff_not_string" for v in d["violations"]
        )


# ── Rollback handle composition ───────────────────────────────────────────


class TestRollbackHandle:
    def test_handle_uses_rollback_plan_when_present(self):
        d = validate_ship_request(_valid_packet(rollback_plan="Revert commit abc123"))
        assert d["rollback_handle"] == "revert:Revert commit abc123"

    def test_handle_falls_back_to_evidence_handle_for_auto_plan(self):
        d = validate_ship_request(_valid_packet(
            rollback_plan="auto",
            stable_evidence_handle="child_run:b:r",
        ))
        assert "child_run:b:r" in d["rollback_handle"]


# ── Aggregate violation reporting ─────────────────────────────────────────


class TestAggregateReporting:
    def test_multiple_violations_all_collected(self):
        # Build a packet that violates several rules at once.
        bad = {
            "release_gate_result": "HOLD",
            "ship_class": "runtime_change",
            "child_keep_reject_decision": "REJECT",
            "child_score": 1.0,
            "risk_level": "high",
            "blocked_execution_record": {"x": 1},
            "stable_evidence_handle": "h",
            "automation_claim_status": "no_execution_claim",
            "rollback_plan": "rb",
            "changed_paths": ["workflow/api/foo.py"],  # forbidden prefix
            "diff": "x",
        }
        d = validate_ship_request(bad)
        assert d["validation_result"] == "blocked"
        rule_ids = {v["rule_id"] for v in d["violations"]}
        # Spot-check we collected several distinct violations rather than bailing on first
        assert "release_gate_not_approved" in rule_ids
        assert "child_decision_not_keep" in rule_ids
        assert "child_score_below_threshold" in rule_ids
        assert "risk_level_not_low" in rule_ids
        assert "ship_class_not_allowed" in rule_ids
        assert "automation_claim_status_not_allowed" in rule_ids
        assert "changed_path_forbidden_prefix" in rule_ids
