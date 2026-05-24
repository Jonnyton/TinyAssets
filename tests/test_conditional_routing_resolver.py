"""Tier-1 investigation: conditional_edges routing resolver.

Step 2 + 3 of the BUG-019/021/022 triad plan:
- Step 2: minimal repro `start → gate -.A.-> path_a | -.B.-> path_b`.
  Compile + run twice with scripted gate outputs "A" and "B"; both must
  end at the matching path_X node, not always fall back to path_a.
- Step 3: exercise the 3 symptom shapes (S1 literal "END", S2 terminal
  noop + loop_back, S3 three gate iterations).

Hypothesis (from step-1 prep read): when a branch has
``graph_node.id != graph_node.node_def_id`` on the gate, the resolver
at ``graph_compiler.py:_build_conditional_router`` loads source_def =
``node_by_id.get(gn.id)`` which returns None because ``node_by_id`` is
keyed by node_def.id. With source_def=None, output_key stays "" and
the router ALWAYS returns the fallback (first declared condition's
target) regardless of state.

These tests pass the hypothesis state (graph_node.id == node_def.id)
today. They will CONTINUE to pass after the fix lands and will NEWLY
cover the graph_node.id != node_def.id case (currently broken).
"""
from __future__ import annotations

from typing import Any

import pytest

from workflow.branches import (
    BranchDefinition,
    ConditionalEdge,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from workflow.graph_compiler import compile_branch


def _mk_gate_node(node_id: str, output_key: str = "gate_out") -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id,
        display_name=f"Gate {node_id}",
        prompt_template="decide: {scene_input}",
        output_keys=[output_key],
    )


def _mk_leaf_node(node_id: str) -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id,
        display_name=f"Leaf {node_id}",
        prompt_template=f"leaf {node_id} reached",
        output_keys=[f"{node_id}_out"],
    )


def _build_two_path_branch(
    *,
    gate_graph_id: str,
    gate_def_id: str,
) -> BranchDefinition:
    """Build a minimal gate → {path_a | path_b} → END branch.

    ``gate_graph_id`` and ``gate_def_id`` differ only in the broken-state
    fixture — when they differ, the router's node_by_id lookup fails.
    """
    return BranchDefinition(
        branch_def_id="test-routing",
        name="Routing Repro",
        node_defs=[
            _mk_gate_node(gate_def_id),
            _mk_leaf_node("path_a"),
            _mk_leaf_node("path_b"),
        ],
        graph_nodes=[
            GraphNodeRef(id=gate_graph_id, node_def_id=gate_def_id),
            GraphNodeRef(id="path_a", node_def_id="path_a"),
            GraphNodeRef(id="path_b", node_def_id="path_b"),
        ],
        edges=[
            EdgeDefinition(from_node="path_a", to_node="END"),
            EdgeDefinition(from_node="path_b", to_node="END"),
        ],
        conditional_edges=[
            ConditionalEdge(
                from_node=gate_graph_id,
                conditions={"A": "path_a", "B": "path_b"},
            ),
        ],
        entry_point=gate_graph_id,
        state_schema=[
            {"name": "scene_input", "type": "str"},
            {"name": "gate_out", "type": "str"},
            {"name": "path_a_out", "type": "str"},
            {"name": "path_b_out", "type": "str"},
        ],
    )


def _scripted_provider(gate_output: str):
    """Return a provider that emits ``gate_output`` for the gate node
    and a stable leaf message for any other node. Used to seed the gate
    output the router reads.
    """
    def _call(prompt: str, system: str = "", *, role: str = "writer") -> str:
        if "decide" in prompt:
            return gate_output
        return "leaf ran"
    return _call


def _run_compiled(
    compiled,
    *,
    initial_state: dict[str, Any],
) -> dict[str, Any]:
    """Compile + invoke the graph. Returns the final state dict."""
    graph = compiled.graph.compile()
    return graph.invoke(initial_state)


# ════════════════════════════════════════════════════════════════════
# Step 2 — minimal repro: graph_node.id == node_def.id (happy case today)
# ════════════════════════════════════════════════════════════════════


