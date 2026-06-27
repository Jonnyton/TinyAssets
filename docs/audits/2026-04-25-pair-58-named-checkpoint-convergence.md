# Pair Convergence: #58 named-checkpoint design ↔ #53 verdict + TypedPatchNotes + #56 sub-branch + graph_compiler + caused_regression metadata

**Date:** 2026-04-25
**Author:** navigator
**Pair:** dev-2's #58 named-checkpoint proposal (`docs/design-notes/2026-04-25-named-checkpoint-routing-proposal.md`) ↔ five substrate dependencies enumerated in lead's brief.
**Note on numbering:** "Task #58" here is the named-checkpoint design (TaskList #57 completed). NOT to be confused with my navigator-side Task #58 attribution-layer-specs which is a different doc entirely.
**Purpose:** close the audit-#62 ⚠ flag about gate-series typed-output contract coupling. Verify #58 absorbs #53's verdict-extension cleanly and composes with the substrate without parallel typed-output contracts.

---

## Stamp

**PAIR CONVERGES.** All five named cross-checks pass cleanly. Audit-#62 ⚠ flag is **CLOSED** — #58 explicitly disambiguates from #53 (§6 "Task #53 route-back: cross-branch routing"); the two are different layers, not parallel contracts. Three substantive new opens surface from the pairing.

---

## 1. Cross-check resolution per substrate dependency

| Substrate | Resolution |
|---|---|
| **#53 EvalVerdict extension (verdict half of typed-output contract)** | **CONVERGES — explicit layer separation, NOT parallel contract.** §6 "Task #53 route-back" says: "Within-branch decisions use `@checkpoint_name` (this proposal). Cross-branch decisions use `route_to` (Task #53) + Task #47's resolver." The two are orthogonal: #58 routes within a branch; #53 routes between branches. A gate-series can mix both — `verdict="route_back"` with `route_to` for goal-level escalation, OR `verdict="pass"`/`"fail"` with `@checkpoint` for branch-internal routing. **Audit-#62's ⚠ flag (gate-series typed-output contract coupling) is closed:** #58 is not in #53's layer; together they form the full typed-output contract. |
| **TypedPatchNotes (Task #66)** | **CONVERGES — different layer, no integration needed.** TypedPatchNotes' `route_history: list[tuple[str, str]]` carries (goal_id, scope_token) tuples — that's cross-branch routing state for #53. #58's checkpoint names are branch-internal; checkpoints never appear in `route_history`. **No composition required:** the two state machines are orthogonal. PatchNotes flows across branches via #53; checkpoint names never leave their authoring branch. Cleanly disambiguated. |
| **#56 sub-branch invocation** | **CONVERGES — explicitly orthogonal.** §6 "Task #56 sub-branch invocation" notes: "`invoke_branch_spec.output_mapping` and `invoke_branch_version_spec.output_mapping` reference parent state keys, not graph node_ids — orthogonal to checkpoints. No interaction." Sub-branch state mapping flows through declared `output_mapping` (parent_state_key ↔ child_output_key); checkpoints route within the parent (or child) branch independently. **The two primitives compose cleanly because they target different state surfaces.** |
| **Engine compile-time resolution (`_compile_conditional_edges`)** | **CONVERGES — compile site verified at `tinyassets/graph_compiler.py:1604-1611`.** I verified this directly. The current loop builds LangGraph conditional edges from `branch.conditional_edges`; #58's `resolve_checkpoint(branch, target)` slots in cleanly inside that loop (per #58 §3 sketch). No structural refactor needed; just a `resolve_checkpoint` call before the existing `graph.add_conditional_edges(...)` call. **The compile site DOES have access to `decision_checkpoints` since `branch` is the BranchDefinition itself** — no plumbing concern. |
| **caused_regression event metadata (per #58 §6)** | **CONVERGES with one structural addition flagged for attribution-layer-specs v2.** §6 says metadata records `checkpoint_name` alongside `node_id`. **The field is NOT yet in attribution-layer-specs §1.5** (which today lists `node_id`, `step_index`, `duration_ms`, `status`). Adding `checkpoint_name` to the metadata is a small one-key addition — backward-compatible (consumers reading without the key fallback to `node_id`). Filing as **[PENDING attribution-layer-specs-v2-metadata]:** add `checkpoint_name: str | None` to caused_regression's metadata schema. Doesn't block #58 design or implementation; the event-emit logic just includes the key when a transition occurred via @-prefix. |

**Net composition health:** five-for-five clean composition, with one minor cross-doc metadata addition flagged for navigator-side attribution-layer v2 update. This is the kind of targeted convergence the pair-read pattern is supposed to surface.

---

## 2. Closure of audit-#62 ⚠ flag

The flag from `2026-04-25-audit-53-gate-route-back-solo.md` §5 (cross-doc consistency check):

> "**The ⚠ is a fresh concern from this audit:** #53 EXTENDS `EvalVerdict` enum, which is the precursor to the gate-series typed-output contract (Phase A item 7 / Task #58 named-checkpoint, in-flight). When #58 design lands, it should explicitly absorb the verdict-extension work from #53, OR explicitly defer with rationale. Otherwise we'll have two parallel typed-output contracts to reconcile in v2 (one in #53 verdict-string land, one in named-checkpoint land)."

**Closure: #58 picked path "explicitly defer with rationale" by separating layers.** §6's clean disambiguation establishes that #53 + #58 are **NOT parallel typed-output contracts** — they're two halves of one contract operating at different layers (cross-branch / within-branch). **The full gate-series typed-output contract = #53 verdict + #58 checkpoint resolution.** Together they fully close Phase A item 7.

**Pair-read confirms convergence is healthier than absorption would have been.** Absorbing the verdict extension into #58 would have conflated branch-internal routing with cross-branch routing semantics; keeping them separate makes both surfaces tighter.

---

## 3. Fresh open Qs from the pairing

Three substantive opens that didn't appear in either solo doc:

1. **Run-event observability schema for checkpoint transitions.** §3 of #58 says runtime preserves checkpoint identity in `run_events.detail`:
   ```python
   detail={
       "transition_from": cond_edge.from_node,
       "transition_to": resolved_node_id,
       "transition_via_checkpoint": original_target,  # "@manual-review" or None
   }
   ```
   But the `RunStepEvent` dataclass (per `tinyassets/runs.py:116-127` DDL) has a `detail TEXT` column that's free-form JSON. Setting a convention for `transition_via_checkpoint` field needs to be either (a) documented in attribution-layer-specs / runs.py docstring as a project convention, OR (b) typed as part of an extended RunStepEvent dataclass. **Recommendation:** option (a) for v1 (just a convention with documented key); option (b) becomes load-bearing if more checkpoint observability tools surface. Open Q for run-events convention doc OR attribution-layer-specs v2.

2. **Per-node-id alias contribution attribution.** §5 "Per-node-id alias support" allows multiple checkpoint names to point at the same graph_node_id. When a regression hits that node, `caused_regression.metadata.checkpoint_name` is set to which? The first key found, the most-recently-traversed, all of them? **#58 doesn't specify.** Recommendation: most-recently-traversed (the one that the gate decision actually used in the conditional edge transition for THIS run). The run_events history has the transition record; the rollback engine can look up which checkpoint name was used in the offending run. Implementation-time clarification, but worth pinning before #57 + #58 implementations land in parallel.

3. **Checkpoint-rename observability under live editing.** Branches are live-editable. If an author renames a checkpoint from `@manual-review` to `@human-review`, all in-flight `caused_regression` events with the old name still reference it — but new readers querying "where did the regression hit?" see only the new name in the current `decision_checkpoints` map. **Cross-doc concern:** version_id-pinned runs avoid this (the snapshot has the original map), but def_id-based runs (per the def-form of the runner per #54) hit the issue. Recommendation: when a checkpoint key is renamed, append-only history. **Implementation-time concern; flag as:** the `decision_checkpoints` field, like `canonical_branch_history_json`, may need a rename-history audit trail. Could be deferred to #58 v2 if observed pain emerges.

---

## 4. Implementation-time constraints (separate from design-doc gaps)

To land in the dispatch task's verification list:

- **Validate-time strict resolution** (#58 §4 rule 3) MUST run before `publish_branch_version` writes the snapshot. Otherwise a published snapshot can carry dangling `@`-references that will fail at compile-time but were missed at publish-time. Threading: `publish_branch_version` calls `BranchDefinition.validate()` already (per #54 §4); confirm the new rule fires there.
- **`_compile_conditional_edges` slot-in test** — the integration must land cleanly without breaking BUG-019/021/022 fix path (per `tinyassets/graph_compiler.py:1422` comment). Test: existing branches with raw node_id `conditional_edges` continue working bit-for-bit identical; new branches with mixed raw + `@checkpoint` references compile to equivalent runtime topology.
- **Reserved-name rejection test** (#58 §4 rule 4) — author tries to set `decision_checkpoints["END"] = "some_node"`; validator rejects with explicit error message.
- **Per-node-id alias test** (#58 §5 Q2 approval) — same node_id under two different checkpoint names; both resolve correctly; gate decisions targeting either name route to the same node.
- **Cycle-rejection test** (§4 rule 5) — author tries to set `decision_checkpoints["foo"] = "@bar"`; validator rejects (values must be node_ids, not @-prefix strings).
- **Run-event metadata convention test** — verify `transition_via_checkpoint` field appears with original `@`-prefix string in run_events when a transition went through a checkpoint, and is absent / None when the transition was direct.
- **Composition with TypedPatchNotes (#66) test** — in a route-back scenario where the gate uses `@checkpoint` AND `verdict="route_back"`, both resolution mechanisms operate independently; no cross-talk.

---

## 5. Roadmap deltas

Three updates for v2 vision / roadmap:

1. **Phase A item 4b (named-checkpoint contract) — CLOSED.** Combined with item 4a (#53 verdict, closed in earlier pair-read), Phase A item 4 is now fully designed. Mark in roadmap.
2. **Phase A item 7 (gate-series typed-output contract) — FULLY CLOSED.** With #53 + #58 + TypedPatchNotes (#66), the typed output is now: `EvalVerdict` enum (5 verdicts, including `route_back`) + `EvalResult.route_to` + `EvalResult.patch_notes` (TypedPatchNotes) + `BranchDefinition.decision_checkpoints` map for branch-internal routing. **No further design work needed for item 7.**
3. **Phase A is design-complete except item 1** (storage-layer authority refactor) **and item 6 implementation** (run_branch_version, in flight as Task #61). Items 2 (variant canonicals) implemented Step 0+1; items 3, 4a/4b, 5a/5b/5c, 7 designed; item 6 designed + implementation in flight. **The Phase A design loop closes with this pair-read.**

---

## 6. Closure of Phase A + Phase E gate-substrate design

Per K (pair-read #57) + L (this pair-read), **Phase A and Phase E gate-substrate design is fully closed end-to-end.** Specifically:

| Phase E item | Status |
|---|---|
| 23 bisect-on-canary | Designed (#57); 6 sub-items per K's roadmap delta |
| 24 atomic-rollback-set | Designed (#57); shared sub-items with 23 |
| 25 watch-window freeze | Designed (#57 §3); on-demand computation per K open Q |

| Phase A item | Status |
|---|---|
| 1 storage-layer authority refactor | Pending design (load-bearing prerequisite per #57 + audit-50) |
| 2 variant_canonicals table | Designed + IMPLEMENTED Step 0+1 (commit `7b020ae`) |
| 3 lookup_canonical | Pending design (Task #59 in flight) |
| 4a verdict (route_back) | Designed (#53, audited solo as #62) |
| 4b named-checkpoint | Designed (#58, paired here as L) |
| 5a invoke_branch_version_spec + builder + actor inheritance | Designed (#56, paired as #60) |
| 5b structured failure propagation | Designed (#56) |
| 5c two-pool concurrency | Designed (#56) |
| 6 run_branch_version | Designed (#54, paired as #59); impl in flight (Task #61) |
| 7 gate-series typed-output contract | Fully closed (#53 + #58 + #66 TypedPatchNotes) |

**8 of 11 Phase A items + 3 of 3 Phase E items fully designed.** Items 1 (authority refactor) and 3 (lookup_canonical) are the remaining design slots; both are small.

---

## 7. References

- Audit target: `docs/design-notes/2026-04-25-named-checkpoint-routing-proposal.md` (#58, dev-2 — Task #57 in current TaskList).
- Substrate cross-checked:
  - `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (#53, dev-2 — verdict half of typed-output contract).
  - `docs/design-notes/2026-04-25-typed-patch-notes-spec.md` (#66, dev-2-2 — TypedPatchNotes with route_history).
  - `docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md` (#56, dev-2 — orthogonal output_mapping).
  - `docs/design-notes/2026-04-25-attribution-layer-specs.md` (navigator — caused_regression metadata schema).
  - `docs/design-notes/2026-04-25-surgical-rollback-proposal.md` (#57, dev-2 — caused_regression event consumer).
  - `tinyassets/graph_compiler.py:1604-1611` (compile site verified directly).
  - `tinyassets/branches.py:920-960` (validate site).
- Closure of audit flag: `docs/audits/2026-04-25-audit-53-gate-route-back-solo.md` §5 ⚠.
- Sibling pair-reads: `docs/audits/2026-04-25-pair-{54-vs-56,50-vs-56,57-surgical-rollback}-convergence.md`.
- v2 vision Phase A/E phasing: `docs/design-notes/2026-04-25-self-evolving-platform-vision-v2.md` §6.
