"""Tests for BUG-034: branch_def_id params accept branch names for chatbot UX."""
import json
from unittest.mock import patch

from tinyassets.api.branches import _resolve_branch_id

_BRANCH_A = {
    "branch_def_id": "uuid-abc-123",
    "name": "Town Climate Claim Checker",
    "author": "user",
    "visibility": "public",
}
_BRANCH_B = {
    "branch_def_id": "uuid-def-456",
    "name": "Fantasy Story Builder",
    "author": "user",
    "visibility": "public",
}


def _patch_lookup(exists_ids=("uuid-abc-123",), all_branches=(_BRANCH_A, _BRANCH_B)):
    def get_branch_def(base, branch_def_id):
        if branch_def_id in exists_ids:
            return {"branch_def_id": branch_def_id, "name": "X"}
        raise KeyError(branch_def_id)

    return (
        patch("tinyassets.daemon_server.get_branch_definition", side_effect=get_branch_def),
        patch("tinyassets.daemon_server.list_branch_definitions", return_value=list(all_branches)),
        patch("tinyassets.api.engine_helpers._current_actor", return_value="user"),
        patch("tinyassets.api.engine_helpers._current_actor", return_value="user"),
    )


class TestResolveBranchId:
    def test_exact_id_returned_unchanged(self):
        """If the input IS a valid branch_def_id, return it directly."""
        p1, p2, p3, p4 = _patch_lookup()
        with p1, p2, p3, p4:
            result = _resolve_branch_id("uuid-abc-123", "/fake")
        assert result == "uuid-abc-123"

    def test_name_resolved_to_id(self):
        """Case-insensitive name match returns the branch_def_id."""
        p1, p2, p3, p4 = _patch_lookup(exists_ids=())
        with p1, p2, p3, p4:
            result = _resolve_branch_id("Town Climate Claim Checker", "/fake")
        assert result == "uuid-abc-123"

    def test_name_resolution_case_insensitive(self):
        """Name lookup is case-insensitive."""
        p1, p2, p3, p4 = _patch_lookup(exists_ids=())
        with p1, p2, p3, p4:
            result = _resolve_branch_id("town climate claim checker", "/fake")
        assert result == "uuid-abc-123"

    def test_unknown_input_returned_unchanged(self):
        """If no ID or name match, original string returned (KeyError will fire downstream)."""
        p1, p2, p3, p4 = _patch_lookup(exists_ids=())
        with p1, p2, p3, p4:
            result = _resolve_branch_id("nonexistent-branch", "/fake")
        assert result == "nonexistent-branch"

    def test_empty_string_returned_unchanged(self):
        """Empty input is returned unchanged (required-check fires in caller)."""
        p1, p2, p3, p4 = _patch_lookup()
        with p1, p2, p3, p4:
            result = _resolve_branch_id("", "/fake")
        assert result == ""

    def test_second_branch_resolved_by_name(self):
        """Name resolution works for any branch, not just the first."""
        p1, p2, p3, p4 = _patch_lookup(exists_ids=())
        with p1, p2, p3, p4:
            result = _resolve_branch_id("Fantasy Story Builder", "/fake")
        assert result == "uuid-def-456"


class TestDescribeBranchAcceptsName:
    """Integration: _ext_branch_describe resolves branch name to ID."""

    def test_describe_by_name_succeeds(self):
        branch_dict = dict(_BRANCH_A, node_defs=[], edges=[], state_schema=[],
                           entry_point="", domain_id="fantasy", goal_id="",
                           description="", tags=[], version=1, parent_def_id="",
                           fork_from=None, graph_nodes=[], conditional_edges=[],
                           published=False, created_at="", updated_at="",
                           stats={}, default_llm_policy=None, concurrency_budget=None)

        def get_def(base, branch_def_id):
            if branch_def_id == "uuid-abc-123":
                return branch_dict
            raise KeyError(branch_def_id)

        from tinyassets.api.branches import _ext_branch_describe

        with (
            patch("tinyassets.daemon_server.get_branch_definition", side_effect=get_def),
            patch("tinyassets.daemon_server.list_branch_definitions", return_value=[_BRANCH_A]),
            patch("tinyassets.api.engine_helpers._current_actor", return_value="user"),
            patch("tinyassets.api.engine_helpers._current_actor", return_value="user"),
            patch("tinyassets.api.helpers._base_path", return_value="/fake"),
            patch("tinyassets.api.branches._related_wiki_pages",
                  return_value={"items": [], "truncated_count": 0}),
            patch("tinyassets.branch_versions.list_branch_versions", return_value=[]),
            patch("tinyassets.daemon_server.list_branch_definitions", return_value=[_BRANCH_A]),
            patch("tinyassets.branches.BranchDefinition.validate", return_value=[]),
        ):
            result = json.loads(_ext_branch_describe(
                {"branch_def_id": "Town Climate Claim Checker"}
            ))

        assert "error" not in result
        assert result["branch_def_id"] == "uuid-abc-123"
