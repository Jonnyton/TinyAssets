"""Tests for build_branch / patch_branch / add_node / connect_nodes /
set_entry_point / add_state_field SUMMARY-by-default response shapes (task #35).

Verifies:
- Default response is SUMMARY shape (<5KB) without 'branch' field.
- verbose=true response includes full 'branch' post-state.
- BUG-030 patch_branch readback invariant still satisfied in SUMMARY mode.
- patched_fields always present in patch_branch response.
- add_node / connect_nodes / set_entry_point / add_state_field: uniform verbose contract.
"""
import json
from unittest.mock import MagicMock, patch


def _make_node(node_id="n1", display_name="node_1"):
    return {
        "node_id": node_id,
        "display_name": display_name,
        "phase": "draft",
        "description": "A test node.",
        "prompt_template": "Process {input} and return JSON.",
        "input_keys": ["input"],
        "output_keys": ["output"],
        "model": "claude-opus-4-6",
        "temperature": 0.3,
        "source_code": None,
        "few_shot_references": [],
        "tags": [],
        "soul_policy": "inherit",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "stats": {},
    }


def _make_branch_dict(branch_def_id="b1", name="test-branch", entry_point="n1",
                      node_defs=None, edges=None):
    return {
        "branch_def_id": branch_def_id,
        "name": name,
        "description": "A test branch.",
        "author": "tester",
        "domain_id": "test",
        "goal_id": "",
        "tags": [],
        "version": 1,
        "parent_def_id": "",
        "fork_from": None,
        "graph_nodes": [],
        "edges": edges or [],
        "conditional_edges": [],
        "entry_point": entry_point,
        "node_defs": node_defs or [_make_node()],
        "state_schema": [],
        "published": False,
        "visibility": "private",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "stats": {},
        "default_llm_policy": None,
        "concurrency_budget": None,
    }


def _call_build(spec_dict, verbose=None):
    from tinyassets.api.branches import _ext_branch_build

    saved = _make_branch_dict(
        branch_def_id="b_built",
        name=spec_dict.get("name", "built-branch"),
        entry_point=spec_dict.get("entry_point", "n1"),
        node_defs=spec_dict.get("node_defs", [_make_node()]),
    )
    save_mock = MagicMock(return_value=saved)

    kwargs = {"spec_json": json.dumps(spec_dict)}
    if verbose is not None:
        kwargs["verbose"] = str(verbose).lower()

    with (
        patch("tinyassets.daemon_server.save_branch_definition", save_mock),
        patch("tinyassets.api.helpers._base_path", return_value="/fake"),
        patch("tinyassets.branches.BranchDefinition.validate", return_value=[]),
    ):
        result = _ext_branch_build(kwargs)
    return json.loads(result)


def _call_patch(branch_before, branch_after, changes_json, verbose=None):
    from tinyassets.api.branches import _ext_branch_patch

    save_mock = MagicMock(return_value=branch_after)

    kwargs = {
        "branch_def_id": branch_before["branch_def_id"],
        "changes_json": json.dumps(changes_json),
    }
    if verbose is not None:
        kwargs["verbose"] = str(verbose).lower()

    # BUG-081: patch_branch author-gates non-author callers. These tests
    # don't set UNIVERSE_SERVER_USER, so _current_actor() returns
    # "anonymous" and the gate would reject mutations against a branch
    # authored by "tester". Mock _current_actor to match the branch's
    # author so the response-shape assertions aren't contaminated by the
    # auth check. Auth-gate semantics are covered in
    # test_patch_branch_auth_gate.py.
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
        result = _ext_branch_patch(kwargs)
    return json.loads(result)


# ── build_branch ─────────────────────────────────────────────────────────────

