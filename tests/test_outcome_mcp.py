"""Tests for outcome evaluators MCP actions in extensions().

Covers: record_outcome, list_outcomes, get_outcome.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.runs import initialize_runs_db
from tinyassets.universe_server import extensions
@pytest.fixture(autouse=True)
def _set_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    initialize_runs_db(tmp_path)


# ── record_outcome ─────────────────────────────────────────────────────────────

class TestRecordOutcome:
    def test_record_roundtrip(self):
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="merged_pr",
        ))
        assert result["status"] == "recorded"
        assert "outcome_id" in result
        assert result["run_id"] == "run-001"
        assert result["outcome_type"] == "merged_pr"
        assert "recorded_at" in result

    def test_record_all_valid_types(self):
        valid_types = [
            "published_paper", "merged_pr", "deployed_app",
            "won_competition", "custom",
        ]
        for ot in valid_types:
            result = json.loads(extensions(
                action="record_outcome",
                run_id=f"run-{ot}",
                event_type=ot,
            ))
            assert result["status"] == "recorded", f"Failed for {ot}"

    def test_record_missing_run_id_returns_error(self):
        result = json.loads(extensions(
            action="record_outcome",
            event_type="merged_pr",
        ))
        assert "error" in result

    def test_record_missing_outcome_type_returns_error(self):
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
        ))
        assert "error" in result

    def test_record_invalid_outcome_type_returns_error(self):
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="not_a_real_type",
        ))
        assert "error" in result
        assert "valid" in result

    def test_record_with_evidence_url(self):
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="deployed_app",
            evidence_url="https://example.com/deploy",
        ))
        assert result["status"] == "recorded"

    def test_record_with_gate_event_linkage(self):
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="merged_pr",
            gate_event_id="gate-abc-123",
        ))
        assert result["status"] == "recorded"
        oid = result["outcome_id"]
        fetched = json.loads(extensions(
            action="get_outcome",
            outcome_id=oid,
        ))
        assert fetched["claim_run_id"] == "gate-abc-123"

    def test_record_produces_unique_ids(self):
        r1 = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="custom",
        ))
        r2 = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="custom",
        ))
        assert r1["outcome_id"] != r2["outcome_id"]

    def test_record_with_payload_json(self):
        payload = json.dumps({"pr_number": 42, "repo": "owner/repo"})
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="merged_pr",
            outcome_payload_json=payload,
        ))
        assert result["status"] == "recorded"
        oid = result["outcome_id"]
        fetched = json.loads(extensions(action="get_outcome", outcome_id=oid))
        assert fetched["payload"]["pr_number"] == 42

    def test_record_with_note(self):
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="custom",
            outcome_note="manually verified by reviewer",
        ))
        assert result["status"] == "recorded"
        fetched = json.loads(extensions(
            action="get_outcome", outcome_id=result["outcome_id"]
        ))
        assert fetched["note"] == "manually verified by reviewer"


# ── get_outcome ────────────────────────────────────────────────────────────────

class TestGetOutcome:
    def test_get_existing_outcome(self):
        recorded = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="deployed_app",
        ))
        fetched = json.loads(extensions(
            action="get_outcome",
            outcome_id=recorded["outcome_id"],
        ))
        assert fetched["outcome_id"] == recorded["outcome_id"]
        assert fetched["run_id"] == "run-001"
        assert fetched["outcome_type"] == "deployed_app"

    def test_get_nonexistent_returns_error(self):
        result = json.loads(extensions(
            action="get_outcome",
            outcome_id="nonexistent-id-xyz",
        ))
        assert "error" in result

    def test_get_missing_outcome_id_returns_error(self):
        result = json.loads(extensions(action="get_outcome"))
        assert "error" in result


# ── list_outcomes ──────────────────────────────────────────────────────────────

class TestListOutcomes:
    def test_list_by_run_id(self):
        extensions(
            action="record_outcome", run_id="run-A", event_type="merged_pr"
        )
        extensions(
            action="record_outcome", run_id="run-A", event_type="deployed_app"
        )
        extensions(
            action="record_outcome", run_id="run-B", event_type="custom"
        )
        result = json.loads(extensions(
            action="list_outcomes", run_id="run-A"
        ))
        assert result["count"] == 2
        assert all(o["run_id"] == "run-A" for o in result["outcomes"])

    def test_list_by_outcome_type(self):
        extensions(
            action="record_outcome", run_id="run-A", event_type="merged_pr"
        )
        extensions(
            action="record_outcome", run_id="run-B", event_type="deployed_app"
        )
        extensions(
            action="record_outcome", run_id="run-C", event_type="merged_pr"
        )
        result = json.loads(extensions(
            action="list_outcomes", event_type="merged_pr"
        ))
        assert result["count"] == 2
        assert all(o["outcome_type"] == "merged_pr" for o in result["outcomes"])

    def test_list_combined_run_and_type_filter(self):
        extensions(
            action="record_outcome", run_id="run-A", event_type="merged_pr"
        )
        extensions(
            action="record_outcome", run_id="run-A", event_type="deployed_app"
        )
        result = json.loads(extensions(
            action="list_outcomes", run_id="run-A", event_type="merged_pr"
        ))
        assert result["count"] == 1
        assert result["outcomes"][0]["outcome_type"] == "merged_pr"

    def test_list_empty_when_no_matches(self):
        result = json.loads(extensions(
            action="list_outcomes", run_id="nonexistent-run"
        ))
        assert result["count"] == 0
        assert result["outcomes"] == []

    def test_list_no_filter_returns_all(self):
        for i in range(3):
            extensions(
                action="record_outcome",
                run_id=f"run-{i}",
                event_type="custom",
            )
        result = json.loads(extensions(action="list_outcomes"))
        assert result["count"] == 3

    def test_cross_run_isolation_by_run_id(self):
        extensions(
            action="record_outcome", run_id="run-X", event_type="merged_pr"
        )
        extensions(
            action="record_outcome", run_id="run-Y", event_type="merged_pr"
        )
        x_results = json.loads(extensions(
            action="list_outcomes", run_id="run-X"
        ))
        y_results = json.loads(extensions(
            action="list_outcomes", run_id="run-Y"
        ))
        assert x_results["count"] == 1
        assert y_results["count"] == 1
        assert x_results["outcomes"][0]["run_id"] == "run-X"
        assert y_results["outcomes"][0]["run_id"] == "run-Y"

    def test_list_by_branch_def_id_no_runs_returns_empty(self):
        result = json.loads(extensions(
            action="list_outcomes", branch_def_id="branch-that-has-no-runs"
        ))
        assert result["count"] == 0
        assert result["outcomes"] == []


# ── available_actions listing ──────────────────────────────────────────────────

class TestOutcomeActionsInAvailableList:
    def test_outcome_actions_listed_on_unknown_action(self):
        result = json.loads(extensions(action="nonexistent_xyz_action"))
        available = result.get("available_actions", [])
        assert "record_outcome" in available
        assert "list_outcomes" in available
        assert "get_outcome" in available
