# Sub-Branch Invocation Primitive Audit

**Date:** 2026-04-25
**Author:** dev
**Scope:** read-only audit of BUG-005 sub-branch invocation. Answers 6 questions about today's primitive, gaps for gate-routing-back-to-canonical, and the variant-vs-version axis. NO redesign. Lead routes redesign as follow-up.
**Surfaces read:** `tinyassets/branches.py` (lines 215-243 NodeDefinition fields, 920-960 validate); `tinyassets/graph_compiler.py` (lines 1185-1380 invoke/await builders); `tinyassets/runs.py` (lines 2087-2129 sub-branch helpers, 1388-1500 execute_branch entry points); `tests/test_sub_branch_invocation.py`; `docs/design-notes/2026-04-25-self-evolving-platform-vision.md`; `docs/audits/2026-04-23-navigator-full-corpus-synthesis.md` §B4; `docs/audits/2026-04-25-canonical-primitive-audit.md` (G1, dev-2-2). Wiki page `bugs/BUG-005` not present in `$APPDATA/Workflow/wiki/pages/bugs/` — bug content reconstructed from design-doc references.

---

## Summary

Sub-branch invocation **partially exists** in the engine. It is implemented as a **graph-internal primitive**: a `NodeDefinition` carries an `invoke_branch_spec` field declaring which child branch to spawn, parent→child input mapping, child→parent output mapping, and a `wait_mode` ("blocking" or "async"). A companion `await_run_spec` field on a separate node kind polls a previously-spawned async child. The graph compiler builds runtime callables from these specs; `workflow.runs.execute_branch` / `execute_branch_async` is the actual spawner. A recursion-depth cap of 5 prevents circular invocation chains.

What does NOT exist:

