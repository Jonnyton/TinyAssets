"""BUG-080 regression: patch_branch auto-snapshots post-state as a version.

Before this fix, `extensions action=patch_branch` mutated a branch in
place. The branch's `version` field stayed at its old value, no
`branch_version_id` appeared in the response, and there was no
preserved pre-patch version that callers could read or roll back to.

Fix: after a successful patch with at least one op applied, call
`publish_branch_version` on the post-state. The response now includes
`branch_version_id` so callers can fork_from / compare / roll back.

Slice-0 substrate-readiness probe 2026-05-13 motivated this filing —
the mutation-in-place behavior breaks the "fork → compare → keep best"
promise the autoresearch lab itself is built on.
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


def _call(us, action, **kwargs):
    return json.loads(us.extensions(action=action, **kwargs))


def _build(us, *, name: str = "b") -> str:
    spec = {
        "name": name,
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
    res = _call(us, "build_branch", spec_json=json.dumps(spec))
    assert res.get("status") == "built", res
    return res["branch_def_id"]


def _patch_tags(us, bid: str, new_tags: list[str]):
    return _call(
        us, "patch_branch",
        branch_def_id=bid,
        changes_json=json.dumps([{"op": "set_tags", "tags": new_tags}]),
    )


class TestPatchBranchVersioning:

    def test_patch_returns_new_branch_version_id(self, ext_env):
        """Successful patch must include a branch_version_id in the response."""
        us, _base = ext_env
        bid = _build(us)
        res = _patch_tags(us, bid, ["initial", "amended"])
        assert res.get("status") == "patched", res
        version_id = res.get("branch_version_id")
        assert version_id, f"patched response missing branch_version_id: {res}"
        assert "@" in version_id, (
            f"branch_version_id must follow def_id@hash format; got {version_id}"
        )
        assert version_id.startswith(bid + "@"), (
            f"branch_version_id must start with the branch_def_id; got {version_id}"
        )

    def test_two_topology_patches_produce_two_distinct_versions(self, ext_env):
        """Two patches that change branch topology must produce distinct
        version_ids. Content-hash semantics: only topology fields
        (node_defs, edges, conditional_edges, state_schema, entry_point)
        feed the hash — tag/description changes deliberately do NOT
        produce a new version_id because they don't affect runtime
        behavior.
        """
        us, _base = ext_env
        bid = _build(us)

        # First topology mutation: rename the node's display_name.
        res1 = _call(
            us, "patch_branch",
            branch_def_id=bid,
            changes_json=json.dumps([
                {"op": "set_name", "name": "first-amend"},
                {"op": "add_state_field", "name": "y", "type": "str"},
            ]),
        )
        assert res1.get("status") == "patched", res1
        v1 = res1["branch_version_id"]

        # Second topology mutation: add another state field.
        res2 = _call(
            us, "patch_branch",
            branch_def_id=bid,
            changes_json=json.dumps([
                {"op": "add_state_field", "name": "z", "type": "str"},
            ]),
        )
        assert res2.get("status") == "patched", res2
        v2 = res2["branch_version_id"]

        assert v1 != v2, "two topology-changing patches must produce distinct versions"

    def test_noop_patch_does_not_create_a_version(self, ext_env):
        """An empty patch (zero ops) is not a real mutation — no version snapshot."""
        us, _base = ext_env
        bid = _build(us)
        res = _call(
            us, "patch_branch",
            branch_def_id=bid,
            changes_json=json.dumps([]),
        )
        assert res.get("status") == "patched"
        assert res.get("ops_applied") == 0
        assert res.get("branch_version_id") is None, (
            "no-op patch must not create a version snapshot"
        )

    def test_version_round_trip_via_list_branch_versions(self, ext_env):
        """The created version_id must be discoverable via list_branch_versions."""
        from workflow.branch_versions import list_branch_versions

        us, base = ext_env
        bid = _build(us)
        res = _patch_tags(us, bid, ["initial", "amended"])
        v_id = res["branch_version_id"]

        versions = list_branch_versions(base, bid)
        assert any(v.branch_version_id == v_id for v in versions), (
            f"patch-created version_id {v_id} not found in "
            f"list_branch_versions; got {[v.branch_version_id for v in versions]}"
        )

    def test_rejected_patch_does_not_create_a_version(self, ext_env):
        """A patch that fails validation must not leave behind a version."""
        from workflow.branch_versions import list_branch_versions

        us, base = ext_env
        bid = _build(us)
        before = list_branch_versions(base, bid)

        # Submit an unknown op — patch_branch will reject before save.
        res = _call(
            us, "patch_branch",
            branch_def_id=bid,
            changes_json=json.dumps([{"op": "unknown_op_for_test"}]),
        )
        assert res.get("status") == "rejected"

        after = list_branch_versions(base, bid)
        assert len(after) == len(before), (
            "rejected patch must not create a version snapshot"
        )
