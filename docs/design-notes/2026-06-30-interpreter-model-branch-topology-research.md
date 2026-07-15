# Interpreter-Model Branch Topology — dynamic, universe-steered runs (research + Codex gate)

**Date:** 2026-06-30 · **Stage:** research pass + Codex opposite-provider review
complete; **paused awaiting host design gate.** · **Build authority:** NONE
(docs-only research lane).

> ⚠️ **Provenance / data-loss note (2026-06-30, salvage).** This file is a
> **reconstruction from the lane HANDOFF summary**, written after the original
> research worktree (`.claude/worktrees/interpreter-research`, branch
> `worktree-interpreter-research`) was swept while its three docs were still
> **uncommitted**. The two originals are **unrecoverable** (not in any git ref,
> stash, dangling commit, or on disk — verified 2026-06-30):
> - `docs/design-notes/2026-06-30-interpreter-model-branch-topology-research.md`
>   — the full research finding (research prose lost).
> - `docs/audits/2026-06-30-interpreter-model-codex-review.md` — the Codex gate
>   record with per-claim file:line verification (full verification prose lost).
>
> What is preserved below is the **distilled, actionable substance** the handoff
> captured: the design vision, the six Codex ADAPT conditions, the falsification
> slice, and the open host decisions. It is **not** the original research prose,
> and it has **not** been re-reviewed. The core idea also survives independently
> at `ideas/INBOX.md` (2026-06-30, navigator). Root cause of the loss: docs never
> committed + worktree swept — the exact failure the handoff's own resume
> checklist flagged. Code anchors below were re-verified against `origin/main`
> on 2026-06-30; line numbers may drift.

---

## TL;DR

Move the graph engine from **static compiled branches** to an **interpreter
model where the branch shape lives in state**: a tiny fixed LangGraph meta-graph
runs a *program-in-state*, and a Goal-anchored daemon decision node restructures
the path at runtime. A navigator research pass + a Codex opposite-provider review
were done. **Codex verdict: ADAPT** — direction sound, core concurred, six
conditions to satisfy before it advances to a host design gate. Nothing is built.
Next move is a host decision (advance / Option A vs B / merge-salvage / park).

## 1. The design vision (concrete)

- **What LangGraph compiles:** ONE tiny fixed meta-graph —
  `START → execute_step → daemon_decision → (advance→loop | pause→interrupt | revert→rewind | done→END)`.
  It never changes. All dynamism is data flowing through it.
- **State shape (four separated regions):**
  - `program` — steps + flow (the branch shape). **Single-writer** (only the
    decision node rewrites it) → this is what sidesteps the `_dict_merge` L4 bug.
  - `cursor` — current step(s).
  - `work` — today's author-typed `state_schema` deliverable fields (keep their
    per-field reducers).
  - `trace` — append-only provenance; doubles as the reproducibility + freeze +
    revert-reasoning artifact.
- **Step executor:** reuses today's node adapters (`_build_prompt_template_node`,
  the source-code approval/hash gate) almost verbatim — a `StepSpec` ≈ today's
  `NodeDefinition`. Not a rewrite; called from a cursor instead of wired into edges.