class TestBuildBranchSummaryDefault:
    def _spec(self, name="test-branch"):
        return {
            "name": name,
            "entry_point": "n1",
            "node_defs": [
                {"node_id": "n1", "display_name": "n1", "phase": "draft",
                 "prompt_template": "do {x}", "input_keys": ["x"], "output_keys": ["y"]},
            ],
        }

    def test_default_has_summary_fields(self):
        result = _call_build(self._spec())
        assert result["status"] == "built"
        assert "branch_def_id" in result
        assert "name" in result
        assert "node_count" in result
        assert "edge_count" in result
        assert "entry_point" in result
        assert "validation_summary" in result

    def test_default_excludes_branch_field(self):
        result = _call_build(self._spec())
        assert "branch" not in result

    def test_default_response_under_5kb(self):
        result = _call_build(self._spec())
        raw = json.dumps(result)
        assert len(raw) < 5_000, f"SUMMARY response is {len(raw)} bytes, expected < 5000"

    def test_verbose_true_includes_branch(self):
        result = _call_build(self._spec(), verbose=True)
        assert result["status"] == "built"
        assert "branch" in result
        assert isinstance(result["branch"], dict)

    def test_verbose_false_same_as_default(self):
        result = _call_build(self._spec(), verbose=False)
        assert "branch" not in result

    def test_verbose_string_true_includes_branch(self):
        from tinyassets.api.branches import _ext_branch_build
        spec = self._spec()
        saved = _make_branch_dict(name=spec["name"])
        save_mock = MagicMock(return_value=saved)
        with (
            patch("tinyassets.daemon_server.save_branch_definition", save_mock),
            patch("tinyassets.api.helpers._base_path", return_value="/fake"),
            patch("tinyassets.branches.BranchDefinition.validate", return_value=[]),
        ):
            result = json.loads(_ext_branch_build(
                {"spec_json": json.dumps(spec), "verbose": "true"}
            ))
        assert "branch" in result

    def test_summary_has_text_field(self):
        result = _call_build(self._spec())
        assert "text" in result
        assert "Built branch" in result["text"]

    def test_validation_summary_is_ok_on_success(self):
        result = _call_build(self._spec())
        assert result["validation_summary"] == "ok"


# ── patch_branch ──────────────────────────────────────────────────────────────

class TestPatchBranchSummaryDefault:
    def _before_after(self, new_name="New Name"):
        before = _make_branch_dict(name="Old Name")
        after = dict(before, name=new_name, updated_at="2026-01-02T00:00:00")
        return before, after

    def test_default_excludes_branch_field(self):
        before, after = self._before_after()
        result = _call_patch(before, after, [{"op": "set_name", "name": "New Name"}])
        assert result["status"] == "patched"
        assert "branch" not in result

    def test_default_includes_patched_fields(self):
        before, after = self._before_after()
        result = _call_patch(before, after, [{"op": "set_name", "name": "New Name"}])
        assert "patched_fields" in result
        assert "name" in result["patched_fields"]

    def test_default_includes_post_patch(self):
        """BUG-030 invariant: post_patch always present in SUMMARY mode."""
        before, after = self._before_after()
        result = _call_patch(before, after, [{"op": "set_name", "name": "New Name"}])
        assert "post_patch" in result
        pp = result["post_patch"]
        assert pp["branch_def_id"] == before["branch_def_id"]
        assert pp["name"] == "New Name"
        assert "entry_point" in pp
        assert "node_count" in pp
        assert "edge_count" in pp

    def test_default_response_under_5kb(self):
        before = _make_branch_dict(
            node_defs=[_make_node(f"n{i}", f"node_{i}") for i in range(3)],
        )
        after = dict(before, name="Patched", updated_at="2026-01-02T00:00:00")
        result = _call_patch(before, after, [{"op": "set_name", "name": "Patched"}])
        raw = json.dumps(result)
        assert len(raw) < 5_000, f"SUMMARY response is {len(raw)} bytes, expected < 5000"

    def test_verbose_true_includes_branch(self):
        before, after = self._before_after()
        result = _call_patch(
            before, after,
            [{"op": "set_name", "name": "New Name"}],
            verbose=True,
        )
        assert result["status"] == "patched"
        assert "branch" in result
        assert isinstance(result["branch"], dict)

    def test_verbose_false_excludes_branch(self):
        before, after = self._before_after()
        result = _call_patch(
            before, after,
            [{"op": "set_name", "name": "New Name"}],
            verbose=False,
        )
        assert "branch" not in result

    def test_bug030_post_patch_branch_def_id_always_present(self):
        """post_patch.branch_def_id is always present (BUG-030 core invariant)."""
        before = _make_branch_dict(branch_def_id="b_target")
        after = dict(before, name="Renamed", updated_at="2026-01-02T00:00:00")
        result = _call_patch(before, after, [{"op": "set_name", "name": "Renamed"}])
        assert result["post_patch"]["branch_def_id"] == "b_target"

    def test_noop_patch_patched_fields_empty(self):
        before = _make_branch_dict(name="Same")
        after = dict(before, updated_at="2026-01-02T00:00:00")
        result = _call_patch(before, after, [{"op": "set_name", "name": "Same"}])
        assert result["patched_fields"] == []


