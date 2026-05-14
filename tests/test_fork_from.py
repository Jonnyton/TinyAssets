"""Tests for fork_from lineage tracking on branches.

Spec: docs/vetted-specs.md §fork_from — content-addressed lineage tracking.
"""

from __future__ import annotations

import json

import pytest

from workflow.branch_versions import publish_branch_version
from workflow.daemon_server import (
    initialize_author_server,
    save_branch_definition,
    update_branch_definition,
)


def _seed_branch(base_path, branch_id: str = "b1", name: str = "Branch") -> dict:
    from workflow.branches import BranchDefinition, EdgeDefinition, GraphNodeRef, NodeDefinition

    initialize_author_server(base_path)
    nd = NodeDefinition(node_id="n1", display_name="N1", prompt_template="do X")
    branch = BranchDefinition(
        branch_def_id=branch_id,
        name=name,
        graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
        edges=[EdgeDefinition(from_node="n1", to_node="END")],
        entry_point="n1",
        node_defs=[nd],
        state_schema=[],
    )
    return save_branch_definition(base_path, branch_def=branch.to_dict())


def _seed_clone_source(base_path, branch_id: str = "source") -> dict:
    from workflow.branches import BranchDefinition, EdgeDefinition, GraphNodeRef, NodeDefinition

    initialize_author_server(base_path)
    branch = BranchDefinition(
        branch_def_id=branch_id,
        name="Clone Source",
        tags=["substrate", "clone"],
        skills=[{
            "name": "analysis-skill",
            "description": "Analyze the request",
            "body": "Use focused reasoning.",
        }],
        graph_nodes=[
            GraphNodeRef(id="experiment_designer", node_def_id="experiment_designer"),
            GraphNodeRef(id="reviewer", node_def_id="reviewer", position=1),
        ],
        edges=[
            EdgeDefinition(from_node="experiment_designer", to_node="reviewer"),
            EdgeDefinition(from_node="reviewer", to_node="END"),
        ],
        entry_point="experiment_designer",
        node_defs=[
            NodeDefinition(
                node_id="experiment_designer",
                display_name="Experiment Designer",
                input_keys=["request"],
                output_keys=["design"],
                prompt_template="Design an experiment for {request}",
            ),
            NodeDefinition(
                node_id="reviewer",
                display_name="Reviewer",
                input_keys=["design"],
                output_keys=["review"],
                prompt_template="Review {design}",
            ),
        ],
        state_schema=[
            {"name": "request", "type": "str"},
            {"name": "design", "type": "str"},
            {"name": "review", "type": "str"},
        ],
    )
    return save_branch_definition(base_path, branch_def=branch.to_dict())


def _publish(base_path, branch_id: str) -> str:
    from workflow.daemon_server import get_branch_definition

    bd = get_branch_definition(base_path, branch_def_id=branch_id)
    v = publish_branch_version(base_path, bd, publisher="alice")
    return v.branch_version_id


