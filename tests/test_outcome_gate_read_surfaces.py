"""Outcome gates integration into goals get and branch get.

Covers docs/specs/outcome_gates_phase6.md rollout details:
- `goals get goal_id=X` gains `gate_summary` field.
- `extensions get_branch branch_def_id=X` gains `gate_claims` field.
- Both threads through GATES_ENABLED=0 fallback (6.2.1 precedent):
  `gate_summary: {status: "gates_disabled"}` and
  `gate_claims: [], gate_status: "gates_disabled"`.

Read-only surface. No new storage / git primitives. No mutation path.
"""

from __future__ import annotations

import importlib
import json

import pytest

# ───────────────────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def gates_on_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("GATES_ENABLED", "1")
    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, base
    importlib.reload(us)


@pytest.fixture
def gates_off_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.delenv("GATES_ENABLED", raising=False)
    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    return json.loads(getattr(us, tool)(action=action, **kwargs))


_LADDER = [
    {"rung_key": "draft_complete", "name": "Draft complete",
     "description": "Full draft."},
    {"rung_key": "peer_reviewed", "name": "Peer reviewed",
     "description": "At least 2 reviewers."},
    {"rung_key": "submitted", "name": "Submitted",
     "description": "Submission tracked."},
]


def _seed_goal_with_ladder(us):
    g = _call(us, "goals", "propose", name="Research paper", description="x")
    gid = g["goal"]["goal_id"]
    b = _call(us, "extensions", "create_branch", name="LoRA v3")
    bid = b["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    return gid, bid


# ───────────────────────────────────────────────────────────────────────
# goal_gate_summary (backend unit)
# ───────────────────────────────────────────────────────────────────────


def test_goal_gate_summary_empty_when_no_ladder(gates_on_env):
    from tinyassets.daemon_server import goal_gate_summary

    us, base = gates_on_env
    g = _call(us, "goals", "propose", name="G", description="x")
    gid = g["goal"]["goal_id"]
    summary = goal_gate_summary(base, goal_id=gid)
    assert summary == {
        "ladder_length": 0,
        "claims_total": 0,
        "branches_with_claims": 0,
        "highest_rung_reached": "",
    }


def test_goal_gate_summary_ladder_length_reflects_rungs(gates_on_env):
    from tinyassets.daemon_server import goal_gate_summary

    us, base = gates_on_env
    gid, _bid = _seed_goal_with_ladder(us)
    summary = goal_gate_summary(base, goal_id=gid)
    assert summary["ladder_length"] == 3
    assert summary["claims_total"] == 0
    assert summary["branches_with_claims"] == 0
    assert summary["highest_rung_reached"] == ""


def test_goal_gate_summary_counts_across_multiple_branches(gates_on_env):
    from tinyassets.daemon_server import goal_gate_summary

    us, base = gates_on_env
    gid, bid_a = _seed_goal_with_ladder(us)
    b = _call(us, "extensions", "create_branch", name="B")
    bid_b = b["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid_b)
    _call(us, "gates", "claim",
          branch_def_id=bid_a, rung_key="draft_complete",
          evidence_url="https://example.com/a")
    _call(us, "gates", "claim",
          branch_def_id=bid_a, rung_key="peer_reviewed",
          evidence_url="https://example.com/a2")
    _call(us, "gates", "claim",
          branch_def_id=bid_b, rung_key="draft_complete",
          evidence_url="https://example.com/b")
    summary = goal_gate_summary(base, goal_id=gid)
    assert summary["claims_total"] == 3
    assert summary["branches_with_claims"] == 2
    assert summary["highest_rung_reached"] == "peer_reviewed"


def test_goal_gate_summary_ignores_retracted(gates_on_env):
    from tinyassets.daemon_server import goal_gate_summary

    us, base = gates_on_env
    gid, bid = _seed_goal_with_ladder(us)
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="submitted",
          evidence_url="https://example.com/x")
    _call(us, "gates", "retract",
          branch_def_id=bid, rung_key="submitted",
          reason="bogus evidence")
    summary = goal_gate_summary(base, goal_id=gid)
    assert summary["claims_total"] == 0
    assert summary["branches_with_claims"] == 0
    assert summary["highest_rung_reached"] == ""


def test_goal_gate_summary_ignores_orphaned_rungs(gates_on_env):
    from tinyassets.daemon_server import goal_gate_summary

    us, base = gates_on_env
    gid, bid = _seed_goal_with_ladder(us)
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="peer_reviewed",
          evidence_url="https://example.com/x")
    # Shrink ladder so peer_reviewed becomes orphaned.
    shrunk = [r for r in _LADDER if r["rung_key"] != "peer_reviewed"]
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(shrunk))
    summary = goal_gate_summary(base, goal_id=gid)
    # Ladder length dropped; orphaned claim doesn't count.
    assert summary["ladder_length"] == 2
    assert summary["claims_total"] == 0
    assert summary["branches_with_claims"] == 0


# ───────────────────────────────────────────────────────────────────────
# goals get integration
# ───────────────────────────────────────────────────────────────────────


def test_goals_get_returns_gate_summary_populated(gates_on_env):
    us, _base = gates_on_env
    gid, bid = _seed_goal_with_ladder(us)
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="submitted",
          evidence_url="https://example.com/x")
    result = _call(us, "goals", "get", goal_id=gid)
    summary = result["gate_summary"]
    assert summary["ladder_length"] == 3
    assert summary["claims_total"] == 1
    assert summary["branches_with_claims"] == 1
    assert summary["highest_rung_reached"] == "submitted"