# ── add_node ──────────────────────────────────────────────────────────────────

def _call_add_node(branch_dict, node_kwargs, verbose=None):
    from tinyassets.api.branches import _ext_branch_add_node

    branch_mock = MagicMock()
    node_mock = MagicMock()
    node_mock.node_id = node_kwargs.get("node_id", "n_new")
    node_mock.to_dict.return_value = {"node_id": node_mock.node_id, "display_name": "new"}
    branch_mock.node_defs = [node_mock]

    kwargs = {"branch_def_id": branch_dict["branch_def_id"], **node_kwargs}
    if verbose is not None:
        kwargs["verbose"] = str(verbose).lower()

    with (
        patch("tinyassets.daemon_server.get_branch_definition", return_value=branch_dict),
        patch("tinyassets.branches.BranchDefinition.from_dict", return_value=branch_mock),
        patch("tinyassets.api.branches._apply_node_spec", return_value=""),
        patch("tinyassets.api.engine_helpers._storage_backend") as sb_mock,
        patch("tinyassets.api.engine_helpers._storage_backend", new=sb_mock),
        patch("tinyassets.api.engine_helpers._current_actor", return_value="tester"),
        patch("tinyassets.api.engine_helpers._current_actor", return_value="tester"),
        patch("tinyassets.identity.git_author", return_value="tester <t@t>"),
    ):
        sb_mock.return_value.save_branch_and_commit = MagicMock()
        result = _ext_branch_add_node(kwargs)
    return json.loads(result)


class TestAddNodeSummaryDefault:
    def _branch(self):
        return _make_branch_dict(branch_def_id="b_add")

    def test_default_includes_branch_def_id_and_node_id(self):
        result = _call_add_node(self._branch(), {"node_id": "n_new", "display_name": "new"})
        assert result["status"] == "added"
        assert result["branch_def_id"] == "b_add"
        assert result["node_id"] == "n_new"

    def test_default_excludes_node_def(self):
        result = _call_add_node(self._branch(), {"node_id": "n_new", "display_name": "new"})
        assert "node_def" not in result

    def test_verbose_true_includes_node_def(self):
        result = _call_add_node(
            self._branch(),
            {"node_id": "n_new", "display_name": "new"},
            verbose=True,
        )
        assert result["status"] == "added"
        assert "node_def" in result

    def test_default_response_under_500_bytes(self):
        result = _call_add_node(self._branch(), {"node_id": "n_new", "display_name": "new"})
        assert len(json.dumps(result)) < 500


# ── connect_nodes ─────────────────────────────────────────────────────────────

def _call_connect_nodes(branch_dict, from_node, to_node, verbose=None):
    from tinyassets.api.branches import _ext_branch_connect_nodes

    branch_mock = MagicMock()
    branch_mock.edges = []

    kwargs = {
        "branch_def_id": branch_dict["branch_def_id"],
        "from_node": from_node,
        "to_node": to_node,
    }
    if verbose is not None:
        kwargs["verbose"] = str(verbose).lower()

    with (
        patch("tinyassets.daemon_server.get_branch_definition", return_value=branch_dict),
        patch("tinyassets.branches.BranchDefinition.from_dict", return_value=branch_mock),
        patch("tinyassets.branches.EdgeDefinition", return_value=MagicMock()),
        patch("tinyassets.api.engine_helpers._storage_backend") as sb_mock,
        patch("tinyassets.api.engine_helpers._storage_backend", new=sb_mock),
        patch("tinyassets.identity.git_author", return_value="tester <t@t>"),
    ):
        sb_mock.return_value.save_branch_and_commit = MagicMock()
        result = _ext_branch_connect_nodes(kwargs)
    return json.loads(result)


