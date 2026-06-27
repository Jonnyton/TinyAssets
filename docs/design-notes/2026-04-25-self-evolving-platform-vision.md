---
status: superseded
superseded_by: docs/design-notes/2026-04-25-self-evolving-platform-vision-v2.md
---

# Self-Evolving Platform Vision (v1 outline)

**Date:** 2026-04-25
**Status:** v1 OUTLINE. Design-truth-target. Not yet ratified — see `[OPEN: ...]` markers throughout. Future sessions converge on specifics.
**Author:** navigator (drafted with team-lead)
**Source material:** four host directives 2026-04-25 on (a) closed-loop, (b) gate primitives are user-built, (c) canonical-branch sharpening, (d) attribution layer.
**Successor versions:** v2 will resolve the highest-priority `[OPEN]` markers (sybil resistance, variant-canonical schema, sub-branch invocation). v3+ will likely add layers host has not yet surfaced (DAO evolution, federation).

---

## 1. The closed loop

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
│   - unit                                      │
│   - integration                               │
│   - user-sim                                  │
│   - real-user proof-of-fix                    │
│  Decisions: ACCEPT / send-back-any-stage /    │
│  RUN on patch_notes branch / RUN on alt /     │
│  REJECT                                       │
└───────────────────────────────────────────────┘
    │ (accept)
    ▼
[coding team branch — already prototype]   ←── user's "agent-teams-on-TinyAssets" idea
    │
    ▼
[GitHub PR]
    │
    ▼
┌───────────────────────────────────────────────┐
│  Private Gate Series #2 — full execution +    │
│  future-proof watch                           │
│  Decisions: ACCEPT (PR merges) /              │
│  send-back-any-stage / REJECT                 │
└───────────────────────────────────────────────┘
    │ (accept)
    ▼
[ship + future-proof-of-fix monitoring]
    │
    ▼
[self-heal + surgical rollback if regression]
    │
    └──── back to top of loop if rollback triggered
