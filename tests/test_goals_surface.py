"""Goals as a first-class shared primitive.

Covers AC from ``docs/specs/community_branches_phase5.md`` §Executable
Addendum:

1. Storage: goals table + branch_definitions.goal_id column.
2. 8 MCP actions on the `goals` tool with tool_return_shapes.md patterns.
3. Leaderboard metrics: run_count + forks today; outcome stub.
4. common_nodes compares on node_id equality.
5. Soft-delete via visibility='deleted'.
6. Ledger write-through on propose/update/bind.
7. build_branch accepts goal_id top-level; patch_branch set_goal/unset_goal ops.
8. Mission-5-independent parts pass without prompt routing.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from workflow.api.helpers import _base_path as _helpers_base_path


@pytest.fixture
def p5_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from workflow import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    """Dispatch to the named MCP tool function with action + kwargs."""
    fn = getattr(us, tool)
    return json.loads(fn(action=action, **kwargs))


# ─────────────────────────────────────────────────────────────────────────────
# propose + storage
# ─────────────────────────────────────────────────────────────────────────────


def test_propose_creates_goal_with_id(p5_env):
    us, _ = p5_env
    result = _call(us, "goals", "propose",
                   name="Research paper",
                   description="Produce an academic research paper",
                   tags="research,academic")
    assert result["status"] == "proposed"
    assert result["goal"]["goal_id"]
    assert result["goal"]["name"] == "Research paper"
    assert result["goal"]["tags"] == ["research", "academic"]
    assert result["goal"]["visibility"] == "public"
    assert "text" in result
    # #58: raw goal_id must stay in structuredContent, not the text channel.
    assert result["goal"]["goal_id"] not in result["text"]
    # The Goal name surfaces in text instead.
    assert "Research paper" in result["text"]


def test_propose_requires_name(p5_env):
    us, _ = p5_env
    result = _call(us, "goals", "propose")
    assert result["status"] == "rejected"
    assert "name" in result["error"].lower()


def test_propose_rejects_bad_visibility(p5_env):
    us, _ = p5_env
    result = _call(us, "goals", "propose",
                   name="x", visibility="deleted")
    assert result["status"] == "rejected"


def test_list_empty_returns_friendly_text(p5_env):
    us, _ = p5_env
    result = _call(us, "goals", "list")
    assert result["count"] == 0
    assert "no goals" in result["text"].lower()


def test_list_returns_proposed_goals(p5_env):
    us, _ = p5_env
    _call(us, "goals", "propose", name="A", tags="x")
    _call(us, "goals", "propose", name="B", tags="y")
    result = _call(us, "goals", "list")
    assert result["count"] == 2
    names = {g["name"] for g in result["goals"]}
    assert names == {"A", "B"}
    assert "- `" in result["text"]


def test_list_can_filter_to_production_goals(p5_env):
    us, _ = p5_env
    _call(us, "goals", "propose", name="Real workflow goal", tags="research")
    _call(us, "goals", "propose", name="Smoke probe goal", tags="smoke")
    _call(us, "goals", "propose", name="Disposable scout goal", tags="disposable")
    _call(us, "goals", "propose", name="RETRACTED old goal", tags="research")
    _call(us, "goals", "propose", name="Private real goal", visibility="private")

    result = _call(us, "goals", "list", production_only=True)

    assert result["count"] == 1
    assert result["production_only"] is True
    assert result["excluded_count"] == 4
    assert [g["name"] for g in result["goals"]] == ["Real workflow goal"]
    assert "production" in result["text"].lower()


def test_list_production_filter_applies_before_limit(p5_env):
    us, _ = p5_env
    _call(us, "goals", "propose", name="Real workflow goal", tags="research")
    _call(us, "goals", "propose", name="Smoke probe goal", tags="smoke")

    result = _call(us, "goals", "list", production_only=True, limit=1)

    assert result["count"] == 1
    assert [g["name"] for g in result["goals"]] == ["Real workflow goal"]


def test_get_returns_full_goal_with_branches(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="Test")["goal"]["goal_id"]
    result = _call(us, "goals", "get", goal_id=gid)
    assert result["goal"]["goal_id"] == gid
    assert result["branch_count"] == 0
    assert "Test" in result["text"]


def test_get_rejects_missing_goal(p5_env):
    us, _ = p5_env
    result = _call(us, "goals", "get", goal_id="deadbeef")
    assert result["status"] == "rejected"


# ─────────────────────────────────────────────────────────────────────────────
# update — owner-only
# ─────────────────────────────────────────────────────────────────────────────


def test_update_by_author_succeeds(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="Original")["goal"]["goal_id"]
    result = _call(us, "goals", "update",
                   goal_id=gid, description="Updated description")
    assert result["status"] == "updated"
    assert "description" in result["changed_fields"]
    assert result["goal"]["description"] == "Updated description"


def test_update_by_non_author_rejected(p5_env, monkeypatch):
    us, _ = p5_env
    # Author = tester per fixture
    gid = _call(us, "goals", "propose", name="Owned")["goal"]["goal_id"]
    # Switch actor
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    importlib.reload(us)
    result = _call(us, "goals", "update",
                   goal_id=gid, name="Stolen")
    assert result["status"] == "rejected"
    assert "author" in result["error"].lower()


def test_update_requires_at_least_one_field(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="x")["goal"]["goal_id"]
    result = _call(us, "goals", "update", goal_id=gid)
    assert result["status"] == "rejected"


# ─────────────────────────────────────────────────────────────────────────────
# bind + list_branches filter
# ─────────────────────────────────────────────────────────────────────────────


def _build_branch(us, name: str = "Trivial") -> str:
    spec = {
        "name": name,
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "Go: {x}"}],
        "edges": [
            {"from": "START", "to": "n"},
            {"from": "n", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    return _call(us, "extensions", "build_branch",
                 spec_json=json.dumps(spec))["branch_def_id"]


def test_bind_attaches_branch_to_goal(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    bid = _build_branch(us)
    result = _call(us, "goals", "bind",
                   branch_def_id=bid, goal_id=gid)
    assert result["status"] == "bound"

    got = _call(us, "extensions", "get_branch", branch_def_id=bid)
    assert got["goal_id"] == gid


def test_bind_rejects_missing_branch(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    result = _call(us, "goals", "bind",
                   branch_def_id="nobranch", goal_id=gid)
    assert result["status"] == "rejected"


def test_bind_rejects_missing_goal(p5_env):
    us, _ = p5_env
    bid = _build_branch(us)
    result = _call(us, "goals", "bind",
                   branch_def_id=bid, goal_id="nogoal")
    assert result["status"] == "rejected"


def test_unbind_via_empty_goal_id(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    bid = _build_branch(us)
    _call(us, "goals", "bind", branch_def_id=bid, goal_id=gid)
    result = _call(us, "goals", "bind", branch_def_id=bid, goal_id="")
    assert result["status"] == "unbound"

    got = _call(us, "extensions", "get_branch", branch_def_id=bid)
    assert got.get("goal_id") in (None, "")


def test_bind_rejects_deleted_goal(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="ToDelete")["goal"]["goal_id"]
    _call(us, "goals", "update", goal_id=gid, visibility="deleted")
    bid = _build_branch(us)
    result = _call(us, "goals", "bind",
                   branch_def_id=bid, goal_id=gid)
    assert result["status"] == "rejected"
    assert "deleted" in result["error"].lower()


def test_list_branches_goal_id_filter(p5_env):
    us, _ = p5_env
    gid1 = _call(us, "goals", "propose", name="G1")["goal"]["goal_id"]
    gid2 = _call(us, "goals", "propose", name="G2")["goal"]["goal_id"]
    b1 = _build_branch(us, name="B1")
    b2 = _build_branch(us, name="B2")
    b3 = _build_branch(us, name="B3")
    _call(us, "goals", "bind", branch_def_id=b1, goal_id=gid1)
    _call(us, "goals", "bind", branch_def_id=b2, goal_id=gid1)
    _call(us, "goals", "bind", branch_def_id=b3, goal_id=gid2)

    # scope="all" so unpublished drafts built by _build_branch are included
    # (default scope="published" would filter them out).
    result = _call(us, "extensions", "list_branches", goal_id=gid1, scope="all")
    assert result["count"] == 2
    ids = {b["branch_def_id"] for b in result["branches"]}
    assert ids == {b1, b2}


def test_get_goal_shows_bound_branches(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    bid = _build_branch(us, name="Bound")
    _call(us, "goals", "bind", branch_def_id=bid, goal_id=gid)

    result = _call(us, "goals", "get", goal_id=gid)
    assert result["branch_count"] == 1
    assert "Bound" in result["text"]


# ─────────────────────────────────────────────────────────────────────────────
# search
# ─────────────────────────────────────────────────────────────────────────────


def test_search_matches_name(p5_env):
    us, _ = p5_env
    _call(us, "goals", "propose",
          name="Research paper pipeline",
          description="Build an academic research paper end-to-end")
    _call(us, "goals", "propose",
          name="Wedding planner",
          description="Track vendor and budget across months")

    result = _call(us, "goals", "search", query="research")
    assert result["count"] == 1
    assert result["goals"][0]["name"] == "Research paper pipeline"


def test_search_matches_description(p5_env):
    us, _ = p5_env
    _call(us, "goals", "propose", name="X",
          description="tracking bees and honey")
    result = _call(us, "goals", "search", query="honey")
    assert result["count"] == 1


def test_search_requires_query(p5_env):
    us, _ = p5_env
    result = _call(us, "goals", "search")
    assert result["status"] == "rejected"


def test_search_hides_deleted_goals(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="Hidden")["goal"]["goal_id"]
    _call(us, "goals", "update", goal_id=gid, visibility="deleted")
    result = _call(us, "goals", "search", query="hidden")
    assert result["count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# leaderboard
# ─────────────────────────────────────────────────────────────────────────────


def test_leaderboard_run_count(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    b1 = _build_branch(us, name="B1")
    b2 = _build_branch(us, name="B2")
    _call(us, "goals", "bind", branch_def_id=b1, goal_id=gid)
    _call(us, "goals", "bind", branch_def_id=b2, goal_id=gid)

    # B2 has 2 runs, B1 has 1. Run sync via execute_branch to avoid
    # background worker waits.
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.runs import execute_branch

    for _ in range(1):
        br = BranchDefinition.from_dict(
            get_branch_definition(Path(_helpers_base_path()), branch_def_id=b1)
        )
        execute_branch(_helpers_base_path(), branch=br, inputs={"x": "a"})
    for _ in range(2):
        br = BranchDefinition.from_dict(
            get_branch_definition(Path(_helpers_base_path()), branch_def_id=b2)
        )
        execute_branch(_helpers_base_path(), branch=br, inputs={"x": "a"})

    result = _call(us, "goals", "leaderboard",
                   goal_id=gid, metric="run_count")
    assert len(result["entries"]) == 2
    assert result["entries"][0]["branch_def_id"] == b2
    assert result["entries"][0]["value"] == 2


def test_leaderboard_outcome_gated_off_when_flag_unset(p5_env):
    # Phase 6.2.1: GATES_ENABLED gates the outcome metric. The p5_env
    # fixture doesn't set the flag, so outcome falls back to a
    # friendly gated-off envelope — not a stub, not a live empty
    # leaderboard.
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    result = _call(us, "goals", "leaderboard",
                   goal_id=gid, metric="outcome")
    assert result["metric"] == "outcome"
    assert result["entries"] == []
    assert result["status"] == "gates_disabled"
    assert "GATES_ENABLED" in result["text"]


def test_leaderboard_rejects_unknown_metric(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    result = _call(us, "goals", "leaderboard",
                   goal_id=gid, metric="moonshots")
    assert result["status"] == "rejected"
    assert "available_metrics" in result
    assert "run_count" in result["available_metrics"]
    assert "outcome" in result["available_metrics"]


def test_leaderboard_forks_counts_parent_chain(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    parent_bid = _build_branch(us, name="Parent")
    _call(us, "goals", "bind", branch_def_id=parent_bid, goal_id=gid)

    # Create two "forks" — manually save branches with parent_def_id
    # pointing at parent.
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import save_branch_definition

    parent = BranchDefinition.from_dict({"branch_def_id": parent_bid})
    for i in range(2):
        forked = parent.fork(new_name=f"Fork{i}", author="tester")
        forked.goal_id = gid  # bind fork too so leaderboard sees both
        save_branch_definition(_helpers_base_path(), branch_def=forked.to_dict())

    result = _call(us, "goals", "leaderboard",
                   goal_id=gid, metric="forks")
    # Parent entry should show 2 forks.
    ranked = {r["branch_def_id"]: r["value"] for r in result["entries"]}
    assert ranked.get(parent_bid) == 2


# ─────────────────────────────────────────────────────────────────────────────
# common_nodes
# ─────────────────────────────────────────────────────────────────────────────


def test_common_nodes_finds_repeated_node_ids(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]

    # Two branches sharing node_id "capture", one with a unique "extra".
    for branch_name in ("A", "B"):
        spec = {
            "name": branch_name,
            "entry_point": "capture",
            "node_defs": [
                {"node_id": "capture", "display_name": "Capture",
                 "prompt_template": "grab: {x}"},
            ],
            "edges": [
                {"from": "START", "to": "capture"},
                {"from": "capture", "to": "END"},
            ],
            "state_schema": [{"name": "x", "type": "str"}],
            "goal_id": gid,
        }
        _call(us, "extensions", "build_branch",
              spec_json=json.dumps(spec))

    # A third with a unique node.
    spec_solo = {
        "name": "C",
        "entry_point": "extra",
        "node_defs": [{"node_id": "extra", "display_name": "Extra",
                       "prompt_template": "z: {x}"}],
        "edges": [
            {"from": "START", "to": "extra"},
            {"from": "extra", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
        "goal_id": gid,
    }
    _call(us, "extensions", "build_branch",
          spec_json=json.dumps(spec_solo))

    result = _call(us, "goals", "common_nodes",
                   goal_id=gid, min_branches=2)
    ids = {e["node_id"] for e in result["entries"]}
    assert "capture" in ids
    assert "extra" not in ids


def test_common_nodes_respects_min_branches_threshold(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    spec = {
        "name": "Solo",
        "entry_point": "unique",
        "node_defs": [{"node_id": "unique", "display_name": "U",
                       "prompt_template": "{x}"}],
        "edges": [
            {"from": "START", "to": "unique"},
            {"from": "unique", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
        "goal_id": gid,
    }
    _call(us, "extensions", "build_branch", spec_json=json.dumps(spec))

    # With threshold 1, the single occurrence shows.
    r1 = _call(us, "goals", "common_nodes",
               goal_id=gid, min_branches=1)
    assert any(e["node_id"] == "unique" for e in r1["entries"])
    # With threshold 2, it doesn't.
    r2 = _call(us, "goals", "common_nodes",
               goal_id=gid, min_branches=2)
    assert not any(e["node_id"] == "unique" for e in r2["entries"])


# ─────────────────────────────────────────────────────────────────────────────
# build_branch goal_id top-level + patch_branch set/unset_goal
# ─────────────────────────────────────────────────────────────────────────────


def test_build_branch_accepts_goal_id(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    spec = {
        "name": "Preloaded",
        "entry_point": "n",
        "goal_id": gid,
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "{x}"}],
        "edges": [
            {"from": "START", "to": "n"},
            {"from": "n", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    result = _call(us, "extensions", "build_branch",
                   spec_json=json.dumps(spec))
    assert result["status"] == "built"
    got = _call(us, "extensions", "get_branch",
                branch_def_id=result["branch_def_id"])
    assert got["goal_id"] == gid


def test_patch_branch_set_goal_and_unset_goal(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    bid = _build_branch(us)
    patch = [{"op": "set_goal", "goal_id": gid}]
    _call(us, "extensions", "patch_branch",
          branch_def_id=bid, changes_json=json.dumps(patch))
    assert _call(us, "extensions", "get_branch",
                 branch_def_id=bid)["goal_id"] == gid

    _call(us, "extensions", "patch_branch",
          branch_def_id=bid,
          changes_json=json.dumps([{"op": "unset_goal"}]))
    got = _call(us, "extensions", "get_branch", branch_def_id=bid)
    assert got.get("goal_id") in (None, "")


# ─────────────────────────────────────────────────────────────────────────────
# soft-delete semantics
# ─────────────────────────────────────────────────────────────────────────────


def test_soft_delete_hides_from_list_but_get_still_works(p5_env):
    us, _ = p5_env
    gid = _call(us, "goals", "propose", name="Doomed")["goal"]["goal_id"]
    _call(us, "goals", "update", goal_id=gid, visibility="deleted")

    # list hides it
    lst = _call(us, "goals", "list")
    assert all(g["goal_id"] != gid for g in lst["goals"])

    # get still resolves with is_deleted flag
    got = _call(us, "goals", "get", goal_id=gid)
    assert got["is_deleted"] is True


# ─────────────────────────────────────────────────────────────────────────────
# ledger write-through
# ─────────────────────────────────────────────────────────────────────────────


def test_propose_writes_ledger(p5_env):
    us, base = p5_env
    _call(us, "goals", "propose", name="Ledgered")
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    assert any(e["action"] == "goals.propose" for e in ledger)


def test_bind_writes_ledger(p5_env):
    us, base = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    bid = _build_branch(us)
    _call(us, "goals", "bind", branch_def_id=bid, goal_id=gid)
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    actions = [e["action"] for e in ledger]
    assert "goals.bind" in actions


def test_update_writes_ledger(p5_env):
    us, base = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    _call(us, "goals", "update", goal_id=gid, description="renamed")
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    assert any(e["action"] == "goals.update" for e in ledger)


def test_rejected_propose_does_not_ledger(p5_env):
    us, base = p5_env
    _call(us, "goals", "propose")  # no name → rejected
    ledger_path = Path(base) / "ledger.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text("utf-8"))
    else:
        ledger = []
    assert not any(e["action"] == "goals.propose" for e in ledger)


def test_reads_do_not_ledger(p5_env):
    us, base = p5_env
    gid = _call(us, "goals", "propose", name="G")["goal"]["goal_id"]
    _call(us, "goals", "list")
    _call(us, "goals", "get", goal_id=gid)
    _call(us, "goals", "search", query="G")
    _call(us, "goals", "leaderboard", goal_id=gid, metric="run_count")
    _call(us, "goals", "common_nodes", goal_id=gid)
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    read_actions = {"goals.list", "goals.get", "goals.search",
                    "goals.leaderboard", "goals.common_nodes"}
    for e in ledger:
        assert e["action"] not in read_actions


# ─────────────────────────────────────────────────────────────────────────────
# unknown action + catalog
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_action_lists_available(p5_env):
    us, _ = p5_env
    result = _call(us, "goals", "not-an-action")
    assert "error" in result
    avail = result.get("available_actions", [])
    for a in ("propose", "update", "bind", "list", "get",
              "search", "leaderboard", "common_nodes"):
        assert a in avail


# ─────────────────────────────────────────────────────────────────────────────
# migration (back-compat)
# ─────────────────────────────────────────────────────────────────────────────


def test_branch_from_pre_phase5_install_reads_cleanly(tmp_path):
    """An installation that existed before Phase 5 has no goal_id column.
    initialize_author_server adds the column; existing rows surface
    goal_id=None without errors."""
    from workflow.daemon_server import (
        _connect,
        get_branch_definition,
        initialize_author_server,
        save_branch_definition,
    )

    base = tmp_path

    # Simulate a pre-Phase-5 install by creating the branch_definitions
    # table without goal_id, inserting a row, then running init to
    # trigger the ADD COLUMN path.
    base.mkdir(exist_ok=True)
    with _connect(base) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS branch_definitions (
            branch_def_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT 'anonymous',
            domain_id TEXT NOT NULL DEFAULT 'workflow',
            tags_json TEXT NOT NULL DEFAULT '[]',
            version INTEGER NOT NULL DEFAULT 1,
            parent_def_id TEXT,
            entry_point TEXT NOT NULL DEFAULT '',
            graph_json TEXT NOT NULL DEFAULT '{}',
            node_defs_json TEXT NOT NULL DEFAULT '[]',
            state_schema_json TEXT NOT NULL DEFAULT '[]',
            published INTEGER NOT NULL DEFAULT 0,
            stats_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        """)
        conn.execute(
            """
            INSERT INTO branch_definitions (
                branch_def_id, name, created_at, updated_at
            ) VALUES ('legacy-1', 'Legacy', 1.0, 1.0)
            """,
        )

    # Now init: should add the goal_id column without loss.
    initialize_author_server(base)
    got = get_branch_definition(base, branch_def_id="legacy-1")
    assert got["name"] == "Legacy"
    assert got["goal_id"] in (None, "")

    # And new saves work end-to-end.
    new_bid = save_branch_definition(base, branch_def={
        "name": "New",
        "goal_id": "some-goal",
    })["branch_def_id"]
    again = get_branch_definition(base, branch_def_id=new_bid)
    assert again["goal_id"] == "some-goal"
