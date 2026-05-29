"""Regression coverage for branch source_code approval.

The run/describe surfaces told hosts to call
``extensions action=approve_source_code`` before running a branch with
source_code nodes, but no such action existed. These tests pin the promised
handler and the approval metadata that lets source edits revoke approval.
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
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host-user")
    from workflow import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, action: str, **kwargs):
    return json.loads(us.extensions(action=action, **kwargs))


def _build_source_branch(us) -> str:
    spec = {
        "name": "code branch",
        "entry_point": "code_node",
        "node_defs": [{
            "node_id": "code_node",
            "display_name": "Code Node",
            "source_code": "def run(state):\n    return {'ok': True}\n",
            "output_keys": ["ok"],
        }],
        "edges": [
            {"from": "START", "to": "code_node"},
            {"from": "code_node", "to": "END"},
        ],
        "state_schema": [{"name": "ok", "type": "bool"}],
    }
    res = _call(us, "build_branch", spec_json=json.dumps(spec))
    assert res["status"] == "built", res
    return res["branch_def_id"]


def _node(base: Path, branch_def_id: str) -> dict:
    from workflow.daemon_server import get_branch_definition

    branch = get_branch_definition(base, branch_def_id=branch_def_id)
    return next(n for n in branch["node_defs"] if n["node_id"] == "code_node")


def test_approve_source_code_marks_branch_node_with_approval_metadata(ext_env):
    us, base = ext_env
    branch_def_id = _build_source_branch(us)

    res = _call(
        us,
        "approve_source_code",
        branch_def_id=branch_def_id,
        node_id="code_node",
        reason="reviewed locally",
    )

    assert res["status"] == "approved"
    assert res["branch_def_id"] == branch_def_id
    assert res["node_id"] == "code_node"
    assert res["approved_by"] == "host-user"
    assert len(res["approved_source_hash"]) == 64
    assert res["approval_warning"] == ""

    node = _node(base, branch_def_id)
    assert node["approved"] is True
    assert node["approved_by"] == "host-user"
    assert node["approved_at"]
    assert node["approved_source_hash"] == res["approved_source_hash"]
    assert node["approval_reason"] == "reviewed locally"


def test_source_code_edit_revokes_approval_metadata(ext_env):
    us, base = ext_env
    branch_def_id = _build_source_branch(us)
    approved = _call(
        us,
        "approve_source_code",
        branch_def_id=branch_def_id,
        node_id="code_node",
    )
    assert approved["status"] == "approved"

    updated = _call(
        us,
        "update_node",
        branch_def_id=branch_def_id,
        node_id="code_node",
        source_code="def run(state):\n    return {'ok': False}\n",
    )

    assert updated["status"] == "updated", updated
    node = _node(base, branch_def_id)
    assert node["approved"] is False
    assert node["approved_by"] == ""
    assert node["approved_at"] == ""
    assert node["approved_source_hash"] == ""
    assert node["approval_reason"] == ""


def test_approve_source_code_requires_extensions_admin_scope_when_auth_enabled():
    from workflow.auth.provider import action_scope_for

    metadata = action_scope_for("extensions", "approve_source_code")
    assert metadata is not None
    assert metadata.oauth_scope == "workflow.extensions.admin"
    assert metadata.effect == "admin"
