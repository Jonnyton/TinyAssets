"""Tests for the ``extensions`` MCP actions added by PR-123 substrate (M2).

- ``quality_leaderboard(goal_id, [author=<viewer>], [force=<include_private>])``
- ``recommended_parent_for_fork(goal_id, ...)``

The dispatch reuses existing ``extensions(...)`` kwargs to keep the
tool signature stable:
  * ``goal_id`` -> Goal under inspection.
  * ``author`` (string) -> optional viewer override; defaults to the
    current actor when omitted.
  * ``force`` (bool) -> include_private flag (host / internal callers).
"""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def us_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from workflow import universe_server as us
    importlib.reload(us)
    yield us, tmp_path
    importlib.reload(us)


def _call(us, action: str, **kwargs) -> dict:
    return json.loads(us.extensions(action=action, **kwargs))


def _seed_goal_and_branches(base_path: Path):
    from workflow.daemon_server import save_branch_definition, save_goal
    from workflow.runs import (
        RUN_STATUS_COMPLETED,
        add_judgment,
        create_run,
        update_run_status,
    )

    save_goal(
        base_path,
        goal=dict(
            goal_id="g-mcp",
            name="Test MCP Goal",
            description="for MCP-surface integration test",
            author="host",
            tags=[],
            visibility="public",
        ),
    )
    for bid, score in (("b-top", 9.0), ("b-mid", 6.0), ("b-low", 3.0)):
        save_branch_definition(
            base_path,
            branch_def=dict(
                branch_def_id=bid,
                name=f"Branch {bid}",
                description="t",
                author="alice",
                tags=[],
                graph_nodes=[],
                edges=[],
                state_schema=[],
                entry_point="",
                published=True,
                goal_id="g-mcp",
            ),
        )
        rid = create_run(
            base_path, branch_def_id=bid, thread_id=bid, inputs={},
        )
        update_run_status(
            base_path, rid,
            status=RUN_STATUS_COMPLETED,
            finished_at=time.time(),
        )
        add_judgment(
            base_path,
            run_id=rid, text="t",
            tags=[f"quality:{score}"],
            author="judge",
        )


# ---------------------------------------------------------------------------
# quality_leaderboard
# ---------------------------------------------------------------------------


def test_quality_leaderboard_requires_goal_id(us_env):
    us, _ = us_env
    result = _call(us, "quality_leaderboard")
    assert "error" in result
    assert result["failure_class"] == "missing_goal_id"


def test_quality_leaderboard_returns_ranked_entries(us_env):
    us, base = us_env
    _seed_goal_and_branches(base)
    result = _call(us, "quality_leaderboard", goal_id="g-mcp")
    assert "entries" in result
    assert len(result["entries"]) == 3
    bids = [e["branch_def_id"] for e in result["entries"]]
    # Higher quality should rank first.
    assert bids[0] == "b-top"
    assert bids[-1] == "b-low"
    # Every entry has rank + score + signals + score_components.
    for entry in result["entries"]:
        assert "rank" in entry
        assert "score" in entry
        assert "signals" in entry
        assert "score_components" in entry
    # Text channel is phone-legible.
    assert "Quality leaderboard" in result["text"]
    assert "Rank | Branch" in result["text"]


def test_quality_leaderboard_empty_goal_renders_friendly_text(us_env):
    us, base = us_env
    from workflow.daemon_server import save_goal
    save_goal(
        base,
        goal=dict(
            goal_id="g-empty", name="Empty", description="", author="h",
            tags=[], visibility="public",
        ),
    )
    result = _call(us, "quality_leaderboard", goal_id="g-empty")
    assert result["entries"] == []
    assert "No Branches" in result["text"]


def test_quality_leaderboard_unknown_goal_returns_no_entries(us_env):
    us, _ = us_env
    result = _call(us, "quality_leaderboard", goal_id="nope")
    assert result["entries"] == []
    # goal is None in the structured payload.
    assert result["goal"] is None


def test_quality_leaderboard_response_includes_formula_disclosure(us_env):
    us, base = us_env
    _seed_goal_and_branches(base)
    result = _call(us, "quality_leaderboard", goal_id="g-mcp")
    assert "formula" in result
    assert "weights" in result["formula"]
    assert "judgment" in result["formula"]["weights"]


# ---------------------------------------------------------------------------
# recommended_parent_for_fork
# ---------------------------------------------------------------------------


def test_recommended_parent_requires_goal_id(us_env):
    us, _ = us_env
    result = _call(us, "recommended_parent_for_fork")
    assert "error" in result
    assert result["failure_class"] == "missing_goal_id"


def test_recommended_parent_returns_top_entry(us_env):
    us, base = us_env
    _seed_goal_and_branches(base)
    result = _call(us, "recommended_parent_for_fork", goal_id="g-mcp")
    parent = result["recommended_parent"]
    assert parent is not None
    assert parent["branch_def_id"] == "b-top"
    assert parent["rank"] == 1
    assert result["leaderboard_size"] == 3
    assert "Recommended parent" in result["text"]


def test_recommended_parent_empty_goal_text_carries_rationale(us_env):
    us, base = us_env
    from workflow.daemon_server import save_goal
    save_goal(
        base,
        goal=dict(
            goal_id="g-empty", name="Empty", description="", author="h",
            tags=[], visibility="public",
        ),
    )
    result = _call(us, "recommended_parent_for_fork", goal_id="g-empty")
    assert result["recommended_parent"] is None
    assert "No Branch is bound" in result["rationale"]
    assert result["text"] == result["rationale"]


# ---------------------------------------------------------------------------
# Tool surface stability — the action names are listed under
# `available_actions` in the unknown-action error so the chatbot can
# discover them.
# ---------------------------------------------------------------------------


def test_unknown_action_lists_new_action_names(us_env):
    us, _ = us_env
    result = _call(us, "does_not_exist")
    actions = result.get("available_actions") or []
    assert "quality_leaderboard" in actions
    assert "recommended_parent_for_fork" in actions
