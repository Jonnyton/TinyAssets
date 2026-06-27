---
name: conditional-edge-testing
description: Enforces compile+invoke discipline for conditional-edge branches. Use when adding or changing tests, graph compilation, BranchDefinition conditional_edges behavior, or regressions related to BUG-019/021/022 routing.
---

# Conditional-edge compile+invoke testing

## The rule

Any test that constructs a `BranchDefinition` with a non-empty
`conditional_edges` list MUST also exercise the runtime path. Shape:

1. **Build** the branch spec (or obtain it via serializer / MCP surface).
2. **Compile** via `workflow.graph_compiler.compile_branch(...)` with a
   scripted `provider_call` that seeds the gate's `output_keys[0]`.
3. **Invoke** via `compiled.graph.compile().invoke(initial_state)`.
4. **Assert terminal state** — check the target-node's output_key got
   populated, and the non-selected-path's output_key did not.

Validation (`branch.validate()`) + serialization round-trip + storage
tests are NECESSARY but NOT SUFFICIENT. The Tier-1 investigation (2026-04-24,
task #7) surfaced a router/LangGraph contract inversion that survived months
because no test compiled+invoked a conditional_edges branch end-to-end.

## Why this shape

LangGraph's `add_conditional_edges(source, router, path_map)` is a
two-sided contract:
- The `router` callable returns a KEY.
- `path_map` (dict) looks that key up → target node.

If either side diverges from the other (e.g., router returns a target
name instead of a key), `graph.invoke` raises `KeyError` deep in
LangGraph. That error never surfaces in validation/storage tests
because those never drive the graph.

## Canonical example

`tests/test_conditional_routing_resolver.py` (new in #7).

- `TestHappyCaseRouting` — gate emits "A" → path_a runs; gate emits
  "B" → path_b runs.
- `TestSymptom1LiteralEndConditions` — `conditions={"STOP": "END"}`
  normalizes the literal "END" string → LangGraph's END sentinel.
- `TestSymptom2TerminalNoopAndLoopBack` — gate invoked twice reads
  fresh state each call (not closure-captured).
- `TestSymptom3ThreeGateIterations` — 3 distinct gate outputs each
  route distinctly (not compile-time mapping capture).

## Canonical regression guard

`tests/test_conditional_edges_compile_invoke.py::TestContractInversionRegressionGuard`
keeps a hand-built pre-fix router (returns a target, not a label) and
asserts `graph.invoke` raises `KeyError`. If someone reverts the fix in
`tinyassets/graph_compiler.py:_build_conditional_router`, that test goes
red immediately.

## Scripted provider helper

Any test exercising a conditional-edge branch needs a provider that
returns the gate's decision value. Minimal pattern:

```python
def _scripted_provider(gate_output: str, *, gate_marker: str = "decide"):
    def _call(prompt, system="", *, role="writer"):
        if gate_marker in prompt:
            return gate_output
        return "leaf ran"
    return _call
```

Pass as `compile_branch(branch, provider_call=_scripted_provider("A"))`.
The prompt_template's placeholder substitution produces a prompt
containing "decide" (because the gate node's template is
`"decide: {scene_input}"`); the scripted provider sees that and returns
"A", which populates `state["gate_out"]`, which the router reads.

## When to skip the invoke leg

If your test is strictly about validation errors (e.g. "a branch
referencing a missing conditional-edge target fails validate()"), you
don't need to invoke — the validator catches it pre-compile. Keep the
validation test as-is and add a sibling invoke test that exercises
the valid-case path.

## Catalog of files that NEED this coverage (audit 2026-04-24)

- `tests/test_branches.py` — validation + serialization only. Gap:
  no compile+invoke of constructed branches.
- `tests/test_branch_definitions_db.py` — storage round-trip. Gap:
  no compile+invoke after DB restore.
- `tests/test_storage_phase7_serializer.py` — YAML round-trip
  identity. **Covered** by `test_conditional_edges_compile_invoke.py::TestYamlRoundTripStillRoutes`.
- `tests/test_conditional_edges_surface.py` — MCP build_branch /
  patch_branch surface. Gap: no post-build invoke.
- `tests/test_branch_visibility.py` — auth/visibility with empty
  conditional_edges fixtures. No routing semantics; skip.
- `tests/test_worldbuild_noop_integration.py` — uses LangGraph
  directly, not BranchDefinition. Different seam; skip.
- `tests/test_graph_topology.py` — tests hand-written router
  functions directly (not the BranchDefinition path). Not the same
  surface; skip.

Add compile+invoke coverage when touching any file in the first group.
