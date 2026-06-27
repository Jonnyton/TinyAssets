# Pair Convergence: #54 (runner version-id bridge) ↔ #56 (run_branch surface audit)

**Date:** 2026-04-25
**Author:** navigator
**Pair:** #56 audit (`docs/audits/2026-04-25-run-branch-surface-audit.md`, navigator) ↔ #54 design (`docs/design-notes/2026-04-25-runner-version-id-bridge.md`, dev-2).
**Purpose:** cross-check #54's design decisions against #56's four §F divergence-constraints. Surface any unresolved gaps + new open questions that didn't appear in either solo doc.

---

## Stamp

**PAIR CONVERGES.** Every #56 §F constraint is honored, in some cases sharpened. One material new open Q surfaces from the pairing (§7).

---

## 1. Resolution of #56 §F divergence points

### Divergence 1 — Three version concepts (def_id vs version_id vs run_lineage.branch_version INTEGER)

**#56's claim:** these are three distinct version concepts, the third unrelated to the second; affects how `_prepare_run`'s lineage writes record version-aware provenance.

**#54's resolution:** **acknowledged but not directly addressed.** §4 schema addition adds `runs.branch_version_id TEXT` column for the new version_id concept. This is correct — the column tracks "which immutable snapshot did this run execute against." It does NOT touch `run_lineage.branch_version` INTEGER (the third concept), which keeps its existing audit-only purpose.

**Verdict:** **HONORED implicitly.** #54 leaves the third concept alone (correct — it serves a different purpose). The new `runs.branch_version_id` column is the right place to record snapshot-id provenance. The two version concepts coexist in the runs row without colliding: `branch_def_id` is always populated; `branch_version_id` is populated only for version-runs and NULL for def-runs.

One subtle thing #54 doesn't say but should be safe: **`run_lineage.branch_version` (INTEGER) keeps tracking live-def integer version even on version-runs.** The snapshot's underlying `branch_def_id` resolves to a live def at lineage-write time, and the integer version of that live def at run-time is what gets recorded. Slightly weird (the version-run is frozen, but its lineage row reads the live def's current integer) — but it's consistent with the lineage column's purpose ("what changed since the last run on this branch") rather than "what was running."

Minor open Q (new): should `run_lineage` ALSO get a `branch_version_id` column for version-runs, so cross-version comparisons work without traversing branch_versions → branch_definitions? **Flag for #47-v2 batch with the merge_distributions audit table** I previously flagged.

### Divergence 2 — Resolver placement: `runs.execute_branch_version_async`, NOT in MCP action handler

**#56's claim:** resolver should live one layer below the MCP action so scheduler, dispatcher, and gate-routing nodes (Phase A item 5 = BUG-005) can all share one resolver. Putting it in the action handler duplicates resolution at every call site.

**#54's resolution:** **explicitly honored.** §2 names the helper `execute_branch_version_async` in `tinyassets/runs.py`, sibling to existing `execute_branch_async`. The MCP handler `_action_run_branch_version` is a thin ~30-line wrapper that calls the helper. §6 explicitly describes Task #53 route-back invoking `execute_branch_version_async` directly — exactly the shared-helper pattern #56 recommended.

**Verdict:** **HONORED + sharpened.** #54 takes the shared-helper recommendation and goes one step further: introduces `_execute_branch_core(branch_version_id=...)` as the *common* implementation underneath BOTH `execute_branch_async` (def-based) AND `execute_branch_version_async` (version-based). Both helpers converge to one execution loop. This is cleaner than #56 sketched — minimizes duplication while keeping the two entry points discoverable.

### Divergence 3 — Sibling action vs. dual-arg overload

**#56's claim:** new sibling action `run_branch_version`, NOT dual-arg overload. Five reasons enumerated in §D — different semantics, different long-term authority, existing callers unchanged, discovery-friendly, mirrors `publish_version`/`list`/`get` convention.

**#54's resolution:** **explicitly honored.** §1 surveys three options (dual-arg, redirect verb, def_id at canonical) and rejects all three. §2 picks sibling-action. §2's "Why sibling-action" subsection cites #56's §D directly with three of the five reasons (discovery, convention parity, validation simplicity).

