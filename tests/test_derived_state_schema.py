"""A branch spec without a state schema must still be runnable.

Every branch built through the agent surface had `state_schema_json: []`, so
inputs had nowhere to land and any automation carrying them failed at execution
while compiling cleanly. Found live 2026-08-08 on an approved run.
"""

from __future__ import annotations

import json

from tinyassets.branch_templates import TEMPLATES
from tinyassets.universe_agent_actions import _with_derived_state_schema


def _schema_names(spec_json: str) -> list[str]:
    return [f["name"] for f in json.loads(spec_json).get("state_schema", [])]


def test_derives_every_key_the_nodes_read_or_write():
    spec = json.dumps({
        "name": "x",
        "nodes": [
            {"node_id": "a", "input_keys": ["brief"], "output_keys": ["draft"]},
            {"node_id": "b", "input_keys": ["draft"], "output_keys": ["final"]},
        ],
    })
    assert _schema_names(_with_derived_state_schema(spec)) == ["brief", "draft", "final"]


def test_an_explicit_schema_is_never_overruled():
    """Filling a gap is not the same as overriding an author."""
    spec = json.dumps({
        "state_schema": [{"name": "mine", "type": "int", "description": "kept"}],
        "nodes": [{"node_id": "a", "input_keys": ["other"], "output_keys": []}],
    })
    assert json.loads(_with_derived_state_schema(spec))["state_schema"] == [
        {"name": "mine", "type": "int", "description": "kept"}
    ]


def test_malformed_input_is_returned_untouched():
    for bad in ("not json", "[]", '"a string"', "{}", '{"nodes": "not a list"}'):
        assert _with_derived_state_schema(bad) == bad


def test_nothing_added_when_no_node_declares_keys():
    spec = json.dumps({"nodes": [{"node_id": "a"}]})
    assert _with_derived_state_schema(spec) == spec


def test_every_shipped_template_gains_a_runnable_schema():
    """The five starting points a user remixes must all be executable.

    They were verified to BUILD, which passed while every one of them was
    unrunnable — compiling is not executing.
    """
    for name, entry in TEMPLATES.items():
        derived = _with_derived_state_schema(json.dumps(entry["spec"]))
        names = set(_schema_names(derived))
        declared = {
            key
            for node in entry["spec"]["nodes"]
            for group in ("input_keys", "output_keys")
            for key in node.get(group, [])
        }
        assert declared, f"{name}: template declares no keys at all"
        assert declared <= names, f"{name}: missing {sorted(declared - names)}"


def test_no_template_field_collides_with_a_node_id():
    """A state field may not share a name with a node — the validator refuses it.

    Three of the five templates did exactly this (`draft`, `plan`, `critique`),
    and it stayed hidden while the specs carried no state schema: they passed a
    build check and were unrunnable. Deriving the schema is what surfaced it.
    """
    for name, entry in TEMPLATES.items():
        spec = entry["spec"]
        nodes = {node["node_id"] for node in spec["nodes"]}
        fields = {
            key
            for node in spec["nodes"]
            for group in ("input_keys", "output_keys")
            for key in node.get(group, [])
        }
        assert not (nodes & fields), f"{name}: {sorted(nodes & fields)} collide"


def test_every_template_prompt_only_references_declared_fields():
    """A renamed field must be renamed in the prompt text too.

    Renaming `draft` to `draft_text` in `output_keys` while leaving `{draft}` in
    a prompt would compile and then fail at execution on the missing key — the
    same class of defect this whole file exists for.
    """
    import re

    for name, entry in TEMPLATES.items():
        spec = entry["spec"]
        declared = {
            key
            for node in spec["nodes"]
            for group in ("input_keys", "output_keys")
            for key in node.get(group, [])
        }
        for node in spec["nodes"]:
            referenced = set(re.findall(r"\{(\w+)\}", node.get("prompt_template", "")))
            missing = referenced - declared
            assert not missing, f"{name}/{node['node_id']}: {sorted(missing)} undeclared"


def test_missing_inputs_are_named_before_the_run_starts(monkeypatch):
    """A run that cannot work must be refused HERE, not deep in the executor.

    Accepted-then-failed gave the founder a run id and silence, and gave the
    agent an empty result it could not explain.
    """
    import tinyassets.universe_server as server
    from tinyassets.universe_agent_actions import _missing_run_inputs

    monkeypatch.setattr(
        server, "read_graph",
        lambda **_k: json.dumps({
            "entry_point": "draft",
            "nodes": [{"node_id": "draft", "input_keys": ["brief", "tone"]}],
        }),
    )
    assert _missing_run_inputs("u", "b", "{}") == ["brief", "tone"]
    assert _missing_run_inputs("u", "b", '{"brief": "x"}') == ["tone"]
    assert _missing_run_inputs("u", "b", '{"brief": "x", "tone": "y"}') == []


def test_unreadable_branch_never_blocks_a_run(monkeypatch):
    """Uncertainty must not invent a refusal the platform would not make."""
    import tinyassets.universe_server as server
    from tinyassets.universe_agent_actions import _missing_run_inputs

    def explode(**_kwargs):
        raise RuntimeError("branch unreadable")

    monkeypatch.setattr(server, "read_graph", explode)
    assert _missing_run_inputs("u", "b", "{}") == []

    monkeypatch.setattr(server, "read_graph", lambda **_k: "not json")
    assert _missing_run_inputs("u", "b", "{}") == []


def test_read_run_is_an_allowed_branch_action():
    """The agent asked for this by name: it could run but not read the result."""
    from tinyassets.universe_agent_actions import BRANCH_ACTIONS

    assert "read_run" in BRANCH_ACTIONS


def test_a_node_without_a_caption_is_still_a_node(tmp_path, monkeypatch):
    """Omitting `display_name` must not delete the node.

    It was required, so a spec missing that one human label had its node
    dropped and came back with three errors — "missing node_id or
    display_name", "Branch must have at least one node", and "Entry point is
    not a defined node" — none of which named the real fault.
    """
    from tinyassets.api.branches import _apply_node_spec

    class _Branch:
        def __init__(self):
            self.node_defs = []
            self.graph_nodes = []

    branch = _Branch()
    err = _apply_node_spec(
        branch,
        {
            "node_id": "draft",
            "input_keys": ["brief"],
            "output_keys": ["draft_text"],
            "prompt_template": "Write from {brief}",
        },
    )
    assert err == "", f"a captionless node was rejected: {err}"
    assert branch.node_defs, "the node was dropped instead of defaulted"
    assert branch.node_defs[0].display_name == "draft", "caption defaults to the id"


def test_a_node_without_an_id_is_still_refused():
    """The id is identity, not a caption — that one must stay required."""
    from tinyassets.api.branches import _apply_node_spec

    class _Branch:
        node_defs: list = []
        graph_nodes: list = []

    assert "node_id" in _apply_node_spec(_Branch(), {"display_name": "Draft"})
