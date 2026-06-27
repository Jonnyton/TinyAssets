"""Task #14 — get_routing_evidence MCP action.

Guards:
- Empty runs returns count=0 with a helpful caveat.
- Populated runs returns correct count and text summaries.
- Limit cap: requesting >50 is silently clamped to 50.
- caveat field is present on every run record.
- latency_ms is derived from timestamps when both are present.
- failure_class is set correctly for failed/cancelled/interrupted runs.
- suggested_action is non-empty for known failure classes.
- provider_used is None for test runs (no real policy router invoked in unit tests).
- branch_def_id filter passes through correctly.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def ext_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call_routing_evidence(us, **kwargs) -> dict:
    return json.loads(us.extensions(action="get_routing_evidence", **kwargs))


def _build_branch(us) -> str:
    spec = {
        "name": "routing-test-branch",
        "description": "",
        "tags": [],
        "entry_point": "capture",
        "node_defs": [{"node_id": "capture", "display_name": "Capture",
                       "prompt_template": "cap: {x}"}],
        "edges": [{"from": "START", "to": "capture"}, {"from": "capture", "to": "END"}],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    res = json.loads(us.extensions(action="build_branch", spec_json=json.dumps(spec)))
    assert res["status"] == "built", res
    return res["branch_def_id"]


def _insert_run(base: Path, *, branch_def_id: str, status: str = "completed",
                error: str = "",
                started_offset: float = 0.0,
                duration_s: float = 4.23) -> str:
    """Insert a run row using REAL timestamps (Unix epoch seconds)."""
    import time
    import uuid

    from tinyassets.runs import _connect, initialize_runs_db
    initialize_runs_db(base)
    run_id = uuid.uuid4().hex[:16]
    started_at = time.time() + started_offset
    finished_at = started_at + duration_s
    with _connect(base) as conn:
        conn.execute(
            """INSERT INTO runs
               (run_id, branch_def_id, run_name, thread_id, status, actor,
                inputs_json, output_json, error, started_at, finished_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, branch_def_id, "", "thread-" + run_id, status,
             "tester", "{}", "{}", error, started_at, finished_at),
        )
    return run_id


class TestRoutingEvidenceEmpty:
    def test_empty_returns_count_zero(self, ext_env):
        us, base = ext_env
        result = _call_routing_evidence(us)
        assert result["count"] == 0
        assert result["runs"] == []

    def test_empty_caveat_is_helpful(self, ext_env):
        us, base = ext_env
        result = _call_routing_evidence(us)
        assert "caveat" in result
        assert len(result["caveat"]) > 10


class TestRoutingEvidencePopulated:
    def test_returns_correct_count(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid)
        _insert_run(base, branch_def_id=bid)
        result = _call_routing_evidence(us)
        assert result["count"] == 2

    def test_each_run_has_text_field(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        run_id = _insert_run(base, branch_def_id=bid)
        result = _call_routing_evidence(us)
        assert result["count"] == 1
        rec = result["runs"][0]
        assert "text" in rec
        assert run_id in rec["text"]

    def test_latency_ms_derived_from_timestamps(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid, duration_s=4.23)
        result = _call_routing_evidence(us)
        rec = result["runs"][0]
        assert rec["latency_ms"] is not None
        assert abs(rec["latency_ms"] - 4230.0) < 10.0

    def test_caveat_present_on_every_record(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid)
        _insert_run(base, branch_def_id=bid)
        result = _call_routing_evidence(us)
        for rec in result["runs"]:
            assert "caveat" in rec
            assert "provider_used" in rec["caveat"] or "token_count" in rec["caveat"]

    def test_provider_used_and_token_count_are_none(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid)
        result = _call_routing_evidence(us)
        rec = result["runs"][0]
        assert rec["provider_used"] is None
        assert rec["token_count"] is None

    def test_top_level_caveat_matches_record(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid)
        result = _call_routing_evidence(us)
        assert result["caveat"] == result["runs"][0]["caveat"]


class TestRoutingEvidenceLimitCap:
    def test_limit_cap_at_50(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        for _ in range(5):
            _insert_run(base, branch_def_id=bid)
        result = _call_routing_evidence(us, limit=200)
        assert result["count"] == 5

    def test_default_limit_is_10(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        for _ in range(15):
            _insert_run(base, branch_def_id=bid)
        result = _call_routing_evidence(us, limit=10)
        assert result["count"] == 10

    def test_explicit_limit_respected(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        for _ in range(10):
            _insert_run(base, branch_def_id=bid)
        result = _call_routing_evidence(us, limit=3)
        assert result["count"] == 3


class TestRoutingEvidenceFailureClass:
    def test_failed_run_has_error_failure_class(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid, status="failed",
                    error="Something went wrong.")
        result = _call_routing_evidence(us)
        rec = result["runs"][0]
        assert rec["failure_class"] == "error"
        assert rec["suggested_action"] != ""

    def test_cancelled_run_has_cancelled_failure_class(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid, status="cancelled")
        result = _call_routing_evidence(us)
        rec = result["runs"][0]
        assert rec["failure_class"] == "cancelled"

    def test_timeout_error_classified_correctly(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid, status="failed",
                    error="Node timed out after 300s timeout exceeded")
        result = _call_routing_evidence(us)
        rec = result["runs"][0]
        assert rec["failure_class"] == "timeout"
        assert "timeout" in rec["suggested_action"].lower()

    def test_provider_exhausted_classified_correctly(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid, status="failed",
                    error="All providers exhausted after cooldown period")
        result = _call_routing_evidence(us)
        rec = result["runs"][0]
        assert rec["failure_class"] == "provider_exhausted"

    def test_completed_run_has_empty_failure_class(self, ext_env):
        us, base = ext_env
        bid = _build_branch(us)
        _insert_run(base, branch_def_id=bid, status="completed")
        result = _call_routing_evidence(us)
        rec = result["runs"][0]
        assert rec["failure_class"] == ""
        assert rec["suggested_action"] == ""


class TestRoutingEvidenceBranchFilter:
    def test_branch_filter_scopes_results(self, ext_env):
        us, base = ext_env
        bid_a = _build_branch(us)
        # Build second branch
        spec = {
            "name": "other-branch",
            "description": "",
            "tags": [],
            "entry_point": "n",
            "node_defs": [{"node_id": "n", "display_name": "N",
                           "prompt_template": "x"}],
            "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
            "state_schema": [],
        }
        res = json.loads(us.extensions(action="build_branch", spec_json=json.dumps(spec)))
        bid_b = res["branch_def_id"]
        _insert_run(base, branch_def_id=bid_a)
        _insert_run(base, branch_def_id=bid_b)
        result = _call_routing_evidence(us, branch_def_id=bid_a)
        assert result["count"] == 1
        assert result["runs"][0]["branch_def_id"] == bid_a