**Verdict:** **HONORED with citation.** Cleanest possible convergence — #54 explicitly grounds the decision in #56's audit. The two reasons #54 didn't echo (different semantics live-vs-frozen, different long-term authority models) are implied by the discussion but not named. Not a gap; just a minor abbreviation.

### Divergence 4 — Schema-drift handling

**#56's claim:** schema-drift between publish-time snapshot and current `BranchDefinition` schema is a load-bearing test concern. A snapshot published before a schema migration may not deserialize. Should be a graceful error with a clear message, not a crash. v2+ may want per-snapshot `schema_version` tag + migration shim.

**#54's resolution:** **partially addressed.** §7 Open Q #3 addresses one slice of schema drift: when state_schema differs between snapshot and live def, validate inputs against the snapshot's schema (correct call). But this is *input validation* drift, not BranchDefinition schema *deserialization* drift.

**Gap:** #54 doesn't address the case where `BranchDefinition.from_dict(snapshot_json)` itself raises (e.g., snapshot has no `entry_point` because that field was added post-publish). #54 says `KeyError` from `get_branch_version` returns gracefully (line 64), but doesn't address the path where `get_branch_version` succeeds but `BranchDefinition.from_dict` blows up.

**Verdict:** **PARTIALLY HONORED.** The from_dict-raises case stays as a fresh open Q for v2 dispatch. Recommendation: implementation must wrap `BranchDefinition.from_dict(bv["snapshot"])` in a try/except and return a structured error like `{"error": "snapshot deserialization failed: <detail>", "failure_class": "snapshot_schema_drift", "suggested_action": "republish at current schema version"}` matching the existing failure-class pattern at `universe_server.py:7060+`. **Calling this out as an implementation-time test requirement, not a design-doc gap requiring rework of #54.**

---

## 2. Sibling-action vs dual-arg

**#54 ships sibling-action.** §2 picks it; §3 tradeoff table confirms it wins on every axis (caller stability, discovery, immutability, validation cost, convention parity, runner internal complexity, migration, composition, test surface). No dual-arg ambiguity left.

The §3 tradeoff table is a sharper version of #56's §D recommendation — same conclusion, more axes evaluated. Healthy convergence.

---

## 3. Resolver-in-runs.py-not-action-handler

**#54 honors §B placement** AND extends it: the resolver lives in `runs.py` as `execute_branch_version_async`, AND the def/version paths share `_execute_branch_core`. #56 didn't propose the core-extraction; #54 evolves a better answer. This is the kind of evolution-not-just-honor that the pairing process should produce.

**Implementation note:** the `_execute_branch_core` extraction is itself a refactor of `execute_branch_async` (per §5 Step 1). Existing tests must continue passing. **Recommend treating this refactor as its own dispatch task** (or first half of the implementation task) — it's a behavior-preserving change with a clear test signal (run a current-flow run, assert outcome unchanged).

---

## 4. Schema-drift handling

Per §1 Divergence 4 above: **partial.** #54 addresses input-schema drift (use snapshot's schema for input validation — correct). But it doesn't explicitly address `BranchDefinition.from_dict` raising on schema-incompatible snapshots.

The implementation-time mitigation: try/except around `from_dict`, structured error matching existing failure-class pattern. Test coverage: publish a snapshot with a synthetic missing-required-field, attempt to run via `run_branch_version`, assert structured error with `failure_class="snapshot_schema_drift"`.

This belongs in the dispatch task's verification list, not in #54 v2.

---

## 5. Three-version-concept distinction

**#54 distinguishes the two it cares about** (def_id vs version_id) with explicit clarity. The third concept (`run_lineage.branch_version` INTEGER) is intentionally untouched — correct, since it serves a different audit purpose. No muddling.

The new open Q I flagged (should `run_lineage` get a `branch_version_id` column for version-runs?) belongs in #47-v2 batch, not in #54.

---

## 6. Composition with sibling proposals