class TestConnectNodesSummaryDefault:
    def test_default_shape(self):
        branch = _make_branch_dict(branch_def_id="b_conn")
        result = _call_connect_nodes(branch, "n1", "n2")
        assert result["status"] == "connected"
        assert result["branch_def_id"] == "b_conn"
        assert result["from_node"] == "n1"
        assert result["to_node"] == "n2"
        assert "edge_count" not in result

    def test_verbose_includes_edge_count(self):
        branch = _make_branch_dict(branch_def_id="b_conn")
        result = _call_connect_nodes(branch, "n1", "n2", verbose=True)
        assert "edge_count" in result

    def test_default_under_300_bytes(self):
        branch = _make_branch_dict(branch_def_id="b_conn")
        result = _call_connect_nodes(branch, "n1", "n2")
        assert len(json.dumps(result)) < 300


# ── set_entry_point ───────────────────────────────────────────────────────────

def _call_set_entry_point(branch_dict, node_id, verbose=None):
    from tinyassets.api.branches import _ext_branch_set_entry_point

    branch_mock = MagicMock()
    branch_mock.node_defs = []

    kwargs = {"branch_def_id": branch_dict["branch_def_id"], "node_id": node_id}
    if verbose is not None:
        kwargs["verbose"] = str(verbose).lower()

    with (
        patch("tinyassets.daemon_server.get_branch_definition", return_value=branch_dict),
        patch("tinyassets.branches.BranchDefinition.from_dict", return_value=branch_mock),
        patch("tinyassets.api.engine_helpers._storage_backend") as sb_mock,
        patch("tinyassets.api.engine_helpers._storage_backend", new=sb_mock),
        patch("tinyassets.identity.git_author", return_value="tester <t@t>"),
    ):
        sb_mock.return_value.save_branch_and_commit = MagicMock()
        result = _ext_branch_set_entry_point(kwargs)
    return json.loads(result)


class TestSetEntryPointSummaryDefault:
    def test_default_shape(self):
        branch = _make_branch_dict(branch_def_id="b_ep")
        result = _call_set_entry_point(branch, "n_start")
        assert result["status"] == "set"
        assert result["branch_def_id"] == "b_ep"
        assert result["entry_point"] == "n_start"
        assert "node_count" not in result

    def test_verbose_includes_node_count(self):
        branch = _make_branch_dict(branch_def_id="b_ep")
        result = _call_set_entry_point(branch, "n_start", verbose=True)
        assert "node_count" in result

    def test_default_under_200_bytes(self):
        branch = _make_branch_dict(branch_def_id="b_ep")
        result = _call_set_entry_point(branch, "n_start")
        assert len(json.dumps(result)) < 200


# ── add_state_field ───────────────────────────────────────────────────────────

def _call_add_state_field(branch_dict, field_name, field_type="str", verbose=None):
    from tinyassets.api.branches import _ext_branch_add_state_field

    branch_mock = MagicMock()
    branch_mock.state_schema = []

    kwargs = {
        "branch_def_id": branch_dict["branch_def_id"],
        "field_name": field_name,
        "field_type": field_type,
    }
    if verbose is not None:
        kwargs["verbose"] = str(verbose).lower()

    with (
        patch("tinyassets.daemon_server.get_branch_definition", return_value=branch_dict),
        patch("tinyassets.branches.BranchDefinition.from_dict", return_value=branch_mock),
        patch("tinyassets.api.engine_helpers._storage_backend") as sb_mock,
        patch("tinyassets.api.engine_helpers._storage_backend", new=sb_mock),
        patch("tinyassets.identity.git_author", return_value="tester <t@t>"),
    ):
        sb_mock.return_value.save_branch_and_commit = MagicMock()
        result = _ext_branch_add_state_field(kwargs)
    return json.loads(result)


class TestAddStateFieldSummaryDefault:
    def test_default_shape(self):
        branch = _make_branch_dict(branch_def_id="b_sf")
        result = _call_add_state_field(branch, "my_field")
        assert result["status"] == "added"
        assert result["branch_def_id"] == "b_sf"
        assert result["field_name"] == "my_field"
        assert "field_count" not in result

    def test_verbose_includes_field_count(self):
        branch = _make_branch_dict(branch_def_id="b_sf")
        result = _call_add_state_field(branch, "my_field", verbose=True)
        assert "field_count" in result

    def test_default_under_200_bytes(self):
        branch = _make_branch_dict(branch_def_id="b_sf")
        result = _call_add_state_field(branch, "my_field")
        assert len(json.dumps(result)) < 200
