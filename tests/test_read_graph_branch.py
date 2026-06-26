"""read_graph target=branch — the SEE-for-branches primitive.

Completes the read/edit symmetry started by PR-180: PR-180 added
read_graph target=run (SEE runs) + write_graph target=branch (EDIT branches);
this adds read_graph target=branch (SEE branches) so a founder can inspect a
branch's full node configs (timeout_seconds, model_hint, prompt_template,
edges, state schema) before editing — informed edits, not blind ones.

Within the PR-178 five-handle invariant: a new *target*, no new handle.
"""
from __future__ import annotations

import asyncio
import importlib
import json

import pytest

ADVERTISED = {
    "read_graph",
    "write_graph",
    "run_graph",
    "read_page",
    "write_page",
    "get_status",
}

_BASIC_SPEC = {
    "name": "Inspectable branch",
    "entry_point": "ready",
    "node_defs": [{
        "node_id": "ready",
        "display_name": "Ready",
        "prompt_template": "Do the work.",
        "timeout_seconds": 450.0,
    }],
    "edges": [
        {"from": "START", "to": "ready"},
        {"from": "ready", "to": "END"},
    ],
    "state_schema": [{"name": "x", "type": "str"}],
}


@pytest.fixture
def server_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "founder")
    from workflow import universe_server as us

    importlib.reload(us)
    yield us
    importlib.reload(us)


def test_five_handles_unchanged(server_env):
    us = server_env
    advertised = {t.name for t in asyncio.run(us.mcp.list_tools(run_middleware=True))}
    assert advertised == ADVERTISED


def test_read_graph_branch_routes_to_get_branch(server_env):
    """target=branch reaches the get_branch handler (not unknown_target)."""
    us = server_env
    payload = json.loads(us.read_graph(target="branch", branch_id="no-such-branch"))
    assert payload.get("error") != "unknown_target"
    assert "not found" in payload.get("error", "").lower()


def test_read_graph_branch_in_allowed_targets(server_env):
    us = server_env
    payload = json.loads(us.read_graph(target="bogus"))
    assert payload["error"] == "unknown_target"
    assert "branch" in payload["allowed_targets"]


def test_read_graph_branch_returns_node_configs(server_env):
    """The whole point: reading a branch surfaces editable node configs."""
    us = server_env
    built = json.loads(us.extensions(action="build_branch", spec_json=json.dumps(_BASIC_SPEC)))
    bid = built["branch_def_id"]

    branch = json.loads(us.read_graph(target="branch", branch_id=bid))
    assert "error" not in branch, branch
    node_ids = {n["node_id"] for n in branch.get("node_defs", [])}
    assert "ready" in node_ids
    ready = next(n for n in branch["node_defs"] if n["node_id"] == "ready")
    # The config a founder needs to make an informed timeout edit is visible.
    assert "timeout_seconds" in ready


def test_read_graph_branch_falls_back_to_graph_id(server_env):
    """branch_id omitted -> graph_id is used (lenient, matches target=run)."""
    us = server_env
    built = json.loads(us.extensions(action="build_branch", spec_json=json.dumps(_BASIC_SPEC)))
    bid = built["branch_def_id"]
    branch = json.loads(us.read_graph(target="branch", graph_id=bid))
    assert branch.get("branch_def_id") == bid