**#54 surfaces a hard dependency I didn't audit:** Task #53 (gate-route-back verdict) requires `execute_branch_version_async` for synchronous sub-branch invocation. §6 of #54 spells this out cleanly. The route-back handler:
1. Receives `EvalResult(verdict="route_back", route_to=(goal_id, scope))`.
2. Resolves (goal, scope) → `branch_version_id` via #47 fallback chain.
3. Invokes `execute_branch_version_async(...)` synchronously.
4. Blocks on terminal status (per #53 sync-only recommendation).

This means **#54 ships before #53 implementation** — a sequencing constraint that wasn't in either #56 or my roadmap. Adding this as a roadmap update: Phase A item 6 (run_branch_version) blocks Phase A item 5 (sub-branch invocation / BUG-005). Roadmap §1 had item 5 → item 6, but #54 reverses: item 5 implementation depends on item 6's helper landing first.

**Roadmap correction noted.** Will update in v2 of vision doc / next roadmap revision.

---

## 7. Fresh open questions surfaced by the pairing

These didn't appear in either solo doc; the pairing brings them out.

1. **Should `run_lineage` get a `branch_version_id` column for version-runs?** Today the integer `branch_version` tracks live-def integer at run-time. For version-runs, that's a slightly weird value (frozen run's lineage row reads live def's current integer). Cleaner: add `run_lineage.branch_version_id TEXT` for version-runs. Flag for #47-v2 batch.

2. **`_execute_branch_core` refactor as a separate dispatch task?** §5 Step 1 of #54 implies the refactor lands together with the new helper. Behavior-preserving refactor + new feature in one task is conventionally fine but enlarges the test surface for verifier review. **Recommendation:** split into two tasks — (a) refactor `execute_branch_async` to call `_execute_branch_core(branch_version_id=None)` with all current tests passing, (b) add `execute_branch_version_async` + new MCP handler + new tests. Smaller dispatch units, cleaner SHIP signal.

3. **Schema-drift error class ratification.** #54 §7 Q3 picks "snapshot's schema for input validation." But neither doc names the failure-class string for the from_dict-raises case. **Recommendation:** add `failure_class="snapshot_schema_drift"` to the existing failure taxonomy at `universe_server.py:7060`, with `suggested_action="republish at current schema version"`. Implementation-task constraint, not design-doc gap.

4. **Cancellation across def/version runs.** #54 §7 Q5 says cancellation is "identical to def-based runs" using the existing `run_cancels` table. Confirmed. But: when a route-back synchronous invocation is mid-flight inside a parent gate-series run, and the *parent* gets cancelled, does the cancellation propagate to the child version-run? **Recommendation:** treat as an implementation-time verification — when parent is cancelled, the child version-run should also receive cancellation signal. Test coverage required.

5. **Lineage column for daemon attribution.** Cross-reference with #58 attribution-layer specs §1.1: `execute_step` events need `daemon_actor_id` from runs row. #54 doesn't extend `runs` schema beyond the new `branch_version_id` column — `daemon_actor_id` was supposed to come in Phase B item 10 separately. Worth confirming the migration sequencing: `branch_version_id` column lands with #54 implementation; `daemon_actor_id` lands with Phase B emit-site work. Both ALTER-only; no conflict.

---

## 8. Roadmap deltas

The pairing surfaces three updates to my primitive-shipment roadmap (`docs/design-notes/2026-04-25-primitive-shipment-roadmap.md`):

1. **Phase A item 5 (BUG-005 sub-branch invocation) depends on item 6 (`run_branch_version`)**, not the other way around. Roadmap §1 sequencing graph needs reversal of those two arrows.
2. **`runs.branch_version_id` column ALTER** is a Phase A migration that should land with item 6's implementation (per #54 §4). Add as a sub-step of item 6.
3. **`_execute_branch_core` refactor** could be split off as its own dispatch unit before item 6 — the cleaner SHIP signal favors this. Optional ordering.

These are minor reorderings, not structural changes. Will batch into v2 vision doc revision (option D in queue).

---

## 9. References

- #56 audit: `docs/audits/2026-04-25-run-branch-surface-audit.md` (navigator, run_branch surface).
- #54 design: `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (dev-2, sibling-action proposal).
- #47 schema: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (dev-2, contribution_events ledger).
- #58 attribution layer: `docs/design-notes/2026-04-25-attribution-layer-specs.md` (navigator, semantics on top of #47).
- #53 route-back design (referenced as hard dependency by #54): per TaskList completed; doc not yet read in this audit. Pair-read with #53 deferred to a separate convergence pass.
- Roadmap: `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md` (Phase A items 5 + 6 sequencing — needs update per §8 above).