1. **No MCP-level `invoke_branch` action.** Sub-branch invocation is callable only from inside a graph definition's `NodeDefinition`, not from chatbot intent or external dispatch. There is no `runs action=invoke` or similar verb.
2. **No `branch_version_id` support.** `execute_branch` / `execute_branch_async` accept a live `BranchDefinition` (resolved from `branch_def_id`), not an immutable `branch_version_id`. This is the same blocker as G1 audit gap row #6 ("NO RUN-FROM-VERSION PRIMITIVE") — canonical-bound code paths cannot run a frozen-snapshot canonical via the sub-branch primitive.
3. **No gate-aware "send back to canonical for goal X" verb.** The G1 audit established that there is no first-class router primitive at all (gap row #4 — "no routing primitive exists"); the sub-branch primitive doesn't add one. A gate node that wants to invoke the canonical for goal G must (a) read the goal via `goals action=get`, (b) extract `canonical_branch_version_id`, (c) … hit the version-id gap above.
4. **No state-merge contract.** Output mapping is whatever the parent declares in the spec. There is no schema validation that the child's output keys exist or have compatible types — runtime returns `None` silently for missing keys.
5. **No failure propagation contract.** Child failures return a RunOutcome with non-completed status; the parent node receives `outcome.output.get(...)` which may yield None or stale partial output. No first-class error-as-data, no parent-fails-on-child-fail toggle.
6. **No concurrency budget mediation between parent and child.** Parent and child each call `execute_branch` independently; their `concurrency_budget_override` does not transfer or pool. Async children spawn into the same shared executor pool as standalone runs.

For Mark's gate-series user-story ("if any gate rejects, route patch_notes back to MY canonical for goal G"), the sub-branch primitive is the right substrate — but the path from gate-decision to actually-running-the-canonical needs (i) version-id execution, (ii) MCP-callable invocation, and (iii) goal-aware routing. Items (i) and (iii) are also flagged in the G1 audit; item (ii) is sub-branch-specific.

---

## A. What is BUG-005?

**Wiki page does not exist on the live wiki at `$APPDATA/Workflow/wiki/pages/bugs/`.** The `bugs/` directory holds only BUG-001, BUG-002, BUG-004, and INDEX.md. BUG-005's content has not been filed at the canonical location — likely retained as concept-only in design discussions, never typed into wiki form.

Reconstructed intent from the navigator full-corpus synthesis (`docs/audits/2026-04-23-navigator-full-corpus-synthesis.md` §B4) and the self-evolving-platform vision (`docs/design-notes/2026-04-25-self-evolving-platform-vision.md` lines 79, 116, 194):

> **Sub-branch invocation primitive.** Today every workflow is monolithic (the 22-node `agent_team_20` flattened everything into one graph). Without sub-branch invocation, the canonical starter-branch model doesn't compose — "a literature-review workflow invokes a source-triage sub-workflow" cannot be expressed as graph composition. The Goals-engine story (Pillar 3 Layer-4) depends on composable branches; gates can decide but can't route work back through canonicals without a sub-branch primitive.

So BUG-005 names the **load-bearing engine substrate** for: (a) gate-rejection routing back to a canonical, (b) workflow composition (one branch invokes another), (c) the Goals-engine convergence story.

**Blast radius if absent:** sweep through agent_team_20 in `domains/`. Any node that today is "embedded inline" because we couldn't invoke a sub-branch is technical debt — those nodes can't be independently versioned, gated, or evaluated.

---

## B. What exists today

### B.1 Schema: `invoke_branch_spec` on NodeDefinition

`tinyassets/branches.py:222-234`

```python
# Sub-branch invocation (invoke_branch node kind).
# When set this node spawns a child branch run rather than executing an
# LLM template or source-code snippet.
# Shape: {
#   "branch_def_id": str,
#   "inputs_mapping": {parent_state_key: child_input_key},
#   "output_mapping": {parent_state_key: child_output_key},
#   "wait_mode": "blocking" | "async",
# }
# "blocking": spawns the child, waits for completion, writes output_mapping.
# "async": spawns the child, writes run_id to the declared
#   output_mapping[0] target key, returns immediately.
invoke_branch_spec: dict[str, Any] | None = None
```

**Companion field** `await_run_spec` (lines 236-243):

```python
# await_branch_run node kind. Reads a run_id from parent state, polls
# until the child run ends, writes output_mapping into parent state.
# Shape: {
#   "run_id_field": str,       # state key that holds the child run_id
#   "output_mapping": {parent_state_key: child_output_key},
#   "timeout_seconds": float,  # default 300
# }
await_run_spec: dict[str, Any] | None = None
```

The two specs together form a fork–join pattern: an `invoke_branch_spec` node with `wait_mode="async"` writes a `run_id` into parent state; later, an `await_run_spec` node reads that `run_id` from state and joins.

### B.2 Validation: `BranchDefinition.validate()`

`tinyassets/branches.py:920-960`. Catches:
- Missing `branch_def_id` in spec.
- Invalid `wait_mode` (must be "blocking" or "async").
- Mutually-exclusive: a node with `invoke_branch_spec` cannot also have `prompt_template` or other execution kinds.
- Missing `run_id_field` in `await_run_spec`.

### B.3 Runtime: `_build_invoke_branch_node`

`tinyassets/graph_compiler.py:1189-1261`. Constructs a closure that:
1. Loads child `BranchDefinition` via `get_branch_definition(base_path, child_branch_def_id)`.
2. Maps parent state keys to child input keys per `inputs_mapping`.
3. If blocking: calls `execute_branch(base_path, branch=child, inputs=child_inputs)`, then maps `outcome.output` back to parent state per `output_mapping`. Returns parent-state updates.
4. If async: calls `execute_branch_async(...)`, writes the returned `run_id` into the first key in `output_mapping`. Returns parent-state updates.

### B.4 Runtime: `_build_await_branch_run_node`

`tinyassets/graph_compiler.py:1264-1380`. Constructs a closure that:
1. Reads `run_id` from parent state via `run_id_field`.
2. Calls `poll_child_run_status(base_path, run_id, timeout_seconds=...)`.
3. If completed: extracts `output_json` from the run record, maps to parent state per `output_mapping`. Returns parent-state updates.
4. If timed out: raises `TimeoutError`.
5. If run_id missing from state: raises `RuntimeError`.

### B.5 Recursion cap

`tinyassets/runs.py:2091-2093`:
```python
#: Maximum nesting depth for invoke_branch nodes. A child run increments
#: the depth counter; reaching this cap raises CompilerError at runtime.
MAX_INVOKE_BRANCH_DEPTH = 5
```

The compiler raises `CompilerError` at depth 5 (`graph_compiler.py:1222-1226`). Each invoke_branch node compilation increments depth.

### B.6 Polling: `poll_child_run_status`

`tinyassets/runs.py:2103-2129`. Blocks until run reaches `RUN_STATUS_COMPLETED | RUN_STATUS_FAILED | RUN_STATUS_CANCELLED | RUN_STATUS_INTERRUPTED`. Default poll interval 1s, default timeout 300s. Raises `KeyError` for unknown run_id, `TimeoutError` on deadline.

### B.7 Tests

`tests/test_sub_branch_invocation.py`. Coverage:
- `validate()` shape errors for missing/invalid spec fields, mutually-exclusive collisions.
- `_build_invoke_branch_node` blocking vs async modes.
- `_build_await_branch_run_node` polling and timeout.
- `poll_child_run_status` terminal status, missing run_id.
- Recursion-depth cap raises CompilerError.

Tests are unit-level. No integration test that builds a real parent→child→grandchild composite branch and runs it end-to-end through the daemon.

---

## C. State-sharing model

**Each child run has independent state.** Parent and child do NOT share a checkpoint, do NOT share a state dict, and do NOT see each other's intermediate values. Communication is strictly through the explicit `inputs_mapping` (parent→child) and `output_mapping` (child→parent) pinches.

**State-schema check:** the runtime does NOT validate that `output_mapping`'s child-side keys exist in the child's `state_schema`, nor that types match. If the child branch never writes `result_text` and the parent's `output_mapping` is `{"my_text": "result_text"}`, the parent's `my_text` becomes `None` silently.

**Nested-context flow:** the `_universe_path` and `actor` are not propagated automatically. The `execute_branch` call in `_build_invoke_branch_node` (graph_compiler.py:1242) defaults `actor` to whatever `execute_branch`'s default is (`"anonymous"` per signature line 1394), NOT the parent's actor. **This is a likely-unintended attribution gap:** child runs are credited to "anonymous" rather than the parent's actor.

---

## D. branch_def_id vs branch_version_id

**The primitive is `branch_def_id`-only.** `invoke_branch_spec.branch_def_id` is required; there is no `branch_version_id` slot. `_build_invoke_branch_node` calls `get_branch_definition(base_path, child_branch_def_id)` (line 1234) which loads the LIVE editable definition.

This means:
- A canonical (which is a `branch_version_id` per G1 audit) cannot be invoked as a sub-branch directly. The caller would need to (a) resolve the version_id back to the original def_id and load THAT, losing the immutability guarantee, OR (b) wait for the runner to support version_id.
- If a published version's definition is later edited via `update_branch_definition`, every parent with `invoke_branch_spec.branch_def_id=<that_id>` silently picks up the change. This is intentional for live-editing semantics during a session, but undesirable for canonical routing.
- There is no "pin a sub-branch to a frozen version" verb.

**Cross-reference G1 audit gap row #6:** "NO RUN-FROM-VERSION PRIMITIVE. Today branches run via `run_branch_def_id` (live editable definition). The canonical is a published `branch_version_id` (immutable snapshot). The runner doesn't accept `branch_version_id` as input." That gap is the same gap surfaced here through the sub-branch lens; closing the runner-side version-id gap unblocks BOTH the G1 canonical-routing story AND the BUG-005 gate-routing story.

**Possible bridge shapes (no design here, scoping only):**
1. New parameter `branch_version_id` on `execute_branch` / `execute_branch_async`. When set, resolves version → def from `branch_versions` table, loads def at that version's snapshot point, runs against that. Requires version-snapshot reconstruction logic.
2. New `invoke_branch_spec.branch_version_id` slot, mutually exclusive with `branch_def_id`. Compiler-side resolves version → def at compile time.
3. New `run_branch_version` MCP action (mentioned in G1 audit gap row #4 and self-evolving vision §A row 6) plus parallel `invoke_branch_version_spec` on NodeDefinition.

Each has cascading test/migration cost. None are landed.

---

## E. Concurrency model

**No coordination between parent and child concurrency.** Both blocking and async modes call into `execute_branch` / `execute_branch_async` which use the same global executor pool (`tinyassets/runs.py:_DEFAULT_MAX_WORKERS = 4`). Behaviors:

- **Blocking sub-branch:** the parent's calling thread blocks inside `execute_branch`. Inside that call, child nodes execute synchronously on the SAME thread (per the SqliteSaver-only constraint and the in-process synchronous `app.invoke`). No concurrency hazard, but parent throughput is gated 1:1 on child throughput.
- **Async sub-branch:** the parent fires a worker into the executor and returns immediately. The parent and child run concurrently. **Parent's `concurrency_budget_override` is NOT propagated to the child run.** Each child run independently consumes from the shared pool. Pathological case: a parent with 4 async-fan-out invoke_branch nodes immediately consumes the entire executor pool plus its own slot, starving sibling parent runs.
- **Recursion-depth cap is a graph-build-time check, not a runtime concurrency check.** A 4-deep chain of blocking invocations holds 4 worker threads simultaneously across the SAME parent-trace until the leaf returns.

There is no "parent waits in a lower-priority queue while child runs" pattern. The dispatcher (`workflow.dispatcher`) handles request-level priority but does not distinguish parent-blocked-by-child from parent-doing-work.

**Failure pattern to flag:** if `_DEFAULT_MAX_WORKERS=4` and 4 parents each blocking-invoke a child, the child cannot acquire a worker → deadlock. The current code does not detect this; it would manifest as `execute_branch` taking unbounded time inside `_invoke_graph`'s `app.invoke` loop. **This is real risk for any production multi-tenant workload.**

---

## F. Failure propagation

**Today's contract: child failure returns a RunOutcome with non-completed status; parent node receives whatever `outcome.output.get(...)` yields.**

`_build_invoke_branch_node` (graph_compiler.py:1242-1259) does NOT inspect `outcome.status`. It only reads `outcome.output`:

```python
outcome = execute_branch(_base, branch=child_branch, inputs=child_inputs)
updates = {}
for parent_key, child_key in output_mapping.items():
    updates[parent_key] = outcome.output.get(child_key)
return updates
```

Implications:
- Child fails before writing any output → `outcome.output.get(child_key)` returns `None` → parent state has None where the spec promised content. Parent continues silently with bad data.
- Child fails partway after writing some output → parent gets partial output; subsequent parent nodes may produce nonsense.
- Child times out (async + await_branch) → the await node raises TimeoutError → parent run's invoke fails with that exception per LangGraph's exception path.
- Child run not found at await time → KeyError raised; surfaces same way.

**No first-class:**
- "Parent fails if child fails" toggle.
- "Default-on-child-fail" output value.
- Error propagation as structured data (current contract just relies on dict's `.get(... , None)` defaulting).
- Retry-the-child-N-times policy.

For gate-routing-back-to-canonical, the absence of structured failure propagation is **important.** A gate-rejection that fires a sub-branch and the sub-branch silently fails is precisely the failure mode that breaks the auto-heal loop. Any redesign must surface this.

---

## G. Gap list (priority-ranked, gate-routing focus)

Cross-referenced with G1 audit gap list where overlapping.

| # | Gap | Severity for gate-routing | Severity for platform | Cross-ref |
|---|---|---|---|---|
| **1** | No `branch_version_id` support in `execute_branch` / `invoke_branch_spec`. Cannot invoke a canonical (which is a frozen version). | **Blocking** | High | Same as G1 row #6. Closing this unblocks BOTH stories. |
| **2** | No MCP-callable `runs action=invoke` (or similar) for spawning a sub-branch from chatbot/external intent. Only graph-internal NodeDefinition can spawn. | **Blocking** for chatbot-driven gate routing; **non-blocking** for graph-internal gate routing | Medium | Sub-branch-specific. |
| **3** | No goal-aware "send to canonical for goal X" verb wrapping the lookup+invoke chain. | **Blocking** | High | Same as G1 row #4. |
| **4** | No structured failure propagation contract between child and parent. Silent None-substitution on child fail. | **High** for auto-heal (sub-branch fails silently → parent emits bad data) | High | Sub-branch-specific. |
| **5** | Child runs default `actor="anonymous"` instead of inheriting parent's actor. Attribution gap. | Low for routing, **Medium** for attribution ledger (Phase B work). | Medium | Cross-cuts Phase B ContributionEvent ledger work. |
| **6** | No concurrency-budget propagation parent→child. Pool starvation possible. | Low immediately, **Blocking** at scale (multi-tenant). | High at scale | Sub-branch-specific. |
| **7** | No state-schema validation of `output_mapping` keys against child's declared schema. Silent typo → None. | Medium for any composite branch correctness | Medium | Sub-branch-specific. |
| **8** | No "pin sub-branch to a specific version_id" affordance. Live def edits silently change sub-branch behavior. | Medium (closely related to #1; the version_id support naturally implies pinning) | Medium | Implied by #1. |
| **9** | No retry-on-child-fail policy. If gate routes to canonical and canonical's deploy is mid-flight, no retry. | Medium for auto-heal robustness | Medium | Sub-branch-specific. |
| **10** | Recursion cap is compile-time only, not runtime-concurrency-aware. Deadlock under tight worker pool. | Low for now (small pool, low usage) | High at scale | Sub-branch-specific. |
| **11** | No integration test for parent→child→grandchild end-to-end through daemon. Unit tests only. | Low for routing, **Medium** for confidence | Medium | Sub-branch-specific. |

**Minimal viable path to unblock Mark's gate-series story** (sub-branch-routing slice):
- Gap **#1** (version_id execution) — required for invoking a canonical at all.
- Gap **#2** (MCP-callable invoke) — required if the gate routes via a chatbot intent rather than baked-in graph node.
- Gap **#3** (goal-aware verb) — required to compose "for goal G, find canonical, invoke it." Same as G1 minimum.
- Gap **#4** (failure propagation) — required for auto-heal correctness; without it, sub-branch failures cause silent corruption.

The other gaps (#5–#11) are non-blocking for first-cut; they become important for production-grade attribution, scale, and robustness.

---

## H. What this audit does NOT cover

- **No design proposal.** The gap list names what's missing; a design pass would propose schema migrations, MCP action shapes, API surface, and migration plans.
- **No live MCP probes.** Paper audit only.
- **No code changes.** Read-only; the existing primitive remains as-is.
- **No BUG-005 wiki content reconstruction.** The wiki page does not exist on disk; this audit's "what is BUG-005" reconstruction is from design-doc references, NOT the user's original filing. If the user has additional content in chatbot history that was never typed into the wiki, this audit doesn't see it.
- **No agent_team_20 sweep.** Identifying which monolithic graph nodes today should become sub-branches is a separate factoring exercise. This audit only confirms the primitive exists for that factoring.
- **No cross-tenant security analysis.** When chatbot A invokes chatbot B's branch via sub-branch, what authority context does the child run under? Out of scope.

---

## References

- Schema: `tinyassets/branches.py` lines 215-243 (NodeDefinition fields), 920-960 (validate).
- Compiler: `tinyassets/graph_compiler.py` lines 1185-1380 (`_build_invoke_branch_node`, `_build_await_branch_run_node`).
- Runtime: `tinyassets/runs.py` lines 1388-1500 (`execute_branch`, `execute_branch_async`), 2087-2129 (`MAX_INVOKE_BRANCH_DEPTH`, `poll_child_run_status`).
- Tests: `tests/test_sub_branch_invocation.py`.
- Cross-reference G1 audit: `docs/audits/2026-04-25-canonical-primitive-audit.md` (gaps #4, #6 overlap with this audit's #3, #1).
- Strategic context: `docs/audits/2026-04-23-navigator-full-corpus-synthesis.md` §B4; `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` lines 79, 116, 194; `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md` row #5.
- Wiki: `bugs/BUG-005` page does not exist at `$APPDATA/Workflow/wiki/pages/bugs/` as of 2026-04-25.
