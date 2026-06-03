---
status: active
---

# Primitive Shipment Roadmap

**Date:** 2026-04-25
**Author:** navigator
**Status:** Roadmap synthesis for the Next-Level Primitives push — pulls from v1 self-evolving-platform vision §4 + canonical primitive audit + variant-canonicals proposal, and consolidates the 22 filed bugs into a single strategic execution plan. Sequencing is design-truth-target; specific dispatch ordering remains lead/host call.
**Builds on:**
- `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` (v1 vision §4 audit table)
- `docs/audits/2026-04-25-canonical-primitive-audit.md` (G1 — current state of canonical primitive)
- `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (Path 1 picked — `canonical_bindings` table + scope_token)
- `[PENDING #48]` — dev-2-2's contribution-ledger schema design proposal (in-progress as Task #47)

---

## 1. Sequencing graph

ASCII DAG. Arrows show "blocks" — A → B means A must ship before B.

```
                         ┌─────────────────────────────────────┐
                         │  E18 host go/no-go: sybil resistance │  (host gate)
                         │  with monetization)                  │
                         └────────────────┬────────────────────┘
                                          │
                                          │ unblocks monetization-flagged primitives
                                          ▼
                                  ┌────────────────┐
                                  │  primitives in │
                                  │  Phase D       │
                                  └────────────────┘

  ╔═════════════════════════════════════════════════════════════════════╗
  ║  Phase A — gate substrate (Mark can build a private gate series)    ║
  ╚═════════════════════════════════════════════════════════════════════╝

   [P1: storage-layer authority refactor]  ──┐
                                              │
   [P2: variant_canonicals table —            │
        canonical_bindings + scope_token]  ◄──┘
            │
            ├─► [P3: lookup_canonical(goal_id, scope) —
            │       node-callable + MCP verb]
            │              │
            │              └────────────────┐
            │                                │
            ▼                                ▼
   [P4: branch visibility=private]   [P5: sub-branch invocation (BUG-005)]
                                                │
                                                └──► [P6: run_branch_version
                                                          (resolves version_id at
                                                           run-time → frozen def)]
                                                              │
                                                              ▼
                                              [P7: gate-series typed-output contract +
                                                   named-checkpoint declaration]
                                                              │
                                                              │ (Phase A complete —
                                                              │  Mark builds end-to-end)
                                                              ▼

  ╔═════════════════════════════════════════════════════════════════════╗
  ║  Phase B — contribution + attribution (every action gets credit)    ║
  ╚═════════════════════════════════════════════════════════════════════╝

   [P8: ContributionEvent ledger schema]   ◄── [PENDING #48 dev-2-2]
            │
            ├─► [P9: lineage walk + N-gen decay (uses fork_from)]
            │
            ├─► [P10: per-step daemon_actor_id on runs row]
            │              │
            │              └──► [P11: derived execute_step events on insert]
            │
            └─► [P12: design_used events from artifact references]

                              │ (Phase B complete —
                              │  every step + every used artifact emits credit)
                              ▼

  ╔═════════════════════════════════════════════════════════════════════╗
  ║  Phase C — closed loop end-to-end (auto-heal MVP)                   ║
  ╚═════════════════════════════════════════════════════════════════════╝

   [P13: generalize bug → patch_request (additive — file_bug stays)]
            │
            └─► [P14: canary-failure → file_bug seam]
                       │
                       │  (now Phase A gate substrate runs on these)
                       ▼
                [closed-loop minimum demo possible — see §5]

   [P15: outcome attribution + aggregation per branch_version_id]
            │
            └─► [P16: outcome → drift-detected → auto-patch_request
                       (recursive evolution)]

  ╔═════════════════════════════════════════════════════════════════════╗
  ║  Phase D — external bridge + economic loop (community contributors) ║
  ║  ↑ host-gated by E18 (sybil resistance landing with monetization)   ║
  ╚═════════════════════════════════════════════════════════════════════╝

   [P17: GitHub PR webhook → patch_request bridge (opt-in via label)]
            │
            └─► [P18: PR-merge auto-update of patch_request status]

   [P19: bounty-distribution calc — deterministic for routine,
         navigator/quorum escalation for disputed]

   [P20: sybil resistance primitives — vouching + decay + GitHub anchor]
            (gated on E18 explicit override)

   [P21: negative ContributionEvents + designer/gate reputation]
            │
            └─► [P22: rollback-set as truth-source for negative events]

  ╔═════════════════════════════════════════════════════════════════════╗
  ║  Phase E — rollback + governance (loop becomes safely autonomous)   ║
  ╚═════════════════════════════════════════════════════════════════════╝

   [P23: bisect-on-canary as attribution primitive]
            │
            ├─► [P24: atomic-rollback-set tracking dependency manifest]
            │
            └─► [P25: watch-window freeze for high-risk paths]

   [P26: sandbox (BUG-017 critical)] ───────► gates ALL user-authored code
            (parallel-track research; multi-week — independent of A-D
             but blocks any user-shipped node-code from running safely)

   [P27: meta-patch_request lane — constitutional changes,
         host-veto + DAO quorum future]
```

---

## Next-Level Primitives strategic roadmap

This section is the execution overlay for the **Next-Level Primitives** push. It turns the current backlog of **22 filed bugs** into **22 actionable work items**, grouped by theme and ordered in the sequence that unlocks the most downstream capability first. The intent is to give lead/host a bug-to-program view: fix the substrate first, then attribution, then closed-loop automation, then external/economic flow.

### Theme A — Core substrate and authority

| Priority | Work item | Why it is first |
|---|---|---|
| 1 | Storage-layer authority refactor | Removes the current enforcement mismatch and is the prerequisite for safe variant authority. |
| 2 | Variant `canonical_bindings` table + `scope_token` | Establishes the data model for scoped canonicals and unlocks user-specific primitive routing. |
| 3 | `lookup_canonical(goal_id, scope)` surface | Makes scoped canonicals actually callable from nodes and MCP clients. |
| 4 | `visibility=private` for Branch / Node / Soul / Evaluator | Preserves symmetric privacy before broader variant-canonical adoption. |

### Theme B — Invocation and routing correctness

| Priority | Work item | Why it follows |
|---|---|---|
| 5 | Sub-branch invocation primitive (`BUG-005`) | Enables gates to hand work off instead of stopping at evaluation. |
| 6 | `run_branch_version` frozen-definition resolution | Ensures invoked work runs against an immutable target rather than a drifting branch head. |
| 7 | Gate-series typed-output contract + named checkpoints | Gives gate branches stable routing targets and predictable downstream behavior. |

### Theme C — Attribution substrate

| Priority | Work item | Why it follows |
|---|---|---|
| 8 | `ContributionEvent` ledger schema | Establishes the durable economic and attribution record. |
| 9 | Lineage walk + N-generation decay | Extends credit assignment across forks and derivative primitives. |
| 10 | Per-step `daemon_actor_id` on runs | Adds direct execution accountability at the run-step level. |
| 11 | Derived `execute_step` events on insert | Converts run facts into ledger events automatically. |
| 12 | `design_used` events from artifact references | Completes attribution for designers whose artifacts are reused. |

### Theme D — Closed-loop request pipeline

| Priority | Work item | Why it follows |
|---|---|---|
| 13 | Generalize bug → `patch_request` | Broadens the system from bug handling to a general change-request substrate. |
| 14 | Canary-failure → `file_bug` seam | Creates the first autonomous trigger for the repair loop. |
| 15 | Outcome attribution + aggregation per `branch_version_id` | Makes branch behavior measurable over time. |
| 16 | Outcome → drift-detected → auto-`patch_request` | Turns repeated bad outcomes into self-generated maintenance work. |

### Theme E — External bridge and marketplace flow

| Priority | Work item | Why it follows |
|---|---|---|
| 17 | GitHub PR webhook → `patch_request` bridge | Connects external contribution flow into the same internal request pipeline. |
| 18 | PR-merge auto-update of `patch_request` status | Closes status drift between GitHub and internal workflow state. |
| 19 | Bounty-distribution calculation | Allows routine payout logic once attribution and request flow exist. |
| 20 | Sybil-resistance primitives | Protects payout and trust systems before open external scaling. |

### Theme F — Trust, rollback, and negative feedback

| Priority | Work item | Why it follows |
|---|---|---|
| 21 | Negative `ContributionEvents` + designer/gate reputation | Introduces downside signals only after attribution and payout semantics exist. |
| 22 | Rollback-set truth source for negative events | Grounds penalties and regressions in auditable rollback evidence. |

### Strategic sequence summary

1. **Fix substrate first.** Items 1-7 are the minimum set that makes Next-Level Primitives routable, private where required, and safe to invoke by frozen definition.
2. **Make every action legible.** Items 8-12 ensure the platform can explain who authored, ran, and influenced each result before economic consequences are attached.
3. **Close the loop.** Items 13-16 turn bug intake into a generalized autonomous repair pipeline.
4. **Bridge outward carefully.** Items 17-20 connect GitHub and payouts only after internal request and attribution semantics are stable.
5. **Add penalties last.** Items 21-22 depend on reliable rollback and attribution evidence; shipping them earlier would create noisy or unjust negative signals.

### Dispatch guidance

- Treat the 22 filed bugs as one program with six themes, not as isolated one-off fixes.
- Keep the execution order above even if individual bug tickets move between engineers; the sequence is dependency-driven, not ownership-driven.
- Use the existing Phase A-D roadmap below as the implementation graph; this strategic layer is the backlog-consolidation view requested for Next-Level Primitives.
- Sandbox work remains a parallel critical track, but it is intentionally outside the 22-item consolidation because it is a broader safety program rather than a single backlog theme.

---

## 2. Ship order

Linear ordering through the DAG, respecting blocks-on relationships, optimizing for "earliest unlock of largest capability." Numbered for dispatch reference; not strict — parallel-safe primitives can ship concurrently if file boundaries don't collide.

| # | Primitive | Phase | Blocks |
|---|---|---|---|
| 1 | Storage-layer authority refactor (audit Gap #7) | A | P2 (variant authority depends on storage-layer enforcement) |
| 2 | Variant `canonical_bindings` table + `scope_token` (proposal P1) | A | P3, P4 |
| 3 | `lookup_canonical(goal_id, scope)` — node-callable + MCP verb | A | P5, P7 |
| 4 | Branch / Node / Soul / Evaluator `visibility=private` flag | A | (parallel — symmetric privacy) |
| 5 | Sub-branch invocation primitive (BUG-005) | A | P6, P7 |
| 6 | `run_branch_version` — resolves version_id → frozen def at run time | A | P7 |
| 7 | Gate-series typed-output contract + named-checkpoint declaration | A | (Phase A end — Mark unblocked) |
| 8 | `ContributionEvent` ledger schema | B | P9, P10, P12 (all attribution) |
| 9 | Lineage walk + N-gen decay (extends `fork_from` to NodeDefinition) | B | P12 |
| 10 | Per-step `daemon_actor_id` on runs row | B | P11 |
| 11 | Derived `execute_step` events on runs insert | B | (Phase B partial — daemons credited) |
| 12 | `design_used` events from artifact references | B | (Phase B end — designers credited) |
| 13 | Generalize bug → patch_request (additive — kind taxonomy + routing) | C | P14 |
| 14 | Canary-failure → file_bug auto-trigger seam | C | (Phase C MVP — closed loop) |
| 15 | Outcome attribution + aggregation per branch_version_id | C | P16 |
| 16 | Outcome → drift-detected → auto-patch_request (recursive evolution) | C | (Phase C end) |
| 17 | GitHub PR webhook → patch_request bridge (opt-in via label) | D | P18 |
| 18 | PR-merge auto-update of patch_request status | D | — |
| 19 | Bounty-distribution calc — deterministic + dispute escalation | D | P20 |
| 20 | Sybil resistance — vouching + decay + GitHub anchor | D | (host-gated on E18) |
| 21 | Negative `ContributionEvents` + designer/gate reputation | D | P22 |
| 22 | Rollback-set as truth-source for negative events | D | — |
| 23 | Bisect-on-canary as attribution primitive | E | P24 |
| 24 | Atomic-rollback-set tracking dependency manifest | E | — |
| 25 | Watch-window freeze for high-risk paths | E | — |
| 26 | Sandbox (BUG-017 critical) | parallel | gates ALL user-authored code (research) |
| 27 | Meta-patch_request lane (constitutional changes) | E | (host-final + DAO quorum future) |

**Parallelism notes.**
- Items 1, 4, 9, 10 can ship concurrently with no file conflict.
- Item 26 (sandbox) is multi-week research; runs in parallel with everything else; blocks no Phase A/B/C/D primitives but blocks user-authored-code adoption (e.g., chatbot-composed NodeDefinitions running daemon-side).
- Item 8 (ledger schema) is dev-2-2's Task #47; ships when their proposal lands. Phase B downstream items hold for it.

---

## 3. Phase milestones — emergent capabilities

| Phase | Capability that emerges when phase completes |
|---|---|
| **A — gate substrate** | **Mark can author a private gate series end-to-end.** He has `visibility=private`, his own variant canonical, sub-branch invocation, version-id-aware runner, and named-checkpoint routing. He can route reject decisions back to a canonical branch he chooses. |
| **B — contribution + attribution** | **Every executed step and every artifact use emits a `ContributionEvent`.** Daemon hosts and primitive designers accrue credit visibly, even before bounty distribution. Lineage walk decays correctly. The economic ledger is live but not yet paying out. |
| **C — closed loop end-to-end** | **Auto-heal MVP closes the loop.** A canary failure files a patch_request, which the bug-investigation branch processes, which Mark's gate series evaluates, which produces patch notes that route to a coding-team branch. The platform is the system that fixes itself end-to-end without human intervention for the routine path. |
| **D — external bridge + economic loop** | **Community contributors are credited and bountied.** External PRs flow through the same pipeline as internal patches. Bounty pool replenishes from take; payouts batch to actors with handle-linkage. Sybil resistance gates payouts. |
| **E — rollback + governance** | **The loop is safely autonomous.** Surgical rollback handles regressions without cascading. Bad actors lose reputation. Constitutional changes have a defined lane with appropriate gates. Host's residual role narrows to true emergencies + meta-evolution. |

---

## 4. Mark's gate-series story across phases

What Mark can do at the end of each phase (cumulative):

### Today (pre-Phase A)
- Author a Branch composed of evaluator nodes with conditional edges.
- Bind it to a Goal he authored.
- Set it as canonical for *his own Goal* only.
- Cannot route reject decisions back to a canonical version (no sub-branch invocation, no version-id runner).
- Cannot have his own canonical for someone else's Goal.
- Cannot keep his gate-series private.

### After Phase A
- Author Branches with `visibility=private`.
- Set his canonical for ANY Goal at scope=`user:mark` — symmetric privacy intact (others can't see his binding by default).
- Use `lookup_canonical(goal_id, scope="user:mark")` from inside a gate node to find his routing target.
- Invoke a sub-branch (`run_branch_version`) on the resolved canonical, passing patch_notes payload.
- Declare named checkpoints on his branches so gate decisions can target `tier-2-integration-test` instead of opaque node ids.
- **Mark's full gate-series story works end-to-end.** Test tiers, send-back routing, real-user-proof tier (programmatic — see Phase C for outcome aggregation), reject paths.

### After Phase B
- Mark's gate-series, every time it executes, emits `execute_step` events for the daemon hosting it and `design_used` events for every node/evaluator/soul it references.
- Mark accrues `design_authored` credit when his gate-series Branch is published as a version.
- Lineage decay surfaces credit for upstream artifacts Mark forked from — N-gen back, weighted.
- Mark sees his contribution ledger entries via a future MCP `contribution action=list_mine` (post-Phase B leaf-shape work).

### After Phase C
- A canary that goes red on Mark's surface (e.g., his canonical patch-investigation branch fails to produce sound packets) auto-files a patch_request *against* Mark's primitive.
- Mark's gate series can consume real-user feedback as decision input — `feedback_provided` events emit only when his gate cites the feedback.
- Outcome aggregation tracks his gate-series's accept/reject distribution + downstream regression rate.
- Drift in outcomes auto-files a patch_request on the gate-series itself; Mark can author v2 to address.

### After Phase D
- Mark's commits get `Co-Authored-By: Mark <mark@github>` in every PR that lands using his primitives.
- Bounty pool distributions credit Mark's design-share + execution-share + lineage-decay weighting.
- External PR contributors who fork from Mark's primitive get credit through the lineage chain — Mark earns decayed share for N generations.
- Sybil-resistance gates payouts; legitimate contributors paid, fake actors filtered.

### After Phase E
- A regression caused by Mark's primitive triggers atomic rollback (just his contribution if isolated; cascade-aware if downstream merges depend).
- A `caused_regression` event reduces Mark's design reputation; recoverable via subsequent clean ships.
- Mark's gate-series accumulates accept/false-accept reputation that surfaces to chatbots in discovery rank — high-rep gates get "trusted" badge; low-rep get "experimental."
- If Mark wants to propose a meta-change (e.g., new ContributionEvent type), it routes through the constitutional lane with host-final authority.

**Casual-vs-hardcore funnel check (E5):** at every phase, casuals interact via chatbot-mediated composition; hardcore (Mark) authors primitives directly. The Branch artifact is the meeting point. The chatbot does discovery + parameter-fill for casuals; Mark fills in the same surfaces by hand. **No phase introduces a separate code path for casual vs. hardcore.**

---

## 5. Auto-heal closed loop minimum viable point

**The loop first closes end-to-end at the end of Phase C.**

Specifically, after items 1-14 ship:
- Phase A primitives let any gate-series-shaped Branch run end-to-end with goal-aware routing.
- Phase B (items 8-12) gives observability into who-ran-what; not strictly required for loop closure but required for *trustworthy* closure (without it, no record of which daemon ran which step → no attribution → no bounty viability).
- Phase C item 13 (generalize bug → patch_request) lets the wiki taxonomy and pipeline accept non-bug requests.
- Phase C item 14 (canary-failure → file_bug seam) is the autonomous trigger — a canary going red files a patch_request without human action.

**The minimum demo at end-of-Phase-C:**
1. Canary detects red (e.g., `wiki action=write` round-trip fails).
2. Canary script calls `submit_patch_request kind=uptime severity=critical title=...` (item 14).
3. Daemon claims the request via dispatcher; runs canonical `request_to_artifact` branch (Mark's `bug_to_patch_packet_v1` generalized — already substrate, just needs request-shape input).
4. Patch packet attaches as wiki comment via `attach_patch_packet_comment`.
5. Mark's gate series (or whichever scope-canonical applies) runs evaluator nodes against the packet. Phase A primitives carry the routing.
6. Gate output: ACCEPT.
7. Phase D items 17-18 (PR bridge) **not yet shipped at end-of-Phase-C** — manual lead-mediated PR + merge.
8. Canary re-probes; green confirms.
9. Phase B items 8-12 ledger has captured every step's contribution events.

**The loop is closed for the auto-detected-bug → manual-merge case.** Step 7 manual hand-off is the "hosts only summoned for true emergencies" invariant relaxed for now; Phase D closes that hand-off by automating PR routing + merging under uptime-emergency carve-outs.

**End-of-Phase-D = full autonomous closure** for routine cases. Phase E adds rollback safety; without rollback, autonomous closure is brittle and a regression takes the system down with no auto-recovery.

So:
- **Phase C end:** loop closes for "auto-detect → manual merge" — the bootstrap demo.
- **Phase D end:** loop closes fully autonomously for routine cases.
- **Phase E end:** loop is autonomously *safe* under regressions.

---

## 6. Open dependencies on host decisions

Primitives that cannot ship until host answers an open question.

| Gate | What it blocks | Status |
|---|---|---|
| **E18 — sybil resistance with monetization** | All Phase D primitives that involve money flow (P19 bounty-distribution, P20 sybil-resistance, P21-22 negative events with economic consequence) | Open. Needs explicit override of memory `project_paid_market_trust_model`'s "don't scope abuse infra until abuse appears." |
| **G4 — variant-canonical schema** | P2 schema migration. **dev-2-2's variant-canonicals proposal recommends Path 1 (`canonical_bindings` table + `scope_token`).** | Proposal exists; awaits host ratification. |
| **A6 — bounty distribution adjudication thresholds** | P19 calc semantics — what's "routine" vs. "disputed"? Where does navigator step in? | Open. Could ship P19 with conservative defaults (low threshold for navigator review) and tighten over time. |
| **G6 — reframe-strength** | P13 and beyond — does every "build X for users" reshape as "ship primitive"? Are there carve-outs (uptime emergency)? | Open in v1 vision §5. Doesn't block specific primitives; affects how new dev tasks get scoped. |
| **Sandbox tech choice (BUG-017)** | P26 sandbox — but P26 is parallel-track research, not blocking Phases A-E specifically. Does block user-authored-code-running-as-node adoption. | Open. WASM / gVisor / Firecracker / per-node container under research. |
| **Outcome → auto-patch_request as primary evolution mechanism** | P15-P16 design — confirms recursive evolution path over parameter-tuning approach. | Open. Doesn't block Phase A-B-C; sharpens Phase C item 16 once chosen. |
| **Symmetric-privacy filter on canonical reads from host** | P4 visibility filter — does even host see only their own + public canonicals by default? | Open. Sharpens P4 implementation. |
| **PR-bridge label vs. blanket auto-routing** | P17 mechanics — opt-in via label is recommended, blanket auto-route is alternative. | Open but recommendation strong (per E14 from prior round). |

**Critical-path observation.** None of E18, A6, G6, sandbox, or outcome-evolution gate Phase A. Phase A is fully unblocked by current host directives + the variant-canonicals proposal once ratified. Phase A is the highest-leverage early dispatch lane.

**Phase B is gated on dev-2-2's Task #47 ledger proposal** (not host-gated, just internal sequencing). That's a near-term unblock.

**Phase D is gated on E18.** This is the longest-running open question. Phases A-C can fully ship in parallel without resolving E18; Phase D queues behind it.

---

## 7. What this roadmap does NOT cover

- **Specific dispatch order** within phases. Lead routes; this gives the precedence relationships.
- **File boundary collisions** for parallel dispatch. Lead checks before assigning concurrent tasks.
- **Test-coverage shape per primitive.** Each primitive needs its own scope; not enumerated here.
- **Cloud redeploy gating.** Several primitives (P14 canary seam, P17 PR bridge) require post-redeploy live testing. Roadmap assumes post-redeploy timing for items requiring live MCP surface.
- **Versioning + backwards compat** for in-flight primitives. Variant-canonicals proposal §5 has the dual-write migration; other primitives need similar migration plans authored at dispatch time.
- **DAO governance + federation horizon.** v3+ vision territory; out of scope for this roadmap. Will surface as constraints on Phase E item 27 (constitutional lane) when host directs.

---

## 8. Cross-references

- v1 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` §4 (audit table) + §5 (open questions) + §6 (convergence path).
- G1 audit: `docs/audits/2026-04-25-canonical-primitive-audit.md` (gap list informs Phase A items 1, 2, 3, 5, 6).
- Variant-canonicals proposal: `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (Path 1 + scope_token + migration phases — feeds Phase A item 2).
- Despawn-chain protocol: `docs/audits/2026-04-25-despawn-chain-protocol.md` (operational layer; orthogonal to this roadmap).
- Memory load-bearing: `project_user_builds_we_enable`, `project_designer_royalties_and_bounties`, `project_paid_market_trust_model` (override candidate for E18), `project_chain_break_taxonomy`, `project_full_platform_target`.

---

## 9. Convergence path for v2 vision doc

When v2 of the self-evolving-platform vision drafts, this roadmap feeds:
- §4 audit table → expand with Phase column + ship-order number.
- §5 open Qs → narrow as roadmap items convert from `[OPEN]` to "shipped (Phase X)."
- §6 convergence path → swap in concrete Phase A → B → C → D → E milestones.
- New §11+ would absorb the Mark-story-across-phases content from §4 here.

The roadmap becomes the executable form of v1's vision; v2 vision becomes a mature design-truth document referencing the roadmap.
