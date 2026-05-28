"""Tests for workflow.branches — Community Branches data models."""

from __future__ import annotations

import json

import pytest

from workflow.branches import (
    VALID_FIELD_TYPES,
    VALID_PHASES,
    VALID_REDUCERS,
    BranchDefinition,
    ConditionalEdge,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
    NodeDefinitionValidationError,
    StateFieldDecl,
)

# ═══════════════════════════════════════════════════════════════════════════
# StateFieldDecl (Phase 3 — available but deferred)
# ═══════════════════════════════════════════════════════════════════════════


class TestStateFieldDecl:
    def test_defaults(self):
        f = StateFieldDecl(name="score")
        assert f.name == "score"
        assert f.type == "any"
        assert f.default_value is None
        assert f.reducer == "overwrite"
        assert f.description == ""

    def test_all_valid_types(self):
        for t in VALID_FIELD_TYPES:
            f = StateFieldDecl(name="x", type=t)
            assert f.type == t

    def test_all_valid_reducers(self):
        for r in VALID_REDUCERS:
            f = StateFieldDecl(name="x", reducer=r)
            assert f.reducer == r

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Invalid field type"):
            StateFieldDecl(name="x", type="integer")

    def test_invalid_reducer_raises(self):
        with pytest.raises(ValueError, match="Invalid reducer"):
            StateFieldDecl(name="x", reducer="concat")

    def test_round_trip(self):
        f = StateFieldDecl(
            name="facts",
            type="list",
            default_value=[],
            reducer="append",
            description="Accumulated facts",
        )
        d = f.to_dict()
        f2 = StateFieldDecl.from_dict(d)
        assert f2.name == f.name
        assert f2.type == f.type
        assert f2.default_value == f.default_value
        assert f2.reducer == f.reducer
        assert f2.description == f.description

    def test_from_dict_ignores_unknown_keys(self):
        f = StateFieldDecl.from_dict({"name": "x", "unknown_key": 42})
        assert f.name == "x"


# ═══════════════════════════════════════════════════════════════════════════
# NodeDefinition
# ═══════════════════════════════════════════════════════════════════════════


