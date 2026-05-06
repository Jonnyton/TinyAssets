from __future__ import annotations

import json


def test_prompt_template_typed_output_key_writes_coerced_state_value():
    from langgraph.checkpoint.memory import InMemorySaver

    from workflow.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from workflow.graph_compiler import compile_branch

    branch = BranchDefinition(name="typed output", entry_point="score")
    branch.node_defs = [
        NodeDefinition(
            node_id="score",
            display_name="Score",
            input_keys=["claim"],
            output_keys=["rating"],
            prompt_template="Rate this claim from 1 to 10: {claim}",
        )
    ]
    branch.graph_nodes = [GraphNodeRef(id="score", node_def_id="score")]
    branch.edges = [
        EdgeDefinition(from_node="START", to_node="score"),
        EdgeDefinition(from_node="score", to_node="END"),
    ]
    branch.state_schema = [
        {"name": "claim", "type": "str"},
        {"name": "rating", "type": "int"},
    ]

    captured_prompts: list[str] = []

    def provider(prompt: str, system: str, *, role: str) -> str:
        captured_prompts.append(prompt)
        return json.dumps({"rating": "7"})

    compiled = compile_branch(branch, provider_call=provider)
    app = compiled.graph.compile(checkpointer=InMemorySaver())

    result = app.invoke(
        {"claim": "The engine writes typed outputs."},
        config={"configurable": {"thread_id": "typed-output"}},
    )

    assert "RESPONSE FORMAT" in captured_prompts[0]
    assert "'rating': int" in captured_prompts[0]
    assert result["rating"] == 7