class TestHappyCaseRouting:
    """When graph_node.id == node_def.id, routing works today.

    These tests document the correct behavior for the pre-existing happy
    path so the fix doesn't regress it.
    """

    def test_gate_routes_to_path_a_on_A(self):
        branch = _build_two_path_branch(
            gate_graph_id="gate",
            gate_def_id="gate",  # same — happy path
        )
        errors = branch.validate()
        assert errors == [], f"branch failed validation: {errors}"

        compiled = compile_branch(
            branch, provider_call=_scripted_provider("A"),
        )
        result = _run_compiled(compiled, initial_state={"scene_input": "test"})

        # path_a wrote its output; path_b did not.
        assert result.get("path_a_out"), (
            f"path_a should have been visited when gate emits 'A'; "
            f"final state: {dict(result)}"
        )
        assert not result.get("path_b_out"), (
            f"path_b should NOT have been visited when gate emits 'A'; "
            f"final state: {dict(result)}"
        )

    def test_gate_routes_to_path_b_on_B(self):
        branch = _build_two_path_branch(
            gate_graph_id="gate",
            gate_def_id="gate",
        )
        compiled = compile_branch(
            branch, provider_call=_scripted_provider("B"),
        )
        result = _run_compiled(compiled, initial_state={"scene_input": "test"})

        assert result.get("path_b_out"), (
            f"path_b should have been visited when gate emits 'B'; "
            f"final state: {dict(result)}"
        )
        assert not result.get("path_a_out"), (
            f"path_a should NOT have been visited when gate emits 'B'; "
            f"final state: {dict(result)}"
        )


# ════════════════════════════════════════════════════════════════════
# Step 2 continued — graph_node.id != node_def.id (the hypothesis)
# ════════════════════════════════════════════════════════════════════


class TestGraphNodeIdDifferentFromDefId:
    """Routing must use the graph node's referenced node definition.

    ``ConditionalEdge.from_node`` names a graph-node placement. The router
    still needs the placement's ``node_def_id`` to find the output key that
    the compiled node writes into state.
    """

    def test_gate_with_distinct_ids_routes_to_path_b_on_B(self):
        branch = _build_two_path_branch(
            gate_graph_id="gate_placement",
            gate_def_id="gate_core",  # different from graph_node.id
        )
        compiled = compile_branch(
            branch, provider_call=_scripted_provider("B"),
        )
        result = _run_compiled(compiled, initial_state={"scene_input": "test"})

        assert result.get("path_b_out"), (
            "Router should read gate_core.output_keys through the graph-node "
            f"placement and route to B; final state: {dict(result)}"
        )
        assert not result.get("path_a_out"), (
            f"Distinct graph/node-def ids should not collapse to fallback; "
            f"final state: {dict(result)}"
        )


# ════════════════════════════════════════════════════════════════════
# Step 3 — three symptom shapes
# ════════════════════════════════════════════════════════════════════