class TestNodeDefinition:
    def test_defaults(self):
        n = NodeDefinition(node_id="test", display_name="Test Node")
        assert n.node_id == "test"
        assert n.display_name == "Test Node"
        assert n.phase == "custom"
        assert n.input_keys == []
        assert n.output_keys == []
        assert n.source_code == ""
        assert n.prompt_template == ""
        assert n.model_hint == ""
        assert n.tools_allowed == []
        assert n.dependencies == []
        # #61: default raised from 30s → 300s so dense LLM calls
        # (90s+ on local models) don't trip the scaffold.
        assert n.timeout_seconds == 300.0
        assert n.retry_policy == {"max_retries": 0, "backoff_seconds": 1.0}
        assert n.evaluation_criteria == []
        assert n.author == "anonymous"
        assert n.enabled is True
        assert n.approved is False

    def test_all_valid_phases(self):
        for p in VALID_PHASES:
            n = NodeDefinition(node_id="x", display_name="X", phase=p)
            assert n.phase == p

    def test_invalid_phase_raises(self):
        with pytest.raises(ValueError, match="Invalid phase"):
            NodeDefinition(node_id="x", display_name="X", phase="invalid")

    def test_round_trip(self):
        n = NodeDefinition(
            node_id="checker",
            display_name="Consistency Checker",
            description="Checks facts for consistency",
            phase="commit",
            input_keys=["draft_output", "extracted_facts"],
            output_keys=["consistency_notes"],
            source_code="def run(state): return {}",
            prompt_template="Check these facts: {facts}",
            model_hint="fast",
            tools_allowed=["story_search"],
            dependencies=["requests"],
            timeout_seconds=60.0,
            retry_policy={"max_retries": 2, "backoff_seconds": 5.0},
            evaluation_criteria=[
                {"name": "accuracy", "description": "Are the facts correct?"}
            ],
        )
        d = n.to_dict()
        n2 = NodeDefinition.from_dict(d)
        assert n2.node_id == n.node_id
        assert n2.display_name == n.display_name
        assert n2.phase == n.phase
        assert n2.input_keys == n.input_keys
        assert n2.output_keys == n.output_keys
        assert n2.source_code == n.source_code
        assert n2.prompt_template == n.prompt_template
        assert n2.model_hint == n.model_hint
        assert n2.tools_allowed == n.tools_allowed
        assert n2.timeout_seconds == n.timeout_seconds
        assert n2.retry_policy == n.retry_policy
        assert n2.evaluation_criteria == n.evaluation_criteria

    def test_to_node_registration_compat(self):
        n = NodeDefinition(
            node_id="test",
            display_name="Test",
            description="desc",
            phase="orient",
            input_keys=["a", "b"],
            output_keys=["c"],
            source_code="def run(s): return {}",
            dependencies=["requests"],
            author="alice",
            enabled=True,
            approved=True,
        )
        reg = n.to_node_registration()
        assert reg["node_id"] == "test"
        assert reg["display_name"] == "Test"
        assert reg["phase"] == "orient"
        assert reg["input_keys"] == ["a", "b"]
        assert reg["output_keys"] == ["c"]
        assert reg["source_code"] == "def run(s): return {}"
        assert reg["dependencies"] == ["requests"]
        assert reg["author"] == "alice"
        assert reg["enabled"] is True
        assert reg["approved"] is True

    def test_from_node_registration(self):
        reg = {
            "node_id": "legacy",
            "display_name": "Legacy Node",
            "description": "From JSON file",
            "phase": "commit",
            "input_keys": ["x"],
            "output_keys": ["y"],
            "source_code": "def run(s): return {}",
            "dependencies": [],
            "author": "admin",
            "registered_at": "2026-01-01",
            "enabled": True,
            "approved": False,
        }
        n = NodeDefinition.from_node_registration(reg)
        assert n.node_id == "legacy"
        assert n.phase == "commit"
        assert n.author == "admin"

    def test_from_dict_ignores_unknown_keys(self):
        n = NodeDefinition.from_dict({
            "node_id": "x",
            "display_name": "X",
            "extra_field": True,
        })
        assert n.node_id == "x"

    def test_tools_allowed_rejects_non_list_shape(self):
        with pytest.raises(NodeDefinitionValidationError) as exc_info:
            NodeDefinition(
                node_id="x",
                display_name="X",
                tools_allowed="goals.leaderboard",  # type: ignore[arg-type]
            )
        assert exc_info.value.field == "tools_allowed"


# ═══════════════════════════════════════════════════════════════════════════
# GraphNodeRef
# ═══════════════════════════════════════════════════════════════════════════


class TestGraphNodeRef:
    def test_defaults(self):
        n = GraphNodeRef(id="orient")
        assert n.id == "orient"
        assert n.node_def_id == ""
        assert n.position == 0

    def test_round_trip(self):
        n = GraphNodeRef(id="orient", node_def_id="orient-v2", position=1)
        d = n.to_dict()
        assert d == {"id": "orient", "node_def_id": "orient-v2", "position": 1}
        n2 = GraphNodeRef.from_dict(d)
        assert n2.id == n.id
        assert n2.node_def_id == n.node_def_id
        assert n2.position == n.position


# ═══════════════════════════════════════════════════════════════════════════
# EdgeDefinition
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeDefinition:
    def test_simple_edge(self):
        e = EdgeDefinition(from_node="orient", to_node="plan")
        assert e.from_node == "orient"
        assert e.to_node == "plan"

    def test_serializes_as_from_to(self):
        """Edge JSON uses 'from'/'to' keys to match LangGraph format."""
        e = EdgeDefinition(from_node="orient", to_node="plan")
        d = e.to_dict()
        assert d == {"from": "orient", "to": "plan"}

    def test_deserialize_from_to_keys(self):
        e = EdgeDefinition.from_dict({"from": "a", "to": "b"})
        assert e.from_node == "a"
        assert e.to_node == "b"

    def test_deserialize_from_node_keys(self):
        """Also accepts from_node/to_node for internal use."""
        e = EdgeDefinition.from_dict({"from_node": "a", "to_node": "b"})
        assert e.from_node == "a"
        assert e.to_node == "b"

    def test_round_trip(self):
        e = EdgeDefinition(from_node="START", to_node="orient")
        d = e.to_dict()
        e2 = EdgeDefinition.from_dict(d)
        assert e2.from_node == e.from_node
        assert e2.to_node == e.to_node


