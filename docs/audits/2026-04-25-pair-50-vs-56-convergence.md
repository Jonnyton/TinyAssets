# Pair Convergence: #50 (sub-branch invocation audit) ↔ #56 (BUG-005 design proposal)

**Date:** 2026-04-25
**Author:** navigator
**Pair:** #50 audit (`docs/audits/2026-04-25-sub-branch-invocation-audit.md`, dev — 252 lines, commit `6943d60`) ↔ #56 design (`docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md`, dev-2 — 277 lines, landed during this session).
**Note on numbering:** dev's commit message says "Task #50 audit"; TaskList shows the audit as completed Task #51. Both numbers refer to the same audit. The design task is TaskList #55 (Task #56 in dev-2's framing).
**Purpose:** cross-check the design proposal's decisions against #50 audit's blocking gaps. Surface unresolved gaps + new opens that didn't appear in either solo doc.
**Status:** **PAIR-READ EXECUTED.** All sections populated.

---

## Stamp

**PAIR CONVERGES.** All 4 blocking gaps (B1-B4) honored. 3 of 7 non-blocking gaps closed in design (gaps #5 actor inheritance, #7 state-schema validation, #8 version pinning). Gap #11 covered by integration test footprint. The pre-pair finding (B1 + B3 already closed by sibling proposals) is confirmed: design correctly defers to #54's `execute_branch_version_async` helper for B1 and to #59 + #53 for B3 resolution chain, focusing its surface on B2 and B4. Three substantive new opens surface from the pairing (§5).

---

## 1. Constraint scaffolding from #50 audit

The #50 audit ranks 11 gaps (§G); 4 are blocking for Mark's gate-series story. The pair-read will resolve each as honored / ignored / evolved better — same shape as #59 (#54↔#56 convergence).

### 1.1 The 4 blocking gaps the design MUST address

| # | Gap | Why it blocks Mark's gate-series | Cross-ref |
|---|---|---|---|
| **B1** (= audit gap #1) | No `branch_version_id` support in `execute_branch` / `invoke_branch_spec`. Cannot invoke a canonical (which is a frozen version). | Without this, gates that resolve a (goal, scope) → branch_version_id have nowhere to send the work. The whole route-back-to-canonical story doesn't compose. | Same as G1 audit row #4 + my #56 audit's three-version-concept finding + dev-2's #54 design (`runner-version-id-bridge.md`) which directly resolves this gap with `execute_branch_version_async`. **B1 is materially CLOSED at the design layer by #54.** Pair-read should confirm BUG-005 design either uses #54's helper or re-derives it consistently. |
| **B2** (= audit gap #2) | No MCP-callable `runs action=invoke` (or similar) for spawning a sub-branch from chatbot/external intent. Only graph-internal NodeDefinition can spawn. | Without this, gate-routing is bound to graph-internal NodeDefinitions only. Chatbot can't say "run this canonical with these inputs" without a wrapping branch. | Sub-branch-specific. Likely intersects with the `run_branch_version` MCP action (#54 §4) — a graph-external `invoke_branch` MCP verb may be the same primitive at a different abstraction level, or a parallel sibling. **Pair-read question: does the design propose a new MCP verb for chatbot-driven invocation, or does it scope down to graph-internal-only?** |
| **B3** (= audit gap #3) | No goal-aware "send to canonical for goal X" verb wrapping the lookup+invoke chain. | Without this, Mark's gate must do (a) read `goals action=get`, (b) extract `canonical_branch_version_id`, (c) invoke. Three steps, error-prone, no atomicity. | Same as G1 audit row #3. dev-2-2's Task #58 (queued in TaskList: "goals action=resolve_canonical MCP read action") is the natural lookup primitive, but **the wrapping verb (lookup + invoke) is the gate-route-back design** — which is dev-2's Task #53 (`gate-route-back-verb-proposal.md`, completed). **B3 is materially CLOSED by #53 at the verb-shape layer.** Pair-read should confirm BUG-005 design composes cleanly with #53's route-back primitive — does the sub-branch primitive provide what #53 needs, or does it impose a different invocation shape? |
| **B4** (= audit gap #4) | No structured failure propagation contract between child and parent. Silent None-substitution on child fail. | Critical for auto-heal: a sub-branch that silently fails causes parent gate-series to emit bad data instead of detecting and routing. Closed-loop integrity depends on structured failure propagation. | Sub-branch-specific. **Pair-read question: does the design propose explicit child-fail → parent-fail propagation? Per-spec configurable (e.g., `on_child_fail: "fail" | "default" | "retry"`)? A new structured failure-class that bubbles up?** This is the most BUG-005-specific design call; #50 audit's recommendation of "structured failure-as-data" is the constraint the design should honor or evolve. |

### 1.2 Non-blocking gaps to watch (audit §G #5-#11)

The design may or may not address these. Ranked by impact if the design defers them:

| # | Gap | Defer? |
|---|---|---|
| **5** | Child runs default `actor="anonymous"` instead of inheriting parent's actor. | Should NOT defer — Phase B contribution-ledger work (Task #48) needs proper actor attribution on child runs. Cheap fix (one parameter pass-through). Should land with the BUG-005 design. |
| **6** | No concurrency-budget propagation parent→child. Pool starvation possible at scale. | Can defer to v2; audit notes it's not blocking at current usage. **But:** flag the deadlock risk explicitly (#50 §E "Failure pattern to flag" — 4 parents blocking-invoke 4 children deadlocks). |
| **7** | No state-schema validation of `output_mapping` keys against child's declared schema. Silent typo → None. | Should land WITH the design — composes with #54's snapshot-schema-drift handling and #59's recommended `failure_class="snapshot_schema_drift"`. Same family of validation. |
| **8** | No "pin sub-branch to a specific version_id" affordance. | Closes for free if B1 (version_id support) lands. |
| **9** | No retry-on-child-fail policy. | Probably defer to v2; depends on B4's resolution shape. |
| **10** | Recursion cap is compile-time only, not runtime-concurrency-aware. | Can defer; cap exists; runtime hardening is v2. |
| **11** | No integration test for parent→child→grandchild end-to-end through daemon. | Implementation-time test footprint, not design-doc gap. |

---

## 2. Per-blocking-gap resolution

| Gap | Resolution | Detail |
|---|---|---|
| **B1 — `branch_version_id` support** | **HONORED via sibling spec** | §3 introduces `invoke_branch_version_spec` as a NodeDefinition field mutually exclusive with the existing `invoke_branch_spec`. Mirrors #54's sibling-action pattern at the spec layer, not the action layer. The runtime builder `_build_invoke_branch_version_node` calls **`execute_branch_version_async` directly** (the helper from #54) instead of re-deriving snapshot resolution. Clean delegation; no duplication. |
| **B2 — MCP-callable invoke verb** | **EVOLVED BETTER — design rejects the new verb, rightly** | §2 explicitly does NOT add `runs action=invoke_branch`. Reasoning: a chatbot calling such a verb has no parent state to map TO; would either need a separate "input source" arg (collapses to existing `run_branch`) or accept opaque parent-state JSON (unsafe). Right primitive: chatbots compose via `extensions action=patch_branch` to add an `invoke_branch_version_spec` to a node — same MCP shape as adding any other node. **This is a smarter answer than the audit asked for.** Discoverability concern is solved by tool-description text on `patch_branch`, not by inventing a new verb. |
| **B3 — goal-aware "send to canonical" verb** | **HONORED via deferral chain** | §8 Q5 explicitly defers the goal→version resolution to Task #59 (`goals action=resolve_canonical`). This proposal stops at running a known `branch_version_id`. The chain "goal_id → canonical → invoke" is split: #59 handles goal-to-version resolution; #56 handles version-to-execution. **Clean split that respects #53's route-back design layer.** Composition: #53 calls #59 to resolve, then invokes #56's primitive (via `invoke_branch_version_spec`) to execute. Three-layer alignment. |
| **B4 — structured failure propagation** | **HONORED + sharpened with policy taxonomy** | §4 adds `RunOutcome.child_failures: list[ChildFailure]` (NEW field, NULLABLE — no behavior change for parent runs without sub-branches). Each `ChildFailure` carries `(run_id, failure_class, child_status, partial_output)`. Per-spec `on_child_fail: Literal["propagate" | "default" | "retry"]` with `propagate` as default — auto-heal correctness. **Three policy modes is sharper than the audit asked for** (audit §F just says "structured failure-as-data"; design pins concrete behavior for each). Plus retry has per-spec `retry_budget` AND global `TINYASSETS_MAX_CHILD_RETRIES_TOTAL` cap — prevents retry-storm pathology. |

---

## 3. Composition with sibling proposals

All five cross-cutting checks confirmed:

- **vs. #54 (`runner-version-id-bridge.md`):** ✓ Design uses `execute_branch_version_async` helper directly (§3 + §10 references "Task #54, committed `dc7d2cb`"). No re-derivation. The shared `_DispatchInvokeBranchCommon` helper in §3 holds input-mapping + output-mapping + on_child_fail logic so def-based and version-based builders share the resolution logic — clean DRY.
- **vs. #53 (`gate-route-back-verb-proposal.md`):** ✓ §10 references that BUG-005's `invoke_branch_version_spec` is what #53's route-back handler invokes after resolving (goal, scope) → branch_version_id. Composition is symmetric: #53 owns the routing decision and resolution; #56 owns the invocation contract. **However:** #53 §5's engine-side handler step 7 says "Invoke runner with branch_version_id (Task #54 bridge) + patch_notes as inputs." That's #54's `execute_branch_version_async`, not #56's `invoke_branch_version_spec`. **#53 invokes the runner directly, not the sub-branch graph primitive.** This isn't a divergence — #53 routes from the gate context (already running inside a parent gate-series), so the runner-level primitive is correct. #56's `invoke_branch_version_spec` is for graph-internal sub-branch composition, distinct from gate route-back. The two coexist.
- **vs. #47 (`contribution-ledger-proposal.md`):** ✓ §6 closes audit gap #5 — child runs default to inherit parent's actor (with `child_actor` override field for advanced cases). This is the load-bearing fix for Phase B contribution ledger correctness; without it, every child run would emit `execute_step` events misattributed to "anonymous."
- **vs. #58 (`attribution-layer-specs.md`):** ✓ §4 explicitly says `child_failures` entries trigger `caused_regression` events on the contribution ledger ("Tasks #48 contribution ledger emits `caused_regression` events on `child_failures` entries — closes that surface gap too"). The structured `ChildFailure` carries enough metadata (`run_id`, `failure_class`, `child_status`, `partial_output`) for attribution to identify the failing artifact.
- **vs. #57 (`canary-to-patch-request-spec.md`):** Not directly composed — canary→file_bug is graph-external; sub-branch invocation is graph-internal. They meet at the dispatcher layer, not at this primitive.

**Net composition health:** the four design docs (#54, #53, #58, #56) form a coherent stack. Each owns its layer; each defers to the others' contracts; no re-derivation. This is cleaner than I expected from solo design proposals.

---

## 4. Implementation-time constraints (separate from design-doc gaps)

To land in the dispatch task's verification list, not as design-doc rework:

- **`_DispatchInvokeBranchCommon` helper extraction.** §3 introduces this as the shared input-mapping + output-mapping + on_child_fail logic between def-based and version-based builders. Like #59 recommended splitting `_execute_branch_core` from new-helper-add for #54, splitting this helper extraction from new-spec-add gives a cleaner two-task SHIP signal.
- **Two-pool config landing order.** §5 introduces `TINYASSETS_CHILD_POOL_SIZE` env (default 6) and re-uses existing `TINYASSETS_RUN_POOL_SIZE` (was `_DEFAULT_MAX_WORKERS`). The rename + new env should land first as a no-behavior-change refactor; the two-pool dispatch logic lands second.
- **Child actor inheritance — verify parent's actor is read at compile time, not at invoke time.** §6 says compiler reads parent's actor and threads it through. Test coverage must verify actor is captured at the parent's run-claim, not at every child invocation (which would be wrong on async-with-late-await).
- **Validation of `output_mapping` against child schema** (§6 audit gap #7) — must run at branch-validate time, not at first-invocation time. Test: invalid output_mapping is rejected by `BranchDefinition.validate()` BEFORE any run starts.
- **Two-pool deadlock test.** §5 names this as integration test #4 ("Two-pool isolation: 5 parents holding parent_pool, 5 children spawning into child_pool, all complete (no deadlock)"). Must be in the test suite as a non-flaky test — flakiness on this one is a uptime risk.
- **Global retry-cap enforcement** (§4 §7 retry budget interaction). Test must exercise multi-spec retry across one parent run to confirm the global cap fires correctly when individual `retry_budget` would otherwise allow more.

---

## 5. Fresh open Qs surfaced by the pairing

Three substantive opens that didn't appear in either solo doc:

1. **Async-spawn-without-matching-await is a chatbot-author bug — design says "validate() warning, not error."** §8 Q6 names this. But warnings are easy to ignore; if a chatbot composes `wait_mode="async"` and then forgets to add an `await_run_spec` for the same run_id, the parent flows past, child completes-or-fails into the void, and `child_failures` never surfaces because no await joined. **Recommendation: promote from warning to validate-time error.** A spec-level rule that every async-spawn requires a corresponding await on the same run_id state field. The chatbot cost is trivial (chatbot must add the await node it would have added anyway); the auto-heal correctness benefit is large.

2. **Cross-actor attribution under `child_actor` override is split.** §8 Q7 calls this "truly open" — recommends override actor for `execute_step` events (they ran the work) and parent for `design_used` events (they composed the workflow). **This split needs to be encoded in the contribution ledger emission logic explicitly** (per #58 §1.1-1.2 emit-site map). Otherwise the implementation defaults to one actor for both event types and the audit trail loses the dual-attribution. **Recommendation: pin the split in #56 design now**, not at implementation time. The split is small (one extra branch in the emit handler) and pinning it now prevents inconsistent implementations later.

3. **`_DispatchInvokeBranchCommon` helper is a third version of the same shared-helper pattern** — first was #54's `_execute_branch_core` (def-based + version-based runners share core), now this is invoke-side def-spec + version-spec sharing common logic. **Pattern observation worth promoting:** every primitive that has both a def-based and version-based form is converging on the same pattern: thin def-based + thin version-based + shared core helper. Worth naming this as a project convention before further primitives bake it in inconsistently.

---

## 6. Roadmap deltas

Three updates to `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md`:

1. **Phase A item 5 (BUG-005) decomposes into 3 sub-items.** Original roadmap treats item 5 as one primitive; #56 design implicitly factors it into:
   - **5a:** `invoke_branch_version_spec` schema + sibling builder (`_build_invoke_branch_version_node`).
   - **5b:** Failure propagation contract (`RunOutcome.child_failures` + `on_child_fail` policies + retry-cap).
   - **5c:** Two-pool concurrency model (`TINYASSETS_CHILD_POOL_SIZE` + parent_pool/child_pool dispatch).
   - Plus child actor inheritance (§6 gap #5) which should land alongside 5a.
   - These are separable dispatch units; ship in this order to minimize blast radius per task.

2. **Phase A item 5 unblocks earlier than thought.** Per #59, item 5 was thought to depend on item 6 (`run_branch_version`). Confirmed by #56 design — `_build_invoke_branch_version_node` calls `execute_branch_version_async`. **Sequencing:** item 6 (#54 implementation, currently in flight per TaskList #61) must SHIP before item 5a can integrate. Items 5b + 5c are independent of item 6 and can ship in parallel.

3. **Item 5b (failure propagation) is the auto-heal-correctness load-bearing piece.** Originally roadmap §5 said the closed-loop MVP closes at end of Phase C. **Sharpening:** the loop closes for *trustable* auto-heal only when item 5b lands — without structured failure propagation, sub-branch failures cause silent corruption that breaks the feedback loop. v2 vision should call out item 5b as load-bearing for the closed-loop integrity claim, not just enabling.

---

## 7. References (updated)

- #50 audit: `docs/audits/2026-04-25-sub-branch-invocation-audit.md` (dev, commit `6943d60`).
- #56 design: `docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md` (dev-2 — landed during this session).
- Sibling design proposals already landed:
  - `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (#54, dev-2 — closes audit B1 via `execute_branch_version_async` helper, committed `dc7d2cb`).
  - `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (#53, dev-2 — closes audit B3 at verb-shape layer; cleanly composes with #56's spec).
  - `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (#47, dev-2-2 — Goal+scope substrate for resolution chain).
  - `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (#48, dev-2-2 — attribution substrate; #56 §4 emits `caused_regression` on `child_failures`).
- My audit + spec docs: `docs/audits/2026-04-25-run-branch-surface-audit.md`, `docs/audits/2026-04-25-pair-54-vs-56-convergence.md`, `docs/design-notes/2026-04-25-attribution-layer-specs.md`, `docs/design-notes/2026-04-25-canary-to-patch-request-spec.md`, `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md`, `docs/design-notes/2026-04-25-self-evolving-platform-vision.md`.
- Roadmap update needed: Phase A item 5 sub-decomposition into 5a / 5b / 5c per §6 above.

---

## 7. References

- #50 audit: `docs/audits/2026-04-25-sub-branch-invocation-audit.md` (dev, commit `6943d60`).
- #56 design: in-flight, file not yet on disk. Will land at `docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md` or similar.
- Sibling design proposals already landed:
  - `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (#54, dev-2 — closes audit B1).
  - `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (#53, dev-2 — closes audit B3 at verb-shape layer).
  - `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (#47, dev-2-2 — Goal+scope substrate).
  - `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (#48, dev-2-2 — attribution substrate).
- My audit + spec docs: `docs/audits/2026-04-25-run-branch-surface-audit.md`, `docs/audits/2026-04-25-pair-54-vs-56-convergence.md`, `docs/design-notes/2026-04-25-attribution-layer-specs.md`, `docs/design-notes/2026-04-25-canary-to-patch-request-spec.md`, `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md`, `docs/design-notes/2026-04-25-self-evolving-platform-vision.md`.
- Roadmap: Phase A item 5 (BUG-005 sub-branch invocation). Sequencing: depends on item 6 (`run_branch_version`) per pair-read #59 finding.
