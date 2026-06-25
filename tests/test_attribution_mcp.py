"""Tests for attribution chain MCP actions in extensions().

Covers: record_remix, get_provenance.
"""

from __future__ import annotations

import json

import pytest

from workflow.runs import initialize_runs_db
from workflow.universe_server import extensions


@pytest.fixture(autouse=True)
def _set_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    initialize_runs_db(tmp_path)


# ── record_remix ───────────────────────────────────────────────────────────────

class TestRecordRemix:
    def test_record_stores_edge(self):
        result = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
        ))
        assert result["status"] == "recorded"
        assert "edge_id" in result
        assert result["parent_branch_def_id"] == "branch-A"
        assert result["child_branch_def_id"] == "branch-B"
        assert result["generation_depth"] == 1

    def test_record_all_valid_contribution_kinds(self):
        valid_kinds = ["remix", "patch", "template", "original"]
        for i, kind in enumerate(valid_kinds):
            result = json.loads(extensions(
                action="record_remix",
                parent_branch_def_id=f"branch-P{i}",
                child_branch_def_id=f"branch-C{i}",
                contribution_kind=kind,
            ))
            assert result["status"] == "recorded", f"Failed for kind={kind}"
            assert result["contribution_kind"] == kind

    def test_record_missing_parent_returns_error(self):
        result = json.loads(extensions(
            action="record_remix",
            child_branch_def_id="branch-B",
        ))
        assert "error" in result

    def test_record_missing_child_returns_error(self):
        result = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
        ))
        assert "error" in result

    def test_record_invalid_contribution_kind_returns_error(self):
        result = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
            contribution_kind="invented",
        ))
        assert "error" in result
        assert "valid" in result

    def test_record_same_parent_child_rejected(self):
        result = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-A",
        ))
        assert "error" in result

    def test_record_duplicate_edge_rejected(self):
        extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
        )
        result = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
        ))
        assert "error" in result

    def test_record_with_credit_share(self):
        result = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
            credit_share=0.3,
        ))
        assert result["status"] == "recorded"
        assert abs(result["credit_share"] - 0.3) < 1e-9

    def test_record_credit_persists_identity_tuple(self, tmp_path):
        from workflow.api.market import _action_record_remix

        result = json.loads(_action_record_remix({
            "parent_branch_def_id": "branch-A",
            "child_branch_def_id": "branch-B",
            "actor_id": "actor-daemon",
            "owner_user_id": "owner-user",
            "daemon_id": "daemon::actor",
            "runtime_instance_id": "runtime-1",
            "worker_id": "worker-1",
            "credit_share": 0.3,
        }))
        assert result["status"] == "recorded"

        from workflow.runs import _connect

        with _connect(tmp_path) as conn:
            row = conn.execute(
                """
                SELECT actor_id, owner_user_id, daemon_id,
                       runtime_instance_id, worker_id, credit_share
                FROM attribution_credit
                WHERE artifact_id = ? AND artifact_kind = 'branch'
                """,
                ("branch-B",),
            ).fetchone()
        assert row["actor_id"] == "actor-daemon"
        assert row["owner_user_id"] == "owner-user"
        assert row["daemon_id"] == "daemon::actor"
        assert row["runtime_instance_id"] == "runtime-1"
        assert row["worker_id"] == "worker-1"
        assert row["credit_share"] == pytest.approx(0.3)

    def test_cycle_rejected_direct(self):
        extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
        )
        result = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-B",
            child_branch_def_id="branch-A",
        ))
        assert "error" in result
        assert "cycle" in result["error"].lower()

    def test_cycle_rejected_transitive(self):
        extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
        )
        extensions(
            action="record_remix",
            parent_branch_def_id="branch-B",
            child_branch_def_id="branch-C",
        )
        result = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-C",
            child_branch_def_id="branch-A",
        ))
        assert "error" in result
        assert "cycle" in result["error"].lower()

    def test_generation_depth_increments(self):
        r1 = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
        ))
        r2 = json.loads(extensions(
            action="record_remix",
            parent_branch_def_id="branch-B",
            child_branch_def_id="branch-C",
        ))
        assert r1["generation_depth"] == 1
        assert r2["generation_depth"] == 2


# ── get_provenance ─────────────────────────────────────────────────────────────

class TestGetProvenance:
    def test_provenance_returns_chain(self):
        extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
        )
        result = json.loads(extensions(
            action="get_provenance",
            child_branch_def_id="branch-B",
        ))
        assert "chain" in result
        assert result["count"] == 1
        assert result["chain"][0]["parent_branch_def_id"] == "branch-A"
        assert result["chain"][0]["child_branch_def_id"] == "branch-B"

    def test_provenance_empty_for_original(self):
        result = json.loads(extensions(
            action="get_provenance",
            child_branch_def_id="branch-Z",
        ))
        assert result["count"] == 0
        assert result["chain"] == []

    def test_provenance_missing_child_returns_error(self):
        result = json.loads(extensions(action="get_provenance"))
        assert "error" in result

    def test_provenance_multi_hop_chain(self):
        extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
        )
        extensions(
            action="record_remix",
            parent_branch_def_id="branch-B",
            child_branch_def_id="branch-C",
        )
        result = json.loads(extensions(
            action="get_provenance",
            child_branch_def_id="branch-C",
        ))
        assert result["count"] == 2
        edge_pairs = {
            (e["parent_branch_def_id"], e["child_branch_def_id"])
            for e in result["chain"]
        }
        assert ("branch-A", "branch-B") in edge_pairs
        assert ("branch-B", "branch-C") in edge_pairs

    def test_max_depth_limits_chain(self):
        # Build chain: A→B→C→D (3 hops)
        extensions(action="record_remix", parent_branch_def_id="branch-A",
                   child_branch_def_id="branch-B")
        extensions(action="record_remix", parent_branch_def_id="branch-B",
                   child_branch_def_id="branch-C")
        extensions(action="record_remix", parent_branch_def_id="branch-C",
                   child_branch_def_id="branch-D")
        # max_depth=1 should only return the direct edge C→D
        result = json.loads(extensions(
            action="get_provenance",
            child_branch_def_id="branch-D",
            max_depth=1,
        ))
        assert result["count"] == 1
        assert result["chain"][0]["child_branch_def_id"] == "branch-D"


# ── Cross-universe isolation ───────────────────────────────────────────────────

class TestCrossUniverseIsolation:
    def test_record_in_one_universe_invisible_in_another(self, tmp_path, monkeypatch):
        universe1 = tmp_path / "u1"
        universe2 = tmp_path / "u2"
        universe1.mkdir()
        universe2.mkdir()

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(universe1))
        initialize_runs_db(universe1)
        extensions(
            action="record_remix",
            parent_branch_def_id="branch-A",
            child_branch_def_id="branch-B",
        )
        result_u1 = json.loads(extensions(
            action="get_provenance",
            child_branch_def_id="branch-B",
        ))
        assert result_u1["count"] == 1

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(universe2))
        initialize_runs_db(universe2)
        result_u2 = json.loads(extensions(
            action="get_provenance",
            child_branch_def_id="branch-B",
        ))
        assert result_u2["count"] == 0


# ── available_actions listing ──────────────────────────────────────────────────

class TestAttributionActionsInAvailableList:
    def test_attribution_actions_listed_on_unknown_action(self):
        result = json.loads(extensions(action="nonexistent_xyz_action"))
        available = result.get("available_actions", [])
        assert "record_remix" in available
        assert "get_provenance" in available
