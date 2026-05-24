"""Tests for BUG-031: describe/validate/get_branch surface unapproved source_code nodes."""
import json
from unittest.mock import patch  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(node_id="n1", display_name="My Node", source_code="", approved=False):
    return {
        "node_id": node_id,
        "display_name": display_name,
        "source_code": source_code,
        "approved": approved,
        "phase": "custom",
        "input_keys": [],
        "output_keys": [],
        "description": "",
        "dependencies": [],
        "author": "anon",
        "registered_at": "",
        "enabled": True,
    }


def _make_branch_dict(node_defs=None, branch_def_id="b1", name="TestBranch"):
    nodes = node_defs or []
    entry_point = nodes[0]["node_id"] if nodes else ""
    return {
        "branch_def_id": branch_def_id,
        "name": name,
        "author": "tester",
        "domain_id": "fantasy",
        "entry_point": entry_point,
        "node_defs": nodes,
        "edges": [],
        "state_schema": [],
        "visibility": "public",
        "fork_from": None,
    }


def _call_validate_real(branch_dict):
    from workflow.api.branches import _ext_branch_validate

    with (
        patch("workflow.daemon_server.get_branch_definition", return_value=branch_dict),
        patch("workflow.api.helpers._base_path", return_value="/fake"),
        patch(
            "workflow.providers.base.get_sandbox_status",
            return_value={"bwrap_available": True},
        ),
    ):
        result = _ext_branch_validate({"branch_def_id": branch_dict["branch_def_id"]})
    return json.loads(result)


def _call_describe(branch_dict, validate_errors=None):
    from workflow.api.branches import _ext_branch_describe

    if validate_errors is None:
        validate_errors = []

    with (
        patch("workflow.daemon_server.get_branch_definition", return_value=branch_dict),
        patch("workflow.api.helpers._base_path", return_value="/fake"),
        patch(
            "workflow.api.branches._related_wiki_pages",
            return_value={"items": [], "truncated_count": 0},
        ),
        patch("workflow.branch_versions.list_branch_versions", return_value=[]),
        patch("workflow.daemon_server.list_branch_definitions", return_value=[]),
        patch("workflow.branches.BranchDefinition.validate", return_value=validate_errors),
    ):
        result = _ext_branch_describe({"branch_def_id": branch_dict["branch_def_id"]})
    return json.loads(result)


def _call_get(branch_dict):
    from workflow.api.branches import _ext_branch_get

    with (
        patch("workflow.daemon_server.get_branch_definition", return_value=branch_dict),
        patch("workflow.api.helpers._base_path", return_value="/fake"),
        patch("workflow.api.engine_helpers._current_actor", return_value="tester"),
        patch("workflow.api.engine_helpers._current_actor", return_value="tester"),
        patch("workflow.api.market._gates_enabled", return_value=False),
        patch(
            "workflow.api.branches._related_wiki_pages",
            return_value={"items": [], "truncated_count": 0},
        ),
        patch("workflow.daemon_server.list_gate_claims", return_value=[]),
    ):
        result = _ext_branch_get({"branch_def_id": branch_dict["branch_def_id"]})
    return json.loads(result)


def _call_validate(branch_dict, validate_errors=None):
    from workflow.api.branches import _ext_branch_validate

    if validate_errors is None:
        validate_errors = []

    with (
        patch("workflow.daemon_server.get_branch_definition", return_value=branch_dict),
        patch("workflow.api.helpers._base_path", return_value="/fake"),
        patch("workflow.branches.BranchDefinition.validate", return_value=validate_errors),
        patch(
            "workflow.providers.base.get_sandbox_status",
            return_value={"bwrap_available": True},
        ),
    ):
        result = _ext_branch_validate({"branch_def_id": branch_dict["branch_def_id"]})
    return json.loads(result)


# ---------------------------------------------------------------------------
# describe_branch tests
# ---------------------------------------------------------------------------

class TestDescribeBranchApproval:
    def test_no_source_code_nodes_runnable(self):
        """Branch with no source_code nodes is runnable with no approval warnings."""
        node = _make_node(source_code="", approved=False)
        branch = _make_branch_dict(node_defs=[node])
        result = _call_describe(branch)

        assert result["runnable"] is True
        assert result["unapproved_source_code_nodes"] == []
        assert "APPROVAL REQUIRED" not in result["summary"]

    def test_approved_source_code_node_runnable(self):
        """Branch with an approved source_code node is runnable."""
        node = _make_node(source_code="def run(state): return state", approved=True)
        branch = _make_branch_dict(node_defs=[node])
        result = _call_describe(branch)

        assert result["runnable"] is True
        assert result["unapproved_source_code_nodes"] == []

    def test_unapproved_source_code_node_not_runnable(self):
        """Branch with an unapproved source_code node is NOT runnable; warning surfaces."""
        node = _make_node(
            node_id="sc1",
            display_name="Custom Runner",
            source_code="def run(state): return state",
            approved=False,
        )
        branch = _make_branch_dict(node_defs=[node])
        result = _call_describe(branch)

        assert result["runnable"] is False
        assert len(result["unapproved_source_code_nodes"]) == 1
        unapp = result["unapproved_source_code_nodes"][0]
        assert unapp["node_id"] == "sc1"
        assert unapp["display_name"] == "Custom Runner"
        assert "APPROVAL REQUIRED" in result["summary"]
        assert "approve_source_code" in result["summary"]
        assert "must be approved before it can run" in result["summary"]
        assert "once validated" not in result["summary"]

    def test_unapproved_node_still_valid_structurally(self):
        """valid reflects structural errors only; approval is separate via runnable."""
        node = _make_node(source_code="code", approved=False)
        branch = _make_branch_dict(node_defs=[node])
        result = _call_describe(branch)

        # No structural errors — valid should be True
        assert result["valid"] is True
        # But not runnable due to approval gate
        assert result["runnable"] is False

    def test_multiple_unapproved_nodes_all_listed(self):
        """All unapproved source_code nodes appear in the list."""
        nodes = [
            _make_node(node_id="n1", display_name="Node A", source_code="code", approved=False),
            _make_node(node_id="n2", display_name="Node B", source_code="code", approved=True),
            _make_node(node_id="n3", display_name="Node C", source_code="code", approved=False),
        ]
        branch = _make_branch_dict(node_defs=nodes)
        result = _call_describe(branch)

        assert result["runnable"] is False
        ids = {n["node_id"] for n in result["unapproved_source_code_nodes"]}
        assert ids == {"n1", "n3"}
        assert "n2" not in str(result["unapproved_source_code_nodes"])