# ═══════════════════════════════════════════════════════════════════════════
# ConditionalEdge
# ═══════════════════════════════════════════════════════════════════════════


class TestConditionalEdge:
    def test_basic(self):
        ce = ConditionalEdge(
            from_node="commit",
            conditions={"accept": "END", "revise": "draft"},
        )
        assert ce.from_node == "commit"
        assert ce.conditions["accept"] == "END"

    def test_serializes_as_from(self):
        ce = ConditionalEdge(from_node="commit", conditions={"a": "b"})
        d = ce.to_dict()
        assert d == {"from": "commit", "conditions": {"a": "b"}}

    def test_round_trip(self):
        ce = ConditionalEdge(
            from_node="commit",
            conditions={"accept": "END", "revise": "draft", "reject": "orient"},
        )
        d = ce.to_dict()
        ce2 = ConditionalEdge.from_dict(d)
        assert ce2.from_node == ce.from_node
        assert ce2.conditions == ce.conditions


# ═══════════════════════════════════════════════════════════════════════════
# BranchDefinition
# ═══════════════════════════════════════════════════════════════════════════


def _make_sample_branch() -> BranchDefinition:
    """Build a minimal valid branch for testing."""
    return BranchDefinition(
        name="scene-loop-v2",
        description="An improved scene loop with reflection",
        author="testuser",
        domain_id="fantasy_author",
        tags=["scene", "reflection"],
        entry_point="orient",
        graph_nodes=[
            GraphNodeRef(id="orient", node_def_id="orient-def", position=0),
            GraphNodeRef(id="plan", node_def_id="plan-def", position=1),
            GraphNodeRef(id="draft", node_def_id="draft-def", position=2),
        ],
        edges=[
            EdgeDefinition(from_node="START", to_node="orient"),
            EdgeDefinition(from_node="orient", to_node="plan"),
            EdgeDefinition(from_node="plan", to_node="draft"),
        ],
        conditional_edges=[
            ConditionalEdge(
                from_node="draft",
                conditions={"done": "END", "revise": "plan"},
            ),
        ],
        node_defs=[
            NodeDefinition(
                node_id="orient-def",
                display_name="Orient",
                phase="orient",
                input_keys=["universe_id"],
                output_keys=["orient_result"],
            ),
            NodeDefinition(
                node_id="plan-def",
                display_name="Plan",
                phase="plan",
                input_keys=["orient_result"],
                output_keys=["plan_output"],
            ),
            NodeDefinition(
                node_id="draft-def",
                display_name="Draft",
                phase="draft",
                input_keys=["plan_output"],
                output_keys=["draft_output"],
            ),
        ],
        state_schema=[
            {"name": "universe_id", "type": "string"},
            {"name": "orient_result", "type": "dict"},
            {"name": "plan_output", "type": "dict"},
            {"name": "draft_output", "type": "dict"},
        ],
    )


