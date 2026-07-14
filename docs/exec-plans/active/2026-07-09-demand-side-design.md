# Demand-Side Design — Standing Goals & Goal Bounties (2026-07-09)

**Status:** Binding design note. Composes existing primitives only (design law: primitives + commons, never features). Addresses the cold-start/retention risk named in OPERATING-NOTES; feeds the north-star metrics directly.

## 1. The native demand unit: the STANDING goal

Chatbots own conversational demand ("answer me now"). TinyAssets owns **standing-goal demand**: goals that run while the user is absent — monitor, maintain, accumulate, curate, optimize — executed on the heartbeat/proactivity envelope from USER-PATH Step 2a(5).

Why this is the demand engine:
- **Decoupled from attention.** A universe with three standing goals consumes compute at 3 a.m. Demand scales with goals held, not sessions opened — this is what fills the batch market.
- **It IS the forecastable-demand moat.** Standing goals' declared branches are tomorrow's demand, visible today (Track E §5).
- **It is the retention answer.** The user returns because something LANDED while they were gone: the Sunday brief, the passed gate, the price alert. Week-three retention is a property of the first standing goal, not of the UI.

**Product rules (binding):**
1. Every commons archetype ships with 2–3 standing goals pre-attached, chosen so the FIRST produces a felt, gate-claimed win inside week one ("your first brief arrives Sunday" — never "explore the platform").
2. Onboarding's terminal state is a standing goal running, not an empty universe.
3. Leading demand metric: **standing goals per active universe** (leads the north-star weekly-gate-claims metric).

## 2. Goal bounties — the missing demand primitive

**Definition:** a goal with escrowed money that ANYONE may claim by passing its gates. Demand becomes transferable: money summons other people's universes and compute.

What it creates: (a) demand without owning compute — posters convert money directly into platform work; (b) speculative fulfillment — sellers' idle capacity attempts open bounties (mining where the proof-of-work is useful); (c) a funding mechanism for the commons' own gaps ("nobody has built X" becomes a priced request).

**Composition rules (pinned — Opus must not improvise these):**
1. **Machine-checkable gates only.** Bounties may only attach to gates with automated verification. No human-acceptance step exists → no poster-side griefing surface. If a goal's gates aren't machine-checkable, it cannot carry a bounty (fail closed).
2. **Escrow at post** via `escrow_lock_entries` into `escrow:bounty:<id>`. Gate-ladder bounties escrow **per-tranche**, tranche weights apportioned exactly via `apportion_exact` over declared gate weights.
3. **First verified claim wins the tranche.** Ordering: (gate-verification timestamp, claim id) — deterministic ties. Settlement per tranche = existing fee split (99/1, `FEE_PPM`), ledger postings via the standard adapters, `assert_drained` on the tranche escrow.
4. **Expiry:** unclaimed tranches past the bounty's declared deadline refund to the poster in full (no fee — no settlement occurred).
5. **Disputes:** standard dispute window on claim evidence; reuses existing machinery unchanged.
6. **Provenance:** a bounty-claimed artifact enters the commons under the claimant's authorship with standard attribution; the bounty poster receives usage rights per the bounty's declared license terms (composed fail-closed at post time, Track G machinery).

**Anti-abuse notes:** self-claiming your own bounty nets −1% (fee) — pointless; sybil racing is harmless (first verified claim wins regardless of who); gate-verification integrity is the same trust boundary as all gates (review finding B-5 applies).

## 3. Universe-to-universe services (named, deferred)

Minted workflows callable as paid service endpoints (universes hiring universes) is the third demand layer. It is deliberately deferred behind bounties: bounties prove transferable demand with zero new trust surface; services add availability/SLA questions. Revisit after bounty volume exists.

## 4. Seeding checklist (joins the demo-blocking seed list)
Each of the six launch archetypes ships with standing goals that claim a gate in week one — e.g. research-brief (weekly, gate: ≥N cited sources), price/deal watch (gate: alert precision), codebase-maintenance (gate: green CI on dependency PRs), print-farm ops (gate: queue utilization report), commons-curation (gate: dedup/contamination pass). Founder to pick the exact six during rehearsal-build week.
