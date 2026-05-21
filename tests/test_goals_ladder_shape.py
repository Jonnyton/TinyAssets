"""PR-126 M5 sub-task 1 — confirm the bound Goal's ladder is queryable
in structured form so branch authors can populate `recommended_rung_claim`
against a real rung_key vocabulary.

The substrate already returns the ladder rungs via two paths:

  * `goals action=get goal_id=<g>` → response.goal.gate_ladder is a
    list of `{rung_key, name, description}` dicts (Phase 6 schema).
  * `gates action=get_ladder goal_id=<g>` → response.gate_ladder is
    the same list.

This module locks in both contracts so a future schema migration that
flattens the ladder would surface here first, not when a branch's
`claim_from_branch_run` call hits an unexpected shape.
"""

from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def us_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    monkeypatch.setenv("GATES_ENABLED", "1")
    monkeypatch.setenv("WORKFLOW_STORAGE_BACKEND", "sqlite")
    from workflow.catalog import backend as backend_mod
    backend_mod.invalidate_backend_cache()
    from workflow import universe_server as us
    importlib.reload(us)
    yield us, tmp_path / "output"
    backend_mod.invalidate_backend_cache()
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    return json.loads(getattr(us, tool)(action=action, **kwargs))


_PATCH_LOOP_LADDER = [
    {"rung_key": "draft_ready",
     "name": "Draft ready",
     "description": "Branch emitted a candidate patch."},
    {"rung_key": "review_passed",
     "name": "Review passed",
     "description": "Cross-family checker approved."},
    {"rung_key": "merged",
     "name": "Merged",
     "description": "Patch landed on main."},
]


_FANTASY_LADDER = [
    {"rung_key": "first_draft",
     "name": "First draft",
     "description": "Chapter complete."},
    {"rung_key": "beta_reader_pass",
     "name": "Beta reader pass",
     "description": "Two beta readers approved."},
    {"rung_key": "published",
     "name": "Published",
     "description": "Available to read."},
]


def _build_branch(us, name: str) -> str:
    spec = {
        "name": name,
        "entry_point": "n",
        "node_defs": [{
            "node_id": "n",
            "display_name": "N",
            "prompt_template": "Input: {x}",
        }],
        "edges": [
            {"from": "START", "to": "n"},
            {"from": "n", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    return _call(us, "extensions", "build_branch",
                 spec_json=json.dumps(spec))["branch_def_id"]


# ---------------------------------------------------------------------------
# `goals action=get` carries gate_ladder
# ---------------------------------------------------------------------------


def test_goals_get_returns_gate_ladder_in_structured_form(us_env):
    us, _ = us_env
    g = _call(us, "goals", "propose", name="Patch loop", description="x")
    gid = g["goal"]["goal_id"]
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_PATCH_LOOP_LADDER))
    result = _call(us, "goals", "get", goal_id=gid)
    goal = result["goal"]
    assert "gate_ladder" in goal
    ladder = goal["gate_ladder"]
    assert isinstance(ladder, list)
    assert [r["rung_key"] for r in ladder] == [
        "draft_ready", "review_passed", "merged",
    ]
    # Each rung has the three Phase-6 fields a branch author needs to
    # render the ladder vocabulary back to the user.
    for rung in ladder:
        assert isinstance(rung, dict)
        assert rung.get("rung_key")
        assert rung.get("name")
        assert "description" in rung


def test_goals_get_returns_empty_ladder_when_undefined(us_env):
    us, _ = us_env
    g = _call(us, "goals", "propose", name="No-ladder goal")
    gid = g["goal"]["goal_id"]
    result = _call(us, "goals", "get", goal_id=gid)
    goal = result["goal"]
    # Empty ladder is `[]`, not absent — branch authors can read the
    # field unconditionally without a KeyError guard.
    assert goal.get("gate_ladder") == []


def test_gates_get_ladder_returns_same_shape(us_env):
    us, _ = us_env
    g = _call(us, "goals", "propose", name="Fantasy novel")
    gid = g["goal"]["goal_id"]
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_FANTASY_LADDER))
    via_gates = _call(us, "gates", "get_ladder", goal_id=gid)
    via_goals = _call(us, "goals", "get", goal_id=gid)
    assert via_gates["gate_ladder"] == via_goals["goal"]["gate_ladder"]


