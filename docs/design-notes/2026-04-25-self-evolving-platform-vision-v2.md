---
status: active
---

# Self-Evolving Platform Vision (v2)

**Date:** 2026-04-25
**Status:** Design-truth synthesis. Builds on v1 (`2026-04-25-self-evolving-platform-vision.md`); preserves v1 alongside for diff lineage. v2 ratifies primitives across 11 design docs + 4 audits + 1 roadmap landed since v1.
**Author:** navigator
**Predecessor:** v1 outline (open-Q-heavy, 7 sections).
**Successor versions:** v3+ adds federation, DAO governance, primitive-economics maturity, evaluator-mesh — see §8.

---

## 1. The closed loop

(carry-forward from v1 §1 — diagram unchanged; loop is design-truth target.)

```
[user chatbot]
    │
    ▼
[wiki: patch_request]              ←── current file_bug primitive, generalized
    │
    ▼
[wiki: patch_notes via live state] ←── processed form ready for execution
    │
    ▼
[daemon market: claim + patch_bounty]   ←── current bug bounty pool, renamed
    │
    ▼
[patch_request_to_patch_notes branch]   ←── current bug_to_patch_packet_v1, generalized
    │
    ▼
┌───────────────────────────────────────────────┐
│  Private Gate Series #1 — testing tiers       │
│  Decisions: ACCEPT / route_back / REJECT      │
└───────────────────────────────────────────────┘
    │ (accept)
    ▼
[coding team branch — user project, not platform]
    │
    ▼
[GitHub PR — opt-in via label]
    │
    ▼
┌───────────────────────────────────────────────┐
│  Private Gate Series #2 — full execution +    │
│  watch-window monitoring                      │
└───────────────────────────────────────────────┘
    │ (accept)
    ▼
[ship + future-proof watch (24h-7d)]
    │
    ▼
[bisect-on-canary + atomic surgical rollback if regression]
    │
    └──── back to top of loop if rollback triggered
```

**Lead/host endgame role unchanged:** true emergencies + meta-evolution only. Auto-heal + community evolution drive the loop.

---

## 2. What we ARE / NOT building

### NOT building (UNCHANGED from v1)

- The private gate series itself (Mark or any user builds it).
- "Coding team" agent-team as fixed pipeline (user project per host directive).
- Specific evaluators, gate logic, moderation rules, governance branches.
- Domain-specific node types.

### ARE building — RATIFIED PRIMITIVES (post-design landings)

Per the substrate landings, the primitive list is now concrete:

