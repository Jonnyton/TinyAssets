"""Tests for goals action=set_canonical MCP wiring.

Spec: docs/vetted-specs.md §canonical_branch.
Implementation: tinyassets/universe_server.py _action_goal_set_canonical().
Depends on canonical_branch storage layer (Task #43 / daemon_server.py).
"""

from __future__ import annotations

import importlib
import inspect
import json

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Live-DB universe_server fixture — same shape as
    tests/test_text_channel_id_redaction.py. Reload the module so the
    base-path env var takes effect on import-time singletons.
    """
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("_FORCE_MOCK", "true")
    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    fn = getattr(us, tool)
    return json.loads(fn(action=action, **kwargs))


def _seed_goal(us, name="Set-canonical test Goal"):
    result = _call(us, "goals", "propose", name=name)
    assert result["status"] == "proposed", result
    return result["goal"]["goal_id"]


def _seed_published_branch(us, base, name="canonical-target"):
    """Build a minimal branch and publish it. Returns branch_version_id."""
    bid = _call(us, "extensions", "create_branch", name=name)["branch_def_id"]
    _call(us, "extensions", "add_node",
          branch_def_id=bid, node_id="n1",
          display_name="N1", prompt_template="echo {x}",
          output_keys="result")
    for src, dst in (("START", "n1"), ("n1", "END")):
        _call(us, "extensions", "connect_nodes",
              branch_def_id=bid, from_node=src, to_node=dst)
    _call(us, "extensions", "set_entry_point", branch_def_id=bid, node_id="n1")
    for field in ("x", "result"):
        _call(us, "extensions", "add_state_field",
              branch_def_id=bid, field_name=field, field_type="str")
    # Publish via the storage-layer helper directly; the MCP `publish_version`
    # action exists but goes through extensions(), so use the lower-level
    # function for a deterministic version_id without depending on extension
    # plumbing for the seed step.
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.daemon_server import get_branch_definition
    branch_dict = get_branch_definition(base, branch_def_id=bid)
    version = publish_branch_version(base, branch_dict, publisher="alice")
    return version.branch_version_id


# ─── shape tests (no DB) ──────────────────────────────────────────────────


class TestSetCanonicalResponseShape:
    """Shape tests that don't require live universe_server state."""

    def test_set_canonical_action_in_goal_available_actions(self):
        from tinyassets.api.market import _GOAL_ACTIONS
        assert "set_canonical" in _GOAL_ACTIONS

    def test_set_canonical_in_goal_write_actions(self):
        from tinyassets.api.market import _GOAL_WRITE_ACTIONS
        assert "set_canonical" in _GOAL_WRITE_ACTIONS

    def test_set_canonical_in_all_goal_actions(self):
        from tinyassets.api.market import (
            _GOAL_ACTIONS,
            _GOAL_WRITE_ACTIONS,
        )
        assert "set_canonical" in _GOAL_ACTIONS
        assert "set_canonical" in _GOAL_WRITE_ACTIONS

    def test_goals_signature_accepts_branch_version_id(self):
        """Task #21 — `branch_version_id` must be a real `goals()`
        function-arg, not a kwarg silently dropped by the MCP layer.
        Pre-Task-#21 the arg was missing from the signature, the MCP
        framework dropped it before reaching `goal_kwargs`, and the
        `set_canonical` handler always saw `branch_version_id=None`.
        """
        from tinyassets.universe_server import goals
        params = inspect.signature(goals).parameters
        assert "branch_version_id" in params, (
            "goals() must accept branch_version_id; otherwise "
            "set_canonical can never receive a real version id."
        )
        # And it must default to "" so chatbots that don't pass it
        # (e.g. for unset semantics on set_canonical) get sensible
        # behavior instead of a TypeError.
        assert params["branch_version_id"].default == "", (
            "branch_version_id should default to empty string; "
            "the handler interprets '' as 'unset' (None)."
        )


class TestRunBranchVersionWiring:
    """Phase A item 6 (Task #65b) — sibling-action runs the canonical bvid."""

    def test_run_branch_version_action_wired(self):
        from tinyassets.api.runs import _RUN_ACTIONS
        assert "run_branch_version" in _RUN_ACTIONS

    def test_run_branch_version_in_run_write_actions(self):
        from tinyassets.api.runs import _RUN_WRITE_ACTIONS
        assert "run_branch_version" in _RUN_WRITE_ACTIONS

    def test_set_canonical_and_run_version_actions_compose(self):
        """End-to-end wiring: a set_canonical -> run_branch_version pipeline
        depends on both actions being registered together. Confirms the
        action namespace pair that gate-routing (Task #53) will rely on."""
        from tinyassets.api.market import _GOAL_ACTIONS
        from tinyassets.api.runs import _RUN_ACTIONS
        assert "set_canonical" in _GOAL_ACTIONS
        assert "run_branch_version" in _RUN_ACTIONS


# ─── live MCP-surface tests (require DB state) ────────────────────────────


class TestSetCanonicalAction:
    """Integration tests for the set_canonical MCP action.

    Task #21 wired `branch_version_id` through the `goals()` MCP signature
    so the handler can receive it. These tests prove the wire-through
    end-to-end and assert symmetric read-side flow via `goals action=get`
    (per `feedback_symmetric_boundary_validation`).
    """

    def test_set_canonical_by_goal_author_succeeds(self, env):
        us, base = env
        gid = _seed_goal(us)
        bvid = _seed_published_branch(us, base)
        result = _call(us, "goals", "set_canonical",
                       goal_id=gid, branch_version_id=bvid)
        assert result["status"] == "ok", result
        assert result["canonical_branch_version_id"] == bvid

    def test_set_canonical_nonexistent_version_rejected(self, env):
        us, _ = env
        gid = _seed_goal(us)
        result = _call(us, "goals", "set_canonical",
                       goal_id=gid, branch_version_id="bv_does_not_exist")
        assert result["status"] == "rejected", result
        # Storage layer rejects non-published version_ids loudly.
        assert "branch_versions" in result.get("error", "").lower() or \
               "not found" in result.get("error", "").lower()

    def test_unset_canonical_returns_null(self, env):
        us, base = env
        gid = _seed_goal(us)
        bvid = _seed_published_branch(us, base)
        # First set so there's something to unset.
        _call(us, "goals", "set_canonical",
              goal_id=gid, branch_version_id=bvid)
        # Empty string == unset semantics (default).
        result = _call(us, "goals", "set_canonical",
                       goal_id=gid, branch_version_id="")
        assert result["status"] == "ok", result
        assert result["canonical_branch_version_id"] is None

    def test_goals_get_returns_canonical_after_set(self, env):
        """Symmetric boundary check: after `set_canonical` writes the
        binding, `goals action=get` must return the new
        canonical_branch_version_id in the goal dict — proving the
        read-side path also surfaces the value the chatbot just wrote.
        """
        us, base = env
        gid = _seed_goal(us)
        bvid = _seed_published_branch(us, base)
        _call(us, "goals", "set_canonical",
              goal_id=gid, branch_version_id=bvid)
        result = _call(us, "goals", "get", goal_id=gid)
        assert "goal" in result, result
        assert result["goal"]["canonical_branch_version_id"] == bvid

    def test_set_canonical_missing_goal_id_rejected(self, env):
        us, _ = env
        result = _call(us, "goals", "set_canonical",
                       goal_id="", branch_version_id="bv_anything")
        assert result["status"] == "rejected"
        assert "goal_id" in result.get("error", "").lower()
