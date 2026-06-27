"""Outcome Gates retract, list_claims, and leaderboard behavior.

Covers docs/specs/outcome_gates_phase6.md rollout details:
- retract: soft-delete, owner/claimant/host authority, reason required.
- list_claims: one-filter rule, include_retracted, orphan tagging.
- leaderboard: highest-rung ordering, earliest-claim tiebreak, ignores
  retracted and orphaned claims.
- goals leaderboard metric=outcome delegation.
- define_ladder host override.
"""

from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def gates_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("GATES_ENABLED", "1")
    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, base, monkeypatch
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    return json.loads(getattr(us, tool)(action=action, **kwargs))


_LADDER = [
    {"rung_key": "draft_complete", "name": "Draft complete",
     "description": "Full draft emitted."},
    {"rung_key": "peer_reviewed", "name": "Peer reviewed",
     "description": "At least 2 reviewers."},
    {"rung_key": "submitted", "name": "Submitted",
     "description": "Submission tracked."},
]


def _seed(us, *, goal_name="Research paper", branch_name="LoRA v3"):
    g = _call(us, "goals", "propose", name=goal_name, description="x")
    gid = g["goal"]["goal_id"]
    b = _call(us, "extensions", "create_branch", name=branch_name)
    bid = b["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    return gid, bid


def _claim(us, bid, rung, url, note=""):
    return _call(us, "gates", "claim",
                 branch_def_id=bid, rung_key=rung,
                 evidence_url=url, evidence_note=note)


# ─── retract ───────────────────────────────────────────────────────────


def test_retract_requires_reason(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "draft_complete", "https://example.com/a")
    result = _call(us, "gates", "retract",
                   branch_def_id=bid, rung_key="draft_complete",
                   reason="")
    assert result["status"] == "rejected"
    assert "reason is required" in result["error"]


def test_retract_rejects_unknown_claim(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    result = _call(us, "gates", "retract",
                   branch_def_id=bid, rung_key="draft_complete",
                   reason="typo")
    assert result["status"] == "rejected"
    assert result["error"] == "claim_not_found"
    assert "No claim exists" in result["message"]


def test_retract_soft_deletes_claim(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "draft_complete", "https://example.com/a")
    result = _call(us, "gates", "retract",
                   branch_def_id=bid, rung_key="draft_complete",
                   reason="evidence 404s")
    assert result["status"] == "retracted"
    assert result["claim"]["retracted_at"] is not None
    assert result["claim"]["retracted_reason"] == "evidence 404s"


def test_retract_by_non_owner_non_claimant_rejected(gates_env, monkeypatch):
    us, _, _ = gates_env
    gid, bid = _seed(us)  # alice owns goal + claims
    _claim(us, bid, "draft_complete", "https://example.com/a")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "mallory")
    importlib.reload(us)
    result = json.loads(us.gates(
        action="retract", branch_def_id=bid, rung_key="draft_complete",
        reason="spite",
    ))
    assert result["status"] == "rejected"
    assert "claim author or Goal owner" in result["error"]


def test_retract_by_goal_owner_allowed(gates_env, monkeypatch):
    us, _, _ = gates_env
    gid, bid = _seed(us)  # alice owns goal
    # Bob claims.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
    importlib.reload(us)
    _claim(us, bid, "draft_complete", "https://example.com/a")
    # Alice (goal owner) retracts.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    importlib.reload(us)
    result = json.loads(us.gates(
        action="retract", branch_def_id=bid, rung_key="draft_complete",
        reason="evidence is misleading",
    ))
    assert result["status"] == "retracted"


def test_retract_by_host_allowed(gates_env, monkeypatch):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
    importlib.reload(us)
    _claim(us, bid, "draft_complete", "https://example.com/a")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host")
    importlib.reload(us)
    result = json.loads(us.gates(
        action="retract", branch_def_id=bid, rung_key="draft_complete",
        reason="host override",
    ))
    assert result["status"] == "retracted"


def test_reclaim_after_retract_reactivates(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    first = _claim(us, bid, "draft_complete", "https://example.com/a")
    _call(us, "gates", "retract",
          branch_def_id=bid, rung_key="draft_complete", reason="oops")
    second = _claim(us, bid, "draft_complete", "https://example.com/b")
    assert second["status"] == "claimed"
    assert second["claim"]["claim_id"] == first["claim"]["claim_id"]
    assert second["claim"]["retracted_at"] is None
    assert second["claim"]["evidence_url"] == "https://example.com/b"


# ─── list_claims ───────────────────────────────────────────────────────


def test_list_claims_requires_one_filter(gates_env):
    us, _, _ = gates_env
    # Neither provided.
    result = _call(us, "gates", "list_claims")
    assert result["status"] == "rejected"
    assert "exactly one" in result["error"]


def test_list_claims_rejects_both_filters(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    result = _call(us, "gates", "list_claims",
                   goal_id=gid, branch_def_id=bid)
    assert result["status"] == "rejected"


def test_list_claims_by_branch_returns_active_only(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "draft_complete", "https://example.com/a")
    _claim(us, bid, "peer_reviewed", "https://example.com/b")
    _call(us, "gates", "retract",
          branch_def_id=bid, rung_key="peer_reviewed", reason="oops")
    result = _call(us, "gates", "list_claims", branch_def_id=bid)
    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["claims"][0]["rung_key"] == "draft_complete"


def test_list_claims_include_retracted(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "draft_complete", "https://example.com/a")
    _claim(us, bid, "peer_reviewed", "https://example.com/b")
    _call(us, "gates", "retract",
          branch_def_id=bid, rung_key="peer_reviewed", reason="oops")
    result = _call(us, "gates", "list_claims",
                   branch_def_id=bid, include_retracted=True)
    assert result["count"] == 2


def test_list_claims_by_goal(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "draft_complete", "https://example.com/a")
    result = _call(us, "gates", "list_claims", goal_id=gid)
    assert result["count"] == 1
    assert result["claims"][0]["branch_def_id"] == bid


def test_list_claims_tags_orphaned_rungs(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "peer_reviewed", "https://example.com/a")
    # Rewrite ladder without peer_reviewed.
    shrunk = [r for r in _LADDER if r["rung_key"] != "peer_reviewed"]
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(shrunk))
    result = _call(us, "gates", "list_claims", branch_def_id=bid)
    assert result["count"] == 1
    assert result["claims"][0]["orphaned"] is True


# ─── leaderboard ───────────────────────────────────────────────────────


def test_leaderboard_requires_goal_id(gates_env):
    us, _, _ = gates_env
    result = _call(us, "gates", "leaderboard")
    assert result["status"] == "rejected"


def test_leaderboard_rejects_unknown_goal(gates_env):
    us, _, _ = gates_env
    result = _call(us, "gates", "leaderboard", goal_id="nope")
    assert result["status"] == "rejected"
    assert "not found" in result["error"]


def test_leaderboard_empty_when_no_claims(gates_env):
    us, _, _ = gates_env
    gid, _ = _seed(us)
    result = _call(us, "gates", "leaderboard", goal_id=gid)
    assert result["status"] == "ok"
    assert result["count"] == 0
    assert result["entries"] == []


def test_leaderboard_orders_by_highest_rung(gates_env):
    us, _, _ = gates_env
    gid, bid_a = _seed(us, branch_name="A")
    # Second branch on same goal.
    b2 = _call(us, "extensions", "create_branch", name="B")
    bid_b = b2["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid_b)
    _claim(us, bid_a, "draft_complete", "https://example.com/a")
    _claim(us, bid_b, "peer_reviewed", "https://example.com/b")
    result = _call(us, "gates", "leaderboard", goal_id=gid)
    assert result["count"] == 2
    assert result["entries"][0]["branch_def_id"] == bid_b
    assert result["entries"][0]["highest_rung_key"] == "peer_reviewed"
    assert result["entries"][1]["branch_def_id"] == bid_a


def test_leaderboard_earliest_wins_tiebreak(gates_env):
    import time
    us, _, _ = gates_env
    gid, bid_a = _seed(us, branch_name="A")
    b2 = _call(us, "extensions", "create_branch", name="B")
    bid_b = b2["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid_b)
    _claim(us, bid_a, "draft_complete", "https://example.com/a")
    time.sleep(1.1)  # _utc_iso_now has second-level resolution.
    _claim(us, bid_b, "draft_complete", "https://example.com/b")
    result = _call(us, "gates", "leaderboard", goal_id=gid)
    assert result["entries"][0]["branch_def_id"] == bid_a


def test_leaderboard_ignores_retracted(gates_env):
    us, _, _ = gates_env
    gid, bid_a = _seed(us, branch_name="A")
    b2 = _call(us, "extensions", "create_branch", name="B")
    bid_b = b2["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid_b)
    _claim(us, bid_a, "peer_reviewed", "https://example.com/a")
    _claim(us, bid_b, "draft_complete", "https://example.com/b")
    _call(us, "gates", "retract",
          branch_def_id=bid_a, rung_key="peer_reviewed",
          reason="evidence bogus")
    result = _call(us, "gates", "leaderboard", goal_id=gid)
    # Only bid_b remains.
    assert result["count"] == 1
    assert result["entries"][0]["branch_def_id"] == bid_b


def test_leaderboard_ignores_orphaned_rungs(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "peer_reviewed", "https://example.com/a")
    shrunk = [r for r in _LADDER if r["rung_key"] != "peer_reviewed"]
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(shrunk))
    result = _call(us, "gates", "leaderboard", goal_id=gid)
    assert result["count"] == 0


# ─── goals leaderboard metric=outcome delegation ───────────────────────


def test_goals_leaderboard_outcome_delegates(gates_env):
    us, _, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "peer_reviewed", "https://example.com/a")
    result = _call(us, "goals", "leaderboard",
                   goal_id=gid, metric="outcome")
    assert result.get("status") != "not_available_until_phase_6"
    assert result["metric"] == "outcome"
    assert len(result["entries"]) == 1
    assert result["entries"][0]["highest_rung_key"] == "peer_reviewed"
    assert result["entries"][0]["value"] == 1  # rung index


def test_goals_leaderboard_outcome_empty_has_friendly_text(gates_env):
    us, _, _ = gates_env
    gid, _ = _seed(us)
    result = _call(us, "goals", "leaderboard",
                   goal_id=gid, metric="outcome")
    assert "No gate claims" in result["text"]


def test_goals_leaderboard_unknown_metric_lists_outcome(gates_env):
    us, _, _ = gates_env
    gid, _ = _seed(us)
    result = _call(us, "goals", "leaderboard",
                   goal_id=gid, metric="bogus")
    assert result["status"] == "rejected"
    assert "outcome" in result["available_metrics"]


# ─── define_ladder host override ───────────────────────────────────────


def test_define_ladder_host_override(gates_env, monkeypatch):
    us, _, _ = gates_env
    gid, _ = _seed(us)  # alice owns
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host")
    importlib.reload(us)
    new_ladder = [{"rung_key": "only", "name": "Only", "description": ""}]
    result = json.loads(us.gates(
        action="define_ladder",
        goal_id=gid, ladder=json.dumps(new_ladder),
    ))
    assert result["status"] == "defined"
    assert [r["rung_key"] for r in result["gate_ladder"]] == ["only"]


# ─── goals leaderboard outcome gated-off fallback (Phase 6.2.1) ───────


def test_goals_leaderboard_outcome_gated_off(tmp_path, monkeypatch):
    """GATES_ENABLED=0: outcome falls back to a friendly gated envelope,
    not an empty live-leaderboard result.
    """
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.delenv("GATES_ENABLED", raising=False)
    from tinyassets import universe_server as us
    importlib.reload(us)
    try:
        gid = json.loads(us.goals(
            action="propose", name="G", description="x",
        ))["goal"]["goal_id"]
        result = json.loads(us.goals(
            action="leaderboard", goal_id=gid, metric="outcome",
        ))
        assert result["status"] == "gates_disabled"
        assert result["entries"] == []
        assert "GATES_ENABLED" in result["text"]
    finally:
        importlib.reload(us)


def test_goals_leaderboard_outcome_live_when_enabled(gates_env):
    """GATES_ENABLED=1: outcome returns the live leaderboard."""
    us, _, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "peer_reviewed", "https://example.com/a")
    result = _call(us, "goals", "leaderboard",
                   goal_id=gid, metric="outcome")
    assert result.get("status") != "gates_disabled"
    assert len(result["entries"]) == 1
    assert result["entries"][0]["highest_rung_key"] == "peer_reviewed"


# ─── branch_rebound guard (Phase 6.2.1) ────────────────────────────────


def test_claim_rejects_after_branch_rebound(gates_env):
    """Reclaim under a different Goal is rejected, not silently moved.

    Spec §6.2 Debt #2 Option 1. Branch rebinds from Goal A to Goal B
    while an active claim still references A. A naive UPDATE would
    silently shift the claim's goal_id to B, erasing A's leaderboard
    history.
    """
    us, _, _ = gates_env
    gid_a, bid = _seed(us, goal_name="Goal A")
    _claim(us, bid, "draft_complete", "https://example.com/a")
    # Create Goal B with the same ladder and rebind the Branch to B.
    gid_b = _call(us, "goals", "propose", name="Goal B",
                  description="")["goal"]["goal_id"]
    _call(us, "gates", "define_ladder",
          goal_id=gid_b, ladder=json.dumps(_LADDER))
    _call(us, "goals", "bind", goal_id=gid_b, branch_def_id=bid)
    # Re-claim the same rung — should reject with branch_rebound.
    result = _claim(us, bid, "draft_complete", "https://example.com/b")
    assert result["status"] == "rejected"
    assert result["error"] == "branch_rebound"
    assert result["original_goal_id"] == gid_a
    assert result["current_goal_id"] == gid_b
    assert "Retract" in result["hint"]


def test_claim_rebind_allowed_after_retract(gates_env):
    """Retract-then-reclaim flow is the supported rebind path."""
    us, _, _ = gates_env
    gid_a, bid = _seed(us, goal_name="Goal A")
    _claim(us, bid, "draft_complete", "https://example.com/a")
    gid_b = _call(us, "goals", "propose", name="Goal B",
                  description="")["goal"]["goal_id"]
    _call(us, "gates", "define_ladder",
          goal_id=gid_b, ladder=json.dumps(_LADDER))
    _call(us, "goals", "bind", goal_id=gid_b, branch_def_id=bid)
    _call(us, "gates", "retract",
          branch_def_id=bid, rung_key="draft_complete",
          reason="rebinding to Goal B")
    result = _claim(us, bid, "draft_complete", "https://example.com/b")
    assert result["status"] == "claimed"
    assert result["claim"]["goal_id"] == gid_b


def test_claim_gate_storage_raises_branch_rebind_error(gates_env):
    """Defense-in-depth: storage layer refuses silent goal_id rewrite.

    Even if a caller reaches ``claim_gate`` directly (bypassing the
    handler's pre-check), the ACTIVE claim's denormalized goal_id must
    match the passed-in goal_id. Otherwise BranchRebindError.
    """
    us, base, _ = gates_env
    gid_a, bid = _seed(us, goal_name="Goal A")
    _claim(us, bid, "draft_complete", "https://example.com/a")
    # Create Goal B but don't re-bind at MCP layer — call claim_gate
    # directly with a divergent goal_id to probe the storage guard.
    gid_b = _call(us, "goals", "propose", name="Goal B",
                  description="")["goal"]["goal_id"]
    from tinyassets.daemon_server import BranchRebindError, claim_gate
    with pytest.raises(BranchRebindError) as exc_info:
        claim_gate(
            base,
            branch_def_id=bid,
            goal_id=gid_b,
            rung_key="draft_complete",
            evidence_url="https://example.com/direct",
            evidence_note="",
            claimed_by="alice",
        )
    assert exc_info.value.original_goal_id == gid_a
    assert exc_info.value.current_goal_id == gid_b


def test_claim_gate_storage_allows_update_on_same_goal(gates_env):
    """Non-rebind UPDATE (evidence refresh) still works."""
    us, base, _ = gates_env
    gid, bid = _seed(us)
    _claim(us, bid, "draft_complete", "https://example.com/first")
    from tinyassets.daemon_server import claim_gate
    updated = claim_gate(
        base,
        branch_def_id=bid,
        goal_id=gid,  # same goal
        rung_key="draft_complete",
        evidence_url="https://example.com/second",
        evidence_note="updated",
        claimed_by="alice",
    )
    assert updated["evidence_url"] == "https://example.com/second"
    assert updated["evidence_note"] == "updated"


def test_claim_gate_storage_reactivates_retracted_under_new_goal(gates_env):
    """Retracted claims are resolved intent — claim_gate reactivates
    them under a new Goal without raising BranchRebindError."""
    us, base, _ = gates_env
    gid_a, bid = _seed(us, goal_name="Goal A")
    _claim(us, bid, "draft_complete", "https://example.com/a")
    _call(us, "gates", "retract",
          branch_def_id=bid, rung_key="draft_complete",
          reason="moving to B")
    gid_b = _call(us, "goals", "propose", name="Goal B",
                  description="")["goal"]["goal_id"]
    from tinyassets.daemon_server import claim_gate
    reactivated = claim_gate(
        base,
        branch_def_id=bid,
        goal_id=gid_b,
        rung_key="draft_complete",
        evidence_url="https://example.com/b",
        evidence_note="",
        claimed_by="alice",
    )
    assert reactivated["goal_id"] == gid_b
    assert reactivated["retracted_at"] is None
