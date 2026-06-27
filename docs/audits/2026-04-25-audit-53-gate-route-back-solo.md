# Solo Audit — #53 Gate-Route-Back Verdict Extension

**Date:** 2026-04-25
**Author:** navigator
**Audit target:** `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (dev-2 — Task #53, completed earlier this session).
**Audit shape:** SOLO audit, NOT pair-read. No navigator-side audit pre-exists for #53; this is a navigator review against the now-rich substrate of paired pieces.
**Constraints checked against:**
- v1 vision (`docs/design-notes/2026-04-25-self-evolving-platform-vision.md`) — closed-loop integrity, route-back semantics, symmetric privacy.
- Roadmap (`docs/design-notes/2026-04-25-primitive-shipment-roadmap.md`) — Phase A items 3 (`lookup_canonical`), 4 (decision-routing), 7 (gate-series typed-output contract).
- Substrate of paired-converged docs: #47 variant canonicals, #48 contribution ledger, #54 runner version-id bridge, #56 sub-branch invocation, #58 attribution layer specs.
- Cross-doc consistency at the boundary: does #53 cite + use what its declared dependencies actually provide?

---

## Stamp

**AUDIT CLEARS WITH ONE SUBSTANTIVE FLAG.** Eight of nine verdict-band dimensions are sound. One material gap: #53 §5 names "`code_committed`-like contribution event" as the route-back attribution emission, but `code_committed` is the wrong event type per #58 §1.3 (which scopes `code_committed` to GitHub PR merges). Route-back resolution is in-graph routing — needs either a new event type or correct re-attribution. Detail in §2 below.

Three of #53's five open questions are now closeable given the substrate landings (§4). Two remain genuinely open.

---

## 1. Verdict bands per dimension

| Dimension | Verdict | Rationale |
|---|---|---|
| **`verdict_extension` vs new MCP action** | **CORRECT** | #53 §1's pivot from "new MCP verb" to "verdict extension" is the right primitive. Route-back is intrinsic to the evaluator's run, not external. A new MCP action would force three round-trips for what should be one engine-side transition. The `EvalVerdict = Literal[..., "route_back"]` extension is minimal-surface-area + maximally compositional. **Same architectural shape as #56 §2's "do NOT add MCP verb, use existing primitive"** — independent convergence on the same principle. Healthy. |
| **`cycle_detection` (max-depth=3 + visited-set)** | **CORRECT, depth-cap configurable per §6 Q3** | Belt-and-braces. Either alone would have edge cases: depth-only fails on A→B→A→B (length 4 but visits A twice); visited-only fails on legitimately deep chains where a primitive is reused at different generations. Both together are robust. Depth=3 default is conservative — almost always far more than legitimate use cases need; the env-tunable `TINYASSETS_ROUTE_BACK_MAX_DEPTH` per §6 Q3 lets emergency adjustments bypass migration. |
| **`sync_vs_async` (sync default)** | **CORRECT, with one caveat below** | Sync gate-series → routed-run → continuation is the right default. Async creates state-management hell; long-running routed branches handle their own throughput via existing runner timeout. **Caveat:** §5 sync-only means a 3-hop route-back chain serializes wall-clock. For Mark's tier-2 use case (test/integration/user-sim/real-user gates) this is fine; for production high-volume routing it could become a bottleneck. §6 Q4 correctly notes "revisit at high volume." |
| **`failure_modes` taxonomy (`no_canonical_bound`, `canonical_artifact_missing`, `route_back_loop`, `evaluator_contract_violation`)** | **CORRECT + sharper than I'd have specified** | Four distinct error classes for four genuinely distinct failure modes. Each carries diagnostic `details` payload. The `evaluator_contract_violation` class for "verdict=route_back but route_to is None" is exactly the structural-typing benefit of the verdict extension — caught at `__post_init__`, not silently propagated as a None-write. |
| **`fallback_chain` (fail-fast, NOT hold-for-bind)** | **CORRECT** | §6 Q5 correctly rejects the "hold-for-host-bind" alternative as async-state-hell. Fail-fast with `details.suggested_action="bind a canonical for (goal, scope) then re-run"` (§6 Q5 recommends this) is the right user-actionable surface. Composes with E18 sybil-resistance — fail-fast doesn't expose state to bad actors mid-routing. |
| **Composition with #54 (`execute_branch_version_async`)** | **CORRECT chain** | §5's hard dependency on #54 is named explicitly. The engine-side handler step 7 ("Invoke runner with branch_version_id (Task #54 bridge) + patch_notes as inputs") is the right call site. Per pair-read #50↔#56 §3, this differs from #56's `invoke_branch_version_spec` (graph-internal sub-branch composition) — #53 invokes the runner directly because it's already running inside a parent gate-series; the runner-level primitive is correct. **Two distinct invocation contexts, two distinct primitives, both delegating to the same `execute_branch_version_async` core.** |
| **Composition with #47 variant canonicals (resolution chain)** | **CORRECT** | §3's SQL sketch lifts the resolver query verbatim from #47 §3 — `scope_token IN (:route_to_scope, '')` ordered by exact-match preference. Falls back to default unscoped, ensuring rejected-patch routing works even when requested scope has no specific binding. Viewer-aware via `runs.actor` field — symmetric privacy preserved. |
| **Composition with #48 contribution ledger (route-back emission)** | **MATERIAL FLAG — see §2** | #53 §5 names "emit `code_committed`-like contribution event" crediting the routing chain. **`code_committed` is the wrong event type** per #58 §1.3, which scopes it specifically to GitHub PR merges (`event_type = code_committed` triggered by `pull_request.closed merged=true` with `patch_request` label). Route-back is in-graph routing, not a PR merge. This is a cross-doc terminology slip; substantive details in §2. |
| **Composition with #59 `goals action=resolve_canonical`** | **DEFERRED CORRECTLY** | §1 names `goals action=resolve_canonical(goal_id, canonical_scope=...)` as a chatbot-side preview surface; §7 explicitly says "ships with Task #47's resolver implementation; this proposal only names it as a chatbot-side preview surface." #59 hasn't landed yet (TaskList shows it pending). #53 doesn't depend on #59 at engine-side — the engine-side resolver in §3 reads `canonical_bindings` directly via the SQL chain, not via the MCP verb. Clean split: #59 is for chatbots authoring gates; #53 engine-side does its own resolution. |

---

## 2. The `code_committed`-vs-route-back attribution slip

#53 §5 says:

> "Each route-back resolution emits a `code_committed`-style event to the contribution ledger (Task #48 §1) crediting the original patch author + the routing chain's intermediate authors."

But per #58 §1.3 (and #48 §1.1 enum), `code_committed` is precisely scoped:

> "**Trigger:** GitHub webhook `pull_request.closed` with `merged=true` AND PR carries the `patch_request` label."

A route-back doesn't merge anything to GitHub. It's an in-graph evaluator-decision-driven sub-branch invocation. The author being credited is the patch-filer (whose patch_notes are being routed), not a PR committer.

**What event type SHOULD route-back emit?**

Three options:

**(a)** Use existing `feedback_provided` (per #48/#58 §1.4). The route-back's `patch_notes` payload IS feedback the gate-series consumed as decision input. The original patch_filer (whose patch_notes are routed) earned `feedback_provided` credit when the gate cited their content as triggering the route-back. **Fits semantically.** Anti-spam invariant (feedback only credited when gate cites) is preserved — gate's verdict literally cited the patch_notes in deciding to route.

**(b)** Add a new event type `route_back_invoked` to the #48 enum. Captures the exact action without overloading existing types. Extension cost is small (per #48 §6 Q1 — fixed initial enum + open registry); but adds a 6th event type when the existing taxonomy could cover it.

**(c)** Keep #53's wording as a *combination*: emit `feedback_provided` for the original patch author (since the gate consumed their patch as decision input) AND emit `design_used` for the canonical's author (since their canonical was used to handle the routed work). Two events, no new event type. **Cleanest semantic fit + uses only existing types.**

**My recommendation: (c).** Two events per route-back, both via existing event types. Maps cleanly to #58 §1.2 and §1.4 emit-site logic. **Action item:** #53 should be sharpened to specify (c) explicitly, OR a #53-v2 follow-on amends §5's "emit `code_committed`-like" to "emit `feedback_provided` (patch author) + `design_used` (canonical author)."

This is a doc-clarity issue, not a design-soundness issue. The resolution is small. Recommend: file as a #53-v2 amend or fold into v2 vision doc. Does NOT block #53's main design landing.

---

## 3. Closed-loop framing — does route-back compose with Phase C MVP?

**Yes, with the §2 attribution caveat.** Specifically:

The Phase C closed-loop MVP per roadmap §5 is: canary detects red → files patch_request → daemon claims → runs canonical bug-investigation branch → patch packet attaches → manual lead-mediated PR + merge → canary green. **Route-back is the gate-series Branch's mechanism for cycling within step 4 (running canonical investigation)** — when a tier-1 evaluator inside the bug-investigation gate decides "this needs another iteration," it routes back via #53's verdict extension to the canonical with augmented patch_notes.

The composition stack at runtime:

```
canary failure → wiki:file_bug → daemon claim
                    │
                    ▼
        canonical bug_investigation branch (Mark's bug_to_patch_packet_v1)
                    │
                    ▼
        gate-series evaluator (test tier 1)
              │
       evaluator returns EvalResult(verdict="route_back",
                                     route_to=(goal_X, scope=user:mark),
                                     patch_notes={...augmented...})
              │
              ▼
       engine-side handler resolves (goal, scope) via #47 chain
              │
              ▼
       calls execute_branch_version_async (#54 helper)
              │
              ▼
       sub-branch run completes; gate-series continues based on terminal status
              │
              ▼
       contribution ledger emission: feedback_provided + design_used per §2 above
              │
              ▼
       loop closes back to gate-series's next evaluator OR terminal status
```

**The composition pierces the closed loop correctly** — route-back is invisible from the outer canary→merge perspective; it's an internal optimization where the gate-series can self-cycle without escalating up to the MVP loop's outer mechanics. **Strong design property.** Without route-back, every gate-internal correction would have to escalate to a full re-investigation — the loop would still close but with much higher latency.

---

## 4. Open-Q resolution status (#53 had 5 open Qs)

| Q# | #53's question | Status given substrate |
|---|---|---|
| Q1 | Verdict-string vs separate `GateDecision` union type | **STILL OPEN.** No substrate has touched this. Recommendation in #53 ("verdict-string for v2 simplicity, revisit if states grow > 6") is sound; v3+ thing. |
| Q2 | `patch_notes` payload schema (opaque vs typed) | **NOW CLOSE-ABLE.** #56 design landed structured `ChildFailure` and `RunOutcome.child_failures`. Same pattern applies: typed `PatchNotes` dataclass with required fields (`reason`, `evidence`, `suggested_changes_json`) wins. The "wait until gate-series typed-output contract from v1 vision §2 lands" rationale is now overtaken by #56's structured-failure precedent. **Recommendation: pin typed.** |
| Q3 | Cycle detection — visited-set vs depth-only | **CLOSED.** #53 picked both + env-tunable depth (`TINYASSETS_ROUTE_BACK_MAX_DEPTH`). Sound; no substrate adjustment needed. |
| Q4 | Sync vs async route-back execution | **CLOSED.** #53 picked sync. Composition with #56 (sync-only sub-branch invocation) reinforces the right default. Mark for revisit when async-needing personas surface. |
| Q5 | Fallthrough chain — fail-fast vs hold-for-host-bind | **CLOSED.** Fail-fast picked. Composes cleanly with E18 sybil-resistance and avoids async-state-hell. |

**Q2 close-able now is the highest-leverage open** — pinning typed `PatchNotes` while #56's structured-shape pattern is fresh prevents future implementations from defaulting to opaque dicts.

---

## 5. Cross-doc consistency check

| Cross-ref | Verdict |
|---|---|
| #53 → #54 (`execute_branch_version_async` for runner invocation) | ✓ §5 step 7 correctly cites the helper |
| #53 → #47 (resolver chain) | ✓ §3 SQL sketch lifts #47's resolver verbatim |
| #53 → #48 contribution ledger | ✗ §5 names `code_committed` — wrong event type per #58 §1.3 (see §2 above) |
| #53 → #59 `goals action=resolve_canonical` | ✓ Deferred correctly to chatbot-side preview surface; engine-side does its own resolution |
| #53 → v1 vision Phase A item 3 (`lookup_canonical`) | ✓ Engine-side handler step 4 implements it inline; #59 surfaces same logic as MCP read |
| #53 → v1 vision Phase A item 7 (gate-series typed-output contract) | ⚠ #53 EXTENDS the existing `EvalVerdict` enum, which is the precursor to the typed-output contract. Item 7 hasn't landed yet but #53 is doing the work. **Worth flagging:** when item 7 design lands (Task #58 named-checkpoint contract, currently in-flight per TaskList), it should explicitly absorb the verdict-extension work. Otherwise we have two parallel typed-output contracts — one in #53 verdict-string land, one in named-checkpoint land. |

The #53→#58-named-checkpoint coupling is the only fresh cross-doc concern that didn't show up in the pair-read trio. **When Task #58 (named-checkpoint) lands, the design should reference #53's verdict extension as the verdict half of the gate-series typed-output contract.** Otherwise we'll have a divergence to reconcile in v2.

---

## 6. Roadmap implications

Three updates to capture (will fold into v2 roadmap when D executes):

1. **Phase A item 4 (decision-routing primitive)** — original roadmap §4 row treats this as "named-checkpoint contract." Per #53, decision-routing has TWO halves: (a) verdict shape (route_back, EvalVerdict extension — closed by #53) and (b) named-checkpoint targeting (still pending — Task #58). Roadmap should mark item 4 as item 4a (verdict, closed by #53) + item 4b (named-checkpoint, in-flight as Task #58).

2. **Phase A item 7 (gate-series typed-output contract)** — same observation: half-closed by #53. The remaining work is named-checkpoint composition. Roadmap should reflect that #53 + #58 named-checkpoint together close item 7.

3. **`PatchNotes` typed dataclass** — newly close-able per §4 Q2 above. Belongs as a small Phase A sub-item or Phase B prerequisite. Lightweight; easy to specify; one design pass.

---

## 7. What this audit does NOT cover

- **No re-design of #53.** Audit clears it; one cross-doc fix (the `code_committed` slip) is the only flag.
- **No live MCP probe.** Paper audit only.
- **No code-touching review.** #53 is design-only; implementation hasn't dispatched.
- **No verification of #59 resolve_canonical specifics.** Design hasn't landed.
- **No verification of #58 named-checkpoint coupling.** Design hasn't landed; flagged as future cross-doc concern.

---

## 8. References

- Audit target: `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (#53, dev-2).
- Substrate cross-checked:
  - `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (#54).
  - `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (#47).
  - `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (#48).
  - `docs/design-notes/2026-04-25-attribution-layer-specs.md` (#58 — `code_committed` scope check).
  - `docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md` (#56 — sub-branch composition baseline).
- v1 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` §2 (decision-routing primitive named-checkpoint contract — half-closed by #53, half pending).
- Roadmap: `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md` Phase A items 4, 7 — sub-decomposition needed per §6.
- Pair-reads completed: `docs/audits/2026-04-25-pair-54-vs-56-convergence.md`, `docs/audits/2026-04-25-pair-50-vs-56-convergence.md`.
- TaskList state at audit: #59 (resolve_canonical) pending, #58 (named-checkpoint) in-flight, #61 (canonical_bindings impl) in-flight.
