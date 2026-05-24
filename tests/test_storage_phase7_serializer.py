"""Phase 7.1 — Branch/Goal/Node YAML round-trip identity tests.

Per spec AC #2: ``SQLite → YAML → SQLite`` is identity over the
subset of fields that survive serialization. Server-managed
timestamps and aggregate stats are preserved, not fabricated, so a
round-trip leaves the stored row unchanged.

These tests don't touch disk. They pin the serializer contract
independent of the backend.
"""

from __future__ import annotations

import pytest
import yaml

from workflow.branches import (
    BranchDefinition,
    ConditionalEdge,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from workflow.catalog.serializer import (
    branch_from_yaml_payload,
    branch_to_yaml_payload,
    goal_from_yaml_payload,
    goal_to_yaml_payload,
    node_from_yaml_payload,
    node_to_yaml_payload,
)


def _make_branch() -> BranchDefinition:
    return BranchDefinition(
        branch_def_id="abc123",
        name="Research paper pipeline",
        description="Literature → rigor → drafting.",
        author="dev-2",
        domain_id="workflow",
        goal_id="produce-academic-paper",
        tags=["research", "academic"],
        version=3,
        parent_def_id=None,
        entry_point="literature_scan",
        graph_nodes=[
            GraphNodeRef(id="literature_scan",
                         node_def_id="literature_scan"),
            GraphNodeRef(id="section_drafter",
                         node_def_id="section_drafter"),
        ],
        edges=[
            EdgeDefinition(from_node="START", to_node="literature_scan"),
            EdgeDefinition(from_node="literature_scan",
                           to_node="section_drafter"),
            EdgeDefinition(from_node="section_drafter", to_node="END"),
        ],
        conditional_edges=[
            ConditionalEdge(
                from_node="literature_scan",
                conditions={"ok": "section_drafter", "fail": "END"},
            ),
        ],
        node_defs=[
            NodeDefinition(
                node_id="literature_scan",
                display_name="Literature scan",
                phase="orient",
                prompt_template="Find sources about {topic}.",
                input_keys=["topic"],
                output_keys=["sources"],
                timeout_seconds=240.0,
            ),
            NodeDefinition(
                node_id="section_drafter",
                display_name="Section drafter",
                phase="draft",
                prompt_template="Draft section {section_name}.",
                input_keys=["section_name", "sources"],
                output_keys=["draft"],
                timeout_seconds=300.0,
                approved=True,
            ),
        ],
        state_schema=[
            {"name": "topic", "type": "str", "default": ""},
            {"name": "sources", "type": "list", "default": []},
            {"name": "draft", "type": "str", "default": ""},
        ],
        published=True,
        stats={"fork_count": 2, "run_count": 11, "avg_quality_score": 0.8},
        created_at="2026-04-13T03:00:00+00:00",
        updated_at="2026-04-13T04:00:00+00:00",
    )


# ─────────────────────────────────────────────────────────────────────
# Branch round-trip — externalized nodes
# ─────────────────────────────────────────────────────────────────────


def test_branch_round_trip_is_identity_with_externalized_nodes():
    original = _make_branch()
    payload, node_payloads = branch_to_yaml_payload(
        original, branch_slug="research-paper-pipeline",
    )
    node_lookup = {n["id"]: n for n in node_payloads}
    reconstituted = branch_from_yaml_payload(payload, node_lookup)

    assert reconstituted.to_dict() == original.to_dict()


def test_branch_round_trip_is_identity_with_inline_nodes():
    original = _make_branch()
    payload, node_payloads = branch_to_yaml_payload(
        original,
        branch_slug="research-paper-pipeline",
        externalize_nodes=False,
    )
    assert node_payloads == []
    # Inline payloads live under nodes[*].inline
    for entry in payload["nodes"]:
        assert "inline" in entry
        assert "path" not in entry
    reconstituted = branch_from_yaml_payload(payload)
    assert reconstituted.to_dict() == original.to_dict()


def test_branch_payload_surfaces_editable_fields_before_mechanical():
    """Phone-legibility: identity + intent fields render near the top
    of the YAML so a reviewer sees them on a 4-inch screen without
    scrolling past stats/timestamps."""
    payload, _ = branch_to_yaml_payload(
        _make_branch(), branch_slug="research-paper-pipeline",
    )
    keys = list(payload)
    # identity + intent first
    assert keys.index("id") < keys.index("stats")
    assert keys.index("name") < keys.index("created_at")
    assert keys.index("description") < keys.index("updated_at")
    assert keys.index("nodes") < keys.index("stats")


def test_branch_node_entries_point_at_per_branch_paths():
    payload, _ = branch_to_yaml_payload(
        _make_branch(), branch_slug="research-paper-pipeline",
    )
    for entry in payload["nodes"]:
        assert entry["path"].startswith(
            "nodes/research-paper-pipeline/"
        )
        assert entry["path"].endswith(".yaml")


def test_branch_edges_serialize_as_compact_from_to_pairs():
    payload, _ = branch_to_yaml_payload(
        _make_branch(), branch_slug="x",
    )
    for entry in payload["edges"]:
        assert set(entry.keys()) == {"from", "to"}


def test_branch_payload_is_yaml_safe():
    """YAML must round-trip through safe_dump/safe_load without loss."""
    payload, _ = branch_to_yaml_payload(
        _make_branch(), branch_slug="x",
    )
    dumped = yaml.safe_dump(payload, sort_keys=False)
    loaded = yaml.safe_load(dumped)
    assert loaded == payload


def test_branch_from_yaml_tolerates_missing_node_file():
    """A contributor may pull a branch whose nodes haven't synced yet;
    deserialization must not crash — downstream validate() handles it."""
    payload, _ = branch_to_yaml_payload(
        _make_branch(), branch_slug="x",
    )
    # Drop the node_payloads map entirely.
    branch = branch_from_yaml_payload(payload, {})
    # Placeholder nodes produced with empty bodies.
    assert len(branch.node_defs) == 2
    for node in branch.node_defs:
        assert node.prompt_template == ""
        assert node.source_code == ""


def test_branch_from_yaml_accepts_legacy_list_edge_shape():
    """dev-3's layout doc example used ``[from, to]`` pairs; keep
    that path working to avoid churning docs."""
    payload, node_payloads = branch_to_yaml_payload(
        _make_branch(), branch_slug="x",
    )
    payload["edges"] = [
        ["START", "literature_scan"],
        ["literature_scan", "section_drafter"],
        ["section_drafter", "END"],
    ]
    branch = branch_from_yaml_payload(
        payload, {n["id"]: n for n in node_payloads},
    )
    assert len(branch.edges) == 3
    assert branch.edges[0].from_node == "START"
    assert branch.edges[0].to_node == "literature_scan"


# ─────────────────────────────────────────────────────────────────────
# Node round-trip
# ─────────────────────────────────────────────────────────────────────


def test_node_round_trip_is_identity_for_prompt_template():
    original = NodeDefinition(
        node_id="literature_scan",
        display_name="Literature scan",
        description="Walks the web for sources.",
        phase="orient",
        prompt_template="Find sources about {topic}.",
        input_keys=["topic"],
        output_keys=["sources"],
        model_hint="writer",
        tools_allowed=["web_search"],
        dependencies=["requests"],
        timeout_seconds=240.0,
        evaluation_criteria=[{"name": "coverage", "weight": "1.0"}],
        author="dev-2",
        approved=True,
        enabled=True,
    )
    payload = node_to_yaml_payload(original)
    reconstituted = node_from_yaml_payload(payload)
    assert reconstituted.to_dict() == original.to_dict()


def test_node_payload_omits_defaults_for_small_files():
    """Phone-legibility: a minimal node YAML shouldn't carry empty
    input_keys/output_keys/dependencies/etc. The bot reads these on
    a small screen."""
    minimal = NodeDefinition(
        node_id="n1",
        display_name="N1",
        prompt_template="hi",
    )
    payload = node_to_yaml_payload(minimal)
    assert "input_keys" not in payload
    assert "output_keys" not in payload
    assert "dependencies" not in payload
    assert "tools_allowed" not in payload
    assert "retry_policy" not in payload  # default policy elided
    # Intent fields stay.
    assert payload["id"] == "n1"
    assert payload["prompt_template"] == "hi"


def test_node_payload_preserves_explicit_non_strict_input_isolation():
    node = NodeDefinition(
        node_id="n1",
        display_name="N1",
        input_keys=["topic"],
        prompt_template="{topic} {legacy_global}",
        strict_input_isolation=False,
    )
    payload = node_to_yaml_payload(node)
    assert payload["strict_input_isolation"] is False
    assert node_from_yaml_payload(payload).strict_input_isolation is False


def test_node_payload_always_includes_timeout_seconds():
    """#61 raised the default; the YAML records intent explicitly so
    operators can see the current contract without remembering it."""
    payload = node_to_yaml_payload(
        NodeDefinition(node_id="n1", display_name="N1"),
    )
    assert payload["timeout_seconds"] == 300.0


# ─────────────────────────────────────────────────────────────────────
# Goal round-trip
# ─────────────────────────────────────────────────────────────────────


def test_goal_round_trip_is_identity():
    # Phase 6.3: `gate_ladder` rides through as a goal attribute,
    # defaulting to [] when absent. The round-trip always surfaces it.
    original = {
        "goal_id": "goal_xyz",
        "name": "Produce academic paper",
        "description": "From a lit review to a submittable draft.",
        "author": "dev-2",
        "tags": ["research", "academic"],
        "visibility": "public",
        "created_at": 1712000000.0,
        "updated_at": 1712000500.0,
        "gate_ladder": [],
    }
    payload = goal_to_yaml_payload(original)
    reconstituted = goal_from_yaml_payload(payload)
    assert reconstituted == original


def test_goal_payload_foregrounds_name_over_id():
    """Phone readers care about the name; goal_id is a machine detail."""
    payload = goal_to_yaml_payload({
        "goal_id": "goal_xyz",
        "name": "Produce academic paper",
    })
    keys = list(payload)
    # id first (spec) but name second — both visible before tags/etc.
    assert keys.index("name") == 1


def test_goal_payload_is_yaml_safe():
    payload = goal_to_yaml_payload({
        "goal_id": "goal_xyz",
        "name": "Produce academic paper",
        "description": "\n".join(["line 1", "line 2"]),
        "tags": ["multi-line", "ok"],
        "visibility": "public",
    })
    dumped = yaml.safe_dump(payload, sort_keys=False)
    loaded = yaml.safe_load(dumped)
    assert loaded == payload


# ─────────────────────────────────────────────────────────────────────
# Validation + rejection
# ─────────────────────────────────────────────────────────────────────


def test_unrecognised_edge_entry_raises():
    payload, node_payloads = branch_to_yaml_payload(
        _make_branch(), branch_slug="x",
    )
    payload["edges"] = ["not-an-edge-structure"]
    with pytest.raises(ValueError, match="edge"):
        branch_from_yaml_payload(
            payload, {n["id"]: n for n in node_payloads},
        )


def test_node_from_yaml_rejects_str_input_keys():
    """Task #12: a YAML payload with `input_keys: framed_question` (str)
    used to char-iterate into ['f','r','a','m','e','d',...] under
    `list(payload.get(...) or [])`. Now passes through to
    NodeDefinition's read-side validator which rejects with
    NodeDefinitionValidationError."""
    from workflow.branches import NodeDefinitionValidationError

    payload = {
        "id": "x", "display_name": "X",
        "input_keys": "framed_question",
    }
    with pytest.raises(NodeDefinitionValidationError) as exc_info:
        node_from_yaml_payload(payload)
    assert exc_info.value.field == "input_keys"
    assert "got str" in exc_info.value.message


def test_node_from_yaml_rejects_str_output_keys():
    """Same gap on the output_keys side (Mara's 2026-04-26 case)."""
    from workflow.branches import NodeDefinitionValidationError

    payload = {
        "id": "x", "display_name": "X",
        "output_keys": "framed_question",
    }
    with pytest.raises(NodeDefinitionValidationError) as exc_info:
        node_from_yaml_payload(payload)
    assert exc_info.value.field == "output_keys"
    assert "got str" in exc_info.value.message


def test_node_from_yaml_passes_proper_lists():
    """Positive control: list[str] survives the read-side guard."""
    payload = {
        "id": "x", "display_name": "X",
        "input_keys": ["a", "b"],
        "output_keys": ["c"],
    }
    node = node_from_yaml_payload(payload)
    assert node.input_keys == ["a", "b"]
    assert node.output_keys == ["c"]
