---
status: active
status_detail: F2 ACCEPTED by host 2026-04-28 (drop Recency, fold continue_branch into run_branch resume_from=<run_id> param); impl pending dev pickup post-Task-#18
---

# Design Note: Extend Run / Continue Branch as a First-Class Primitive

**Date:** 2026-04-25
**Status:** Scoping — open questions for host/navigator
**Source signal:** Priya Session 2 user-sim (2026-04-24), `ideas/INBOX.md`, competitor-trials-sweep Signal 2
**Chain-break:** Interface 1 — primitive gap

---

## 1. Problem Statement

From `ideas/INBOX.md` (Priya-Session2, 2026-04-24):

> "Add BIOCLIM + RF for comparison on the same 14 species" has no clean TinyAssets verb. "New branch" implies fresh scaffolding. "New run" implies same branch. Chatbot must semantically infer "clone this branch, add algorithm nodes, re-run same species set." No existing primitive surfaces this as an intent.

From `docs/audits/user-chat-intelligence/2026-04-24-competitor-trials-sweep.md` Signal 2:

> "New branch" implies fresh scaffolding. "New run" implies same branch. The chatbot would have to semantically infer "extend this completed branch with additional algorithm nodes." Neither existing primitive surfaces this as a first-class intent.

**Chain-break framing:** Interface 1 — the chatbot improvises a multi-step composition (clone + add_node + re-run) where it should have a single clear tool. At scale, every chatbot will improvise this differently, producing inconsistent state and confusing run history for users comparing results.

The ask has two distinct sub-intents that are currently entangled:

- **Extend the algorithm set**: "I want to add BIOCLIM and RF to the existing MaxEnt branch and compare all three on the same species set."
- **Continue an existing run**: "I want to pick up from where the last run left off, adding new steps, not re-running the whole thing from scratch."

These are related but not identical. The first is about branch structure; the second is about run state carryover. The primitive design must handle both or explicitly scope to one.

---

## 2. What Today's Primitives Offer

| User intent | Closest existing verb | Friction |
|---|---|---|
| "Add BIOCLIM node to my MaxEnt branch" | `extensions action=add_node` | Works for structure, but creates a new branch version — a second `run_branch` on the same def_id does NOT inherit state from the first run |
| "Run the extended branch on the same inputs" | `extensions action=run_branch` with same inputs | Requires user to know and re-supply exact original inputs; no automatic state carryover |
| "Fork this branch and add new algorithms" | No verb (`clone_branch` is not implemented) | Chatbot must `build_branch` from scratch, manually copying all nodes from the original — very high friction, error-prone |
| "Continue the run from the last checkpoint" | `extensions action=resume_run` | Only works for INTERRUPTED runs (LangGraph checkpoint exists); not for COMPLETED runs; cannot add new nodes |
| "Re-run with one extra parameter" | `extensions action=run_branch` with different inputs | Works if the branch accepts the param; does NOT add nodes dynamically |
| "Clone this branch then modify" | No verb | Would require read → manual rebuild — extremely high friction |

**Gap summary:** There is no verb that says "take this branch + its run's inputs/state, add nodes to the branch definition, and re-execute." The closest legal path today is:

1. `patch_branch` to add the new nodes to the branch definition (mutates the canonical branch)
2. `run_branch` with the same inputs again

