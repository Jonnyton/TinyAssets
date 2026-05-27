"""DESIGN-008 — tests for goals action=set_selector MCP wiring.

Spec: drafts/concepts/selector-branch-contract.md
Implementation:
  * workflow/api/market.py::_action_goal_set_selector
  * workflow/daemon_server.py::set_selector_branch
  * workflow/api/quality_leaderboard.py — consumes the binding
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("_FORCE_MOCK", "true")
    from workflow import universe_server as us
    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    fn = getattr(us, tool)
    return json.loads(fn(action=action, **kwargs))


def _seed_goal(us, name="Selector binding test Goal"):
    result = _call(us, "goals", "propose", name=name)
    assert result["status"] == "proposed", result
    return result["goal"]["goal_id"]


def _seed_published_branch(us, base, name="selector-candidate"):
    """Build + publish a minimal selector-conformant branch."""
    bid = _call(
        us, "extensions", "create_branch", name=name,
    )["branch_def_id"]
    _call(
        us, "extensions", "add_node",
        branch_def_id=bid, node_id="rank",
        display_name="Rank", prompt_template="rank {candidate_branches}",
        output_keys="ranked_entries",
    )
    for src, dst in (("START", "rank"), ("rank", "END")):
        _call(
            us, "extensions", "connect_nodes",
            branch_def_id=bid, from_node=src, to_node=dst,
        )
    _call(us, "extensions", "set_entry_point", branch_def_id=bid, node_id="rank")
    for field in ("goal_id", "candidate_branches", "ranked_entries"):
        _call(
            us, "extensions", "add_state_field",
            branch_def_id=bid, field_name=field, field_type="str",
        )
    from workflow.branch_versions import publish_branch_version
    from workflow.daemon_server import get_branch_definition
    branch_dict = get_branch_definition(base, branch_def_id=bid)
    version = publish_branch_version(base, branch_dict, publisher="alice")
    return version.branch_version_id


# ---------------------------------------------------------------------------
# Dispatch table wiring
# ---------------------------------------------------------------------------


def test_set_selector_action_in_goal_actions():
    from workflow.api.market import _GOAL_ACTIONS
    assert "set_selector" in _GOAL_ACTIONS


def test_set_selector_in_goal_write_actions():
    from workflow.api.market import _GOAL_WRITE_ACTIONS
    assert "set_selector" in _GOAL_WRITE_ACTIONS


# ---------------------------------------------------------------------------
# MCP surface — happy path
# ---------------------------------------------------------------------------


def test_set_selector_by_goal_author_succeeds(env):
    us, base = env
    gid = _seed_goal(us)
    bvid = _seed_published_branch(us, base)
    result = _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id=bvid,
    )
    assert result["status"] == "ok", result
    assert result["selector_branch_version_id"] == bvid


def test_set_selector_persists_in_goal_record(env):
    us, base = env
    gid = _seed_goal(us)
    bvid = _seed_published_branch(us, base)
    _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id=bvid,
    )
    goal = _call(us, "goals", "get", goal_id=gid)["goal"]
    assert goal["selector_branch_version_id"] == bvid


def test_set_selector_empty_branch_version_id_unbinds(env):
    us, base = env
    gid = _seed_goal(us)
    bvid = _seed_published_branch(us, base)
    _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id=bvid,
    )
    # Now unbind.
    result = _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id="",
    )
    assert result["status"] == "ok"
    assert result["selector_branch_version_id"] is None
    goal = _call(us, "goals", "get", goal_id=gid)["goal"]
    assert goal["selector_branch_version_id"] is None


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


def test_set_selector_requires_author_or_host(env, monkeypatch):
    us, base = env
    gid = _seed_goal(us)  # author = alice
    bvid = _seed_published_branch(us, base)
    # Switch actor to eve — not author and no selector-bind grant.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "eve")
    importlib.reload(us)
    try:
        result = _call(
            us, "goals", "set_selector",
            goal_id=gid, branch_version_id=bvid,
        )
        assert result["status"] == "rejected"
        assert "author" in result["error"]
    finally:
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
        importlib.reload(us)


def test_set_selector_granted_actor_can_bind(env, monkeypatch):
    us, base = env
    gid = _seed_goal(us)  # author = alice
    bvid = _seed_published_branch(us, base)
    # Switch to a non-author carrying the explicit selector-bind grant.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "operator")
    monkeypatch.setenv("UNIVERSE_SERVER_CAPABILITIES", "set_goal_selector")
    importlib.reload(us)
    try:
        result = _call(
            us, "goals", "set_selector",
            goal_id=gid, branch_version_id=bvid,
        )
        assert result["status"] == "ok"
        assert result["selector_branch_version_id"] == bvid
    finally:
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
        importlib.reload(us)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_set_selector_missing_goal_id_rejected(env):
    us, _ = env
    result = _call(us, "goals", "set_selector")
    assert result["status"] == "rejected"
    assert "goal_id" in result["error"]


def test_set_selector_unknown_goal_rejected(env):
    us, _ = env
    result = _call(
        us, "goals", "set_selector",
        goal_id="ghost-goal", branch_version_id="x@y",
    )
    assert result["status"] == "rejected"
    assert "not found" in result["error"]


def test_set_selector_nonexistent_version_rejected(env):
    us, _ = env
    gid = _seed_goal(us)
    result = _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id="phantom_branch@deadbeef",
    )
    assert result["status"] == "rejected"
    assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# DESIGN-008 round 2 P1.3 — bind rejects effectful selector branches
# ---------------------------------------------------------------------------


def _publish_effectful_branch(base, name="effectful-selector"):
    """Publish a branch_version whose snapshot declares effects.

    Selector branches that declare ``effects`` (e.g. github_pull_request)
    would silently fire external writes on every leaderboard read —
    set_selector_branch must reject the bind.
    """
    from workflow.branch_versions import publish_branch_version
    from workflow.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )
    bid = "effectful_rank_branch"
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id=bid,
            name=name,
            description="",
            author="alice",
            tags=[],
            graph_nodes=[
                {
                    "id": "rank",
                    "type": "prompt",
                    "phase": "custom",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                },
            ],
            edges=[
                {"from": "START", "to": "rank"},
                {"from": "rank", "to": "END"},
            ],
            state_schema=[
                {"name": "candidate_branches", "type": "list"},
                {"name": "ranked_entries", "type": "list"},
            ],
            entry_point="rank",
            published=True,
            visibility="public",
            node_defs=[
                {
                    "node_id": "rank",
                    "display_name": "Rank",
                    "phase": "custom",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                    "prompt_template": "rank {candidate_branches}",
                    # P1.3 fail-trigger: this node declares an effect.
                    "effects": ["github_pull_request"],
                },
            ],
        ),
    )
    branch_dict = get_branch_definition(base, branch_def_id=bid)
    version = publish_branch_version(base, branch_dict, publisher="alice")
    return version.branch_version_id


def test_set_selector_rejects_branch_with_effects(env):
    """P1.3 — a selector that declares effects would turn every
    leaderboard read into a silent external write. Substrate rejects
    the bind."""
    us, base = env
    gid = _seed_goal(us)
    bvid = _publish_effectful_branch(base)
    result = _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id=bvid,
    )
    assert result["status"] == "rejected"
    assert result.get("error_kind") == "selector_has_effects"
    assert "effects" in result["error"].lower()
    # Error message must name the offending node so the operator
    # can fix it.
    assert "rank" in result["error"]


def test_set_selector_storage_layer_raises_selector_has_effects(env):
    """Storage-layer regression — set_selector_branch raises
    SelectorHasEffectsError on an effectful version, no MCP wrapper
    involved."""
    us, base = env
    gid = _seed_goal(us)
    bvid = _publish_effectful_branch(base)
    from workflow.daemon_server import (
        SelectorHasEffectsError,
        set_selector_branch,
    )
    with pytest.raises(SelectorHasEffectsError) as exc_info:
        set_selector_branch(
            base, goal_id=gid,
            branch_version_id=bvid, set_by="host",
        )
    assert "effects" in str(exc_info.value).lower()


def test_set_selector_unbind_path_does_not_check_effects(env):
    """Unbind passes branch_version_id=None which short-circuits the
    effects check entirely — the operator must always be able to
    unbind back to the platform default selector regardless of
    whatever was previously bound."""
    us, _ = env
    gid = _seed_goal(us)
    result = _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id="",
    )
    assert result["status"] == "ok"
    assert result["selector_branch_version_id"] is None


# ---------------------------------------------------------------------------
# DESIGN-008 round 3 P1.B — child-branch invocation rejected at bind time
# ---------------------------------------------------------------------------


def _publish_branch_with_invoke_branch_spec(base, name="invoking-selector"):
    """Publish a branch_version with no direct effects but a node
    that invokes a child branch via ``invoke_branch_spec``.

    Round-3 P1.B: the round-2 purity scan only inspected direct
    ``effects`` on node_defs. A selector with no direct effects can
    still spawn a child run via invoke_branch_spec — the child's
    completion fires the child's effectors. Bind must reject.
    """
    from workflow.branch_versions import publish_branch_version
    from workflow.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )
    bid = "invoking_rank_branch"
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id=bid,
            name=name,
            description="",
            author="alice",
            tags=[],
            graph_nodes=[
                {
                    "id": "rank",
                    "type": "prompt",
                    "phase": "custom",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                },
            ],
            edges=[
                {"from": "START", "to": "rank"},
                {"from": "rank", "to": "END"},
            ],
            state_schema=[
                {"name": "candidate_branches", "type": "str"},
                {"name": "ranked_entries", "type": "str"},
            ],
            entry_point="rank",
            published=True,
            visibility="public",
            node_defs=[
                {
                    "node_id": "rank",
                    "display_name": "Rank",
                    "phase": "custom",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                    # No direct effects, but it invokes a child
                    # branch — that child's completion path fires
                    # ITS effectors. P1.B fail-trigger.
                    "invoke_branch_spec": {
                        "branch_def_id": "some_effectful_child",
                        "inputs_mapping": {},
                        "output_mapping": {"ranked_entries": "result"},
                        "wait_mode": "blocking",
                    },
                },
            ],
        ),
    )
    branch_dict = get_branch_definition(base, branch_def_id=bid)
    version = publish_branch_version(base, branch_dict, publisher="alice")
    return version.branch_version_id


def _publish_branch_with_invoke_branch_version_spec(
    base, name="version-invoking-selector",
):
    """Same idea but using ``invoke_branch_version_spec`` (frozen
    child snapshot) instead of ``invoke_branch_spec``."""
    from workflow.branch_versions import publish_branch_version
    from workflow.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )
    bid = "version_invoking_rank_branch"
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id=bid,
            name=name,
            description="",
            author="alice",
            tags=[],
            graph_nodes=[
                {
                    "id": "rank",
                    "type": "prompt",
                    "phase": "custom",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                },
            ],
            edges=[
                {"from": "START", "to": "rank"},
                {"from": "rank", "to": "END"},
            ],
            state_schema=[
                {"name": "candidate_branches", "type": "str"},
                {"name": "ranked_entries", "type": "str"},
            ],
            entry_point="rank",
            published=True,
            visibility="public",
            node_defs=[
                {
                    "node_id": "rank",
                    "display_name": "Rank",
                    "phase": "custom",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                    "invoke_branch_version_spec": {
                        "branch_version_id": "child@deadbeef",
                        "inputs_mapping": {},
                        "output_mapping": {"ranked_entries": "result"},
                        "wait_mode": "blocking",
                    },
                },
            ],
        ),
    )
    branch_dict = get_branch_definition(base, branch_def_id=bid)
    version = publish_branch_version(base, branch_dict, publisher="alice")
    return version.branch_version_id


def test_set_selector_rejects_invoke_branch_spec(env):
    """P1.B — selector with invoke_branch_spec rejected at bind."""
    us, base = env
    gid = _seed_goal(us)
    bvid = _publish_branch_with_invoke_branch_spec(base)
    result = _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id=bvid,
    )
    assert result["status"] == "rejected"
    assert result.get("error_kind") == "selector_has_effects"
    err = result["error"].lower()
    assert "child" in err or "invoke_branch_spec" in err
    # Names the offending node so the operator can fix it.
    assert "rank" in result["error"]


def test_set_selector_rejects_invoke_branch_version_spec(env):
    """P1.B — same guard covers the version-spec sibling."""
    us, base = env
    gid = _seed_goal(us)
    bvid = _publish_branch_with_invoke_branch_version_spec(base)
    result = _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id=bvid,
    )
    assert result["status"] == "rejected"
    assert result.get("error_kind") == "selector_has_effects"
    err = result["error"].lower()
    assert "child" in err or "invoke_branch_version_spec" in err


def test_set_selector_storage_layer_raises_on_child_invoker(env):
    """Direct storage-layer assertion that the new purity guard fires
    on a branch that has no direct effects but invokes children."""
    us, base = env
    gid = _seed_goal(us)
    bvid = _publish_branch_with_invoke_branch_spec(base)
    from workflow.daemon_server import (
        SelectorHasEffectsError,
        set_selector_branch,
    )
    with pytest.raises(SelectorHasEffectsError) as exc_info:
        set_selector_branch(
            base, goal_id=gid,
            branch_version_id=bvid, set_by="host",
        )
    msg = str(exc_info.value).lower()
    assert "child" in msg or "invoke" in msg


def test_set_selector_rejects_branch_with_both_effects_and_invoke(env):
    """A branch with both direct effects AND a child invoker must
    surface both violation classes in the error message."""
    from workflow.branch_versions import publish_branch_version
    from workflow.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )
    us, base = env
    gid = _seed_goal(us)
    bid = "double_violation_branch"
    save_branch_definition(
        base,
        branch_def=dict(
            branch_def_id=bid,
            name="double",
            description="",
            author="alice",
            tags=[],
            graph_nodes=[
                {
                    "id": "n1",
                    "type": "prompt",
                    "phase": "custom",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                },
            ],
            edges=[
                {"from": "START", "to": "n1"},
                {"from": "n1", "to": "END"},
            ],
            state_schema=[
                {"name": "candidate_branches", "type": "str"},
                {"name": "ranked_entries", "type": "str"},
            ],
            entry_point="n1",
            published=True,
            visibility="public",
            node_defs=[
                {
                    "node_id": "n1",
                    "display_name": "Double Violator",
                    "phase": "custom",
                    "input_keys": ["candidate_branches"],
                    "output_keys": ["ranked_entries"],
                    "prompt_template": "rank {candidate_branches}",
                    "effects": ["github_pull_request"],
                    "invoke_branch_spec": {
                        "branch_def_id": "child",
                        "inputs_mapping": {},
                        "output_mapping": {"ranked_entries": "result"},
                        "wait_mode": "blocking",
                    },
                },
            ],
        ),
    )
    branch_dict = get_branch_definition(base, branch_def_id=bid)
    bvid = publish_branch_version(
        base, branch_dict, publisher="alice",
    ).branch_version_id
    result = _call(
        us, "goals", "set_selector",
        goal_id=gid, branch_version_id=bvid,
    )
    assert result["status"] == "rejected"
    assert result.get("error_kind") == "selector_has_effects"
    err = result["error"].lower()
    assert "effects" in err
    assert "child" in err or "invoke" in err
