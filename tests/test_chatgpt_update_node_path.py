"""BUG-034 — name-based branch_def_id through mutation paths.

ChatGPT sends branch names (not UUIDs) in update_node and patch_branch
calls because the UX shows human-readable names. Guards:
- update_node accepts a branch name as branch_def_id and resolves it.
- patch_branch accepts a branch name as branch_def_id and resolves it.
- update_node with an unknown name returns a clear 'not found' error (not crash).
- update_node with a valid name succeeds end-to-end and persists the update.
- patch_branch with a valid name succeeds end-to-end and persists the patch.
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
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, tool: str, action: str, **kwargs):
    fn = getattr(us, tool)
    return json.loads(fn(action=action, **kwargs))


def _build(us, *, name: str = "test-branch") -> tuple[str, str]:
    """Build a branch and return (branch_def_id, node_id)."""
    spec = {
        "name": name,
        "description": "for name-based ref tests",
        "tags": [],
        "entry_point": "capture",
        "node_defs": [{
            "node_id": "capture",
            "display_name": "Capture Node",
            "prompt_template": "cap: {x}",
        }],
        "edges": [
            {"from": "START", "to": "capture"},
            {"from": "capture", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    res = _call(us, "extensions", "build_branch", spec_json=json.dumps(spec))
    assert res["status"] == "built", res
    return res["branch_def_id"], "capture"


class TestUpdateNodeNameBasedRef:
    """update_node must resolve branch names, not just UUIDs."""

    def test_update_node_by_name_succeeds(self, ext_env):
        """update_node with branch name resolves to correct branch."""
        us, base = ext_env
        bid, nid = _build(us, name="climate-claim-checker")

        res = _call(
            us, "extensions", "update_node",
            branch_def_id="climate-claim-checker",
            node_id=nid,
            display_name="Updated Display Name",
        )

        assert res.get("status") == "updated", res
        assert "error" not in res

    def test_update_node_by_name_persists_change(self, ext_env):
        """Change made via name-based ref is visible when loading by ID."""
        us, base = ext_env
        bid, nid = _build(us, name="my-workflow")

        _call(
            us, "extensions", "update_node",
            branch_def_id="my-workflow",
            node_id=nid,
            display_name="New Display Name",
        )

        from tinyassets.daemon_server import get_branch_definition
        branch = get_branch_definition(base, branch_def_id=bid)
        node = next(n for n in branch["node_defs"] if n["node_id"] == nid)
        assert node["display_name"] == "New Display Name"

    def test_update_node_by_name_case_insensitive(self, ext_env):
        """Name resolution for update_node is case-insensitive."""
        us, base = ext_env
        bid, nid = _build(us, name="Climate TinyAssets")

        res = _call(
            us, "extensions", "update_node",
            branch_def_id="climate workflow",
            node_id=nid,
            description="updated via lowercase name",
        )

        assert res.get("status") == "updated", res

    def test_update_node_unknown_name_returns_error(self, ext_env):
        """update_node with unrecognized name returns a clear error."""
        us, base = ext_env
        _build(us, name="real-workflow")

        res = _call(
            us, "extensions", "update_node",
            branch_def_id="nonexistent-workflow-name",
            node_id="capture",
            display_name="new name",
        )

        assert res.get("status") == "rejected", res
        assert "error" in res

    def test_update_node_by_exact_id_still_works(self, ext_env):
        """Backward compat: update_node still accepts a raw branch_def_id."""
        us, base = ext_env
        bid, nid = _build(us, name="id-test-workflow")

        res = _call(
            us, "extensions", "update_node",
            branch_def_id=bid,
            node_id=nid,
            description="updated via raw ID",
        )

        assert res.get("status") == "updated", res


class TestPatchBranchNameBasedRef:
    """patch_branch must resolve branch names, not just UUIDs."""

    def test_patch_branch_set_name_by_branch_name(self, ext_env):
        """patch_branch accepts human name as branch_def_id for set_name op."""
        us, base = ext_env
        bid, _ = _build(us, name="original-workflow-name")

        res = _call(
            us, "extensions", "patch_branch",
            branch_def_id="original-workflow-name",
            changes_json=json.dumps([{"op": "set_name", "name": "renamed-workflow"}]),
        )

        assert res.get("status") == "patched", res
        assert res.get("name_updated") is True
        assert res.get("new_name") == "renamed-workflow"

    def test_patch_branch_name_resolves_and_persists(self, ext_env):
        """patch_branch via name persists the change visibly by loading via ID."""
        us, base = ext_env
        bid, _ = _build(us, name="persist-test-workflow")

        _call(
            us, "extensions", "patch_branch",
            branch_def_id="persist-test-workflow",
            changes_json=json.dumps([{"op": "set_description", "description": "updated via name"}]),
        )

        from tinyassets.daemon_server import get_branch_definition
        branch = get_branch_definition(base, branch_def_id=bid)
        assert branch["description"] == "updated via name"