class TestForkFromField:
    def test_branch_has_no_fork_from_by_default(self, tmp_path):
        _seed_branch(tmp_path)
        from workflow.daemon_server import get_branch_definition

        bd = get_branch_definition(tmp_path, branch_def_id="b1")
        assert bd["fork_from"] is None

    def test_save_branch_with_fork_from(self, tmp_path):
        _seed_branch(tmp_path, "b1")
        bvid = _publish(tmp_path, "b1")
        _seed_branch(tmp_path, "b2", "Branch 2")

        update_branch_definition(tmp_path, branch_def_id="b2", updates={"fork_from": bvid})
        from workflow.daemon_server import get_branch_definition

        bd = get_branch_definition(tmp_path, branch_def_id="b2")
        assert bd["fork_from"] == bvid

    def test_fork_from_immutable_after_set(self, tmp_path):
        _seed_branch(tmp_path, "b1")
        bvid1 = _publish(tmp_path, "b1")
        _seed_branch(tmp_path, "b2")
        bvid2 = _publish(tmp_path, "b2")

        _seed_branch(tmp_path, "b3", "Branch 3")
        update_branch_definition(tmp_path, branch_def_id="b3", updates={"fork_from": bvid1})

        with pytest.raises(ValueError, match="immutable"):
            update_branch_definition(tmp_path, branch_def_id="b3", updates={"fork_from": bvid2})

    def test_build_branch_with_fork_from_roundtrips(self, tmp_path, monkeypatch):
        from workflow.api.branches import _ext_branch_build

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path, "b1")
        bvid = _publish(tmp_path, "b1")

        spec = json.dumps({
            "name": "Forked Branch",
            "fork_from": bvid,
            "node_defs": [{"node_id": "n1", "display_name": "N1", "prompt_template": "hi"}],
            "edges": [{"from_node": "n1", "to_node": "END"}],
            "entry_point": "n1",
        })
        result = json.loads(_ext_branch_build({"spec_json": spec, "verbose": "true"}))
        assert result["status"] == "built"
        assert result["branch"]["fork_from"] == bvid

    def test_build_branch_invalid_fork_from_rejected(self, tmp_path, monkeypatch):
        from workflow.api.branches import _ext_branch_build

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        initialize_author_server(tmp_path)

        spec = json.dumps({
            "name": "Bad Fork",
            "fork_from": "not-a-real-version-id",
            "node_defs": [{"node_id": "n1", "display_name": "N1", "prompt_template": "hi"}],
            "edges": [{"from_node": "n1", "to_node": "END"}],
            "entry_point": "n1",
        })
        result = json.loads(_ext_branch_build({"spec_json": spec}))
        assert result["status"] == "rejected"
        assert any("fork_from" in e for e in result["errors"])

    def test_build_branch_fork_from_empty_node_overrides_clones_parent(
        self, tmp_path, monkeypatch
    ):
        from workflow.api.branches import _ext_branch_build
        from workflow.daemon_server import get_branch_definition

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        parent = _seed_clone_source(tmp_path)
        bvid = _publish(tmp_path, "source")
        parent_before = get_branch_definition(tmp_path, branch_def_id="source")

        result = json.loads(_ext_branch_build({
            "spec_json": json.dumps({
                "name": "Inherited Clone",
                "fork_from": bvid,
                "node_overrides": {},
            }),
            "verbose": "true",
        }))

        assert result["status"] == "built", result
        clone = result["branch"]
        assert clone["fork_from"] == bvid
        assert clone["parent_def_id"] == "source"
        assert clone["node_defs"] == parent["node_defs"]
        assert clone["graph"] == parent["graph"]
        assert clone["entry_point"] == parent["entry_point"]
        assert clone["state_schema"] == parent["state_schema"]
        assert clone["skills"] == parent["skills"]
        assert clone["tags"] == parent["tags"]
        assert get_branch_definition(tmp_path, branch_def_id="source") == parent_before

    def test_build_branch_fork_from_node_overrides_one_node_preserves_siblings(
        self, tmp_path, monkeypatch
    ):
        from workflow.api.branches import _ext_branch_build

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        parent = _seed_clone_source(tmp_path)
        bvid = _publish(tmp_path, "source")

        result = json.loads(_ext_branch_build({
            "spec_json": json.dumps({
                "name": "Prompt Variant",
                "fork_from": bvid,
                "node_overrides": {
                    "experiment_designer": {
                        "prompt_template": "Design a tighter experiment for {request}",
                    },
                },
            }),
            "verbose": "true",
        }))

        assert result["status"] == "built", result
        clone_nodes = {
            node["node_id"]: node for node in result["branch"]["node_defs"]
        }
        parent_nodes = {node["node_id"]: node for node in parent["node_defs"]}
        assert (
            clone_nodes["experiment_designer"]["prompt_template"]
            == "Design a tighter experiment for {request}"
        )
        inherited_designer = dict(parent_nodes["experiment_designer"])
        inherited_designer["prompt_template"] = (
            "Design a tighter experiment for {request}"
        )
        assert clone_nodes["experiment_designer"] == inherited_designer
        assert clone_nodes["reviewer"] == parent_nodes["reviewer"]
        assert result["branch"]["graph"] == parent["graph"]
        assert result["branch"]["state_schema"] == parent["state_schema"]


class TestSetForkFromPatchOp:
    def test_set_fork_from_op_sets_lineage(self, tmp_path, monkeypatch):
        from workflow.api.branches import _ext_branch_patch

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path, "b1")
        bvid = _publish(tmp_path, "b1")
        _seed_branch(tmp_path, "b2", "Branch 2")

        result = json.loads(_ext_branch_patch({
            "branch_def_id": "b2",
            "changes_json": json.dumps([
                {"op": "set_fork_from", "branch_version_id": bvid}
            ]),
            "verbose": "true",
        }))
        assert result["status"] == "patched"
        assert result["branch"]["fork_from"] == bvid

    def test_set_fork_from_invalid_version_rejected(self, tmp_path, monkeypatch):
        from workflow.api.branches import _ext_branch_patch

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path, "b1")

        result = json.loads(_ext_branch_patch({
            "branch_def_id": "b1",
            "changes_json": json.dumps([
                {"op": "set_fork_from", "branch_version_id": "nonexistent-bvid"}
            ]),
        }))
        assert result["status"] in ("partial", "rejected")
        assert result.get("errors") or result.get("error")

    def test_set_fork_from_immutable_after_set(self, tmp_path, monkeypatch):
        from workflow.api.branches import _ext_branch_patch

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path, "b1")
        bvid1 = _publish(tmp_path, "b1")
        _seed_branch(tmp_path, "b2")
        bvid2 = _publish(tmp_path, "b2")
        _seed_branch(tmp_path, "b3", "Branch 3")

        _ext_branch_patch({
            "branch_def_id": "b3",
            "changes_json": json.dumps([{"op": "set_fork_from", "branch_version_id": bvid1}]),
        })
        result = json.loads(_ext_branch_patch({
            "branch_def_id": "b3",
            "changes_json": json.dumps([{"op": "set_fork_from", "branch_version_id": bvid2}]),
        }))
        assert result["status"] in ("partial", "rejected")


