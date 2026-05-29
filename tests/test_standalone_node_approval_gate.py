"""Regression coverage for standalone node approval identity gates."""

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
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "registrant")
    from workflow import universe_server as us

    importlib.reload(us)
    yield us, base, monkeypatch
    importlib.reload(us)


def _call(us, action: str, **kwargs):
    return json.loads(us.extensions(action=action, **kwargs))


def _register_node(us, node_id: str = "code_node") -> dict:
    return _call(
        us,
        "register",
        node_id=node_id,
        display_name="Code Node",
        description="User contributed code",
        phase="custom",
        input_keys="",
        output_keys="ok",
        source_code="def run(state): return {'ok': True}\n",
        dependencies="",
    )


def test_standalone_node_registrant_cannot_self_approve(ext_env):
    us, _base, _monkeypatch = ext_env
    registered = _register_node(us)
    assert registered["status"] == "registered"

    rejected = _call(us, "approve", node_id="code_node")

    assert rejected["status"] == "rejected"
    assert rejected["error"] == "node_approval_requires_distinct_actor"
    inspected = _call(us, "inspect", node_id="code_node")
    assert inspected["approved"] is False
    assert inspected.get("approved_by", "") == ""


def test_standalone_node_distinct_actor_approval_records_metadata(ext_env):
    us, _base, monkeypatch = ext_env
    _register_node(us)

    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host-operator")
    approved = _call(us, "approve", node_id="code_node")

    assert approved["status"] == "approved"
    assert approved["approved"] is True
    assert approved["approved_by"] == "host-operator"
    assert len(approved["approved_source_hash"]) == 64

    inspected = _call(us, "inspect", node_id="code_node")
    assert inspected["approved"] is True
    assert inspected["approved_by"] == "host-operator"
    assert inspected["approved_at"]
    assert inspected["approved_source_hash"] == approved["approved_source_hash"]


def test_standalone_node_approve_requires_extensions_admin_scope_when_auth_enabled():
    from workflow.auth.provider import action_scope_for

    metadata = action_scope_for("extensions", "approve")
    assert metadata is not None
    assert metadata.oauth_scope == "workflow.extensions.admin"
    assert metadata.effect == "admin"