This mutates the live branch (risky for Priya's original workflow) and requires the user to manually track original inputs. There is no "fork and extend" path at all.

---

## 3. Candidate Primitive Shapes

### Candidate A — New MCP verb `extend_branch`

```
extensions action=extend_branch
  source_branch_def_id=<id>       # branch to fork from
  add_nodes=[{node_id, ...}, ...]  # nodes to add
  connect=[{from_node, to_node}]   # new edges
  run_with_inputs={...}            # optional: re-run immediately with these inputs
  inherit_inputs_from_run_id=<id>  # alternative: carry inputs from a prior run
```

Creates a new branch definition as a fork of `source_branch_def_id` (new `branch_def_id`), adds the specified nodes, wires them, optionally enqueues a run. The source branch is untouched. Returns the new `branch_def_id` and optionally a `run_id`.

**Key design decision:** "extend" produces a new branch, not a mutation of the original. This is intentional — Priya keeps MaxEnt-only as a reproducible branch and gets MaxEnt+BIOCLIM+RF as a sibling.

### Candidate B — Composition: `clone_branch` + `add_node` + `run_branch`

Implement `clone_branch` as a first-class verb that returns a new `branch_def_id` with the same structure. The chatbot then:

1. `clone_branch source=<id>` → `new_branch_def_id`
2. `add_node branch=<new_id> ...` (one call per new node)
3. `connect_nodes ...`
4. `run_branch branch=<new_id> inputs={...}`

This is composable and requires no new semantics — just `clone_branch` is new. But the chatbot must orchestrate 4+ calls with shared state across them. Interface 1 friction is lower than today (at least `clone_branch` surfaces the intent) but not eliminated.

### Candidate C — Parameterized re-run with `--add-nodes` flag

Extend `run_branch` with optional `extend_with` payload:

```
extensions action=run_branch
  branch_def_id=<id>
  inputs={...}
  extend_with=[{op: "add_node", ...}, ...]   # applied transiently, not persisted
```

The engine applies the `extend_with` patch to the branch definition in memory for this run only — the original branch definition is not mutated. The run's lineage records the transient extension. No new branch definition is created unless the user explicitly asks for one.

**Risk:** Transient branch mutations complicate run history and debugging. "What branch did run X use?" becomes ambiguous. Reproducibility is harder.

### Candidate D — `branch.next_iteration()` lifecycle method (run lifecycle primitive)

Model "extend" as a new run status: `ITERATING`. A run in `ITERATING` status has produced an intermediate output and is waiting for a branch extension before continuing. The chatbot calls:

```
extensions action=iterate_run
  run_id=<completed-run-id>
  extend_with=[{op: "add_node", ...}, ...]
  continue_inputs={...}
```

This produces a new branch version and a new run that semantically "continues" the prior run, with explicit lineage linking (parent_run_id).

Most expressive for the "compare on same dataset" use case since run history shows the evolution cleanly. Highest implementation cost — requires new run status, new lineage semantics, LangGraph integration for state handoff.

---

## 4. Tradeoffs Table

| Dimension | A — `extend_branch` verb | B — `clone_branch` + compose | C — Transient `extend_with` param | D — `iterate_run` lifecycle |
|---|---|---|---|---|
| **Discoverability** | High — single verb surfaces the intent | Medium — chatbot must compose; `clone_branch` is new but pattern not obvious | Low — buried in `run_branch` params | Medium — new verb but tied to run status concept |
| **Idempotency** | Yes — same call → same new branch | Partially — `clone_branch` is idempotent; add_node calls may not be | No — transient; run results differ by params | Partial — `iterate_run` on same run_id could be idempotent with a result cache |
| **State carryover semantics** | Explicit via `inherit_inputs_from_run_id` | Explicit — chatbot decides what to carry | Implicit — run inputs re-supplied | Native — prior run output feeds into continuation |
| **Original branch safety** | Intact (fork produces new id) | Intact (clone produces new id) | Intact (transient patch, not persisted) | Intact (new branch version + new run) |
| **Implementation cost** | Medium — new action handler, branch fork logic, optional run enqueue | Low — only `clone_branch` is new; rest exists | Low for engine, High for UX reasoning | High — new run status, lineage extension, LangGraph state bridge |
| **Naming clarity** | Clear — "extend this branch" matches user vocabulary | Requires chatbot to know "clone then add" pattern | Confusing — looks like run params, not branch extension | Clear for power users; opaque for casual users |
| **Aligns with `user_builds_we_enable`** | Yes — exposes the substrate, user decides scope | Yes — maximum composability | Partial — hides structural change inside run call | Yes — models iteration explicitly |
| **W&B parity** | Closes the gap directly | Closes gap if chatbot is fluent | Does not close gap (no persistent fork) | Exceeds W&B — makes iteration a first-class tracked concept |

---

## 5. Recommendation

**Candidate A (`extend_branch`)** best closes the Interface 1 chain-break with acceptable implementation cost.

Rationale:

- Single verb matches the user's mental model ("extend my branch") without requiring the chatbot to compose 4 calls
- Fork-by-default keeps the original branch untouched — matches reproducibility expectations of scientific users (Priya)
- `inherit_inputs_from_run_id` eliminates the main source of re-run friction (user tracking original inputs)
- Implementation can land incrementally: (1) fork-only without auto-run, (2) add `run_with_inputs` / `inherit_inputs_from_run_id` in phase 2
- Candidate B (`clone_branch`) should be implemented **alongside** A as the underlying primitive — `extend_branch` is syntactic sugar over `clone_branch` + `add_node(s)` + optional `run_branch`

Candidate D is the right long-term direction for "compare results across iterations" but should land after A proves the use case.

---

## 6. Open Questions for Host / Navigator

1. **Fork vs. mutate policy:** Should `extend_branch` always produce a new `branch_def_id`, or should there be a `--in-place` flag for users who explicitly want to mutate the live branch? Mutation is faster but breaks reproducibility.

2. **State carryover depth:** When `inherit_inputs_from_run_id` is used, does state carryover include only the original `inputs` dict, or also the run's `output` (so new nodes can reference prior results as inputs)? The latter enables true pipeline chaining but requires defining the state handoff contract.

3. **Branch lineage display:** Should the extended branch show "forked from MaxEnt-branch@v3" in `describe_branch`? This affects how the chatbot narrates the history to users.

4. **Naming:** `extend_branch` vs. `fork_branch` vs. `branch_from`? "Fork" is programmer vocabulary; "extend" is closer to user vocabulary from the Priya signal.

5. **Multi-node extension atomic?** If `extend_branch` adds 3 nodes and one fails validation, does the whole fork fail (atomic) or does a partial fork exist?

---

## 7. Dependencies

- **In-flight run recovery / daemon P0 (STATUS.md Concern #1):** The daemon is currently PAUSED due to a revert-loop P0 (`docs/audits/2026-04-23-p0-auto-recovery-trace.md`). Resume semantics for interrupted runs should be stable before implementing Candidate D (iterate_run), since both touch LangGraph checkpoint handoff. Candidate A (`extend_branch`) is **not blocked** by the P0 — it forks branch definitions, not run checkpoints.

- **`clone_branch` as a prerequisite:** Candidate A depends on a branch-fork primitive that does not currently exist. `clone_branch` (or equivalent internal function) must be implemented before `extend_branch` can be wired as an MCP action. Estimated effort: medium (copy branch YAML to new `branch_def_id`, re-register in DB).

- **`resume_run` semantics clarification:** The inbox note flags "in-flight run recovery part 2" as a gating prereq. This applies to Candidate D only. Candidate A is independent.