class TestForkTree:
    def test_fork_tree_no_lineage(self, tmp_path, monkeypatch):
        from workflow.api.branches import _action_fork_tree

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path)
        result = json.loads(_action_fork_tree({"branch_def_id": "b1"}))
        assert result["branch_def_id"] == "b1"
        assert result["ancestors"] == []
        assert result["descendant_count"] == 0

    def test_fork_tree_shows_descendant(self, tmp_path, monkeypatch):
        from workflow.api.branches import _action_fork_tree

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path, "b1", "Root")
        bvid = _publish(tmp_path, "b1")
        _seed_branch(tmp_path, "b2", "Fork")
        update_branch_definition(tmp_path, branch_def_id="b2", updates={"fork_from": bvid})

        result = json.loads(_action_fork_tree({"branch_def_id": "b1"}))
        assert result["descendant_count"] == 1
        assert result["descendants"][0]["branch_def_id"] == "b2"

    def test_fork_tree_shows_ancestor(self, tmp_path, monkeypatch):
        from workflow.api.branches import _action_fork_tree

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path, "b1", "Root")
        bvid = _publish(tmp_path, "b1")
        _seed_branch(tmp_path, "b2", "Fork")
        update_branch_definition(tmp_path, branch_def_id="b2", updates={"fork_from": bvid})

        result = json.loads(_action_fork_tree({"branch_def_id": "b2"}))
        assert len(result["ancestors"]) == 1
        assert result["ancestors"][0]["branch_def_id"] == "b1"

    def test_fork_tree_missing_branch_error(self, tmp_path, monkeypatch):
        from workflow.api.branches import _action_fork_tree

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        initialize_author_server(tmp_path)
        result = json.loads(_action_fork_tree({"branch_def_id": "nonexistent"}))
        assert "error" in result

    def test_fork_tree_missing_branch_def_id_error(self, tmp_path, monkeypatch):
        from workflow.api.branches import _action_fork_tree

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        initialize_author_server(tmp_path)
        result = json.loads(_action_fork_tree({}))
        assert "error" in result


class TestDescribeBranchLineageEnrichment:
    def test_describe_branch_includes_fork_from(self, tmp_path, monkeypatch):
        from workflow.api.branches import _ext_branch_describe

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path, "b1")
        bvid = _publish(tmp_path, "b1")
        _seed_branch(tmp_path, "b2", "Fork")
        update_branch_definition(tmp_path, branch_def_id="b2", updates={"fork_from": bvid})

        result = json.loads(_ext_branch_describe({"branch_def_id": "b2"}))
        assert result["fork_from"] == bvid

    def test_describe_branch_no_fork_from_is_none(self, tmp_path, monkeypatch):
        from workflow.api.branches import _ext_branch_describe

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path)

        result = json.loads(_ext_branch_describe({"branch_def_id": "b1"}))
        assert result["fork_from"] is None

    def test_describe_branch_includes_fork_descendants(self, tmp_path, monkeypatch):
        from workflow.api.branches import _ext_branch_describe

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path, "b1", "Root")
        bvid = _publish(tmp_path, "b1")
        _seed_branch(tmp_path, "b2", "Fork")
        update_branch_definition(tmp_path, branch_def_id="b2", updates={"fork_from": bvid})

        result = json.loads(_ext_branch_describe({"branch_def_id": "b1"}))
        assert len(result["fork_descendants"]) == 1
        desc = result["fork_descendants"][0]
        assert desc["branch_def_id"] == "b2"
        assert "author" in desc
        assert "published_versions_count" in desc

    def test_describe_branch_no_descendants_returns_empty_list(self, tmp_path, monkeypatch):
        from workflow.api.branches import _ext_branch_describe

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        _seed_branch(tmp_path)

        result = json.loads(_ext_branch_describe({"branch_def_id": "b1"}))
        assert result["fork_descendants"] == []
