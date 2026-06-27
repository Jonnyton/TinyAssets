---
status: active
---

# BUG-005 Sub-Branch Invocation — Closure Proposal

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Closes BUG-005 by extending the existing partially-implemented primitive.
**Builds on:** dev's audit `docs/audits/2026-04-25-sub-branch-invocation-audit.md` (commit `6943d60`); my Task #54 sibling-action pattern (committed `dc7d2cb`); my Task #47 variant canonicals; Task #59 (`goals action=resolve_canonical` — queued).
**Scope:** schema/contract/runtime design only. No code changes.

---

## 1. Recommendation summary — extend, don't replace

The audit confirmed sub-branch invocation IS partially implemented: `invoke_branch_spec` + `await_run_spec` on `NodeDefinition`, recursion cap of 5, blocking + async modes. This proposal closes the 4 blocking gaps for Mark's gate-series story (audit gaps #1, #2, #4, #10) by extending the existing primitive, not replacing it.

Four sub-decisions:

1. **MCP exposure: graph-spec-only.** No new `runs action=invoke_branch` verb. Chatbots compose via `extensions action=patch_branch` to add an `invoke_branch_spec` to a node — uniform with every other node shape.
2. **branch_version_id: sibling spec field `invoke_branch_version_spec`.** Mirrors #54's sibling-action pattern. Mutually exclusive with `invoke_branch_spec`; validate at branch-validate time.
3. **Failure propagation: structured `outcome.child_failures` + per-spec `on_child_fail` policy.** Three policies (`propagate` default / `default` / `retry`). Auto-heal-correctness wins over silent continue.
4. **Pool starvation: separate child-execution pool sized `MAX_INVOKE_BRANCH_DEPTH + 1 = 6`.** Two-pool model prevents the parent-holds-own-slot deadlock.

Each decision is additive on the existing schema; no current callers break.

---

## 2. MCP exposure — graph-spec-only

**Decision: do NOT add a `runs action=invoke_branch` MCP verb.**

Sub-branch invocation is a graph composition primitive, not a chatbot-driven action. The audit gap #2 ("no MCP-callable invoke") is real but solving it the obvious way (new MCP verb) breaks the parent-child state-mapping contract. A chatbot calling `runs action=invoke_branch branch_def_id=X inputs=Y` has no parent state to map TO; it would either:

- Need a separate "input source" arg that mirrors the existing `inputs_json` on `run_branch` — at which point it's just `run_branch` with extra ceremony.
- Need a "parent state" arg shaped as a dict — at which point chatbots are constructing parent-state JSON outside any graph context, which is the exact unsafe state-shape that immutable canonicals exist to prevent.

The right primitive is the existing graph-shape edit. Chatbot intent: "I want a gate to route patches through canonical X." Chatbot action: `extensions action=patch_branch` adds an `invoke_branch_version_spec` node to the gate's reject path. Same MCP shape as adding any other node. The compiler builds the runtime; the runner runs it.

**The chatbot-level discoverability concern** (sub-branch invocation invisible in MCP catalog) is real — but it's solved by tool-description text on `extensions action=patch_branch`, not by a new MCP verb.

---

## 3. branch_version_id support — sibling spec field

Mirrors my #54 sibling-action pattern. Two `NodeDefinition` fields:

| Field | Source | Use for |
|---|---|---|
| `invoke_branch_spec` (existing) | live `branch_def_id` | Composition during dev / when canonical isn't yet pinned. |
| `invoke_branch_version_spec` (NEW) | frozen `branch_version_id` | Production routing where immutability matters (gate routing back to canonical). |

### Schema

```python
# tinyassets/branches.py — NodeDefinition gets a new optional field
@dataclass
class NodeDefinition:
    # ... existing fields ...
    invoke_branch_spec: dict[str, Any] | None = None
    invoke_branch_version_spec: dict[str, Any] | None = None  # NEW
    await_run_spec: dict[str, Any] | None = None
```

`invoke_branch_version_spec` shape:

```python
{
    "branch_version_id": str,                # required, e.g. "<def_id>@<sha8>"
    "inputs_mapping": {parent_state_key: child_input_key},
    "output_mapping": {parent_state_key: child_output_key},
    "wait_mode": "blocking" | "async",
    "on_child_fail": "propagate" | "default" | "retry",  # NEW, see §4
    "default_outputs": dict | None,         # used when on_child_fail="default"
    "retry_budget": int | None,             # used when on_child_fail="retry"
    "child_actor": str | None,              # NEW, override actor inheritance — see §6
}
```

### Validation

`BranchDefinition.validate()` (extending `tinyassets/branches.py:920-960`):