- **Variant canonicals** — `canonical_bindings(goal_id, scope_token, branch_version_id, ...)` table per Task #47. Step 0+1 implemented (commit `7b020ae`).
- **Sub-branch invocation (BUG-005)** — `invoke_branch_version_spec` mutually exclusive with `invoke_branch_spec`; `_DispatchInvokeBranchCommon` shared helper; structured `RunOutcome.child_failures` + per-spec `on_child_fail` policy. Splits into 5a (spec + builder + actor inheritance), 5b (failure propagation + retry-cap), 5c (two-pool concurrency).
- **Decision-routing** — `EvalVerdict.route_back` extension (#53 verdict half) + `BranchDefinition.decision_checkpoints` map with `@<name>` syntax (#58 named-checkpoint half).
- **`run_branch_version`** — sibling action calling `execute_branch_version_async` helper (#54).
- **`ContributionEvent` ledger** — single `contribution_events` table; 5 event types (`execute_step`, `design_used`, `code_committed`, `feedback_provided`, `caused_regression`).
- **Surgical rollback** — atomic-rollback-set + bisect-on-canary (#57).
- **GitHub PR bridge** — webhook + opt-in via `patch_request` label (#55).
- **Canary→file_bug seam** — per-canary thin-module wiring + 6h throttle + Jaccard server-side dedup.
- **Visibility per-piece** — `visibility=private` flag on Branch / Node / Soul / Evaluator.

### Meta-pattern (NEW in v2): "extend existing primitives over adding new ones"

Independent convergence from #53 (verdict extension, not new MCP action) and #56 (chatbots compose via `extensions action=patch_branch`, not new `runs action=invoke_branch`) names a project principle: **when a new capability can ride an existing primitive's contract, prefer that. Add a new primitive only when the existing surface fundamentally cannot carry the new semantics.** Both pivots independently rejected the obvious-but-wrong "add a new MCP verb" answer.

This composes with `project_user_builds_we_enable`: every primitive we ship is reused by every user-built piece. Bloating the primitive surface is a tax on every future user.

### Meta-pattern (NEW in v2): shared-helper pattern for def/version sibling primitives

Twice now, the substrate has surfaced primitives with both a "live def" form and a "frozen version" form — the right pattern is **thin def-form + thin version-form + shared core helper**:

| Instance | Def form | Version form | Shared core |
|---|---|---|---|
| Runner (#54) | `execute_branch_async` | `execute_branch_version_async` | `_execute_branch_core(branch_version_id=None)` |
| Sub-branch invocation (#56) | `invoke_branch_spec` + `_build_invoke_branch_node` | `invoke_branch_version_spec` + `_build_invoke_branch_version_node` | `_DispatchInvokeBranchCommon` |

Future primitives with both shapes (likely candidates: cross-run state query, scheduled invocations, dispatcher claims) should adopt this pattern. Captured for follow-on convention doc.

---

## 3. Five contribution surfaces (RATIFIED)

All five emit into the single `contribution_events` ledger (per #48 single-table model).

| # | Event type | Trigger (RATIFIED emit-site) | Weight (RATIFIED) | Source |
|---|---|---|---|---|
| 1 | `execute_step` | Step finalize on a run; `runs.daemon_actor_id` populated | 1.0 flat | #58 §1.1, #48 §3 |
| 2 | `design_used` | Step references published artifact; per-reference event | 1.0 default; 0.5 node, 0.3 soul (calibration) | #58 §1.2, #48 §3 |
| 3 | `code_committed` | GitHub webhook `pull_request.closed` + `merged=true` + `patch_request` label | `1.0 × pr_size_factor × coauthor_split_factor` | #58 §1.3, #48 §3, #55 |
| 4 | (lineage credit derived at calc-time, not emit-time) | n/a — fork_from walk + decay | `1.0 × α^depth` (α = 0.6, max_depth = 12) | #58 §3, #48 §1.3 |
| 5 | `feedback_provided` | Gate evaluator cites artifact in decision metadata; **anti-spam: no cite, no credit** | `0.1 × gate_decision_strength × evidence_strength_multiplier` | #58 §1.4, #48 §3 |
| (E19) | `caused_regression` | Post-merge canary regression in watch-window AND attribution chain identifies artifact | -10 (P0) / -3 (P1) / -1 (P2); proportional to merge-time positive share | #58 §6, #57 |

### Ratified semantics (closed in v2)

- **Sybil scoring scales DISTRIBUTION, not events.** Events recorded at full weight (audit integrity); bounty distribution multiplies by `sybil_confidence_score`. Past distributions stay as-issued.
- **Daemon-host credits don't bear regression liability** (#58 §6.3) — only designers and committers chose what to ship; daemons just executed. Regression-distribution skips `execute_step` events.
- **Lineage decay coefficient α = 0.6, max_lineage_depth = 12.** Bounty calc result includes `truncated_at_depth` flag if cap fires. Storage in `tinyassets/economics/decay.py` (config-as-code; PR-required to change).
- **Bounty distribution math** — 3-pass (positive_contributions + negative_contributions + sybil-scaled normalization). Sub-0.5% shares bucket into pool remainder. 48h challenge window before auto-distribute; navigator/quorum mediates disputes.
- **Route-back attribution emission (CORRECTED from v1):** route-back invocations emit TWO events — `feedback_provided` for the original patch author (gate consumed their patch_notes as decision input) + `design_used` for the canonical's author (their canonical was used to handle the routed work). Replaces #53 §5's earlier "code_committed-like" placeholder. (Closure of the pair-read flag from `2026-04-25-audit-53-gate-route-back-solo.md` §2.)

### `PatchNotes` typed dataclass (NEW in v2)

Per audit-53 §4 Q2 ratification: `patch_notes` payload is typed, not opaque. Required fields:

```python
@dataclass
class PatchNotes:
    reason: str                              # why route-back fired
    evidence: list[dict[str, Any]]           # citation refs (artifact_id, kind)
    suggested_changes_json: dict[str, Any]   # what should change downstream
    _route_history: list[tuple[str, str]] = field(default_factory=list)  # (goal_id, scope_token) chain for cycle detection
```

Pin now while #56's `ChildFailure` shape is fresh. Prevents implementations defaulting to opaque dicts.

---

## 4. Primitives audit table (RATIFIED VERSION)

Every row in v1 §4 was either a gap or a pending design. V2 records the resolution state.

| Primitive | v1 status | v2 RATIFIED state | Implementation status |
|---|---|---|---|
| Canonical-branch-for-goal (single) | "in place" | UNCHANGED at single-canonical | Live, fully implemented. |
| Variant canonicals — `canonical_bindings` table | HIGH priority gap | **DESIGNED + IMPLEMENTED Step 0+1** | Schema lives; backfill done at commit `7b020ae`. Step 2 (dual-write) in flight (TaskList #60). |
| Sub-branch invocation (BUG-005) | HIGHEST priority gap | **DESIGNED** (#56) | Audit + design + pair-read converged. Phase A item 5 splits 5a/5b/5c. Implementation pending dispatch. |
| Daemon contribution ledger | HIGH priority gap | **DESIGNED** (#48 single-table, 5 event types) | Schema not yet implemented; emit-sites enumerated. |
| Usage-event ledger (`design_used` events) | HIGH priority gap | **DESIGNED** — same `contribution_events` table; lineage walk derived at calc-time | Same as ledger above. |
| External-PR bridge | MEDIUM priority gap | **DESIGNED** (#55 — webhook + opt-in `patch_request` label + carve-outs) | Pending implementation dispatch. |
| Real-user-feedback credit | MEDIUM priority gap | **DESIGNED** (#58 §1.4 — anti-spam: no cite, no credit; pool-share at distribution) | Emit-site lives in gate evaluator decision logic; pending sample evaluator integration. |
| Gate-series composition primitive | HIGH priority gap | **DESIGNED** — typed output contract = #53 verdict extension + #58 named-checkpoint | Typed-output-contract design closed; impl pending. |
| Decision-routing (named-checkpoint contract) | MEDIUM priority gap | **DESIGNED** (#58 — `decision_checkpoints` map + `@<name>` syntax + reserved `@END`/`@START`) | Pending impl dispatch. |
| Surgical rollback (bisect-on-canary + atomic-rollback-set) | MEDIUM priority gap | **DESIGNED** (#57 — atomic-rollback-set + watch-window + bisect-on-canary; auto-fires P1+, P2 emits event only) | Pending impl dispatch. |
| Fair-distribution calc | MEDIUM priority gap | **DESIGNED** (#58 §4 — 3-pass calc + 48h challenge window + navigator dispute mediation) | Pending impl dispatch. |
| Sandbox (BUG-017 critical) | HIGHEST research priority | **STILL UNRESOLVED — research track open** | Bubblewrap broken; tech selection (WASM / gVisor / Firecracker / per-node container) pending host decision. |
| Symmetric-privacy read filter | MEDIUM priority gap | **DESIGNED** in concept (per-row `visibility` on `canonical_bindings`); cross-cutting filter for canonical reads still TBD | Schema lives; canonical-read filter implementation pending. |
| Outcome attribution + aggregation | MEDIUM priority gap | **PARTIALLY DESIGNED** (#58 §6 negative events; #57 watch-window + caused_regression metadata) | Outcome aggregation per branch_version_id pending. |
| `run_branch_version` MCP action | NOT in v1 | **DESIGNED** (#54 sibling action + audit-paired #56) | Pending impl dispatch (Task #61 in flight is the precursor). |
| `goals action=resolve_canonical` MCP read | Implied | **PENDING DESIGN** (Task #59 in flight, dev-2-2) | Design hasn't landed. |
| Generalize bug → patch_request | Additive | **DESIGNED** — additive (file_bug stays as user-vocabulary verb; submit_patch_request is broader sibling). `kind=feature/design` routing implemented (Task #54 completed). | Routing landed; verb naming additive in v3+. |
| Branch / Node / Soul / Evaluator visibility=private | MEDIUM priority gap | **STILL DESIGNED at field level**; needs cross-cutting filter | Pending. |
| `_execute_branch_core` shared helper extraction | NEW from #59 pair-read | **PENDING** — separate dispatch unit before #54 implementation | Implementation prerequisite. |
| `_DispatchInvokeBranchCommon` shared helper | NEW from #56 design | **DESIGNED** | Implementation prerequisite. |
| `PatchNotes` typed dataclass | NEW in v2 | **DESIGNED** (§3 above) | Pending impl dispatch. |

**Ratified primitive count:** 18 designed (vs. v1's 11 gap rows). Substantial substrate consolidation in <12 hours of design work.

---

## 5. Open questions — RATIFIED OR STILL OPEN

V1 §5 had ~30 open questions across E1-E19 + G1-G6 + A1-A6. Status now:

### CLOSED by substrate landings

- **E2 meta-primitive layer** — partial: meta-NodeDefinition design deferred, but the pattern is established (sub-branch invocation, named-checkpoint contract, variant canonicals are all instances of "primitive composition over fixed types").
- **E3 auto-heal closed loop demo** — designed end-to-end (canary→patch_request seam #57, gate-series #53+#58, sub-branch invocation #56, ledger emission #58, surgical rollback #57). Demo executable post-impl.
- **E9 gate-series composition primitive** — closed: typed output contract via #53 verdict + #58 named-checkpoint.
- **E10 decision-routing — state machine vs. linear** — closed: named-checkpoint primitive (#58) provides the state-machine substrate.
- **E11 auto-rollback safety / cascading reverts** — closed by #57 (atomic-rollback-set + bisect-on-canary).
- **E12 real-user-proof-of-fix as gate input** — closed via `feedback_provided` event with anti-spam invariant (gate-cite required).
- **E13 coding-team handoff** — closed at design level: class-routing via daemon market (community competition).
- **E14 PR-bridge mechanics** — closed: opt-in via label + carve-outs (#55).
- **E15 daemon contribution recording** — closed: single-table model (#48); `daemon_actor_id` on runs.
- **E16 feedback monetization granularity** — closed: pool-share at distribution events (no microtransactions); base weight 0.1.
- **E17 GitHub-handle missing case** — closed: today's CONTRIBUTORS.md format honors both cases; retroactive linking primitive.
- **E19 negative contribution events** — closed: `caused_regression` event type with severity-magnitude weights.
- **G1 canonical primitive audit** — closed by audit + #47 design.
- **G2 Mark gate-series gaps** — 4 blocking gaps closed by #54 (B1) + #53 (B3) + #56 (B2, B4).
- **G3 private collection primitive** — closed: per-piece visibility flag (Option A), not Collection object.
- **G4 variant-canonical model** — closed: scope_token (Option γ from v1; Path 1 from #47).
- **G5 outcome → auto-patch_request evolution mechanism** — designed at concept level via `caused_regression` + auto-investigation; impl in #57.
- **A1-A6 attribution surfaces** — closed by #48 + #58.

### REMAINING OPEN — host decision required

- **E1 rename rollout** — file_bug stays user-vocabulary; broader naming generalization is v3+.
- **E18 sybil resistance with monetization** — explicit override of `project_paid_market_trust_model`. Three sketches in #58 §5 (vouching / GitHub anchor / decay-on-bad-vouches). **Host pick required before bounty payout ships.** Recommendation: A + B in v1, layer C in v2 once vouching activity accumulates data.
- **E4 (subset) — community-iteration primitives we don't have yet** — sandbox (BUG-017) gating decision still open.
- **G6 reframe-strength** — confirmed: every "build X for users" reshaped as "ship primitive for users to build X" — but carve-outs (uptime emergency where platform builds directly) need explicit policy.
- **PLAN.md update timing** — host approves v2 design-truth → PLAN.md update follows.

### DEFERRED to v3+ (research / longer-horizon)

- Federation horizon (multi-instance ActivityPub-shaped).
- DAO governance evolution timing.
- Economic-incentive activation timing (when to flip from earn-only to earn-and-payout).
- Sandbox technology selection (WASM vs. gVisor vs. Firecracker vs. per-node container).
- E5 casual-vs-hardcore funnel — registry as gateway is correct framing; substrate pending.
- E6 self-evolving governance — meta-patch_request lane design pending.
- Constitutional-amendment lane (host-veto + DAO quorum future).
- The two true opens from #56 (async-spawn-without-await error vs warning; cross-actor attribution under child_actor override).
- Q1 from #53 (verdict-string vs separate `GateDecision` union type — revisit if verdict count grows > 6).

**From ~30 v1 opens to ~5 ratification gates + ~10 v3+ items.** Substantial consolidation.

---

## 6. Phase A/B/C/D/E milestones (RATIFIED PHASING)

Per roadmap (`docs/design-notes/2026-04-25-primitive-shipment-roadmap.md`), with deltas captured:

### Phase A — gate substrate

Items 1-7 + Phase A item 5 sub-decomposition into 5a/5b/5c per pair-read #60 §6:

- 1. Storage-layer authority refactor.
- 2. `canonical_bindings` table + `scope_token` (**implemented commit `7b020ae`**, dual-write Step 2 in flight).
- 3. `lookup_canonical(goal_id, scope)` MCP read action (Task #59 in flight).
- 4. Decision-routing primitive — splits into 4a (verdict, **closed by #53**) + 4b (named-checkpoint, **closed by #58**).
- 5. Sub-branch invocation (BUG-005) — splits into:
  - 5a: `invoke_branch_version_spec` + builder + actor inheritance. **Depends on item 6 SHIP.**
  - 5b: Failure propagation contract. **Independent of item 6.**
  - 5c: Two-pool concurrency. **Independent of item 6.**
- 6. `run_branch_version` (#54). **Item 5a depends on this.**
- 7. Gate-series typed-output contract — half-closed by #53 (verdict) + half-closed by #58 (named-checkpoint).

**End of Phase A capability:** Mark can author a private gate series end-to-end with all decision routing, version-pinned execution, and structured failure handling.

### Phase B — contribution + attribution

Items 8-12: contribution_events ledger + lineage walk + per-step `daemon_actor_id` + `execute_step` + `design_used` events.

**End of Phase B capability:** every step + every artifact use emits credit events. Economic ledger live (no payout yet — gated on E18).

### Phase C — closed loop end-to-end (auto-heal MVP)

Items 13-16: generalize bug → patch_request + canary→file_bug seam (#57 spec) + outcome attribution + auto-patch_request on drift.

**End of Phase C capability:** Auto-heal MVP closes the loop for auto-detect → manual-merge case. Trustable closure requires Phase A item 5b (structured failure propagation) — without it, sub-branch failures cause silent corruption.

### Phase D — external bridge + economic loop

Items 17-22: GitHub PR webhook (#55) + bounty distribution calc (#58) + sybil resistance (gated on E18) + negative ContributionEvents + rollback-set as truth-source.

**End of Phase D capability:** Community contributors credited and bountied. Loop closes fully autonomously for routine cases.

### Phase E — rollback + governance

Items 23-27: bisect-on-canary (#57) + atomic-rollback-set (#57) + watch-window freeze + sandbox (BUG-017, parallel-track research) + meta-patch_request lane.

**End of Phase E capability:** Loop is autonomously safe under regressions. Constitutional changes have a defined lane.

---

## 7. Implementation status snapshot

What's committed vs. designed vs. pending design:

### Committed to main (selected, this session)

- Variant canonicals schema + backfill (Step 0+1) — commit `7b020ae` (dev-2-2).
- BUG-005 sub-branch audit — commit `6943d60` (dev).
- Run_branch sibling-action design — commit `dc7d2cb` (dev-2; #54).
- Multiple SHIPs across the session: v1 vision, primitive-shipment roadmap, contribution ledger proposal, BUG-005 design, surgical rollback design, named-checkpoint design, external-PR bridge design, attribution-layer specs, canary-to-patch_request spec, three pair-reads/audits.

### Designed, NOT implemented (dispatch pending)

All 18 ratified primitives in §4 except the three already implemented (variant canonicals, file_bug kind routing, fork_from MCP). Phase A items 4a/4b/5a/5b/5c/6/7 are the highest-priority dispatch queue.

### Pending design

- `goals action=resolve_canonical` (Task #59, dev-2-2 in flight).
- Sandbox technology selection (BUG-017, host decision).
- Constitutional-amendment lane (v3+).
- Federation primitives (v3+).

### Pre-impl dispatch units flagged

- `_execute_branch_core` shared helper extraction (split before #54 impl per pair-read #59 §3).
- `_DispatchInvokeBranchCommon` shared helper extraction (split before #56 impl per pair-read #60 §4).
- Two-pool config rename (`_DEFAULT_MAX_WORKERS` → `TINYASSETS_RUN_POOL_SIZE`) before two-pool dispatch logic.
- `PatchNotes` typed dataclass before #53 implementation.

---

## 8. v3+ horizon

What v3 likely adds (not designed yet; placeholder):

- **Federation primitives.** Multi-instance Workflow installations federate. A primitive authored on instance A consumed by users on instance B. Registry shape needs to support distributed identity + cross-instance attribution. Architecturally load-bearing — affects `actor_id` opacity decisions and ContributionEvent ledger sharding.
- **DAO governance evolution timing.** When does host-veto-only convert to DAO-weighted? Memory `project_dao_evolution_weighted_votes` outlines weighted-votes + permanent-minimum-leverage + gradual-handoff. v3 picks activation criteria.
- **Sandbox tech selection.** BUG-017 resolution is the gating decision for any user-authored code primitive running daemon-side.
- **Primitive-economics maturity.** Today's bounty distribution is conceptually clean but unproven at volume. v3 ratifies pool-replenishment cadence, payout batching, dispute escalation thresholds based on observed volume.
- **Evaluator-mesh.** Today evaluators are per-branch nodes. At scale, a registry of typed evaluators (TypeAssert / ContentScore / RegressionDetect / etc.) becomes its own discoverable surface — chatbots compose gate-series from registered evaluators rather than re-implementing per-branch.
- **Cross-domain primitive sharing.** Today domains are scoped (per memory `project_memory_scope_mental_model`). A primitive proven cross-domain useful needs a "promote to engine" path. v3 designs the promotion + provenance path.
- **Constitutional-amendment lane.** Meta-patch_request type for changes-to-the-loop-itself. Host-veto + DAO quorum future. v3 pins the lane.

---

## 9. References

- v1 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision.md`.
- Roadmap: `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md`.
- Design proposals: `2026-04-25-{variant-canonicals,contribution-ledger,runner-version-id-bridge,sub-branch-invocation,gate-route-back-verb,named-checkpoint-routing,surgical-rollback,external-pr-bridge}-proposal.md` + `2026-04-25-{attribution-layer-specs,canary-to-patch-request-spec}.md`.
- Audits: `2026-04-25-{canonical-primitive,sub-branch-invocation,run-branch-surface}-audit.md` + `2026-04-25-pair-{54-vs-56,50-vs-56}-convergence.md` + `2026-04-25-audit-53-gate-route-back-solo.md`.
- Memory load-bearing for v2 ratification:
  - `project_user_builds_we_enable` — primitives shipped, communities use.
  - `project_designer_royalties_and_bounties` — N-gen decay, royalty math.
  - `project_paid_market_trust_model` — E18 override candidate (sybil with monetization).
  - `project_full_platform_target` — closed-loop endgame.
  - `project_chain_break_taxonomy` — three-layer System→Chatbot→User lens.
  - `project_evaluation_layers_unifying_frame` — gate-series as Branch composition.
  - `project_user_builds_we_enable` — applied recursively to gates, evaluators, coding teams.
- Implementation commits captured in §7.

---

## 10. v2 → v3 transition criteria

v3 dispatches when:
1. E18 host go/no-go on sybil resistance lands.
2. Phase A primitives (items 1-7) ship to main.
3. Phase B contribution_events ledger lands and accumulates ≥30 days of execute_step + design_used data.
4. Phase C auto-heal MVP demo runs end-to-end at least once.

**v2 is the design-truth checkpoint between "extensive design" and "extensive implementation."** When the four criteria land, v3 captures the next architectural layer (federation, DAO, primitive economics maturity).
