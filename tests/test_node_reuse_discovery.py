"""#62 Part B: cross-branch + cross-Goal node reuse discovery MCP surface.

Pairs with #62 Part A (daemon_server helpers) and #66 (node_ref /
intent primitives). Part A gave us the query helpers; Part B wires
them to MCP so Claude.ai can actually reach them.

What we pin:
- `extensions action=search_nodes` returns reuse candidates with a
  phone-card text layout, and each hit carries the branch_def_id
  needed for a subsequent `node_ref` copy.
- `goals action=common_nodes scope=all` aggregates across every Goal
  + unbound Branches; `scope=this_goal` (default) still works and
  requires goal_id.
- The control_station prompt + branch_design_guide carry the
  "search before invent" nudge so the bot steers toward reuse.
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
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from workflow import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, tool: str, action: str, **kwargs):
    fn = getattr(us, tool)
    return json.loads(fn(action=action, **kwargs))


def _build(us, *, name: str, node_ids: list[str], goal_id: str = "") -> str:
    spec = {
        "name": name,
        "entry_point": node_ids[0],
        "node_defs": [
            {
                "node_id": nid,
                "display_name": nid.replace("_", " ").title(),
                "description": f"{nid} node in {name}",
                "prompt_template": f"{nid}: {{x}}",
            }
            for nid in node_ids
        ],
        "edges": (
            [{"from": "START", "to": node_ids[0]}]
            + [
                {"from": node_ids[i], "to": node_ids[i + 1]}
                for i in range(len(node_ids) - 1)
            ]
            + [{"from": node_ids[-1], "to": "END"}]
        ),
        "state_schema": [{"name": "x", "type": "str"}],
    }
    if goal_id:
        spec["goal_id"] = goal_id
    res = _call(us, "extensions", "build_branch", spec_json=json.dumps(spec))
    assert res["status"] == "built", res
    return res["branch_def_id"]


# ─────────────────────────────────────────────────────────────────────────────
# extensions action=search_nodes
# ─────────────────────────────────────────────────────────────────────────────


class TestSearchNodesAction:

    def test_empty_query_returns_all(self, ext_env):
        us, _ = ext_env
        _build(us, name="b1", node_ids=["alpha", "beta"])
        res = _call(us, "extensions", "search_nodes", node_query="")
        ids = {e["node_id"] for e in res["entries"]}
        assert {"alpha", "beta"}.issubset(ids)
        assert "Reusable nodes" in res["text"]

    def test_query_filters_by_substring(self, ext_env):
        us, _ = ext_env
        _build(
            us, name="research-paper",
            node_ids=["rigor_checker", "drafter"],
        )
        _build(us, name="recipes", node_ids=["capture", "archive"])
        res = _call(us, "extensions", "search_nodes", node_query="rigor")
        ids = {e["node_id"] for e in res["entries"]}
        assert "rigor_checker" in ids
        assert "drafter" not in ids
        assert "capture" not in ids

    def test_reuse_count_reflects_branches(self, ext_env):
        us, _ = ext_env
        _build(us, name="research", node_ids=["rigor_checker", "outline"])
        _build(us, name="legal", node_ids=["rigor_checker", "brief"])
        res = _call(us, "extensions", "search_nodes", node_query="rigor")
        hit = next(
            e for e in res["entries"] if e["node_id"] == "rigor_checker"
        )
        assert hit["reuse_count"] == 2

    def test_hit_carries_branch_def_id_for_node_ref(self, ext_env):
        """#66 + #62 handoff: a search hit must tell the caller which
        branch to cite as the node_ref source. Otherwise the bot can't
        actually reuse the node it just found.
        """
        us, _ = ext_env
        source_bid = _build(
            us, name="source", node_ids=["shared_audit"],
        )
        res = _call(us, "extensions", "search_nodes", node_query="shared_audit")
        hit = next(e for e in res["entries"] if e["node_id"] == "shared_audit")
        assert hit["branch_def_id"] == source_bid

        # Round-trip: use that branch_def_id as a node_ref source.
        target_spec = {
            "name": "target",
            "entry_point": "shared_audit",
            "node_defs": [{
                "node_id": "shared_audit",
                "display_name": "",
                "node_ref": {
                    "source": hit["branch_def_id"],
                    "node_id": "shared_audit",
                },
            }],
            "edges": [
                {"from": "START", "to": "shared_audit"},
                {"from": "shared_audit", "to": "END"},
            ],
            "state_schema": [{"name": "x", "type": "str"}],
        }
        out = _call(us, "extensions", "build_branch",
                    spec_json=json.dumps(target_spec))
        assert out["status"] == "built"

    def test_zero_hits_nudges_toward_descriptive_ids(self, ext_env):
        us, _ = ext_env
        res = _call(us, "extensions", "search_nodes", node_query="ghost")
        assert res["count"] == 0
        assert "invent" in res["text"].lower() or "register" in res["text"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# goals action=common_nodes scope=all
# ─────────────────────────────────────────────────────────────────────────────


class TestGoalsCommonNodesScope:

    def test_default_scope_requires_goal_id(self, ext_env):
        us, _ = ext_env
        res = _call(us, "goals", "common_nodes")
        assert res.get("status") == "rejected"
        assert "goal_id" in res.get("error", "").lower()

    def test_scope_all_does_not_require_goal_id(self, ext_env):
        us, _ = ext_env
        # One branch; min_branches=1 so it shows.
        _build(us, name="solo", node_ids=["capture"])
        res = _call(us, "goals", "common_nodes",
                    scope="all", min_branches=1)
        assert "entries" in res
        ids = {e["node_id"] for e in res["entries"]}
        assert "capture" in ids

    def test_scope_all_aggregates_across_goals(self, ext_env):
        """The scenario #62 diagnosed: same node shared across
        branches that live under different Goals.
        """
        us, _ = ext_env
        # Two Goals, each with a branch using rigor_checker.
        gid1 = _call(us, "goals", "propose",
                     name="Research paper")["goal"]["goal_id"]
        gid2 = _call(us, "goals", "propose",
                     name="Prosecutorial brief")["goal"]["goal_id"]
        _build(us, name="research", node_ids=["rigor_checker"], goal_id=gid1)
        _build(us, name="legal", node_ids=["rigor_checker"], goal_id=gid2)

        res = _call(us, "goals", "common_nodes",
                    scope="all", min_branches=2)
        hit = next(
            e for e in res["entries"] if e["node_id"] == "rigor_checker"
        )
        assert hit["occurrence_count"] == 2
        assert set(hit["goal_ids"]) == {gid1, gid2}

    def test_scope_this_goal_filters_correctly(self, ext_env):
        us, _ = ext_env
        gid1 = _call(us, "goals", "propose", name="G1")["goal"]["goal_id"]
        gid2 = _call(us, "goals", "propose", name="G2")["goal"]["goal_id"]
        _build(us, name="g1-branch-a",
               node_ids=["shared_node"], goal_id=gid1)
        _build(us, name="g1-branch-b",
               node_ids=["shared_node"], goal_id=gid1)
        _build(us, name="g2-branch",
               node_ids=["shared_node"], goal_id=gid2)

        res = _call(us, "goals", "common_nodes",
                    goal_id=gid1, scope="this_goal", min_branches=2)
        hit = next(
            e for e in res["entries"] if e["node_id"] == "shared_node"
        )
        # Only g1's two branches count under scope=this_goal.
        assert hit["occurrence_count"] == 2

    def test_scope_unknown_rejected(self, ext_env):
        us, _ = ext_env
        res = _call(us, "goals", "common_nodes",
                    scope="everywhere", min_branches=1)
        assert res.get("status") == "rejected"
        assert "scope" in res.get("error", "").lower()


# ─────────────────────────────────────────────────────────────────────────────
# Reuse-nudge prompt language
# ─────────────────────────────────────────────────────────────────────────────


class TestReusePromptNudges:

    def test_control_station_has_search_before_invent_rule(self, ext_env):
        us, _ = ext_env
        text = us._CONTROL_STATION_PROMPT.lower()
        assert "reuse before invent" in text or "before you invent" in text
        assert "search_nodes" in text
        assert "common_nodes" in text
        assert "node_ref" in text

    def test_branch_design_guide_points_at_search_first(self, ext_env):
        from workflow.api.branches import _BRANCH_DESIGN_GUIDE
        text = _BRANCH_DESIGN_GUIDE.lower()
        assert "search_nodes" in text
        assert "node_ref" in text
        # The guide must position search BEFORE the author flow.
        search_idx = text.index("search_nodes")
        author_idx = text.index("author flow")
        assert search_idx < author_idx, (
            "search-before-invent nudge must appear before the author flow"
        )

    def test_branch_design_guide_names_chat_native_authoring(self, ext_env):
        from workflow.api.branches import _BRANCH_DESIGN_GUIDE
        text = _BRANCH_DESIGN_GUIDE
        assert "chat-native" in text
        assert "GitHub Actions YAML" in text
        assert "build_branch" in text
        assert "patch_branch" in text
