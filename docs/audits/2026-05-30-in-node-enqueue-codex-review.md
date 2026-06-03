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

## Verdict (codex, 2026-05-30)

**Verdict: adapt before enabling `WORKFLOW_NODE_ENQUEUE_ENABLED` in
production.** The dark merge is acceptable: the verb is default-off, the local
depth/budget guards are real, `BranchTask.depth` is threaded across the
dispatcher boundary, and the focused tests pass. It is not ready for live
enable because the first side-effecting in-node primitive still lacks
production-scope containment for queue growth, current-universe targeting, and
target branch authority.

### Answers to the six adversarial questions

1. **Total spawn bound: adapt required.** The current bounds limit chain length
   and per-run branching factor, but they do not bound total queued work at the
   origin or universe level. With the defaults, one depth-0 driver can enqueue
   50 depth-1 tasks, and each of those can enqueue 50 depth-2 tasks: 2,550
   descendant tasks before repeated origin runs are counted. The dispatcher cap
   paces execution, not queue growth. Before the flag flips, add a trusted
   global pending/running queue cap and a system-owned per-origin lineage cap
   such as `origin_branch_task_id` / `spawn_chain_id` plus `parent_branch_task_id`
   on `BranchTask`. Do not rely on `inputs` for lineage because branch code
   controls it.
2. **Cross-process lock safety: acceptable for the current single-host
   filesystem model.** `workflow/branch_tasks.py` locks a sidecar
   `branch_tasks.json.lock` with `msvcrt.locking` on Windows and `fcntl.flock`
   on POSIX, and `read_queue`, `append_task`, and claim/update paths all operate
   under that lock before atomically replacing the JSON file. The checked-in
   concurrency proof is thread-based, so I also ran an ad hoc child-process
   probe on Windows: 6 Python processes appended 12 tasks each to one queue,
   producing 72 rows and 72 unique task IDs. This is still not a distributed
   lock guarantee for multiple hosts or weak network filesystems; document that
   boundary if the runtime ever shares one queue across machines.
3. **Universe targeting: adapt required.** `_node_enqueue_branch_run` currently
   uses `kwargs["universe_id"]` if branch code supplies it, otherwise
   `_default_universe()`. That means the current run's universe is not a
   trusted runtime context. A node running in universe B can accidentally append
   to the active default universe, or deliberately name another safe
   `universe_id`. Read-only goals/gates calls can tolerate default-universe
   semantics more easily; a queue write cannot. Thread the current universe
   through the dispatcher, `execute_branch`, `compile_branch`, and the source
   invoker as trusted context, then default to that context or fail closed when
   it is absent. Treat caller-supplied cross-universe targeting as a separate
   explicit authority decision.
4. **`branch_def_id` authority: adapt required.** `tools_allowed` gates access
   to the verb, but the target branch is only a string. Unknown IDs are deferred
   to dispatch-time failure, and exact branch IDs bypass the visibility-aware
   name-search path. Before production enable, validate that the target branch
   exists before appending, and enforce the intended authority rule for the
   current actor/source branch. A conservative first policy is: same trusted
   universe/run context, target branch exists, and private branches are runnable
   only by their owner or an explicitly privileged actor. Same-goal or
   same-author constraints can be layered after the existence/visibility check
   is in place.
5. **Depth integrity: acceptable within the queue-writer trust boundary.** The
   node controls `inputs`, but `_node_enqueue_branch_run` ignores any caller
   `depth` argument and writes `BranchTask.depth = invocation_depth + 1`
   server-side. The daemon passes `claimed_task.depth` into
   `execute_branch(... _invocation_depth=...)`, `execute_branch` threads it into
   `_invoke_graph`, and `compile_branch` threads it into source-code node MCP
   invokers. An `inputs={"depth": 0}` value remains ordinary branch input and
   does not reset `BranchTask.depth`. If another public queue-writing surface is
   added, it must enforce the same server-owned depth rule.
6. **Failure modes: acceptable with one audit caveat.** `append_task` failures
   are not swallowed by the verb. They escape `_node_enqueue_branch_run`, the
   source-code wrapper logs and wraps them as `CompilerError`, and the run layer
   marks the run failed when the exception is not caught by branch code. As with
   any Python helper call, branch source can catch `Exception` and choose to
   continue; that is branch-authored behavior, not a silent platform drop. For
   live enable, consider adding an event/audit record for failed enqueue
   attempts so broad source-code `except Exception` blocks cannot hide storage
   pressure from operators.

### Required changes before production enable

- Add a trusted current-universe context to enqueued tasks and stop defaulting
  side-effecting queue writes to `_default_universe()`.
- Add queue-growth containment beyond local depth and per-run budget: a global
  queue cap plus a persisted per-origin spawn lineage/descendant cap.
- Validate target `branch_def_id` before append and enforce the target branch
  visibility/authority posture for the current actor/source branch.
- Add regression tests for multi-universe enqueue targeting, unknown/private
  branch refusal before append, and the new queue/lineage cap. Keep the existing
  depth, per-run budget, and lock tests.

Verification run from `C:\Users\Jonathan\Projects\wf-node-enqueue-review` on
2026-05-30:

- `python -m pytest tests/test_node_enqueue_verb.py tests/test_node_enqueue_concurrency.py -q`
  -> `9 passed`.
- Ad hoc child-process lock probe: 6 processes x 12 appends -> 72 queued rows,
  72 unique task IDs.
