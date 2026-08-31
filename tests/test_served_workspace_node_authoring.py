"""A workspace node must survive the SERVED authoring path.

Found live on 2026-08-31: the founder's universe was given repository access
and workspace consent, tried to build the graph, and reported "the build tool
exposed to me here refuses workspace nodes". The sink was deployed, the docs
described it, and every unit test constructed :class:`NodeDefinition` directly
-- so nothing exercised the one path a user actually goes through. The served
builder passed ``effects`` and simply never passed ``workspace``: the field was
dropped on the floor, the node was stored without its binding, and at run time
there was no ``ws`` object and no explanation.

These tests drive the served helpers, not the dataclass, because the dataclass
was never the thing that was broken.
"""
from __future__ import annotations

import inspect as _inspect

import pytest

from tinyassets.api.branches import _NODE_UPDATE_FIELDS, _apply_node_updates
from tinyassets.branches import NodeDefinition


def _node(**kwargs) -> NodeDefinition:
    base = {
        "node_id": "inspect",
        "display_name": "Inspect",
        "source_code": "def run(state):\n    return {}\n",
        "output_keys": ["seen"],
    }
    base.update(kwargs)
    return NodeDefinition(**base)


def test_the_served_node_builder_carries_the_workspace_binding() -> None:
    """The regression itself: a spec naming a workspace must reach the node."""
    from tinyassets.api import branches as api

    source = _inspect.getsource(api)
    # The builder constructs NodeDefinition with an explicit keyword list, so
    # a missing field is invisible - assert the wiring, since a unit test that
    # builds the dataclass by hand cannot see this at all.
    assert "workspace=workspace_arg," in source, (
        "the served builder must pass workspace to NodeDefinition; it passed "
        "effects and dropped this one, which is exactly the live failure"
    )
    assert 'workspace_raw = raw.get("workspace", "")' in source


def test_a_workspace_binding_can_be_added_to_an_existing_node() -> None:
    """Rebuilding a whole branch to add a binding is not an authoring path."""
    assert "workspace" in _NODE_UPDATE_FIELDS
    assert "effects" in _NODE_UPDATE_FIELDS

    node = _node()
    assert node.workspace == ""
    err = _apply_node_updates(node, {"workspace": "checkout"})
    assert err == "", err
    assert node.workspace == "checkout"


def test_effects_can_be_added_to_an_existing_node() -> None:
    node = _node()
    err = _apply_node_updates(node, {"effects": ["workspace"]})
    assert err == "", err
    assert node.effects == ["workspace"]


def test_a_workspace_binding_can_be_cleared() -> None:
    node = _node(workspace="checkout")
    err = _apply_node_updates(node, {"workspace": ""})
    assert err == "", err
    assert node.workspace == ""


@pytest.mark.parametrize("bad", [123, ["checkout"], {"node": "checkout"}, 1.5])
def test_a_non_string_workspace_is_refused_by_name(bad: object) -> None:
    node = _node()
    err = _apply_node_updates(node, {"workspace": bad})
    assert "workspace must be the node id" in err
    assert node.workspace == "", "a refused update must not partially apply"


def test_the_workspace_id_is_stripped_not_reinterpreted() -> None:
    node = _node()
    assert _apply_node_updates(node, {"workspace": "  checkout  "}) == ""
    assert node.workspace == "checkout"