def test_goals_get_gate_summary_empty_before_claims(gates_on_env):
    us, _base = gates_on_env
    gid, _bid = _seed_goal_with_ladder(us)
    result = _call(us, "goals", "get", goal_id=gid)
    summary = result["gate_summary"]
    assert summary["ladder_length"] == 3
    assert summary["claims_total"] == 0
    assert summary["highest_rung_reached"] == ""


def test_goals_get_gate_summary_gated_off(gates_off_env):
    us, _base = gates_off_env
    g = _call(us, "goals", "propose", name="G", description="x")
    gid = g["goal"]["goal_id"]
    result = _call(us, "goals", "get", goal_id=gid)
    # Gate-disabled: surfaces a flag-gated placeholder, not counters.
    assert result["gate_summary"] == {"status": "gates_disabled"}


# ───────────────────────────────────────────────────────────────────────
# extensions get_branch integration
# ───────────────────────────────────────────────────────────────────────


def test_get_branch_includes_gate_claims_populated(gates_on_env):
    us, _base = gates_on_env
    gid, bid = _seed_goal_with_ladder(us)
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/x")
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="peer_reviewed",
          evidence_url="https://example.com/y")
    result = _call(us, "extensions", "get_branch", branch_def_id=bid)
    assert "gate_claims" in result
    assert len(result["gate_claims"]) == 2
    rungs = {c["rung_key"] for c in result["gate_claims"]}
    assert rungs == {"draft_complete", "peer_reviewed"}


def test_get_branch_gate_claims_excludes_retracted(gates_on_env):
    us, _base = gates_on_env
    gid, bid = _seed_goal_with_ladder(us)
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/x")
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="peer_reviewed",
          evidence_url="https://example.com/y")
    _call(us, "gates", "retract",
          branch_def_id=bid, rung_key="peer_reviewed",
          reason="bogus")
    result = _call(us, "extensions", "get_branch", branch_def_id=bid)
    # Only non-retracted claim surfaces.
    assert len(result["gate_claims"]) == 1
    assert result["gate_claims"][0]["rung_key"] == "draft_complete"


def test_get_branch_empty_gate_claims_when_no_claims(gates_on_env):
    us, _base = gates_on_env
    b = _call(us, "extensions", "create_branch", name="Solo")
    bid = b["branch_def_id"]
    result = _call(us, "extensions", "get_branch", branch_def_id=bid)
    assert result["gate_claims"] == []
    # No gate_status when flag is on — empty list means "no claims yet."
    assert "gate_status" not in result


def test_get_branch_gated_off(gates_off_env):
    us, _base = gates_off_env
    b = _call(us, "extensions", "create_branch", name="Solo")
    bid = b["branch_def_id"]
    result = _call(us, "extensions", "get_branch", branch_def_id=bid)
    # Gate-disabled: empty list + explicit status, so UI can render
    # "gates off" distinct from "no claims."
    assert result["gate_claims"] == []
    assert result["gate_status"] == "gates_disabled"


def test_goal_gate_summary_hides_existing_claims(tmp_path, monkeypatch):
    """Symmetric to the branch-get flip test: seeding claims under
    GATES_ENABLED=1 and then flipping to 0 must make goals-get
    surface the `gates_disabled` placeholder, hiding stored counters.
    """
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("GATES_ENABLED", "1")
    from tinyassets import universe_server as us
    importlib.reload(us)
    try:
        gid, bid = _seed_goal_with_ladder(us)
        _call(us, "gates", "claim",
              branch_def_id=bid, rung_key="draft_complete",
              evidence_url="https://example.com/x")
        _call(us, "gates", "claim",
              branch_def_id=bid, rung_key="peer_reviewed",
              evidence_url="https://example.com/y")
        # Sanity: on-state surfaces populated counters.
        on_result = json.loads(us.goals(action="get", goal_id=gid))
        assert on_result["gate_summary"]["claims_total"] == 2
        assert on_result["gate_summary"]["highest_rung_reached"] == "peer_reviewed"
        # Flip to off; reload so the env-check re-reads.
        monkeypatch.delenv("GATES_ENABLED", raising=False)
        importlib.reload(us)
        off_result = json.loads(us.goals(action="get", goal_id=gid))
        assert off_result["gate_summary"] == {"status": "gates_disabled"}
        # Stored claims are NOT leaked through any other response key.
        assert "claims_total" not in json.dumps(off_result["gate_summary"])
    finally:
        importlib.reload(us)


def test_get_branch_gates_off_hides_existing_claims(tmp_path, monkeypatch):
    """A daemon flipping GATES_ENABLED from 1 to 0 must hide previously
    stored claims — the fallback is not a cache of the last on-state.
    """
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("GATES_ENABLED", "1")
    from tinyassets import universe_server as us
    importlib.reload(us)
    try:
        gid, bid = _seed_goal_with_ladder(us)
        _call(us, "gates", "claim",
              branch_def_id=bid, rung_key="draft_complete",
              evidence_url="https://example.com/x")
        # Flip flag off; reload module so the env-check re-reads.
        monkeypatch.delenv("GATES_ENABLED", raising=False)
        importlib.reload(us)
        result = json.loads(us.extensions(
            action="get_branch", branch_def_id=bid,
        ))
        assert result["gate_claims"] == []
        assert result["gate_status"] == "gates_disabled"
        # Same flip for goals get.
        goal_result = json.loads(us.goals(
            action="get", goal_id=gid,
        ))
        assert goal_result["gate_summary"] == {"status": "gates_disabled"}
    finally:
        importlib.reload(us)
