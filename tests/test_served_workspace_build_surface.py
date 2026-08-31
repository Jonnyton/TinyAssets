"""The SERVED build surface must accept the graph the docs tell agents to write.

Two gates blocked this in production, hours apart, each found only by a live
universe trying to do the job:

1. the served node builder never passed ``workspace`` to ``NodeDefinition``,
   so the binding was dropped on the way in (fixed in #2737);
2. ``_sanitize_served_branch_spec`` allowed exactly one effect sink, so
   ``effects: ["workspace"]`` was refused outright with "not available on the
   served build surface".

Every other test built the objects directly and passed throughout. These drive
the served sanitiser with the exact spec shape the tool docstring teaches, so a
third gate cannot hide behind the same blind spot.
"""
from __future__ import annotations

import copy

import pytest

from tinyassets.engine_mcp_server import _sanitize_served_branch_spec

CHECKOUT_NODE = {
    "node_id": "checkout",
    "display_name": "Check out the repo",
    "source_code": (
        "def run(state):\n"
        "    return {'workspace_packet': {'op': 'checkout', "
        "'connection_id': 'c1', 'repo': 'owner/name', 'ref': 'main'}}\n"
    ),
    "output_keys": ["workspace_packet"],
    "effects": ["workspace"],
}
WORKSPACE_NODE = {
    "node_id": "compile",
    "display_name": "Compile it",
    "source_code": (
        "def run(state):\n"
        "    got = ws.run(['python', '-m', 'compileall', '-q', '.'])\n"
        "    return {'rc': got['returncode']}\n"
    ),
    "output_keys": ["rc"],
    "workspace": "checkout",
}


def _spec(*nodes: dict) -> dict:
    return {
        "name": "compile check",
        "entry_point": "checkout",
        "node_defs": [copy.deepcopy(n) for n in nodes],
        "edges": [{"from": "START", "to": "checkout"}, {"from": "compile", "to": "END"}],
        "state_schema": [
            {"name": "workspace_packet", "type": "dict"},
            {"name": "rc", "type": "int"},
        ],
    }


def test_the_served_surface_accepts_a_workspace_graph() -> None:
    """The whole point: what the docs teach must survive the sanitiser."""
    spec = _spec(CHECKOUT_NODE, WORKSPACE_NODE)
    _sanitize_served_branch_spec(spec)  # must not raise
    checkout, compile_node = spec["node_defs"]
    assert checkout["effects"] == ["workspace"], "the sink was stripped"
    assert compile_node["workspace"] == "checkout", "the binding was stripped"


def test_the_channel_node_still_works() -> None:
    node = {
        "node_id": "call",
        "display_name": "Call",
        "source_code": "def run(state):\n    return {}\n",
        "output_keys": [],
        "effects": ["authenticated_external_call"],
    }
    spec = _spec(node)
    spec["entry_point"] = "call"
    spec["edges"] = [{"from": "START", "to": "call"}, {"from": "call", "to": "END"}]
    _sanitize_served_branch_spec(spec)
    assert spec["node_defs"][0]["effects"] == ["authenticated_external_call"]


def test_the_allowlist_is_still_an_allowlist() -> None:
    """Widening it to two sinks must not turn it into a denylist."""
    node = dict(CHECKOUT_NODE, effects=["wiki_write_back"])
    with pytest.raises(ValueError) as caught:
        _sanitize_served_branch_spec(_spec(node))
    message = str(caught.value)
    assert "not available on the served build surface" in message
    # The refusal must name what IS allowed, or an agent cannot self-correct.
    assert "authenticated_external_call" in message
    assert "workspace" in message


def test_a_node_may_still_declare_only_one_sink() -> None:
    node = dict(CHECKOUT_NODE, effects=["workspace", "authenticated_external_call"])
    with pytest.raises(ValueError) as caught:
        _sanitize_served_branch_spec(_spec(node))
    assert "at most one effect sink" in str(caught.value)


def test_sub_branch_invocation_is_still_refused() -> None:
    """The other half of the same gate must not have been loosened."""
    node = dict(CHECKOUT_NODE, invoke_branch_spec={"branch_def_id": "b"})
    with pytest.raises(ValueError) as caught:
        _sanitize_served_branch_spec(_spec(node))
    assert "invoke_branch_spec is not available" in str(caught.value)


def test_handoffs_are_still_refused() -> None:
    node = dict(CHECKOUT_NODE, handoffs=[{"to": "somewhere"}])
    with pytest.raises(ValueError) as caught:
        _sanitize_served_branch_spec(_spec(node))
    assert "handoffs" in str(caught.value)


def test_node_ref_is_still_refused() -> None:
    with pytest.raises(ValueError) as caught:
        _sanitize_served_branch_spec(_spec({"node_ref": "public-node"}))
    assert "node_ref is not allowed" in str(caught.value)


def test_the_docstring_and_the_gate_agree_on_the_sink_name() -> None:
    """The docs tell agents to write ``effects: ["workspace"]``. If the served
    gate ever renamed the sink, the instructions would teach a refusal."""
    import tinyassets.engine_mcp_server as server
    from tinyassets.effectors.workspace import EXTERNAL_WRITE_SINK_WORKSPACE

    assert EXTERNAL_WRITE_SINK_WORKSPACE == "workspace"
    doc = server.write_graph.__doc__ or ""
    if not doc:
        import inspect

        doc = inspect.getsource(server)
    assert '"effects": ["workspace"]' in doc or '["workspace"]' in doc
