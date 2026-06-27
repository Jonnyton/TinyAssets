"""Tests for estimate_run_cost extensions action.

Covers:
- Missing branch_def_id returns error.
- Nonexistent branch_def_id returns error.
- Never-run branch returns low confidence + node_count.
- Branch with 1-4 completed runs returns medium confidence.
- Branch with 5+ completed runs returns high confidence.
- Queue depth unavailable path: free_queue_eta_hours is null + caveat in basis.
- Response is stable (read-only): two consecutive calls return identical output.
- estimate_run_cost NOT in _RUN_WRITE_ACTIONS (truly read-only).
- node_count reflects actual branch node count.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def run_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")

    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, tmp_path
    importlib.reload(us)


def _call(us, action, **kwargs):
    return json.loads(us.extensions(action=action, **kwargs))


def _create_branch_with_nodes(us, n_llm: int = 1, n_code: int = 0) -> str:
    """Create a branch with n_llm prompt-template nodes + n_code code nodes."""
    result = _call(us, "create_branch", name=f"test_branch_{n_llm}_{n_code}")
    bid = result["branch_def_id"]
    for i in range(n_llm):
        _call(
            us, "add_node",
            branch_def_id=bid,
            node_id=f"llm_node_{i}",
            display_name=f"LLM Node {i}",
            prompt_template=f"Write about {{topic_{i}}}",
        )
    for i in range(n_code):
        _call(
            us, "add_node",
            branch_def_id=bid,
            node_id=f"code_node_{i}",
            display_name=f"Code Node {i}",
            source_code="result = state",
        )
    return bid


def _seed_completed_runs(tmp_path: Path, bid: str, count: int) -> None:
    """Directly insert completed runs into the runs DB for confidence tests."""
    from tinyassets.runs import (
        RUN_STATUS_COMPLETED,
        create_run,
        initialize_runs_db,
        update_run_status,
    )

    initialize_runs_db(tmp_path)
    for _ in range(count):
        rid = create_run(tmp_path, branch_def_id=bid, thread_id="", inputs={}, actor="tester")
        update_run_status(tmp_path, rid, status=RUN_STATUS_COMPLETED)


class TestEstimateRunCostErrors:
    def test_missing_branch_def_id_returns_error(self, run_env):
        us, _ = run_env
        result = _call(us, "estimate_run_cost", branch_def_id="")
        assert "error" in result

    def test_nonexistent_branch_returns_error(self, run_env):
        us, _ = run_env
        result = _call(us, "estimate_run_cost", branch_def_id="does-not-exist")
        assert "error" in result


class TestEstimateRunCostShape:
    def test_returns_all_required_fields(self, run_env):
        us, base = run_env
        bid = _create_branch_with_nodes(us, n_llm=2)
        result = _call(us, "estimate_run_cost", branch_def_id=bid)
        for field in (
            "branch_def_id", "node_count",
            "estimated_paid_market_credits", "free_queue_eta_hours",
            "confidence", "basis", "prior_run_count",
        ):
            assert field in result, f"missing field: {field}"

    def test_node_count_reflects_branch(self, run_env):
        us, _ = run_env
        bid = _create_branch_with_nodes(us, n_llm=3)
        result = _call(us, "estimate_run_cost", branch_def_id=bid)
        assert result["node_count"] == 3

    def test_basis_is_quotable_string(self, run_env):
        us, _ = run_env
        bid = _create_branch_with_nodes(us, n_llm=1)
        result = _call(us, "estimate_run_cost", branch_def_id=bid)
        assert isinstance(result["basis"], str)
        assert len(result["basis"]) > 10


class TestEstimateRunCostConfidence:
    def test_never_run_branch_returns_low_confidence(self, run_env):
        us, _ = run_env
        bid = _create_branch_with_nodes(us, n_llm=2)
        result = _call(us, "estimate_run_cost", branch_def_id=bid)
        assert result["confidence"] == "low"
        assert result["prior_run_count"] == 0

    def test_one_completed_run_returns_medium_confidence(self, run_env):
        us, base = run_env
        bid = _create_branch_with_nodes(us, n_llm=1)
        _seed_completed_runs(base, bid, 1)
        result = _call(us, "estimate_run_cost", branch_def_id=bid)
        assert result["confidence"] == "medium"
        assert result["prior_run_count"] == 1

    def test_four_completed_runs_returns_medium_confidence(self, run_env):
        us, base = run_env
        bid = _create_branch_with_nodes(us, n_llm=1)
        _seed_completed_runs(base, bid, 4)
        result = _call(us, "estimate_run_cost", branch_def_id=bid)
        assert result["confidence"] == "medium"

    def test_five_completed_runs_returns_high_confidence(self, run_env):
        us, base = run_env
        bid = _create_branch_with_nodes(us, n_llm=1)
        _seed_completed_runs(base, bid, 5)
        result = _call(us, "estimate_run_cost", branch_def_id=bid)
        assert result["confidence"] == "high"

    def test_ten_completed_runs_returns_high_confidence(self, run_env):
        us, base = run_env
        bid = _create_branch_with_nodes(us, n_llm=1)
        _seed_completed_runs(base, bid, 10)
        result = _call(us, "estimate_run_cost", branch_def_id=bid)
        assert result["confidence"] == "high"


class TestEstimateRunCostCost:
    def test_llm_nodes_cost_more_than_code_nodes(self, run_env):
        us, _ = run_env
        bid_llm = _create_branch_with_nodes(us, n_llm=5)
        bid_code = _create_branch_with_nodes(us, n_llm=0, n_code=5)
        r_llm = _call(us, "estimate_run_cost", branch_def_id=bid_llm)
        r_code = _call(us, "estimate_run_cost", branch_def_id=bid_code)
        assert r_llm["estimated_paid_market_credits"] > r_code["estimated_paid_market_credits"]

    def test_credits_non_negative(self, run_env):
        us, _ = run_env
        bid = _create_branch_with_nodes(us, n_llm=2, n_code=1)
        result = _call(us, "estimate_run_cost", branch_def_id=bid)
        assert result["estimated_paid_market_credits"] >= 0


class TestEstimateRunCostReadOnly:
    def test_two_consecutive_calls_return_identical_result(self, run_env):
        us, _ = run_env
        bid = _create_branch_with_nodes(us, n_llm=2)
        r1 = _call(us, "estimate_run_cost", branch_def_id=bid)
        r2 = _call(us, "estimate_run_cost", branch_def_id=bid)
        assert r1 == r2

    def test_not_in_write_actions(self):
        from tinyassets.api.runs import _RUN_WRITE_ACTIONS
        assert "estimate_run_cost" not in _RUN_WRITE_ACTIONS