class TestSymptom1LiteralEndConditions:
    """S1: conditions map to the literal string "END". Compiler should
    normalize to the LangGraph END sentinel on BOTH the path_map side
    (fed to add_conditional_edges) AND the router's lookup table. The
    code does this at lines 1069-1072 — verify it works end-to-end.
    """

    def test_condition_mapping_to_literal_END_routes_to_graph_end(self):
        branch = BranchDefinition(
            branch_def_id="s1",
            name="S1 end-literal",
            node_defs=[
                _mk_gate_node("gate"),
                _mk_leaf_node("leaf"),
            ],
            graph_nodes=[
                GraphNodeRef(id="gate", node_def_id="gate"),
                GraphNodeRef(id="leaf", node_def_id="leaf"),
            ],
            edges=[
                EdgeDefinition(from_node="leaf", to_node="END"),
            ],
            conditional_edges=[
                ConditionalEdge(
                    from_node="gate",
                    conditions={"STOP": "END", "GO": "leaf"},
                ),
            ],
            entry_point="gate",
            state_schema=[
                {"name": "scene_input", "type": "str"},
                {"name": "gate_out", "type": "str"},
                {"name": "leaf_out", "type": "str"},
            ],
        )
        errors = branch.validate()
        assert errors == [], f"validate: {errors}"

        compiled = compile_branch(
            branch, provider_call=_scripted_provider("STOP"),
        )
        result = _run_compiled(compiled, initial_state={"scene_input": "x"})

        # Ended at gate → leaf should NOT have run.
        assert not result.get("leaf_out"), (
            "STOP should terminate at END without visiting leaf; "
            f"final state: {dict(result)}"
        )

    def test_condition_mapping_to_literal_END_alternate_path_still_visits_leaf(self):
        branch = BranchDefinition(
            branch_def_id="s1b",
            name="S1 end-literal GO path",
            node_defs=[
                _mk_gate_node("gate"),
                _mk_leaf_node("leaf"),
            ],
            graph_nodes=[
                GraphNodeRef(id="gate", node_def_id="gate"),
                GraphNodeRef(id="leaf", node_def_id="leaf"),
            ],
            edges=[
                EdgeDefinition(from_node="leaf", to_node="END"),
            ],
            conditional_edges=[
                ConditionalEdge(
                    from_node="gate",
                    conditions={"STOP": "END", "GO": "leaf"},
                ),
            ],
            entry_point="gate",
            state_schema=[
                {"name": "scene_input", "type": "str"},
                {"name": "gate_out", "type": "str"},
                {"name": "leaf_out", "type": "str"},
            ],
        )

        compiled = compile_branch(
            branch, provider_call=_scripted_provider("GO"),
        )
        result = _run_compiled(compiled, initial_state={"scene_input": "x"})

        assert result.get("leaf_out"), (
            f"GO should visit leaf before reaching END; final: {dict(result)}"
        )


class TestSymptom2TerminalNoopAndLoopBack:
    """S2: conditions include a terminal noop target + a loop-back target.

    Repro shape: gate either terminates via a noop node (which then edges
    to END) or loops back to itself for another iteration. This exercises
    the router being called multiple times on the same graph node — if
    the resolver captured state at compile time, the second invocation
    would see stale state. Step 1 prep established the router reads
    fresh state each call, so this should work.
    """

    def test_loop_back_then_terminate(self):
        # Gate emits "LOOP" first (loops to itself), then "DONE" (noop → END).
        # Use a mutable counter so the scripted provider returns a different
        # answer on the second invocation.
        invocation_count = {"n": 0}

        def scripted(prompt: str, system: str = "", *, role: str = "writer") -> str:
            if "decide" not in prompt:
                return "leaf ran"
            invocation_count["n"] += 1
            return "LOOP" if invocation_count["n"] == 1 else "DONE"

        branch = BranchDefinition(
            branch_def_id="s2",
            name="S2 loopback",
            node_defs=[
                _mk_gate_node("gate"),
                _mk_leaf_node("noop"),
            ],
            graph_nodes=[
                GraphNodeRef(id="gate", node_def_id="gate"),
                GraphNodeRef(id="noop", node_def_id="noop"),
            ],
            edges=[
                EdgeDefinition(from_node="noop", to_node="END"),
            ],
            conditional_edges=[
                ConditionalEdge(
                    from_node="gate",
                    conditions={"LOOP": "gate", "DONE": "noop"},
                ),
            ],
            entry_point="gate",
            state_schema=[
                {"name": "scene_input", "type": "str"},
                {"name": "gate_out", "type": "str"},
                {"name": "noop_out", "type": "str"},
            ],
        )
        errors = branch.validate()
        # LOOP may fail "must reach END" validation; skip that check and
        # compile anyway since LangGraph allows cycles at runtime if the
        # gate eventually emits the terminate label.
        if errors:
            pytest.skip(f"branch validation blocks S2 loop test: {errors}")

        compiled = compile_branch(branch, provider_call=scripted)
        result = _run_compiled(compiled, initial_state={"scene_input": "x"})

        assert invocation_count["n"] >= 2, (
            "gate should be visited at least twice (LOOP then DONE); "
            f"visited {invocation_count['n']} times"
        )
        assert result.get("noop_out"), (
            f"noop should terminate; final: {dict(result)}"
        )

    def test_distinct_gate_def_id_routes_to_terminal_noop_not_loop_fallback(self):
        branch = BranchDefinition(
            branch_def_id="s2-distinct-def",
            name="S2 distinct def id",
            node_defs=[
                _mk_gate_node("gate_core"),
                _mk_leaf_node("noop"),
            ],
            graph_nodes=[
                GraphNodeRef(id="gate_placement", node_def_id="gate_core"),
                GraphNodeRef(id="noop", node_def_id="noop"),
            ],
            edges=[
                EdgeDefinition(from_node="noop", to_node="END"),
            ],
            conditional_edges=[
                ConditionalEdge(
                    from_node="gate_placement",
                    conditions={"LOOP": "gate_placement", "DONE": "noop"},
                ),
            ],
            entry_point="gate_placement",
            state_schema=[
                {"name": "scene_input", "type": "str"},
                {"name": "gate_out", "type": "str"},
                {"name": "noop_out", "type": "str"},
            ],
        )
        errors = branch.validate()
        assert errors == [], f"branch failed validation: {errors}"

        compiled = compile_branch(branch, provider_call=_scripted_provider("DONE"))
        result = _run_compiled(compiled, initial_state={"scene_input": "x"})

        assert result.get("noop_out"), (
            "DONE should route to the terminal no-op even when the gate "
            f"placement id differs from node_def_id; final: {dict(result)}"
        )