def test_goal_branch_protocol_round_trips_ordered_handoffs(us_env):
    us, _ = us_env
    gid = _call(us, "goals", "propose", name="Meridian opening")[
        "goal"
    ]["goal_id"]
    architect = _build_branch(us, "Opening Architect")
    compressor = _build_branch(us, "Opening Compressor")
    _call(us, "goals", "bind", branch_def_id=architect, goal_id=gid)
    _call(us, "goals", "bind", branch_def_id=compressor, goal_id=gid)

    protocol = [
        {
            "order": 2,
            "step_id": "compress",
            "branch_def_id": compressor,
            "source_label": "Opening Compressor",
            "input_artifact_labels": ["architecture_plan"],
            "output_artifact_labels": ["compression_blueprint"],
            "required_rung_key": "review_passed",
            "rollback_policy": "supersede prior blueprint",
            "status": "pending",
        },
        {
            "order": 1,
            "step_id": "architect",
            "branch_def_id": architect,
            "source_label": "Opening Architect",
            "output_artifact_labels": ["architecture_plan"],
            "status": "completed",
        },
    ]

    defined = _call(
        us, "goals", "define_protocol",
        goal_id=gid, protocol_json=json.dumps(protocol),
    )

    assert defined["status"] == "defined"
    assert [step["step_id"] for step in defined["branch_protocol"]] == [
        "architect", "compress",
    ]
    assert defined["current_protocol_step"]["step_id"] == "compress"
    assert defined["branch_protocol"][1]["input_artifact_labels"] == [
        "architecture_plan",
    ]

    via_get = _call(us, "goals", "get", goal_id=gid)
    assert via_get["goal"]["branch_protocol"] == defined["branch_protocol"]
    assert via_get["branch_protocol"] == defined["branch_protocol"]
    assert via_get["current_protocol_step"]["step_id"] == "compress"
    assert "Branch protocol" in via_get["text"]

    via_protocol = _call(us, "goals", "get_protocol", goal_id=gid)
    assert via_protocol["count"] == 2
    assert via_protocol["current_protocol_step"]["branch_def_id"] == compressor


def test_goal_branch_protocol_rejects_unbound_branch(us_env):
    us, _ = us_env
    gid = _call(us, "goals", "propose", name="Runbook goal")[
        "goal"
    ]["goal_id"]
    unbound = _build_branch(us, "Unbound branch")

    result = _call(
        us, "goals", "define_protocol",
        goal_id=gid,
        protocol_json=json.dumps([{"branch_def_id": unbound}]),
    )

    assert result["status"] == "rejected"
    assert "not bound" in result["error"]


def test_goal_branch_protocol_rejects_bad_order(us_env):
    us, _ = us_env
    gid = _call(us, "goals", "propose", name="Ordered goal")[
        "goal"
    ]["goal_id"]
    branch_id = _build_branch(us, "Ordered branch")
    _call(us, "goals", "bind", branch_def_id=branch_id, goal_id=gid)

    result = _call(
        us, "goals", "define_protocol",
        goal_id=gid,
        protocol_json=json.dumps([{
            "branch_def_id": branch_id,
            "order": "first",
        }]),
    )

    assert result["status"] == "rejected"
    assert "order must be an integer" in result["error"]


# ---------------------------------------------------------------------------
# Goal-genericity — different ladders for different Goals
# ---------------------------------------------------------------------------


def test_two_goals_can_have_independent_ladders(us_env):
    """Same primitive, different ladder vocabularies — patch loop's
    `draft_ready` doesn't collide with fantasy's `first_draft`."""
    us, _ = us_env
    g_patch = _call(us, "goals", "propose", name="Patch loop")
    g_fantasy = _call(us, "goals", "propose", name="Fantasy novel")
    pid = g_patch["goal"]["goal_id"]
    fid = g_fantasy["goal"]["goal_id"]
    _call(us, "gates", "define_ladder",
          goal_id=pid, ladder=json.dumps(_PATCH_LOOP_LADDER))
    _call(us, "gates", "define_ladder",
          goal_id=fid, ladder=json.dumps(_FANTASY_LADDER))
    patch_rungs = [
        r["rung_key"]
        for r in _call(us, "goals", "get", goal_id=pid)["goal"]["gate_ladder"]
    ]
    fantasy_rungs = [
        r["rung_key"]
        for r in _call(us, "goals", "get", goal_id=fid)["goal"]["gate_ladder"]
    ]
    assert patch_rungs == ["draft_ready", "review_passed", "merged"]
    assert fantasy_rungs == ["first_draft", "beta_reader_pass", "published"]
    # No cross-contamination.
    assert set(patch_rungs) & set(fantasy_rungs) == set()


def test_ladder_redefinition_replaces_rungs(us_env):
    """Calling `define_ladder` a second time replaces the previous
    rung set. Confirmed against the substrate so we know branch authors
    can re-emit `recommended_rung_claim` after a ladder evolution."""
    us, _ = us_env
    g = _call(us, "goals", "propose", name="Patch loop")
    gid = g["goal"]["goal_id"]
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_PATCH_LOOP_LADDER))
    refined = _PATCH_LOOP_LADDER + [
        {"rung_key": "post_merge_validated",
         "name": "Post-merge validated",
         "description": "Smoke tests green for 24h."},
    ]
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(refined))
    ladder = _call(us, "goals", "get", goal_id=gid)["goal"]["gate_ladder"]
    assert [r["rung_key"] for r in ladder] == [
        "draft_ready", "review_passed", "merged", "post_merge_validated",
    ]