```

**Lead/host endgame role.** Once the loop is closed and stable, lead/host is summoned only for (a) true emergencies — phone-ping that the system is actually down, (b) evolving the self-evolving system itself (the meta-work). Everything else — auto-heal, evolution, attribution, distribution — runs community-driven without human intervention. The Forever Rule (24/7 uptime, zero hosts online) is the necessary condition; this loop is the enabling architecture.

---

## 2. What we ARE building / NOT building

### NOT building

- **The private gate series itself.** Mark (or any user) builds it. The community evolves competing implementations; we pick our preferred canonical from among them. We get control via canonical-binding; community gets evolution via free composition. Symmetric privacy: nobody sees which gate-series anyone else uses by default.
- **A "coding team" agent-team as a fixed pipeline.** User project per host directive. Communities ship competing coding-team branches; daemon market picks based on bid + reputation.
- **Specific evaluators, gate logic, moderation rules, governance branches.** All user-built primitives.
- **Domain-specific node types** (e.g. a "notes node"). Ship the meta-primitive that lets chatbots compose node types from base primitives; communities author specifics.

### ARE building (the primitives)

- **Canonical-branch-for-goal — sharpened.** Variant-scoped model so Mark's canonical, community-tier canonical, and our canonical can all coexist for the same Goal. `[OPEN: scope-token model — see §4 + E E1.G4]`
- **Sub-branch invocation primitive (BUG-005).** Load-bearing — without it, gates can decide but can't route work back through canonicals.
- **Decision-routing primitive — named-checkpoint contract** so gate decisions can target named stages (`tier-2-integration-test`) not opaque node ids.
- **Branch / Node / Soul / Evaluator visibility primitive** — `visibility ∈ {public, private, friends}`. Per-piece, not per-collection.
- **`ContributionEvent` ledger** — single append-only table, all five contribution surfaces emit to it. Spine of the attribution layer.
- **Lineage walk + decay** — uses existing `fork_from`, extends to NodeDefinition.
- **Surgical rollback infrastructure** — bisect-on-canary as attribution primitive; atomic-rollback-set for cascade safety.
- **Sandbox (BUG-017 critical-status)** — gating decision for any user-authored code primitive. No community-iteration without it.
- **GitHub PR webhook → patch_request bridge** — opt-in via label; carve-outs for docs/hot-fix/format-only PRs.
- **Outcome attribution + aggregation** — feedback loop from real-world result back to gate-series reputation.
- **Generalized request type beyond bug** — additive: keep `file_bug` for user-vocabulary defects, add `submit_patch_request` as broader sibling. `kind=` field already supports the taxonomy.

---

## 3. Five contribution surfaces (attribution layer)

All five are event types on one `ContributionEvent` ledger. Each row: `(event_id, event_type, actor_id, source_run_id?, source_artifact_id?, weight, timestamp, metadata_json)`.

1. **Daemon-host contribution.** A daemon ran a step (node execution, gate evaluation, real-world-outcome detection). **Missing primitive:** per-step `daemon_actor_id` recorded on `runs` row; `execute_step` event derived per insert. `[OPEN: A1 — runs schema extension OR separate ledger? See §4.]`
2. **Node/gate/branch designer contribution.** Whoever's design got used. **Missing primitive:** `design_used` events emitted on every step execution that references an artifact, plus N-generation lineage walk with decay (per memory `project_designer_royalties_and_bounties`). `[OPEN: A2 — usage-event recording site.]`
3. **Direct repo contribution.** PR author + Co-Authored-By chain on commit. **Missing primitive:** GitHub webhook on PR open auto-files patch_request when labeled; PR author + commit Co-Authored-By chain emit `code_committed` events. `[OPEN: A3 / E14 — opt-in via label; carve-outs.]`
4. **Past attributors (lineage chain).** N-generation back, decaying weights. **Missing primitive:** lineage walk reads `fork_from` chain, emits weighted `design_used` events for ancestors. Substrate exists (`fork_from` MCP wired commit `ea0790a`); decay coefficients + multi-artifact extension are gaps.
5. **Helpful chatbot-action contribution** — drafted patch_request content, provided real-user feedback consumed by a gate, vouched for a no-handle contributor, etc. **Missing primitive:** `feedback_provided` events emit only when a gate-series cites the feedback as decision input (anti-spam). `[OPEN: A4 / E16 — granularity + spam protection.]`

**Bounty distribution.** Calc runs at every patch merge. Reads ledger entries within a window; computes (actor_id, github_handle, percent_share); routes to commit Co-Authored-By + bounty payout. **Deterministic for routine merges; navigator (or community quorum) adjudicates disputed cases only.** `[OPEN: A6 / E E1.E E11 — adjudication thresholds.]`

**Sybil resistance — load-bearing risk.** Without it, monetization invites N-actor-id farming. Three primitives sketched (web-of-trust via vouching, GitHub-handle as identity anchor, decay on bad vouches). **Must land with monetization, not after.** `[OPEN: E18 — explicit override of memory `project_paid_market_trust_model`'s "don't scope abuse infra until abuse appears." This is the single biggest deviation from prior framing. Host go/no-go required.]`

**Negative contribution events.** Rollback-triggering changes emit `caused_regression` events; designer/committer reputation reduces accordingly. **Without this, system rewards quantity over quality.** `[OPEN: E19 — confirm as part of model.]`

---

## 4. Open primitives audit

| Primitive | Already exists today | Gap to close | Priority |
|---|---|---|---|
| Canonical-branch-for-goal (single) | YES — `goals.canonical_branch_version_id`, `set_canonical_branch` (`daemon_server.py:2354`), authority = Goal author or host. History audit trail exists. | None at single-canonical level. | (in place) |
| Variant canonicals (per-(goal, scope)) | NO — single canonical only | Schema: `canonical_branch_version_id` → `canonical_branch_versions: {scope: branch_version_id}` jsonb map. Lookup helper. Scope-namespace authority rule. `[OPEN: G4 — scope tokens vs. tiers vs. user-id. My recommendation: opaque scope tokens.]` | HIGH |
| Sub-branch invocation (BUG-005) | NO | Engine substrate. Without it, gates can't route work back to canonical. | HIGHEST — load-bearing for gates |
| Daemon contribution ledger | PARTIAL — `provider_used` column landed (Task #20) is LLM-provider; daemon-actor differs | Per-row `daemon_actor_id`, `daemon_host_id`, `daemon_node_id_in_branch` on `runs`. Derived `execute_step` event. | HIGH |
| Usage-event ledger (`design_used` events) | NO | Append-only `contribution_events` table. Emit on each step execution per artifact referenced. `[OPEN: A2/E15 — single table or two-table model?]` | HIGH |
| External-PR bridge | NO | GitHub webhook on `pull_request.opened`, opt-in via `patch_request` label, auto-file wiki patch_request, link PR author actor_id. Carve-outs for docs/hot-fix/format-only. | MEDIUM |
| Real-user-feedback credit | NO | Anti-spam: only credit when gate-series cites the feedback. Pool-share at distribution events; no microtransactions. `[OPEN: E16.]` | MEDIUM |
| Gate-series composition primitive | PARTIAL — Branch + Evaluator + conditional edges | Typed output contract (gate-decision shape). Fan-out + aggregate for parallel test tiers. Named-checkpoint declaration for send-back targeting. | HIGH |
| Decision-routing (named-checkpoint contract) | PARTIAL — node ids exist | Branches declare `checkpoints: {name: node_id}`. Gate decisions reference checkpoint names. | MEDIUM |
| Surgical rollback (bisect-on-canary + atomic-rollback-set) | NO — manual git revert | Bisect-on-canary as attribution primitive (binary search across recent merges, replay canary). Atomic-rollback-set tracks dependency manifest. Watch-window freeze for high-risk paths. | MEDIUM |
| Fair-distribution calc | NO — deferred spec per `project_designer_royalties_and_bounties` | Deterministic calc reads ledger window at merge; emits (actor_id, share). Routine = auto; disputed = navigator/quorum escalation. | MEDIUM |
| Sandbox (BUG-017 critical) | BROKEN (bubblewrap permissions) | Gating decision for user-authored code. Tech choice: WASM / gVisor / Firecracker / per-node container. Multi-week research. | HIGHEST research |
| Symmetric-privacy read filter | NO | Visibility filter on canonical map reads — host doesn't see other users' private canonicals. `[OPEN: ρ — confirm host-trust call.]` | MEDIUM (with variant canonicals) |
| Outcome attribution + aggregation | NO | `attach_outcome` extension. Aggregates per branch_version_id. Auto-patch_request when drift detected (G5 path 3 — recursive evolution). | MEDIUM |

---

## 5. Open questions (research backlog)

Paste-verbatim from the four directives. **Not yet answered — research/converge in v2+.**

### From closed-loop directive (E1-E13 framing)

- E1. Rename rollout for bug → patch_request. Aliasing strategy. Where is "bug" load-bearing in code/wiki/UX?
- E2. Meta-primitive layer — what does "chatbot creates a NodeType on the fly" actually require?
- E3. Auto-heal closed loop — smallest end-to-end demo? Auto-merge gate philosophy?
- E4. Community-iteration primitives we don't have yet but the vision requires.
- E5. Casual-vs-hardcore funnel — gateway design.
- E6. Self-evolving governance — when system proposes a fix to itself, who reviews?
- E7. Forever Rule × self-evolving system intersection.
- E8. Smallest END-TO-END demo of the closed loop?
- E9. Gate-series composition primitive — new BranchType or specific output schema sufficient?
- E10. Decision-routing primitive — state machine vs. linear pipeline.
- E11. Auto-rollback safety — cascading reverts.
- E12. Real-user-proof-of-fix as gate input — implicit vs. explicit; time-window.
- E13. Coding-team-branch handoff — what's "best"?

### From canonical-pivot directive (G1-G6)

- G1. Audit goals/canonical primitive (data model, authority, lookup site). **(Partially answered in §4 table.)**
- G2. What's missing for Mark to build a private gate series himself.
- G3. The "private collection" primitive — visibility scope vs. richer Collection object.
- G4. Variant-canonical model — per-(goal, user) vs. per-(goal, tier) vs. per-(goal, scope-token).
- G5. Real-world result feedback loop — primitives needed for evolution-by-outcome.
- G6. Team-level reframe — every "build X for users" reshaped as "ship primitive for users to build X."

### From attribution directive (A1-A6 + E14-E17)

- A1. Daemon contribution ledger — runs schema extension or separate.
- A2. Node/gate/branch usage events — recording site.
- A3. External PR → patch_request bridge — webhook + labeling.
- A4. Real-world-feedback-as-contribution — credit granularity.
- A5. Chatbot-mediated link-up — first-contribution opt-in flow.
- A6. Bounty distribution computation — navigator role + automation boundary.
- E14. External-PR-to-patch_request bridge mechanics — opt-in via label.
- E15. Daemon contribution recording surface — runs extension or new ledger.
- E16. Real-user feedback monetization granularity — microtransactions vs. pool share.
- E17. GitHub-handle missing case — handled by today's CONTRIBUTORS.md format; retroactive linking primitive.
- E18. **[LOAD-BEARING]** Sybil resistance must land with monetization, not after — explicit override of `project_paid_market_trust_model`. Host go/no-go required.
- E19. Negative contribution events + designer/gate reputation — confirm as part of model.

### Cross-cutting `[OPEN]`s noted in §2-§4

- Variant-canonical model: scope tokens (recommended) vs. tiers vs. user-id.
- Authority model under variant canonicals: scope-namespace-implicit vs. explicit rules.
- Symmetric-privacy filter applies even from host — host-trust call.
- Outcome → auto-patch_request as primary evolution mechanism (vs. parameters-on-nodes).
- Reframe-everything-as-primitive-shipping: how strong? Are there carve-outs (uptime emergency)?
- Smallest end-to-end demo (E8) — primitive checklist + 4-6 week scoping.
- Sandbox tech choice (BUG-017) — WASM / gVisor / Firecracker / per-node container.

---

## 6. Convergence path

v1 (this doc): outline + research backlog. Stable target shape; specifics open.

v2 (next session): resolve the load-bearing OPENs in priority order:
1. **E18 sybil resistance** — explicit host go/no-go.
2. **G4 variant-canonical schema** — pin Option γ or alternate.
3. **BUG-005 sub-branch invocation** — promote to dispatch.
4. **A1/E15 contribution ledger schema** — pin one-table or two-table model.
5. Reframe-strength (G6) — pin level for team-busy plan integration.

v3+: layers not yet surfaced. Likely candidates: DAO evolution + governance schedule (memory `project_dao_evolution_weighted_votes`), federation horizon (multi-instance ActivityPub-shaped), economic-incentive activation timing, sandbox tech selection.

---

## 7. Cross-references

- Closed-loop diagram: §1 above.
- Always-busy team plan: pairs with §2 — wiki→patch_request pipeline IS the team-busy steady-state answer post-redeploy.
- Forever Rule (AGENTS.md): §1 endgame role. Auto-heal is the bootstrap-completion criterion for "24/7 uptime, zero hosts online."
- Existing memory load-bearing for this doc: `project_user_builds_we_enable`, `project_designer_royalties_and_bounties`, `project_full_platform_target`, `project_chain_break_taxonomy`, `project_evaluation_layers_unifying_frame`, `project_paid_market_trust_model` (load-bearing override candidate per E18), `project_node_capability_decisions`, `project_dao_evolution_weighted_votes`.
- Today's commits relevant: `ea0790a` fork_from MCP wiring; CONTRIBUTORS.md surface (commit `87e96bb` docs bundle).
- Audits this doc references: `docs/audits/2026-04-25-despawn-chain-protocol.md` (operational layer), `docs/design-notes/2026-04-18-full-platform-architecture.md` (predecessor).
