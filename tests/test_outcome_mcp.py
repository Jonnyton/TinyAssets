"""Tests for outcome evaluators MCP actions in extensions().

Covers: record_outcome, list_outcomes, get_outcome.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tinyassets.runs import create_run, initialize_runs_db
from tinyassets.universe_server import extensions


@pytest.fixture(autouse=True)
def _set_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "tinyassets.api.permissions.current_request_actor_id",
        lambda: "account-alice",
    )
    initialize_runs_db(tmp_path)
    run_ids = {
        "run-001", "run-A", "run-B", "run-C", "run-X", "run-Y",
        *(f"run-{index}" for index in range(3)),
        *(f"run-{kind}" for kind in (
            "published_paper", "merged_pr", "deployed_app",
            "won_competition", "custom",
        )),
    }
    for run_id in run_ids:
        generated = create_run(
            tmp_path,
            branch_def_id="branch-owned",
            thread_id=f"thread-{run_id}",
            inputs={},
            actor="account-alice",
            owner_user_id="account-alice",
        )
        with sqlite3.connect(tmp_path / ".runs.db") as conn:
            conn.execute(
                "UPDATE runs SET run_id = ? WHERE run_id = ?",
                (run_id, generated),
            )


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

    def test_record_nonexistent_run_is_refused(self):
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-does-not-exist",
            event_type="merged_pr",
        ))
        assert result["code"] == "handoff_authority_required"

    def test_record_foreign_run_is_refused(self, tmp_path):
        create_run(
            tmp_path,
            branch_def_id="branch-foreign",
            thread_id="thread-foreign",
            inputs={},
            actor="account-bob",
            owner_user_id="account-bob",
        )
        with sqlite3.connect(tmp_path / ".runs.db") as conn:
            foreign_run_id = conn.execute(
                "SELECT run_id FROM runs WHERE owner_user_id = 'account-bob'"
            ).fetchone()[0]

        result = json.loads(extensions(
            action="record_outcome",
            run_id=foreign_run_id,
            event_type="merged_pr",
        ))
        assert result["code"] == "handoff_authority_required"

    def test_record_requires_an_authenticated_subject(self, monkeypatch):
        monkeypatch.setattr(
            "tinyassets.api.permissions.current_request_actor_id",
            lambda: "anonymous",
        )
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="merged_pr",
        ))
        assert result["code"] == "handoff_authority_required"

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

    def test_record_enters_the_user_attested_evidence_lifecycle(self, tmp_path):
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="deployed_app",
            evidence_url="https://example.com/deploy",
        ))

        with sqlite3.connect(tmp_path / ".runs.db") as conn:
            evidence = conn.execute(
                """
                SELECT evidence_level, evidence_source
                  FROM outcome_evidence
                 WHERE outcome_id = ?
                """,
                (result["outcome_id"],),
            ).fetchone()
            transitions = conn.execute(
                """
                SELECT seq, from_level, to_level
                  FROM outcome_evidence_transition
                 WHERE outcome_id = ?
                 ORDER BY seq
                """,
                (result["outcome_id"],),
            ).fetchall()

        assert evidence == ("user_attested", "user_attestation")
        assert transitions == [(1, "", "user_attested")]

    def test_record_attributes_the_authenticated_account_and_attester(self, tmp_path):
        result = json.loads(extensions(
            action="record_outcome",
            run_id="run-001",
            event_type="deployed_app",
        ))
        with sqlite3.connect(tmp_path / ".runs.db") as conn:
            evidence = conn.execute(
                """
                SELECT account_id, attested_by
                  FROM outcome_evidence
                 WHERE outcome_id = ?
                """,
                (result["outcome_id"],),
            ).fetchone()
            actor = conn.execute(
                """
                SELECT actor_id
                  FROM outcome_evidence_transition
                 WHERE outcome_id = ?
                """,
                (result["outcome_id"],),
            ).fetchone()

        assert evidence == ("account-alice", "account-alice")
        assert actor == ("account-alice",)

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
        assert fetched["account_id"] == "account-alice"
        assert fetched["attested_by"] == "account-alice"
        assert fetched["evidence_level"] == "user_attested"
        assert fetched["evidence_transitions"] == [{
            "seq": 1,
            "from_level": "",
            "to_level": "user_attested",
            "evidence_source": "user_attestation",
            "actor_id": "account-alice",
            "evidence": {},
            "recorded_at": fetched["recorded_at"],
        }]

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
        assert all(o["evidence_level"] == "user_attested" for o in result["outcomes"])
        assert all(o["attested_by"] == "account-alice" for o in result["outcomes"])

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

    @pytest.mark.parametrize(
        ("limit", "expected_count"),
        [(0, 2), (-1, 1), ("invalid", 2)],
    )
    def test_list_nonpositive_or_invalid_limit_uses_a_positive_bound(
        self, limit, expected_count
    ):
        extensions(action="record_outcome", run_id="run-A", event_type="merged_pr")
        extensions(action="record_outcome", run_id="run-B", event_type="merged_pr")

        result = json.loads(extensions(action="list_outcomes", limit=limit))

        assert result["count"] == expected_count


# ── available_actions listing ──────────────────────────────────────────────────

class TestOutcomeActionsInAvailableList:
    def test_outcome_actions_listed_on_unknown_action(self):
        result = json.loads(extensions(action="nonexistent_xyz_action"))
        available = result.get("available_actions", [])
        assert "record_outcome" in available
        assert "list_outcomes" in available
        assert "get_outcome" in available