- A node MUST NOT carry both `invoke_branch_spec` AND `invoke_branch_version_spec` — mutually exclusive (matches the existing rule that a node can't have both `invoke_branch_spec` and `prompt_template`).
- `branch_version_id` is required when `invoke_branch_version_spec` is set.
- `output_mapping` keys are validated against the resolved child's `state_schema` at branch-validate time (audit gap #7 — strict, not warn-at-runtime per Q3).
- For version specs: `branch_version_id` must exist in `branch_versions` table at validate time (catches typo-canonical-version IDs at compose, not run).

### Runtime: sibling compiler builder

`tinyassets/graph_compiler.py` gains `_build_invoke_branch_version_node` mirroring `_build_invoke_branch_node` (lines 1189-1261). The new builder calls `execute_branch_version_async` (the helper from #54, now committed) instead of `execute_branch`. Otherwise identical.

The shared `_DispatchInvokeBranchCommon` helper (NEW) holds the input-mapping + output-mapping + on_child_fail logic so the two builders don't duplicate. Both call into it.

---

## 4. Failure propagation — `child_failures` + `on_child_fail`

The audit established that today's `_build_invoke_branch_node` does NOT inspect `outcome.status`; it reads `outcome.output.get(child_key)` and substitutes `None` on missing keys. This is the auto-heal failure-class breaker.

### Structured outcome extension

```python
# tinyassets/runs.py — RunOutcome gains a new field (NULLABLE, additive)

@dataclass
class ChildFailure:
    run_id: str
    failure_class: Literal["child_failed", "child_timeout", "child_cancelled", "child_unknown"]
    child_status: str           # the child's terminal RUN_STATUS
    partial_output: dict | None # whatever the child wrote before failing

@dataclass
class RunOutcome:
    # ... existing fields ...
    child_failures: list[ChildFailure] = field(default_factory=list)  # NEW
```

A parent run with no sub-branch invocations has `child_failures == []` (no behavior change). A parent that invoked children and saw any non-completed terminal status has structured entries the parent's downstream graph can inspect. Tasks #48 contribution ledger emits `caused_regression` events on `child_failures` entries — closes that surface gap too.

### Per-spec `on_child_fail` policy

Each `invoke_branch_spec` and `invoke_branch_version_spec` carries:

```python
on_child_fail: Literal["propagate", "default", "retry"] = "propagate"
```

| Policy | Engine behavior |
|---|---|
| `"propagate"` (default) | Parent run terminates with structured error including the `ChildFailure`. Downstream nodes in the parent do NOT execute. **Auto-heal-correctness default.** |
| `"default"` | Parent continues. `output_mapping` fields populate from `default_outputs` dict in the spec, OR `None` if no defaults declared. The `ChildFailure` row still appears in `outcome.child_failures` for observability. |
| `"retry"` | Engine re-fires the child up to `retry_budget` times (per-spec, default 1; global cap below). Each retry creates a fresh child run_id. If all retries exhaust, behavior falls through to `"propagate"`. |

### Retry budget — per-spec with global cap

Per-spec `retry_budget` (default 1) lets a chatbot mark a critical sub-branch as more aggressive without making every sub-branch retry-heavy. **Global cap `TINYASSETS_MAX_CHILD_RETRIES_TOTAL` env var (default 5)** prevents retry-storm pathology — across all sub-branch retries in a single parent run, no more than N retries fire in total. Cap reached → behaves like `"propagate"` regardless of per-spec budget.

### Why default=propagate

Auto-heal correctness wins over silent continue. The audit gap #4 is "child fails silently → parent emits bad data" — that's a class of bug that destroys the auto-heal feedback loop. `propagate` makes child failures visible at the parent level; gate-series can then act on the failure (route-back per #53, retry, escalate).

---

## 5. Pool starvation — two-pool model

The audit gap #10 + the 4-deep-blocking deadlock pattern establish the risk: with `_DEFAULT_MAX_WORKERS=4` and `MAX_INVOKE_BRANCH_DEPTH=5`, four parents each blocking-invoking can deadlock.

### Two-pool model

```
parent_pool: ThreadPoolExecutor(max_workers=TINYASSETS_RUN_POOL_SIZE, default 4)
  - Top-level runs (no parent context) execute here.

child_pool: ThreadPoolExecutor(max_workers=TINYASSETS_CHILD_POOL_SIZE, default 6)
  - Child runs (any depth ≥ 1) execute here.
  - Sized MAX_INVOKE_BRANCH_DEPTH + 1 by default.
```

A parent-pool slot held by a parent doing `_invoke_graph` waits in I/O on the blocking sub-branch result; the child gets its own slot from `child_pool`. Pools never compete for the same resource. Deadlock impossible.

### Why two-pool, not depth-priority queueing

The alternative — single pool with priority-queue based on depth — was considered. Rejected because:

1. The deadlock root cause is "parent holds its own slot while waiting on child." Depth-priority doesn't solve this; it just reorders WHICH starved parent waits longest.
2. Depth-priority needs runtime depth-tracking on every dispatch; brittle.
3. Two-pool is dead-simple to reason about. Each pool is independent. Each pool's exhaustion only blocks ITS own caller class.

### Pool sizing rationale

Default child pool size = `MAX_INVOKE_BRANCH_DEPTH + 1 = 6`. Reasoning:

- A 5-deep invocation chain needs 5 simultaneous child slots (one per level beyond root).
- +1 buffer slot lets a sibling at any level fire without blocking on the deepest chain.
- Under steady-state, total worker count = parent_pool (4) + child_pool (6) = 10 threads. Acceptable for SQLite-backed daemon.

Both pools are env-configurable: `TINYASSETS_RUN_POOL_SIZE` (already exists, was `_DEFAULT_MAX_WORKERS`) and `TINYASSETS_CHILD_POOL_SIZE` (new, default 6).

### Parent run depth detection

`execute_branch` and `execute_branch_async` gain a private `_invocation_depth` arg (default 0) that the compiler's invoke-branch builder threads through when spawning a child. `_invocation_depth >= 1` → use child_pool; else parent_pool. The recursion-cap check at `MAX_INVOKE_BRANCH_DEPTH` reads the same counter.

---

## 6. Other audit gaps addressed (#5, #7, #8, #11)

### Gap #5 — child actor inheritance (default-inherit + explicit override)

Today `execute_branch` defaults `actor="anonymous"` per signature line 1394, NOT the parent's actor. This breaks contribution attribution.

**Recommendation: child runs default to inherit parent's actor.** Both `invoke_branch_spec` and `invoke_branch_version_spec` gain an optional `child_actor: str | None` override field. When unset (default), the compiler reads parent's actor from the parent run record and threads it through to `execute_branch(..., actor=parent_actor)`. When set, used verbatim — useful for "run this sub-branch as a different identity" advanced cases.

### Gap #7 — state-schema validation of `output_mapping`

Validate at branch-validate time, not warn-at-runtime. When the child branch has a declared `state_schema`, the compose-time validator verifies every `output_mapping` value (child-side key) appears in that schema. Errors surface in `BranchDefinition.validate()` output before any run starts.

For child branches without an explicit `state_schema` (rare, but legal), the validator emits a warning rather than an error — strict mode requires the schema to be declared.

### Gap #8 — pin sub-branch to a frozen version

Resolved by §3's `invoke_branch_version_spec`. A spec with `branch_version_id` cannot drift; the version is content-addressed and immutable.

### Gap #11 — integration test parent → child → grandchild

New test `tests/test_sub_branch_invocation_integration.py` covering:

- Parent (def_id) → blocking child (def_id) → grandchild (def_id): full state round-trip.
- Parent (def_id) → blocking child (version_id) → grandchild (version_id): version-pinned chain.
- Parent → async child fan-out (3 children) → await each: concurrency-correct.
- Two-pool isolation: 5 parents holding parent_pool, 5 children spawning into child_pool, all complete (no deadlock).

These complement the existing unit-level tests at `tests/test_sub_branch_invocation.py`.

---

## 7. Tests footprint

Beyond the integration test above:

- `validate()` rejects nodes with both `invoke_branch_spec` and `invoke_branch_version_spec`.
- `validate()` rejects `invoke_branch_version_spec` with non-existent `branch_version_id`.
- `validate()` rejects `output_mapping` referencing keys not in child's `state_schema`.
- `_build_invoke_branch_version_node` blocking mode loads snapshot from `branch_versions`, runs, maps output.
- `_build_invoke_branch_version_node` async mode writes child run_id to parent state, returns immediately.
- `outcome.child_failures` populated with each failure class (`child_failed`, `child_timeout`, `child_cancelled`, `child_unknown`).
- `on_child_fail="propagate"` parent run terminates with structured error.
- `on_child_fail="default"` parent continues; output_mapping populates from `default_outputs` or None.
- `on_child_fail="retry"` re-fires child up to `retry_budget`; falls through to propagate after exhaustion.
- Global retry cap `TINYASSETS_MAX_CHILD_RETRIES_TOTAL` enforced across multiple sub-branches in one parent.
- Two-pool isolation: parent-pool exhaustion does NOT block child runs.
- Child actor inheritance: child run_id's `actor` field == parent's actor when `child_actor` unset.
- Explicit `child_actor` override: child run_id's `actor` field == override value.
- Recursion-cap respected when chains are version_id-only (compile-time check works through both spec kinds).

Estimate: ~12 new tests in `test_sub_branch_invocation.py` extension + 4 in new integration file.

---

## 8. Open questions

1. **Per-spec retry budget vs global cap interaction.** RECOMMENDED: per-spec `retry_budget` (default 1) honored AS LONG AS global counter < `TINYASSETS_MAX_CHILD_RETRIES_TOTAL` (default 5). Global cap ALWAYS wins. Closed.

2. **Child actor inheritance default.** RECOMMENDED: parent's actor by default; explicit `child_actor` field for override. Closed per lead's pre-draft note.

3. **State-schema validation strictness.** RECOMMENDED: strict at validate-time. Branches without declared `state_schema` get a warning, not an error. Closed.

4. **Pool size config.** RECOMMENDED: `TINYASSETS_CHILD_POOL_SIZE` env, default 6 (= `MAX_INVOKE_BRANCH_DEPTH + 1`). Closed.

5. **Goal-aware "invoke canonical for goal X" wrapper.** Belongs in Task #59 (`goals action=resolve_canonical`), NOT here. This proposal stops at running a known `branch_version_id`. The chain "goal_id → canonical → invoke" is split: #59 handles the goal-to-version resolution; this proposal handles the version-to-execution. Confirmed split. Closed.

6. **(Truly open) Async sub-branch + child failure interaction.** When `wait_mode="async"` and the child fails LATER (parent has already moved on), the failure surfaces only at the eventual `await_run_spec` node. Should the parent run be retroactively-marked-failed if the await never fires (e.g., parent's graph flowed past without an await)? Recommend NO — async-without-await is a chatbot-author bug, surface as a `validate()` warning if a graph has async-spawn without a matching await on the same run_id field.

7. **(Truly open) Cross-actor attribution when `child_actor` overrides.** The overridden `child_actor` runs the child but who gets attribution credit in the contribution ledger (#48)? The parent (who set up the invocation) or the override actor (who's named in the spec)? Recommend: override actor for `execute_step` events (they're the one whose work runs); parent for `design_used` events (they composed the workflow). Document explicitly.

---

## 9. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No `runs action=invoke_branch` MCP verb.** Explicitly rejected in §2.
- **No sub-branch DAG composition primitives** (e.g. "fan out to 100 children, aggregate"). The existing fan-out via async + await covers it for now; explicit DAG ops are downstream.
- **No `goals action=resolve_canonical` definition.** Punted to #59 per §8 Q5.
- **No factoring of `agent_team_20` into sub-branches.** Audit §A noted this as separate work; out of scope here.
- **No cross-tenant authority model for sub-branches.** When chatbot A invokes chatbot B's branch via sub-branch, what authority context does the child run under? Audit §H punted; this proposal does not solve it.
- **No durability changes.** Existing terminal-on-restart guarantee for runs (per `_action_run_branch` docstring) applies identically to children.

---

## 10. References

- Audit (paired): `docs/audits/2026-04-25-sub-branch-invocation-audit.md` (commit `6943d60`).
- G1 audit cross-references: `docs/audits/2026-04-25-canonical-primitive-audit.md` (gaps #4, #6 overlap with this audit's #3, #1 — G1 row #6 "no run-from-version primitive" maps to sub-branch gap #1 branch_version_id support; G1 row #4 "no routing primitive" maps to sub-branch gap #3 goal-aware verb).
- Sibling-action pattern: `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (Task #54, committed `dc7d2cb`) — `execute_branch_version_async` is the helper called by `_build_invoke_branch_version_node`.
- Variant canonicals: `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (Task #47).
- Contribution ledger: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (Task #48) — `child_failures` and `on_child_fail` policies emit `execute_step` / `caused_regression` events correctly.
- Future pair: Task #59 `goals action=resolve_canonical` — supplies the (goal_id, scope_token) → branch_version_id resolution this proposal's `invoke_branch_version_spec` consumes.
- Existing primitive: `tinyassets/branches.py:215-243` (NodeDefinition), `:920-960` (validate), `tinyassets/graph_compiler.py:1185-1380` (compiler builders), `tinyassets/runs.py:2087-2129` (recursion cap + poll helper).
- Existing tests: `tests/test_sub_branch_invocation.py`.
- Strategic context: `docs/audits/2026-04-23-navigator-full-corpus-synthesis.md` §B4; `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` lines 79, 116, 194.
