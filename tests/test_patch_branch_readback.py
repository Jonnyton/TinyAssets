"""Tests for BUG-030: patch_branch response includes post_patch read-back + patched_fields."""
import json
from unittest.mock import MagicMock, patch


def _make_branch_dict(branch_def_id="b1", name="Old Name", entry_point="n1",
                      node_defs=None, edges=None):
    return {
        "branch_def_id": branch_def_id,
        "name": name,
        "description": "",
        "author": "tester",
        "domain_id": "fantasy",
        "goal_id": "",
        "tags": [],
        "version": 1,
        "parent_def_id": "",
        "fork_from": None,
        "graph_nodes": [],
        "edges": edges or [],
        "conditional_edges": [],
        "entry_point": entry_point,
        "node_defs": node_defs or [],
        "state_schema": [],
        "published": False,
        "visibility": "public",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "stats": {},
        "default_llm_policy": None,
        "concurrency_budget": None,
    }


def _call_patch(branch_before, branch_after, changes_json):
    from tinyassets.api.branches import _ext_branch_patch

    save_mock = MagicMock(return_value=branch_after)

    # BUG-081: patch_branch now author-gates non-author callers. These
    # tests build a branch with author="tester" but don't set
    # UNIVERSE_SERVER_USER — so _current_actor() returns "anonymous"
    # by default and the gate would reject. Mock _current_actor to
    # return the branch's author so the readback-shape assertions are
    # not contaminated by the auth check. Tests covering the auth
    # behavior itself live in test_patch_branch_auth_gate.py.
    with (
        patch("tinyassets.daemon_server.get_branch_definition", return_value=branch_before),
        patch("tinyassets.daemon_server.save_branch_definition", save_mock),
        patch("tinyassets.api.helpers._base_path", return_value="/fake"),
        patch("tinyassets.branches.BranchDefinition.validate", return_value=[]),
        patch(
            "tinyassets.api.engine_helpers._current_actor",
            return_value=branch_before.get("author", "tester"),
        ),
    ):
        result = _ext_branch_patch({
            "branch_def_id": branch_before["branch_def_id"],
            "changes_json": json.dumps(changes_json),
        })
    return json.loads(result)


class TestPatchBranchReadback:
    def test_rename_patch_includes_post_patch_name(self):
        """Rename op → post_patch.name matches new name; patched_fields includes 'name'."""
        before = _make_branch_dict(name="Old Name")
        after = dict(before, name="New Name", updated_at="2026-01-02T00:00:00")

        result = _call_patch(
            before, after,
            [{"op": "set_name", "name": "New Name"}],
        )

        assert result["status"] == "patched"
        assert result["post_patch"]["name"] == "New Name"
        assert "name" in result["patched_fields"]

    def test_multi_field_patch_lists_all_changed_fields(self):
        """Two changed fields → patched_fields lists both."""
        before = _make_branch_dict(name="Alpha", entry_point="n1")
        after = dict(
            before,
            name="Beta",
            entry_point="n2",
            updated_at="2026-01-02T00:00:00",
        )

        result = _call_patch(
            before, after,
            [{"op": "set_name", "name": "Beta"}, {"op": "set_entry_point", "node_id": "n2"}],
        )

        assert result["status"] == "patched"
        assert set(result["patched_fields"]) >= {"name", "entry_point"}
        assert result["post_patch"]["name"] == "Beta"
        assert result["post_patch"]["entry_point"] == "n2"

    def test_noop_patch_patched_fields_empty(self):
        """Patch that changes nothing (same values) → patched_fields is empty."""
        before = _make_branch_dict(name="Same Name")
        after = dict(before, updated_at="2026-01-02T00:00:00")

        result = _call_patch(
            before, after,
            [{"op": "set_name", "name": "Same Name"}],
        )

        assert result["status"] == "patched"
        assert result["patched_fields"] == []

    def test_post_patch_contains_required_fields(self):
        """post_patch always includes branch_def_id, name, entry_point, node_count, edge_count."""
        before = _make_branch_dict(branch_def_id="b42", name="My Branch", entry_point="start")
        after = dict(before, name="Renamed", updated_at="2026-01-02T00:00:00")

        result = _call_patch(
            before, after,
            [{"op": "set_name", "name": "Renamed"}],
        )

        pp = result["post_patch"]
        assert pp["branch_def_id"] == "b42"
        assert pp["name"] == "Renamed"
        assert pp["entry_point"] == "start"
        assert "node_count" in pp
        assert "edge_count" in pp

    def test_updated_at_not_in_patched_fields(self):
        """updated_at is excluded from patched_fields even though it always changes."""
        before = _make_branch_dict(name="Branch")
        after = dict(before, updated_at="2026-12-31T23:59:59")

        result = _call_patch(
            before, after,
            [{"op": "set_name", "name": "Branch"}],
        )

        assert "updated_at" not in result["patched_fields"]