# ---------------------------------------------------------------------------
# get_branch tests
# ---------------------------------------------------------------------------

class TestGetBranchApproval:
    def test_no_source_code_nodes_runnable(self):
        """get_branch: no source_code nodes → runnable True, list empty."""
        node = _make_node(source_code="", approved=False)
        branch = _make_branch_dict(node_defs=[node])
        result = _call_get(branch)

        assert result["runnable"] is True
        assert result["unapproved_source_code_nodes"] == []

    def test_unapproved_source_code_node_not_runnable(self):
        """get_branch: unapproved source_code node → runnable False, node listed."""
        node = _make_node(
            node_id="sc1",
            display_name="Script Node",
            source_code="def run(state): ...",
            approved=False,
        )
        branch = _make_branch_dict(node_defs=[node])
        result = _call_get(branch)

        assert result["runnable"] is False
        assert len(result["unapproved_source_code_nodes"]) == 1
        assert result["unapproved_source_code_nodes"][0]["node_id"] == "sc1"


# ---------------------------------------------------------------------------
# validate_branch tests (BUG-031: was missing runnable + unapproved fields)
# ---------------------------------------------------------------------------

class TestValidateBranchApproval:
    def test_no_source_code_nodes_runnable(self):
        """validate_branch: no source_code nodes → runnable True, list empty."""
        node = _make_node(source_code="", approved=False)
        branch = _make_branch_dict(node_defs=[node])
        result = _call_validate(branch)

        assert result["valid"] is True
        assert result["runnable"] is True
        assert result["unapproved_source_code_nodes"] == []

    def test_unapproved_source_code_node_not_runnable(self):
        """validate_branch: unapproved source_code node → runnable False, node listed."""
        node = _make_node(
            node_id="sc1",
            display_name="Custom Script",
            source_code="def run(state): return state",
            approved=False,
        )
        branch = _make_branch_dict(node_defs=[node])
        result = _call_validate(branch)

        assert result["valid"] is True
        assert result["runnable"] is False
        assert len(result["unapproved_source_code_nodes"]) == 1
        assert result["unapproved_source_code_nodes"][0]["node_id"] == "sc1"
        assert result["unapproved_source_code_nodes"][0]["display_name"] == "Custom Script"

    def test_approved_source_code_node_runnable(self):
        """validate_branch: approved source_code node → runnable True."""
        node = _make_node(source_code="def run(state): ...", approved=True)
        branch = _make_branch_dict(node_defs=[node])
        result = _call_validate(branch)

        assert result["valid"] is True
        assert result["runnable"] is True
        assert result["unapproved_source_code_nodes"] == []

    def test_structural_errors_make_not_runnable(self):
        """validate_branch: structural validation errors → valid False, runnable False."""
        node = _make_node(source_code="", approved=False)
        branch = _make_branch_dict(node_defs=[node])
        result = _call_validate(branch, validate_errors=["entry_point is required"])

        assert result["valid"] is False
        assert result["runnable"] is False

    def test_unapproved_and_structural_errors(self):
        """validate_branch: both structural errors and unapproved node → both flagged."""
        node = _make_node(
            node_id="sc1", source_code="code", approved=False,
        )
        branch = _make_branch_dict(node_defs=[node])
        result = _call_validate(branch, validate_errors=["entry_point is required"])

        assert result["valid"] is False
        assert result["runnable"] is False
        assert len(result["unapproved_source_code_nodes"]) == 1

    def test_multiple_unapproved_nodes_all_listed(self):
        """validate_branch: multiple unapproved nodes all appear in list."""
        nodes = [
            _make_node(node_id="n1", source_code="code", approved=False),
            _make_node(node_id="n2", source_code="code", approved=True),
            _make_node(node_id="n3", source_code="code", approved=False),
        ]
        branch = _make_branch_dict(node_defs=nodes)
        result = _call_validate(branch)

        ids = {n["node_id"] for n in result["unapproved_source_code_nodes"]}
        assert ids == {"n1", "n3"}
        assert result["runnable"] is False

    def test_state_field_node_id_collision_not_valid_or_runnable(self):
        node = _make_node(node_id="status", display_name="Status")
        branch = _make_branch_dict(node_defs=[node])
        branch["graph_nodes"] = [{
            "id": "status",
            "node_def_id": "status",
            "position": 0,
        }]
        branch["edges"] = [
            {"from": "START", "to": "status"},
            {"from": "status", "to": "END"},
        ]
        branch["state_schema"] = [{"name": "status", "type": "str"}]

        result = _call_validate_real(branch)

        assert result["valid"] is False
        assert result["runnable"] is False
        assert any(
            "State field name 'status' collides with a graph node ID" in error
            for error in result["errors"]
        )
