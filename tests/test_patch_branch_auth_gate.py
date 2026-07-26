"""Regression tests for authenticated ``patch_branch`` authority.

Authority comes from the authenticated request subject. A non-author receives
the same generic denial with or without ``force=true``; force is conflict
recovery for an authorized author, never an authority bypass.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Callable

import pytest


@pytest.fixture
def ext_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authenticate_request: Callable[[str | None], None],
):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "environment-only")
    authenticate_request("alice")
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us, base, authenticate_request
    importlib.reload(us)


def _call(us, tool: str, action: str, **kwargs):
    fn = getattr(us, tool)
    return json.loads(fn(action=action, **kwargs))


def _build_as_alice(us) -> str:
    spec = {
        "name": "alice-branch",
        "tags": ["initial"],
        "entry_point": "capture",
        "node_defs": [{
            "node_id": "capture",
            "display_name": "Capture",
            "prompt_template": "cap: {x}",
        }],
        "edges": [
            {"from": "START", "to": "capture"},
            {"from": "capture", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    result = _call(us, "extensions", "build_branch", spec_json=json.dumps(spec))
    assert result["status"] == "built", result
    return result["branch_def_id"]


def _patch_tags(us, branch_def_id: str, *, force: bool = False):
    return _call(
        us,
        "extensions",
        "patch_branch",
        branch_def_id=branch_def_id,
        changes_json=json.dumps([{"op": "set_tags", "tags": ["amended"]}]),
        force=force,
    )


class TestPatchBranchAuthGate:
    def test_author_can_patch_own_branch(self, ext_env):
        us, _base, _authenticate = ext_env
        branch_def_id = _build_as_alice(us)
        result = _patch_tags(us, branch_def_id)
        assert result["status"] == "patched", result
        assert result["patched_fields"] == ["tags"]

    def test_non_author_is_rejected(self, ext_env):
        us, _base, authenticate = ext_env
        branch_def_id = _build_as_alice(us)

        authenticate("bob")
        result = _patch_tags(us, branch_def_id)
        assert result == {"error": "Authenticated branch author required."}

    def test_non_author_cannot_force_through(self, ext_env):
        us, _base, authenticate = ext_env
        branch_def_id = _build_as_alice(us)

        authenticate("bob")
        result = _patch_tags(us, branch_def_id, force=True)
        assert result == {"error": "Authenticated branch author required."}

    def test_anonymous_cannot_create_branch(self, ext_env):
        us, _base, authenticate = ext_env
        authenticate(None)
        spec = {
            "name": "anonymous-branch",
            "entry_point": "capture",
            "node_defs": [{"node_id": "capture", "prompt_template": "capture"}],
            "edges": [],
            "state_schema": [],
        }
        result = _call(
            us,
            "extensions",
            "build_branch",
            spec_json=json.dumps(spec),
        )
        assert result["error"] == "Authentication required"
        assert result["auth_scope_required"] is True

    def test_anonymous_caller_against_authored_branch_is_rejected(self, ext_env):
        us, _base, authenticate = ext_env
        branch_def_id = _build_as_alice(us)

        authenticate(None)
        result = _patch_tags(us, branch_def_id)
        assert result["error"] == "Authentication required"
        assert result["auth_scope_required"] is True
