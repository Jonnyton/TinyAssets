"""Runs cannot emit app events; wakes use owner compute bounded by seats."""

from __future__ import annotations

import json


def test_no_run_can_emit_an_app_event_so_a_self_loop_cannot_be_built(monkeypatch) -> None:
    """The self-loop needs a run that emits. None can, by capability:

    * a code node reaches MCP actions only through the alias map, which has no
      emit;
    * an agent node's served ``run_graph`` refuses the operation;
    * only the connector's ``run_graph``, as a signed-in person's own session
      (their app, or a UI they are looking at), emits.
    """
    from tinyassets import engine_mcp_server as engine
    from tinyassets import graph_compiler

    assert not [k for k in graph_compiler._NODE_MCP_ACTION_ALIASES if "emit" in k]
    monkeypatch.setattr(engine, "_binding_error", lambda: None)
    out = json.loads(engine.run_graph(operation="emit_event",
                                      inputs_json=json.dumps({"name": "x"})))
    assert "operation must be" in out.get("error", ""), out
