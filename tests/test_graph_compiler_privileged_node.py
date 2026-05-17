"""Privileged node runtime selection."""

from __future__ import annotations

import json

import pytest

from workflow.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from workflow.graph_compiler import CompilerError, compile_branch


def _branch() -> BranchDefinition:
    return BranchDefinition(
        branch_def_id="branch1",
        name="Privileged branch",
        entry_point="privileged",
        graph_nodes=[GraphNodeRef(id="privileged", node_def_id="privileged")],
        edges=[EdgeDefinition(from_node="privileged", to_node="END")],
        node_defs=[
            NodeDefinition(
                node_id="privileged",
                display_name="Privileged",
                prompt_template="PUBLIC {x}",
                input_keys=["x"],
                output_keys=["out"],
                host_controlled=True,
            )
        ],
        state_schema=[{"name": "x", "type": "str"}, {"name": "out", "type": "str"}],
    )


def test_host_controlled_node_requires_private_runtime_body(tmp_path):
    with pytest.raises(CompilerError, match="host_controlled"):
        compile_branch(_branch(), base_path=tmp_path)


def test_host_controlled_node_uses_private_runtime_body(tmp_path):
    private_dir = tmp_path / ".host_controlled_nodes" / "branch1"
    private_dir.mkdir(parents=True)
    (private_dir / "privileged.json").write_text(
        json.dumps({
            "node_id": "privileged",
            "display_name": "Privileged private runtime",
            "prompt_template": "PRIVATE {x}",
            "input_keys": ["x"],
            "output_keys": ["out"],
        }),
        encoding="utf-8",
    )
    prompts: list[str] = []

    def _provider(prompt: str, _system: str, *, role: str) -> str:
        prompts.append(prompt)
        return "private-result"

    compiled = compile_branch(_branch(), base_path=tmp_path, provider_call=_provider)
    app = compiled.graph.compile()
    result = app.invoke({"x": "input"})

    assert prompts == ["PRIVATE input"]
    assert result["out"] == "private-result"