- **Decision grammar (the interpreter's instruction set):** `ADVANCE(to_step?)`,
  `INSERT/APPEND(spec)`, `REWRITE`, `INVOKE(sub-branch, pipes back)`,
  `PAUSE(→founder)`, `REVERT(state-only)`, `DONE`. Likely collapses to ~5 verbs
  (`INSERT/APPEND/REWRITE → edit_program`).
- **Authority:** the **Goal is the invariant, the path is the variable.** The
  daemon may reshape the path but never the Goal / budgets / its own source.
- **Security line:** daemon may invent `prompt_template` steps freely (always
  safe — regex-rendered) but **never** invent `source_code` (only compose
  already-approved code nodes). ⚠️ Codex caveat: **opaque / domain-trusted nodes
  bypass the hash gate by design** (`tinyassets/graph_compiler.py`, hash-gate /
  trusted-callable logic ~1251–1275; domain-trusted registration ~268), so the
  grammar must also forbid synthesizing opaque / trusted node paths.
- **Lifecycle prize:** explore dynamically, then **freeze** the executed program
  (already data in `trace`) back into a static deterministic `BranchDefinition`.

## 2. Codex verdict — ADAPT (concurred on the core)

Codex thread `019f1b02-f12d-7023-ad9e-e03ff6d3614a` (read-only). The original
gate record with per-claim file:line verification is **lost**; the conclusions
below are reconstructed from the handoff.

**Concurred:** interpreter model sound; **Option B-first**; and all three v1
forks — **LINEAR-first**, **armed deterministic stretches**, **forward-only
effects**.

**Six required changes (conditions for the host design gate):**
1. Correct stale paths + overstatements. *(The finding was authored 14 commits
   behind, citing `workflow/…`; the `workflow/ → tinyassets/` rename has landed —
   current paths are `tinyassets/…`.)*
2. Source or qualify external claims — "4× tokens" and "2026 SOTA" are
   **unverified** (AIPOM / LLMCompiler refs themselves are real).
3. Define freeze-back acceptance as the **full round-trip**:
   `trace → BranchDefinition → validate → save/publish/reload → static
   deterministic run`, **plus a BUG-037 topology-drop regression.** This is the
   core unproven claim.
4. Make prerequisites explicit: **hard Goal-binding** (`goal_id` is optional
   today — `tinyassets/branches.py:862` defaults `goal_id: str = ""`);
   server-enforced decision budget + no-progress definition over
   `cursor`/`work`/`trace` + wall-clock / provider caps; source/opaque grammar
   restriction; forward-only effect boundary.
5. Treat **Option B as an *expiring* dark proof harness** — promote-to-A **or
   delete**, criteria written into the gate from day one (else it's the second
   path Hard-Rule-#11 forbids).
6. Lock v1 scope: linear-only, single-writer `program`/`cursor`, append-only
   `trace`, **no DAG/`Send` until the L4 `_dict_merge` bug is fixed**
   (`tinyassets/graph_compiler.py:371`; STATUS dev-ready row).

**Corrections Codex made to the original framing:** recursion limit is a per-run
**default (overridable 10..1000), not a hard ~50-cycle wall**; LangGraph
time-travel forks a **checkpoint branch (history preserved), not a "new
thread"**; `invoke_branch` pipe-back is **`wait_mode="blocking"` only**.

## 3. Smallest provable slice (the falsification test)

A single **linear** program on the meta-graph, decision node with just
`ADVANCE(→next|done)` + `REWRITE(current prompt_template)`: bind to a Goal →
rewrite one step mid-run on a surprising output → complete → **full freeze
round-trip** (per condition #3) and run the frozen static branch. Build as
**interpreter-as-node (Option B), flagged dark + expiring.** Defers effects, DAG,
PAUSE, INVOKE, REVERT, source-code-invention.

## 4. Open host decisions (paused here)

1. **Advance** this direction to a host design gate / OpenSpec change, or not?
2. **Hard-Rule-#11 framing:** Option A (interpreter-canonical — `compile_branch`
   becomes a `BranchDefinition→program` translator; true single route, big
   rewrite) vs **Option B** (interpreter-as-node; Codex-recommended, as an
   expiring dark harness).
3. **Merge this salvage note to `main`** (and re-open a proper lane) vs **park**?
   The original "leave as-is, it's durable" park option is **no longer viable** —
   the durable artifacts were destroyed. Preservation now requires a commit.

## 5. Prerequisite watch

- **Hard Goal-binding** (`goal_id` optional today) gates live use.
- **L4 `_dict_merge` fix** (`tinyassets/graph_compiler.py:371`, shallow
  right-biased / non-convergent; STATUS dev-ready row) gates any DAG / `Send`
  fan-out.

## 6. If advancing (resume checklist)

1. Sync to `origin/main`; confirm code paths are `tinyassets/`.
2. Draft the design note **with the six ADAPT conditions baked in** (not the raw
   research framing), run it through `idea-refine` (design-approval gate), and
   get host sign-off on Option A vs B.
3. Only then build the §3 slice behind a dark, expiring flag.
4. Because the original finding + Codex verification prose are lost, a re-review
   may be warranted before treating any claim here as gate-passed.