class TestBranchDefinition:
    def test_defaults(self):
        b = BranchDefinition()
        assert len(b.branch_def_id) == 12
        assert b.name == ""
        assert b.author == "anonymous"
        # Project identity migrated fantasy_author → workflow; the
        # default domain_id follows.
        assert b.domain_id == "workflow"
        assert b.version == 1
        assert b.parent_def_id is None
        assert b.graph_nodes == []
        assert b.edges == []
        assert b.conditional_edges == []
        assert b.node_defs == []
        assert b.state_schema == []
        assert b.published is False
        assert b.stats["fork_count"] == 0

    def test_auto_generated_id(self):
        b1 = BranchDefinition()
        b2 = BranchDefinition()
        assert b1.branch_def_id != b2.branch_def_id

    def test_round_trip_dict(self):
        b = _make_sample_branch()
        d = b.to_dict()
        b2 = BranchDefinition.from_dict(d)
        assert b2.name == b.name
        assert b2.description == b.description
        assert b2.author == b.author
        assert b2.domain_id == b.domain_id
        assert b2.tags == b.tags
        assert b2.entry_point == b.entry_point
        assert len(b2.graph_nodes) == 3
        assert len(b2.edges) == 3
        assert len(b2.conditional_edges) == 1
        assert len(b2.node_defs) == 3
        assert len(b2.state_schema) == 4
        assert b2.graph_nodes[0].id == "orient"
        assert b2.edges[0].from_node == "START"
        assert b2.state_schema[0]["name"] == "universe_id"

    def test_round_trip_json(self):
        b = _make_sample_branch()
        j = b.to_json()
        b2 = BranchDefinition.from_json(j)
        assert b2.name == b.name
        assert len(b2.node_defs) == len(b.node_defs)
        # Verify JSON is valid
        parsed = json.loads(j)
        assert isinstance(parsed, dict)
        assert "edges" in parsed
        assert "node_defs" in parsed

    def test_graph_json_langgraph_shape(self):
        """graph_json() should match LangGraph-native format."""
        b = _make_sample_branch()
        g = b.graph_json()
        assert g["entry_point"] == "orient"
        assert len(g["nodes"]) == 3
        assert len(g["edges"]) == 3
        assert len(g["conditional_edges"]) == 1
        # Edges use from/to keys
        assert g["edges"][0]["from"] == "START"
        assert g["edges"][0]["to"] == "orient"
        # Conditional edges use from/conditions
        assert g["conditional_edges"][0]["from"] == "draft"
        assert g["conditional_edges"][0]["conditions"]["done"] == "END"
        # Should be JSON-serializable
        json.dumps(g)

    def test_state_schema_json(self):
        b = _make_sample_branch()
        s = b.state_schema_json()
        assert len(s) == 4
        assert s[0]["name"] == "universe_id"
        json.dumps(s)

    def test_node_def_ids(self):
        b = _make_sample_branch()
        assert b.node_def_ids() == ["orient-def", "plan-def", "draft-def"]

    def test_get_node_def(self):
        b = _make_sample_branch()
        n = b.get_node_def("plan-def")
        assert n is not None
        assert n.display_name == "Plan"
        assert b.get_node_def("nonexistent") is None

    def test_validate_valid_branch(self):
        b = _make_sample_branch()
        errors = b.validate()
        assert errors == []

    def test_validate_missing_name(self):
        b = _make_sample_branch()
        b.name = ""
        errors = b.validate()
        assert any("name is required" in e for e in errors)

    def test_validate_no_nodes(self):
        b = BranchDefinition(name="empty")
        errors = b.validate()
        assert any("at least one node" in e for e in errors)

    def test_validate_bad_entry_point(self):
        b = _make_sample_branch()
        b.entry_point = "nonexistent"
        errors = b.validate()
        assert any("Entry point" in e for e in errors)

    def test_validate_duplicate_node_def_ids(self):
        b = _make_sample_branch()
        b.node_defs.append(NodeDefinition(node_id="orient-def", display_name="Dup"))
        errors = b.validate()
        assert any("Duplicate node definition ID" in e for e in errors)

    def test_validate_duplicate_graph_node_ids(self):
        b = _make_sample_branch()
        b.graph_nodes.append(GraphNodeRef(id="orient"))
        errors = b.validate()
        assert any("Duplicate graph node ID" in e for e in errors)

    def test_validate_bad_edge_from(self):
        b = _make_sample_branch()
        b.edges.append(EdgeDefinition(from_node="nonexistent", to_node="plan"))
        errors = b.validate()
        assert any("'from' node 'nonexistent'" in e for e in errors)

    def test_validate_bad_edge_to(self):
        b = _make_sample_branch()
        b.edges.append(EdgeDefinition(from_node="orient", to_node="nonexistent"))
        errors = b.validate()
        assert any("'to' node 'nonexistent'" in e for e in errors)

    def test_validate_start_end_are_valid(self):
        """START and END are reserved and valid in edges."""
        b = _make_sample_branch()
        # These edges reference START and END — should be valid
        errors = b.validate()
        assert not any("START" in e for e in errors)

    def test_validate_bad_conditional_edge_from(self):
        b = _make_sample_branch()
        b.conditional_edges.append(
            ConditionalEdge(from_node="nonexistent", conditions={"a": "orient"})
        )
        errors = b.validate()
        assert any("'from' node 'nonexistent'" in e for e in errors)

    def test_validate_bad_conditional_edge_target(self):
        b = _make_sample_branch()
        b.conditional_edges.append(
            ConditionalEdge(from_node="orient", conditions={"a": "nonexistent"})
        )
        errors = b.validate()
        assert any("Conditional edge target 'nonexistent'" in e for e in errors)

    def test_validate_graph_node_bad_def_ref(self):
        b = _make_sample_branch()
        b.graph_nodes.append(GraphNodeRef(id="extra", node_def_id="missing-def"))
        errors = b.validate()
        assert any("unknown node_def_id 'missing-def'" in e for e in errors)

    def test_validate_duplicate_state_fields(self):
        b = _make_sample_branch()
        b.state_schema.append({"name": "universe_id"})
        errors = b.validate()
        assert any("Duplicate state field" in e for e in errors)

    def test_validate_state_field_cannot_collide_with_graph_node_id(self):
        b = _make_sample_branch()
        b.state_schema.append({"name": "orient", "type": "str"})
        errors = b.validate()
        assert any("collides with a graph node ID" in e for e in errors)

    def test_state_field_graph_node_collision_suggestion_names_both_sides(self):
        from workflow.api.branches import _errors_to_suggestions

        b = _make_sample_branch()
        b.state_schema.append({"name": "orient", "type": "str"})
        errors = b.validate()

        suggestions = _errors_to_suggestions(b, errors)
        fixes = " ".join(s["proposed_fix"] for s in suggestions)

        assert "state_schema field 'orient'" in fixes
        assert "graph node ID 'orient'" in fixes
        assert "before running" in fixes

    def test_validate_input_key_must_be_declared_when_state_schema_exists(self):
        b = _make_sample_branch()
        b.node_defs[0].input_keys.append("missing_runtime_input")

        errors = b.validate()

        assert any(
            "Node 'orient-def' input_key 'missing_runtime_input' "
            "is not declared in state_schema" in e
            for e in errors
        )

    def test_validate_output_key_must_be_declared_when_state_schema_exists(self):
        b = _make_sample_branch()
        b.node_defs[0].output_keys.append("missing_runtime_output")

        errors = b.validate()

        assert any(
            "Node 'orient-def' output_key 'missing_runtime_output' "
            "is not declared in state_schema" in e
            for e in errors
        )

    def test_validate_legacy_empty_state_schema_remains_allowed(self):
        b = BranchDefinition(name="legacy", entry_point="n1")
        b.node_defs = [
            NodeDefinition(
                node_id="n1",
                display_name="N1",
                input_keys=["topic"],
                output_keys=["draft"],
                prompt_template="{topic}",
            )
        ]
        b.graph_nodes = [GraphNodeRef(id="n1", node_def_id="n1")]
        b.edges = [
            EdgeDefinition(from_node="START", to_node="n1"),
            EdgeDefinition(from_node="n1", to_node="END"),
        ]
        b.state_schema = []

        assert b.validate() == []

    def test_fork(self):
        b = _make_sample_branch()
        b.stats["run_count"] = 42
        f = b.fork(new_name="scene-loop-v3", author="forkuser")
        assert f.branch_def_id != b.branch_def_id
        assert f.name == "scene-loop-v3"
        assert f.author == "forkuser"
        assert f.domain_id == b.domain_id
        assert f.version == 1
        assert f.parent_def_id == b.branch_def_id
        assert f.published is False
        assert f.stats["run_count"] == 0
        assert f.stats["fork_count"] == 0
        # Topology is deep-copied
        assert len(f.node_defs) == len(b.node_defs)
        assert f.node_defs[0].node_id == b.node_defs[0].node_id
        # Mutating the fork doesn't affect the original
        f.node_defs[0].display_name = "Modified"
        assert b.node_defs[0].display_name == "Orient"

    def test_fork_default_name(self):
        b = _make_sample_branch()
        f = b.fork()
        assert f.name == "scene-loop-v2 (fork)"

    def test_legacy_nodes_key_compat(self):
        """from_dict should accept legacy 'nodes' key as node_defs."""
        b = BranchDefinition.from_dict({
            "name": "legacy",
            "nodes": [
                {"node_id": "a", "display_name": "A"},
            ],
            "edges": [],
            "state_schema": [],
        })
        assert len(b.node_defs) == 1
        assert b.node_defs[0].node_id == "a"

    def test_from_dict_ignores_unknown_keys(self):
        b = BranchDefinition.from_dict({
            "name": "test",
            "unknown_field": True,
            "node_defs": [],
            "edges": [],
            "state_schema": [],
        })
        assert b.name == "test"

    def test_state_schema_is_unvalidated(self):
        """State schema accepts any dict shape — no formal validation."""
        b = BranchDefinition(
            name="test",
            state_schema=[
                {"name": "x", "type": "magic_type", "custom_field": True},
                {"arbitrary": "data"},
            ],
        )
        assert len(b.state_schema) == 2
        # Round-trips without error
        d = b.to_dict()
        b2 = BranchDefinition.from_dict(d)
        assert b2.state_schema == b.state_schema

    def test_from_dict_does_not_mutate_input(self):
        """from_dict must not modify the caller's dict."""
        data = {
            "name": "test",
            "graph_nodes": [{"id": "a", "node_def_id": "", "position": 0}],
            "edges": [{"from": "START", "to": "a"}],
            "conditional_edges": [],
            "node_defs": [{"node_id": "a-def", "display_name": "A"}],
            "state_schema": [{"name": "x"}],
        }
        original_keys = set(data.keys())
        BranchDefinition.from_dict(data)
        assert set(data.keys()) == original_keys
        assert len(data["graph_nodes"]) == 1

    def test_from_dict_db_row_shape(self):
        """from_dict should accept DB row shape with nested 'graph' dict."""
        db_row = {
            "branch_def_id": "abc123",
            "name": "db-branch",
            "entry_point": "orient",
            "graph": {
                "nodes": [{"id": "orient", "node_def_id": "o-def", "position": 0}],
                "edges": [{"from": "START", "to": "orient"}],
                "conditional_edges": [{"from": "orient", "conditions": {"done": "END"}}],
                "entry_point": "orient",
            },
            "node_defs": [{"node_id": "o-def", "display_name": "Orient"}],
            "state_schema": [],
        }
        b = BranchDefinition.from_dict(db_row)
        assert b.name == "db-branch"
        assert len(b.graph_nodes) == 1
        assert b.graph_nodes[0].id == "orient"
        assert len(b.edges) == 1
        assert b.edges[0].from_node == "START"
        assert len(b.conditional_edges) == 1
        assert b.conditional_edges[0].conditions["done"] == "END"

    def test_validate_missing_entry_point(self):
        """Entry point is required when branch has nodes."""
        b = BranchDefinition(
            name="no-entry",
            graph_nodes=[GraphNodeRef(id="a")],
            node_defs=[NodeDefinition(node_id="a-def", display_name="A")],
        )
        errors = b.validate()
        assert any("Entry point is required" in e for e in errors)

    def test_validate_orphaned_node(self):
        """Nodes not reachable from entry point should be flagged."""
        b = BranchDefinition(
            name="orphan-test",
            entry_point="a",
            graph_nodes=[
                GraphNodeRef(id="a"),
                GraphNodeRef(id="b"),
                GraphNodeRef(id="orphan"),
            ],
            edges=[
                EdgeDefinition(from_node="START", to_node="a"),
                EdgeDefinition(from_node="a", to_node="b"),
                EdgeDefinition(from_node="b", to_node="END"),
                # orphan has no incoming edges from the main path
            ],
            node_defs=[
                NodeDefinition(node_id="a-def", display_name="A"),
                NodeDefinition(node_id="b-def", display_name="B"),
                NodeDefinition(node_id="orphan-def", display_name="Orphan"),
            ],
        )
        errors = b.validate()
        assert any("'orphan' is not reachable" in e for e in errors)
        assert not any("'a' is not reachable" in e for e in errors)
        assert not any("'b' is not reachable" in e for e in errors)

    def test_validate_cycle_without_exit(self):
        """Nodes in a cycle that can never reach END should be flagged."""
        b = BranchDefinition(
            name="cycle-test",
            entry_point="a",
            graph_nodes=[
                GraphNodeRef(id="a"),
                GraphNodeRef(id="b"),
            ],
            edges=[
                EdgeDefinition(from_node="START", to_node="a"),
                EdgeDefinition(from_node="a", to_node="b"),
                EdgeDefinition(from_node="b", to_node="a"),
                # No edge to END — infinite cycle
            ],
            node_defs=[
                NodeDefinition(node_id="a-def", display_name="A"),
                NodeDefinition(node_id="b-def", display_name="B"),
            ],
        )
        errors = b.validate()
        assert any("cycle without exit" in e for e in errors)

    def test_validate_cycle_with_exit_is_ok(self):
        """A cycle with a conditional exit to END should pass validation."""
        b = BranchDefinition(
            name="ok-cycle",
            entry_point="a",
            graph_nodes=[
                GraphNodeRef(id="a"),
                GraphNodeRef(id="b"),
            ],
            edges=[
                EdgeDefinition(from_node="START", to_node="a"),
                EdgeDefinition(from_node="a", to_node="b"),
            ],
            conditional_edges=[
                ConditionalEdge(
                    from_node="b",
                    conditions={"done": "END", "retry": "a"},
                ),
            ],
            node_defs=[
                NodeDefinition(node_id="a-def", display_name="A"),
                NodeDefinition(node_id="b-def", display_name="B"),
            ],
        )
        errors = b.validate()
        assert not any("cycle" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════════════
# Task #12 — Read-side strict validation for input_keys / output_keys.
#
# Mara's chain-break (2026-04-26): a chatbot built a 7-node research-paper
# branch with output_keys="framed_question" (str). Some path bypassed the
# lenient write-side coercion (`_coerce_node_keys`), the value reached
# storage as a str, and downstream code character-iterated it into
# ['f','r','a','m','e','d',...] — silent state corruption.
#
# Option B fix per `feedback_symmetric_boundary_validation`: write-side
# stays lenient (legitimate auto-wrap of bare tokens, see
# tests/test_patch_branch_node_keys.py). Read-side strict-validates in
# NodeDefinition.__post_init__ so corrupted persisted state can't load
# silently — fail loudly per Hard Rule #8.
# ═══════════════════════════════════════════════════════════════════════════


class TestNodeDefinitionStrictKeysValidation:
    """`__post_init__` rejects non-list input_keys / output_keys."""

    def test_str_input_keys_rejects(self):
        with pytest.raises(NodeDefinitionValidationError) as exc_info:
            NodeDefinition(
                node_id="x", display_name="X",
                input_keys="framed_question",  # type: ignore[arg-type]
            )
        assert exc_info.value.field == "input_keys"
        assert "list of strings" in exc_info.value.message
        assert "got str" in exc_info.value.message

    def test_str_output_keys_rejects(self):
        """Mara's exact case."""
        with pytest.raises(NodeDefinitionValidationError) as exc_info:
            NodeDefinition(
                node_id="x", display_name="X",
                output_keys="framed_question",  # type: ignore[arg-type]
            )
        assert exc_info.value.field == "output_keys"
        assert "got str" in exc_info.value.message

    def test_int_input_keys_rejects(self):
        with pytest.raises(NodeDefinitionValidationError) as exc_info:
            NodeDefinition(
                node_id="x", display_name="X",
                input_keys=42,  # type: ignore[arg-type]
            )
        assert exc_info.value.field == "input_keys"
        assert "got int" in exc_info.value.message

    def test_dict_output_keys_rejects(self):
        with pytest.raises(NodeDefinitionValidationError) as exc_info:
            NodeDefinition(
                node_id="x", display_name="X",
                output_keys={"a": 1},  # type: ignore[arg-type]
            )
        assert exc_info.value.field == "output_keys"
        assert "got dict" in exc_info.value.message

    def test_list_of_non_string_input_keys_rejects(self):
        with pytest.raises(NodeDefinitionValidationError) as exc_info:
            NodeDefinition(
                node_id="x", display_name="X",
                input_keys=["a", 1, "c"],  # type: ignore[list-item]
            )
        assert exc_info.value.field == "input_keys"
        assert "[1]" in exc_info.value.message
        assert "got int" in exc_info.value.message

    def test_list_of_non_string_output_keys_rejects(self):
        with pytest.raises(NodeDefinitionValidationError) as exc_info:
            NodeDefinition(
                node_id="x", display_name="X",
                output_keys=[None],  # type: ignore[list-item]
            )
        assert exc_info.value.field == "output_keys"
        assert "[0]" in exc_info.value.message
        assert "got NoneType" in exc_info.value.message

    def test_proper_lists_pass(self):
        """Positive control: list[str] is the contract; round-trips fine."""
        node = NodeDefinition(
            node_id="x", display_name="X",
            input_keys=["a", "b"],
            output_keys=["c"],
        )
        assert node.input_keys == ["a", "b"]
        assert node.output_keys == ["c"]

    def test_empty_lists_pass(self):
        """Empty default also satisfies the contract."""
        node = NodeDefinition(node_id="x", display_name="X")
        assert node.input_keys == []
        assert node.output_keys == []

    def test_from_dict_with_str_input_keys_rejects(self):
        """The actual Mara load-path: persisted dict round-trips
        through `NodeDefinition.from_dict` and trips on the str."""
        with pytest.raises(NodeDefinitionValidationError) as exc_info:
            NodeDefinition.from_dict({
                "node_id": "x", "display_name": "X",
                "input_keys": "framed_question",
            })
        assert exc_info.value.field == "input_keys"

    def test_from_dict_with_str_output_keys_rejects(self):
        """Same path, output_keys side."""
        with pytest.raises(NodeDefinitionValidationError) as exc_info:
            NodeDefinition.from_dict({
                "node_id": "x", "display_name": "X",
                "output_keys": "framed_question",
            })
        assert exc_info.value.field == "output_keys"

    def test_branch_from_dict_propagates_node_validation(self):
        """`BranchDefinition.from_dict` constructs each node via
        `NodeDefinition.from_dict` — corrupted persisted state surfaces
        the validation error at the branch-load boundary."""
        with pytest.raises(NodeDefinitionValidationError):
            BranchDefinition.from_dict({
                "branch_def_id": "b", "name": "b",
                "node_defs": [
                    {"node_id": "x", "display_name": "X",
                     "output_keys": "framed_question"},
                ],
            })

    def test_validation_error_is_value_error_subclass(self):
        """Existing `except ValueError` catch sites still work — the
        structured shape is opt-in via `field`/`message` attrs."""
        try:
            NodeDefinition(
                node_id="x", display_name="X",
                output_keys="bad",  # type: ignore[arg-type]
            )
        except ValueError as exc:
            # Catches as plain ValueError too.
            assert isinstance(exc, NodeDefinitionValidationError)
            assert "output_keys" in str(exc)
            assert "got str" in str(exc)
        else:
            pytest.fail("expected ValueError-family exception")

    def test_to_dict_round_trip_preserves_lists(self):
        """Sanity: a clean to_dict→from_dict round-trip stays clean."""
        node = NodeDefinition(
            node_id="x", display_name="X",
            input_keys=["alpha", "beta"],
            output_keys=["gamma"],
        )
        restored = NodeDefinition.from_dict(node.to_dict())
        assert restored.input_keys == ["alpha", "beta"]
        assert restored.output_keys == ["gamma"]
