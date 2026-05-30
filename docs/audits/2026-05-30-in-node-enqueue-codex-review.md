# Codex review gate — in-node paced enqueue verb

**Status:** OPEN — needs opposite-provider (Codex) review.
**Author of code under review:** Claude Code (this is the first side-effecting
in-node primitive, so per AGENTS.md it gets opposite-provider review before
live rollout).
**Gate:** review must return **approve** or **adapt** before
`WORKFLOW_NODE_ENQUEUE_ENABLED` is flipped on in production. The code is merged
**dark** (flag default off), so the *merge* already happened; this gate blocks
*enabling the capability live*, not the merge.

## What to review (scope)

The in-node `invoke_mcp_action('enqueue_branch_run', ...)` verb that lets a
`source_code` node append a run-request to its universe's dispatcher queue.
Built across two merged PRs (+ a proof PR):

| PR | sha | What |
|----|-----|------|
| #1213 | `7b9381e6` | slice 1 — wiki READ in-node (`read/search/list/since/lint`), read-only-enforced. Low risk; review lightly. |
| #1214 | `67797ba3` | **slice 2 — the paced enqueue verb + spawn guards. PRIMARY REVIEW TARGET.** |
| #1215 | `a148b9f1` | §14 concurrency proof + this gate row. |

### Files / symbols to read
- `workflow/graph_compiler.py`:
  - `_NODE_MCP_ACTION_ALIASES` (the `dispatch`/`wiki` entries),
  - `_node_enqueue_enabled` / `_node_enqueue_max_depth` / `_node_enqueue_budget`,
  - `_node_enqueue_branch_run(...)` — the verb body (guards + append),
  - `_invoke_mcp_action` dispatch branch `elif tool_name == "dispatch"`,
  - the `invocation_depth` threading: `_build_node_mcp_invoker` →
    `_build_source_code_node` → `_build_node` call site.
- `workflow/branch_tasks.py`: the new `BranchTask.depth` field (+ `append_task`
  file lock, `from_dict` migration filter).
- `fantasy_daemon/__main__.py`: the dispatcher passes
  `_invocation_depth=getattr(claimed_task, "depth", 0)` into `execute_branch`.
- `tests/test_node_enqueue_verb.py`, `tests/test_node_enqueue_concurrency.py`.

## Design intent (so the review checks the right thing)

Background: the platform `backfill_investigations` (re-drove the bug backlog as
daemon Python) was **cut** in #1212 because intake/selection policy should be a
**user-composed driver branch**, not engine code. This verb is the missing
primitive that makes that driver buildable: a branch can read the backlog
(wiki) and enqueue runs of the canonical loop. It is the **paced** shape — it
**appends to `branch_tasks.json`**, it does NOT synchronously spawn/run a
branch. The daemon's existing concurrency cap + per-provider cooldown pace
execution (the same mechanism that kept the old backfill safe).

Composability is already demonstrated: the driver branch `cca3c93b632e`
(`backlog-driver-v0`) builds + validates `ok` from these primitives alone.

## Three bounds (fail-closed) — verify each holds

1. **Capability flag** `WORKFLOW_NODE_ENQUEUE_ENABLED` (default **off**) — the
   verb refuses unless explicitly enabled. Ships dark.
2. **Spawn-depth cap** `WORKFLOW_NODE_ENQUEUE_MAX_DEPTH` (default **2**) —
   bounds chain *length*. Depth rides on `BranchTask.depth`, threaded across the
   queue boundary (dispatcher → `execute_branch(_invocation_depth=)` →
   `compile_branch` → node invoker). A node enqueues at `parent_depth + 1`;
   refuse beyond cap. Mirrors the existing `_runtime_max_invocation_depth`
   invoke-branch guard.
3. **Per-run budget** `WORKFLOW_NODE_ENQUEUE_MAX_PER_RUN` (default **50**) —
   bounds branching *factor*; one run may enqueue at most this many.

Also: `trigger_source` is forced to `owner_queued` (no arbitrary tier); the verb
is gated by the node's `tools_allowed`; universe resolves via
`_default_universe()` (matching the existing in-node `goals`/`gates` behavior).

## Adversarial questions Codex should answer (don't rubber-stamp)

1. **Total spawn bound.** depth cap 2 + budget 50 ⇒ worst-case one origin run
   can enqueue `50 + 50*50 = 2550` tasks (depth-2 runs can't enqueue further).
   Is 2550 queued tasks acceptable? Should there be a **global queue-size cap**
   or **per-origin-run total cap** in addition to depth+budget? (The dispatcher
   concurrency cap bounds *concurrent execution*, not *queue size*.)
2. **Cross-process lock safety.** The §14 proof exercises *in-process threads*
   on one `append_task` file lock (40 appends, zero loss). Confirm the
   `branch_tasks.json` lock is **cross-process** safe (multiple daemon workers),
   or flag it. Cite the lock implementation.
3. **Universe targeting.** Enqueue resolves `_default_universe()`. In a
   multi-universe daemon, a node in universe B enqueues to the *default*
   universe, not B. Correct, or a latent bug? (It matches current in-node
   goals/gates semantics — but those are reads.)
4. **branch_def_id authority.** The verb enqueues *any* `branch_def_id` the node
   names, with no existence/authority check (deferred to dispatch-time, where an
   unknown branch fails the task cleanly). Is "a user branch can enqueue a run
   of any branch" an acceptable authority posture, or should the verb validate
   existence / actor-authority / a same-author or same-goal constraint?
5. **Depth integrity.** Can `BranchTask.depth` be spoofed? A node controls
   `inputs` but NOT the task's `depth` (set server-side to `parent+1`). Confirm
   there's no path for a node to reset its own children to depth 0 and evade the
   cap (e.g., via `inputs` injection or a second enqueue arg).
6. **Failure modes.** What happens if `append_task` raises mid-run (disk full,
   lock timeout)? The verb lets it propagate as `CompilerError` (run fails) —
   confirm that's the intended fail-loud behavior and can't silently drop.

## Required output

Leave a durable verdict in this file (append a `## Verdict (codex, YYYY-MM-DD)`
section): **approve** / **adapt** / **reject**, with reasoning per question
above. On **adapt**, list the concrete changes required before the flag flips.
Per AGENTS.md, re-check sources and Workflow context; this artifact is the gate
record.

## Evidence pointers
- PRs #1213 / #1214 / #1215 (above).
- Composability proof: built branch `cca3c93b632e` (`backlog-driver-v0`),
  validation `ok`, `runnable=false` only because its source_code nodes are
  unapproved (a separate, legitimate gate).
- STATUS.md "Codex review gate" Work row references this file.
