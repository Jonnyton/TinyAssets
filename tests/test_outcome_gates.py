"""Phase 6.1 — Outcome Gates schema + tool surface.

Covers docs/specs/outcome_gates_phase6.md §Rollout 6.1:
- Schema migration (goals.gate_ladder_json + gate_claims table).
- gates tool gated by GATES_ENABLED.
- define_ladder owner-only.
- claim idempotent on (branch_def_id, rung_key).
- claim unknown rung returns available_rungs for the humans.
- ladder validation (non-empty rung_key, no dup keys).

Phase 6.2+ actions (retract / list_claims / leaderboard) ship in
separate test files.
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
    yield us, base
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    return json.loads(getattr(us, tool)(action=action, **kwargs))


def _seed_goal_and_branch(us, *, goal_name="Research paper",
                          branch_name="LoRA v3"):
    g = _call(us, "goals", "propose", name=goal_name,
              description="produce an academic research paper")
    gid = g["goal"]["goal_id"]
    b = _call(us, "extensions", "create_branch", name=branch_name)
    bid = b["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid)
    return gid, bid


_LADDER = [
    {"rung_key": "draft_complete", "name": "Draft complete",
     "description": "TinyAssets produced a full draft."},
    {"rung_key": "peer_reviewed", "name": "Peer-reviewed",
     "description": "At least 2 external reviewers commented."},
    {"rung_key": "submitted", "name": "Submitted to venue",
     "description": "Submission ID or tracking URL."},
]


# ─── feature flag ──────────────────────────────────────────────────────


def test_gates_tool_gated_by_flag(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.delenv("GATES_ENABLED", raising=False)
    from tinyassets import universe_server as us
    importlib.reload(us)
    try:
        result = json.loads(us.gates(action="get_ladder", goal_id="x"))
        assert result["status"] == "not_available"
        assert "GATES_ENABLED" in result["error"]
    finally:
        importlib.reload(us)


def test_gates_list_discovers_actions(gates_env):
    us, _ = gates_env

    result = _call(us, "gates", "list")

    assert result["status"] == "ok"
    assert result["tool"] == "gates"
    assert "list" in result["available_actions"]
    assert "list_claims" in result["available_actions"]


# ─── define_ladder ─────────────────────────────────────────────────────


def test_define_ladder_stores_rungs(gates_env):
    us, _ = gates_env
    gid, _ = _seed_goal_and_branch(us)
    result = _call(us, "gates", "define_ladder",
                   goal_id=gid, ladder=json.dumps(_LADDER))
    assert result["status"] == "defined"
    assert [r["rung_key"] for r in result["gate_ladder"]] == [
        "draft_complete", "peer_reviewed", "submitted",
    ]


def test_define_ladder_owner_only(gates_env, monkeypatch):
    us, _ = gates_env
    gid, _ = _seed_goal_and_branch(us)  # owner = alice
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "mallory")
    importlib.reload(us)
    result = json.loads(us.gates(action="define_ladder",
                                 goal_id=gid, ladder=json.dumps(_LADDER)))
    assert result["status"] == "rejected"
    assert "define_gate_ladder" in result["error"]


def test_define_ladder_rejects_invalid_json(gates_env):
    us, _ = gates_env
    gid, _ = _seed_goal_and_branch(us)
    result = _call(us, "gates", "define_ladder",
                   goal_id=gid, ladder="not json")
    assert result["status"] == "rejected"
    assert "JSON list" in result["error"]


def test_define_ladder_rejects_duplicate_rung_key(gates_env):
    us, _ = gates_env
    gid, _ = _seed_goal_and_branch(us)
    dup = [
        {"rung_key": "a", "name": "A", "description": ""},
        {"rung_key": "a", "name": "A2", "description": ""},
    ]
    result = _call(us, "gates", "define_ladder",
                   goal_id=gid, ladder=json.dumps(dup))
    assert result["status"] == "rejected"
    assert "duplicate rung_key" in result["error"]


def test_define_ladder_rejects_missing_rung_key(gates_env):
    us, _ = gates_env
    gid, _ = _seed_goal_and_branch(us)
    bad = [{"name": "No key here", "description": ""}]
    result = _call(us, "gates", "define_ladder",
                   goal_id=gid, ladder=json.dumps(bad))
    assert result["status"] == "rejected"
    assert "rung_key is required" in result["error"]


# ─── get_ladder ────────────────────────────────────────────────────────


def test_get_ladder_empty_by_default(gates_env):
    us, _ = gates_env
    gid, _ = _seed_goal_and_branch(us)
    result = _call(us, "gates", "get_ladder", goal_id=gid)
    assert result["status"] == "ok"
    assert result["gate_ladder"] == []


def test_get_ladder_after_define(gates_env):
    us, _ = gates_env
    gid, _ = _seed_goal_and_branch(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    result = _call(us, "gates", "get_ladder", goal_id=gid)
    assert result["status"] == "ok"
    assert len(result["gate_ladder"]) == 3


# ─── claim ─────────────────────────────────────────────────────────────


def test_claim_unknown_rung_returns_available_rungs(gates_env):
    us, _ = gates_env
    gid, bid = _seed_goal_and_branch(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    result = _call(us, "gates", "claim",
                   branch_def_id=bid, rung_key="nope",
                   evidence_url="https://example.com/x")
    assert result["status"] == "rejected"
    assert result["error"] == "unknown_rung"
    assert "draft_complete" in result["available_rungs"]


def test_claim_rejects_non_http_url(gates_env):
    us, _ = gates_env
    gid, bid = _seed_goal_and_branch(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    result = _call(us, "gates", "claim",
                   branch_def_id=bid, rung_key="draft_complete",
                   evidence_url="file:///local/path")
    assert result["status"] == "rejected"
    assert "http(s) URL" in result["error"]


def test_claim_accepts_workflow_run_evidence_handle(gates_env):
    us, _ = gates_env
    gid, bid = _seed_goal_and_branch(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    result = _call(us, "gates", "claim",
                   branch_def_id=bid, rung_key="draft_complete",
                   evidence_url="workflow:run:run-abc123",
                   evidence_note="completed local run")
    assert result["status"] == "claimed"
    assert result["claim"]["evidence_url"] == "workflow:run:run-abc123"


def test_claim_rejects_unbound_branch(gates_env):
    us, _ = gates_env
    # Fresh branch not bound to any goal.
    b = _call(us, "extensions", "create_branch", name="Solo branch")
    result = _call(us, "gates", "claim",
                   branch_def_id=b["branch_def_id"],
                   rung_key="x",
                   evidence_url="https://example.com/y")
    assert result["status"] == "rejected"
    assert "bound to a Goal" in result["error"]


def test_claim_is_idempotent_on_branch_rung(gates_env):
    us, _ = gates_env
    gid, bid = _seed_goal_and_branch(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    first = _call(us, "gates", "claim",
                  branch_def_id=bid, rung_key="draft_complete",
                  evidence_url="https://example.com/a",
                  evidence_note="first")
    second = _call(us, "gates", "claim",
                   branch_def_id=bid, rung_key="draft_complete",
                   evidence_url="https://example.com/b",
                   evidence_note="second")
    assert first["status"] == "claimed"
    assert second["status"] == "claimed"
    # Same row, updated evidence.
    assert first["claim"]["claim_id"] == second["claim"]["claim_id"]
    assert second["claim"]["evidence_url"] == "https://example.com/b"
    assert second["claim"]["evidence_note"] == "second"


def test_claim_persists_to_gate_claims_table(gates_env):
    import sqlite3
    us, base = gates_env
    gid, bid = _seed_goal_and_branch(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="submitted",
          evidence_url="https://example.com/subm")
    from tinyassets.daemon_server import db_path
    conn = sqlite3.connect(db_path(base))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM gate_claims WHERE branch_def_id = ? "
        "AND rung_key = ?",
        (bid, "submitted"),
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["goal_id"] == gid
    assert rows[0]["claimed_by"] == "alice"
    assert rows[0]["retracted_at"] is None


# ─── schema migration ──────────────────────────────────────────────────


def test_schema_has_gate_ladder_column(gates_env):
    import sqlite3
    us, base = gates_env  # noqa: F841 — importlib reloads ensure init
    from tinyassets.daemon_server import (
        db_path,
        initialize_author_server,
    )
    initialize_author_server(base)
    conn = sqlite3.connect(db_path(base))
    cols = {
        r[1] for r in conn.execute("PRAGMA table_info(goals)")
    }
    conn.close()
    assert "gate_ladder_json" in cols


def test_schema_has_gate_claims_table(gates_env):
    import sqlite3
    us, base = gates_env  # noqa: F841
    from tinyassets.daemon_server import (
        db_path,
        initialize_author_server,
    )
    initialize_author_server(base)
    conn = sqlite3.connect(db_path(base))
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    conn.close()
    assert "gate_claims" in tables