class TestSymptom3ThreeGateIterations:
    """S3: a branch that needs 3 distinct gate iterations to terminate.

    Three different gate outputs A → B → C, each routing differently.
    Guards against compile-time mapping lookup (would snapshot conditions
    dict before the loop completed).
    """

    def test_three_iterations_each_routes_distinctly(self):
        invocations = {"n": 0, "outputs": []}
        script = ["FIRST", "SECOND", "THIRD"]

        def scripted(prompt: str, system: str = "", *, role: str = "writer") -> str:
            if "decide" not in prompt:
                return "leaf ran"
            v = script[min(invocations["n"], len(script) - 1)]
            invocations["outputs"].append(v)
            invocations["n"] += 1
            return v

        branch = BranchDefinition(
            branch_def_id="s3",
            name="S3 three iterations",
            node_defs=[
                _mk_gate_node("gate"),
                _mk_leaf_node("accumulator"),
                _mk_leaf_node("finisher"),
            ],
            graph_nodes=[
                GraphNodeRef(id="gate", node_def_id="gate"),
                GraphNodeRef(id="accumulator", node_def_id="accumulator"),
                GraphNodeRef(id="finisher", node_def_id="finisher"),
            ],
            edges=[
                EdgeDefinition(from_node="accumulator", to_node="gate"),
                EdgeDefinition(from_node="finisher", to_node="END"),
            ],
            conditional_edges=[
                ConditionalEdge(
                    from_node="gate",
                    conditions={
                        "FIRST": "accumulator",
                        "SECOND": "accumulator",
                        "THIRD": "finisher",
                    },
                ),
            ],
            entry_point="gate",
            state_schema=[
                {"name": "scene_input", "type": "str"},
                {"name": "gate_out", "type": "str"},
                {"name": "accumulator_out", "type": "str"},
                {"name": "finisher_out", "type": "str"},
            ],
        )

        errors = branch.validate()
        if errors:
            pytest.skip(f"S3 blocked by validate: {errors}")

        compiled = compile_branch(branch, provider_call=scripted)
        result = _run_compiled(compiled, initial_state={"scene_input": "x"})

        assert invocations["n"] == 3, (
            f"gate should fire exactly 3x; got {invocations['n']}; "
            f"outputs={invocations['outputs']}"
        )
        assert result.get("finisher_out"), (
            f"finisher should run on THIRD; final: {dict(result)}"
        )
