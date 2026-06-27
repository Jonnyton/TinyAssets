---
title: Discovery / similarity / remix substrate — community-evolves-features mechanism
date: 2026-04-27
author: navigator
status: active
companion:
  - project_commons_first_architecture (memory — Part 3 is the rule this note designs)
  - docs/audits/2026-04-27-commons-first-architecture-implications.md (sibling — implications sweep)
  - docs/design-notes/2026-04-27-host-resident-private-data-design.md (sibling — data architecture)
  - docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md (5+2 → 6+2 reframe per F21)
  - project_designer_royalties_and_bounties (the engine that makes remix work)
  - project_minimal_primitives_principle (`discover` as a 6th primitive — earns its keep)
  - project_convergent_design_commons (the architectural realization)
load-bearing-question: What's the substrate that lets community designs become primitives for next users via discover + similarity + remix? Specifically: which primitives, which scoring/ranking, which attribution shape, which integration with the 5+2 (or 6+2) tool surface?
audience: lead, host (final scope + sequencing decision)
---

# Discovery / similarity / remix substrate

## §0 — Frame

Per `project_commons_first_architecture` Part 3:

> User A wants to build something. Their chatbot uses platform primitives to compose it.
> User A publishes the result to the public commons.
> User B comes along, finds User A's design via discovery primitives, remixes it, re-publishes.
> User C arrives, finds either A's or B's version, picks the better-tested one, remixes again.
> The "feature" that we (platform builders) might have built is now in the commons, evolving across users in real time.

> **The platform's job is the remix substrate.** Discovery + similarity + ranking + attribution + remix-with-credit primitives are what we ship. The features themselves we don't.

This note designs that substrate. **Strategic proposal** — after host approval, detailed implementation arc gets a separate exec-plan.

---

## §1 — Primitive scope: 6+2 vs 5+2

Per `docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md` the proposed primitive set was 5 (browser-only) + 2 (local-app):
1. workspace, 2. workflow, 3. run, 4. evaluate, 5. commons (+host, +upload local-app)

**Commons-first sharpens the question: should `discover` split off from `commons`?**

Per `project_minimal_primitives_principle`: a primitive earns its keep if it's irreducible AND serves a load-bearing user-goal verb. Per the principle's Part 3: discover/similarity/ranking IS load-bearing infrastructure. The principle's spirit pulls toward making `discover` first-class.

**Argument FOR splitting (recommended):**
- "Find something" is conceptually distinct from "publish something." Different verbs, different cognitive frames.
- Discover gets HEAVY (search + similarity + ranking + filtering + recommendation). Stuffing it into `commons.search`, `commons.similar_to`, `commons.recommend` etc bloats `commons` action menu past the user-cognitive-load threshold.
- Per `project_commons_first_architecture`: discover is the LOAD-BEARING infrastructure. It deserves first-class top-level primitive status.
- Phone-screen friendliness — 6 verbs vs 5 is fine; 5 verbs with one massive action-menu inside is worse.

**Argument AGAINST splitting:**
- Adds 1 to primitive count. Per minimal-primitives, the budget should shrink.
- All discover actions ARE actions on the commons; conceptually they could live there.

**Recommendation: SPLIT. New 6+2 set:**

1. **`workspace`** — DISCOVER-bootstrap + own-state
2. **`workflow`** — DESIGN + EXTEND
3. **`run`** — RUN + OBSERVE + DELIVER
4. **`evaluate`** — EVALUATE
5. **`commons`** — PUBLISH + FORK + ATTRIBUTE (write-side cross-user)
6. **`discover`** ← NEW — SEARCH + SIMILAR + RECOMMEND + RANK (read-side cross-user)
+ `host` (local-app)
+ `upload` (local-app)

The `discover` ↔ `commons` split mirrors GitHub's "browse + clone" vs "push + PR" split. Different intents, different primitives.

---

## §2 — `discover` primitive — actions + shape

### §2.1 — The 7 user-goal verbs the principle's Part 3 generates

Working backward from "what does the user actually want to discover":

| User-goal sub-verb | Description | Action |
|---|---|---|
| **SEARCH** | "find branches matching this query" | `discover.search(query, type='branch'|'goal'|'node'|'wiki', limit, filters={...})` |
| **SIMILAR_TO** | "find branches similar to this one I'm building / running" | `discover.similar_to(reference_id, axis='structure'|'domain'|'outcome', limit)` |
| **TOP_N** | "what's the best in this space" | `discover.top_in(domain, ranked_by='community_signal'|'verified_outcomes'|'recency', limit)` |
| **RECOMMEND** | "based on what I'm building, what should I look at" | `discover.recommend(seed=current_branch_id, k=5)` |
| **TRENDING** | "what's hot / freshly remixed" | `discover.trending(window='week'|'month', domain=...)` |
| **EXPLAIN** | "why is this design battle-tested / what makes it good" | `discover.explain(branch_id)` — rationale + lineage + signal |
| **CROSS_DOMAIN** | "this fantasy-author technique might apply to scientific computing — show me" | `discover.cross_domain(seed_id, target_domain)` (advanced; v2) |

### §2.2 — Action signature design

Each action returns a list of catalog entries (branch defs / goal defs / etc.) with consistent metadata:

```jsonc
{
  "results": [
    {
      "id": "<commons-id>",
      "type": "branch" | "goal" | "node" | "wiki",
      "name": "...",
      "author": "github:alice",
      "domain": "fantasy_author" | "scientific_computing" | "...",
      "license": "CC-BY-SA-4.0",
      "signal": {
        "verified_outcomes": 12,           // gates claimed by community
        "remix_count": 47,                  // descendants
        "recency_days": 3,                  // last update
        "rank_score": 0.87                  // composite
      },
      "lineage": ["<parent-id>", "<grandparent-id>"],  // attribution chain
      "summary": "...",                     // ~100 word description
      "preview_url": "https://commons.../<id>/preview"  // browser-clickable
    }
  ],
  "next_page": "..."
}
```

**Browser-only-friendly:** every result has a clickable preview URL. User on Maya's phone can tap a result to see the design before deciding to remix.

### §2.3 — Search backends — what powers SEARCH + SIMILAR_TO

**SEARCH (text + structured filter):**
- BM25 / inverted-index over branch names + descriptions + tags + node names + wiki body
- Faceted filtering by domain / license / author
- Existing seed: `goals search` does multi-token matching; `extensions list` filters by domain. Generalizes.
- Backend: SQLite FTS5 over the local commons-cache mirror; no new infra needed for v1.

**SIMILAR_TO (semantic + structural):**
- Two distinct similarity axes:
  - **Structural similarity:** graph topology (node count, edge shape, state-schema overlap). Cheap; runs locally.
  - **Semantic similarity:** embedding-based (sentence-embed branch description + node prompts; cosine similarity). Uses existing `tinyassets/retrieval/` substrate (E5).
- Backend: LanceDB (already in tree per E5 substrate) holds embeddings of public commons content. Each chatbot's host (or anchor host for browser-only) queries against it.

**RECOMMEND (collaborative-filtering shape):**
- "Users who built X also built Y" — cohort-shape recommendations.
- Requires user-history-aggregation across the commons. Per commons-first: this is PUBLIC interaction data (publishes / forks / runs) — already commons-resident. Can aggregate.
- Backend: SQL aggregations over `attribution/events.jsonl` log + commons catalog.

**TOP_N + TRENDING + EXPLAIN:**
- Driven by the SIGNAL aggregation (§3 below).
- Cheap to compute; updates on every commons commit.

### §2.4 — User-vocabulary alignment

Per `feedback_user_vocabulary_discipline`: actions should use user vocabulary. The proposed verbs:

- `search` ✓ (universal)
- `similar_to` ✓ (natural English)
- `top_in` ✓ (Maya might say "what's good in this space")
- `recommend` ✓ (Tomás might say "what should I try")
- `trending` ✓ (anyone)
- `explain` ✓ (universal)
- `cross_domain` ✓ (Priya might say "this idea from MaxEnt might apply to RF")

All non-engineery. Phone-friendly. Pass.

---

## §3 — Signal layer: how community evolves quality without platform-judging

Per principle: "battle-tested in this domain by community signal." The platform doesn't decide what's good — community signal does.

### §3.1 — Signal sources (all commons-resident; all opt-in)

| Signal | Source | Update cadence |
|---|---|---|
| **`fork_count`** | When User B forks User A's branch via `commons.fork(from=A_id)` — attribution event published | Real-time on fork |
| **`remix_count`** | When User B's fork is itself forked further (multi-generation) | Real-time |
| **`run_count`** (public runs) | When a run completes against a public commons branch + result is publicly attributed | Real-time |
| **`verified_outcome_count`** | When a `gate.claim` is registered against a public commons branch (per `project_designer_royalties_and_bounties`) | Real-time |
| **`bounty_received`** | If branch fixed a bug + bug-bounty was awarded | On settlement |
| **`recency_days`** | Last commit / fork / run | Computed |
| **`star_count`** (lightweight community endorsement) | User-can-star via `commons.star(branch_id)` — like GitHub stars | Real-time |
| **`attribution_chain_length`** | How many generations of remix lead to here | Computed at query time |
| **`license`** | From the YAML frontmatter (CC-BY-SA / CC0 / proprietary fork — but commons-first only allows open licenses) | Static per row |

### §3.2 — Composite ranking (v1 — naive)

Simple weighted score for v1; tunable later:

```
rank_score = (
  0.25 * normalize(verified_outcome_count) +
  0.25 * normalize(fork_count) +
  0.15 * normalize(run_count) +
  0.10 * normalize(remix_count) +
  0.10 * normalize(star_count) +
  0.10 * recency_decay(recency_days, half_life=30) +
  0.05 * normalize(bounty_received)
)
```

**Properties:**
- New designs aren't crushed by old ones (recency_decay)
- Multi-generation remix surfaces (remix_count)
- Verified outcomes count more than raw forks (designs that work in production)
- Stars matter but don't dominate (gaming-resistant)

**v2 candidates:** PageRank-shape over the attribution graph (designs everyone reaches via remix get higher). LLM-judged quality (carefully — `project_platform_responsibility_model` says no auto-judge gates; but for ranking it's user-callable).

### §3.3 — Anti-gaming + abuse posture

- **Star count alone is gameable** → low weight in composite.
- **Run count is gameable by spamming runs** → only PUBLICLY-ATTRIBUTED runs count.
- **Fork count is gameable by self-forking** → exclude same-author forks; weight cross-author forks more.
- **Verified outcomes** are the strongest signal because they require gate-claim infrastructure (real work).

Per `project_q10_q11_q12_resolutions`: community-flagged moderation handles the long tail. Platform doesn't pre-judge; community flags get expert-review.

### §3.4 — Explainability — every rank shows its work

`discover.explain(branch_id)` returns:

```jsonc
{
  "branch_id": "...",
  "rank_score": 0.87,
  "components": {
    "verified_outcomes": {"value": 12, "weight": 0.25, "contribution": 0.21},
    "fork_count": {"value": 47, "weight": 0.25, "contribution": 0.18},
    ...
  },
  "lineage": [
    {"id": "...", "name": "Original MaxEnt sweep by Priya", "remix_distance": 0},
    {"id": "...", "name": "BIOCLIM extension by Bjorn", "remix_distance": 1},
    {"id": "...", "name": "RF + presence-only fix by Sam", "remix_distance": 2}
  ],
  "rationale": "Battle-tested across 14 species + 3 reviewer rounds; Sam's RF extension closed a methodological gap the original missed."
}
```

This is what makes user trust ranking. Per Priya's grievances: she WON'T trust black-box ranking; she'll trust transparent ranking she can audit.

---

## §4 — Remix-with-credit primitive (`commons` extension)

Remix happens via `commons` primitive (write-side), not `discover` (read-side). Discover finds it; commons forks it.

### §4.1 — `commons.fork` — single-generation remix

```
commons.fork(from=<source_branch_id>, into=<my_universe>, license=<auto-from-source>) → new_branch_id
```

**What it does:**
1. Clones the source branch definition into the user's universe (host-resident or commons-publishable, user picks).
2. Generates an attribution event:
   ```jsonc
   {
     "event": "fork",
     "from": "<source_branch_id>",
     "to": "<new_branch_id>",
     "actor": "github:userB",
     "timestamp": "...",
     "license": "CC-BY-SA-4.0"
   }
   ```
3. Records LINEAGE in the new branch's metadata: `parent: <source_branch_id>`, `lineage: [grandparent, ..., source]`.
4. Source author gets attribution credit per `project_designer_royalties_and_bounties` rules.

### §4.2 — Multi-generation attribution

When User B forks User A's design, then User C forks B's:

```
A (original) → B (fork v1) → C (fork v2)

C's lineage: ["A", "B"]
A's "descendants" view: ["B", "C", ...]
B's "descendants" view: ["C", ...]
```

When User D wants to credit "everyone whose work this builds on":

```
commons.attribution_chain(branch_id="C") →
  ["A", "B", "C"] (depth-first walk through lineage)
```

When royalties / bug-bounties pay out (per `project_designer_royalties_and_bounties`):
- N% to direct author (C)
- M% distributed across lineage (B + A) per generation-decay
- O% to platform treasury (1% take per `project_monetization_crypto_1pct`)

### §4.3 — Attribution chain integrity

Each attribution event is a commit in a public log (jsonl in commons-git-repo). Cryptographically:
- Append-only (commit history)
- Public (anyone can verify)
- Fork-resistant (a malicious fork removing prior lineage signs a commit that other tools can compare to the canonical chain → flagged)

For v1: trust git-commit history. For v2: optional cryptographic signatures on attribution events (Sigstore-shape — `sigstore.dev`).

### §4.4 — Edge cases

| Case | Handling |
|---|---|
| User forks but heavily modifies — still attribution? | YES. Attribution is for the SEED + IDEA, not the implementation. Wikipedia model. |
| User forks and explicitly disclaims attribution | NOT ALLOWED in commons-first. The license requires attribution. (Per `project_license_fully_open_commons` direction — CC-BY-SA-4.0 mandates attribution.) |
| User wants to keep their fork PRIVATE (host-resident) | Attribution event ISN'T published until user makes the fork public. Fork can be host-resident; lineage stays intact for when user later publishes. |
| User forks from a SOURCE that gets later retracted | Attribution stays; the source's retraction doesn't invalidate descendants. (Wikipedia model — copyright violations get DMCA'd, but normal retractions don't unwind the chain.) |
| User wants to rename their fork | Fine; the ID is stable, the name is metadata. |

---

## §5 — Integration with 5+2 (now 6+2) primitive set

### §5.1 — Refined primitive set

| # | Primitive | New scope (post commons-first reframe) |
|---|---|---|
| 1 | **workspace** | Own universes + own host inventory |
| 2 | **workflow** | DESIGN + EXTEND (within own universe) |
| 3 | **run** | Execute workflows + observe + deliver |
| 4 | **evaluate** | User-callable evaluators against public commons + own work |
| 5 | **commons** | PUBLISH + FORK + ATTRIBUTE — the WRITE side of cross-user |
| 6 | **discover** | SEARCH + SIMILAR + RECOMMEND + RANK + EXPLAIN — the READ side of cross-user |
| + | host (local-app) | Tray daemon hosting |
| + | upload (local-app) | File-system → commons / host transfer |

### §5.2 — How user-goal verbs distribute (refined from primitive-set proposal §1)

| User verb | Distribution |
|---|---|
| **DESIGN** | `discover.search` (find prior work) → `commons.fork` (or copy) → `workflow.build/patch` |
| **DISCOVER** | `discover.*` (the whole primitive) |
| **RUN** | `run.submit/status/fetch` |
| **OBSERVE** | `run.events/status` + `discover.explain` (for understanding what you ran) |
| **EXTEND** | `discover.search` for self → `run.continue from_run_id=...` |
| **DELIVER** | `run.fetch_outputs` + `commons.publish` (if making it shareable) |
| **COLLABORATE** | `commons.fork` + `commons.attribute` + wiki + `discover.explain` of contributors |

**All 7 user-goal verbs distribute cleanly across 6 primitives.** Pass.

### §5.3 — The split is robust to MCP roadmap changes

Per `project_user_capability_axis` + MCP roadmap (per primary primitive-set proposal §6.1):

- When MCP **resources** ship in Claude.ai web: `discover` results become server-published resources the chat-client BROWSES directly (no tool roundtrip per result). `discover` primitive itself unchanged; richer rendering.
- When MCP **prompts** ship: `discover.recommend` could surface as user-pickable templates ("start from this design"). Same primitive; new render path.
- When MCP **sampling** ships: `discover.recommend` can use server-side LLM judging for personalization. Same primitive; richer backend.

**`discover` is roadmap-stable.**

---

## §6 — Implementation roadmap

### §6.1 — Phase 1: SEARCH (v0 — local catalog)

**Scope:** `discover.search(query, type, filters)` over the commons-cache (local mirror of git catalog).

**What ships:**
- SQLite FTS5 index over branch defs / goal defs / wiki / nodes
- Faceted filter (domain / author / license)
- Result ranking by raw text-relevance + recency

**Effort:** ~1-2 weeks. Mostly mechanical — backends exist (`tinyassets/api/wiki.py`'s search is the seed pattern).

**Gates on:** `commons` primitive (5+2 → 6+2 reframe lands)

### §6.2 — Phase 2: SIGNAL aggregation

**Scope:** Build the signal-source pipeline. Aggregate fork_count, remix_count, run_count, verified_outcomes from existing event sources.

**What ships:**
- `attribution/events.jsonl` log format (append-only, public)
- Event emitter: every `fork` / `publish` / `gate.claim` writes an event
- Aggregator: rebuilds `signal/<branch_id>.json` per branch with all metrics
- `discover.top_in` + `discover.trending` actions backed by signal layer

**Effort:** ~2-3 weeks.

**Gates on:** Phase 1 + multi-generation attribution wiring (§4.2).

### §6.3 — Phase 3: SIMILAR_TO (semantic + structural)

**Scope:** Embedding-backed similarity search.

**What ships:**
- LanceDB index of public commons content (descriptions + node prompts → vectors)
- `discover.similar_to(reference_id, axis='structure' | 'domain' | 'outcome')`
- Structural similarity computed on graph topology

**Effort:** ~3-4 weeks (LanceDB integration is the largest piece; existing E5 retrieval substrate is the seed).

### §6.4 — Phase 4: RECOMMEND + EXPLAIN

**Scope:** Collaborative filtering + rank-explainability.

**What ships:**
- `discover.recommend(seed=current_branch_id, k=5)`
- `discover.explain(branch_id)` returns rationale + lineage + signal breakdown

**Effort:** ~2-3 weeks.

### §6.5 — Phase 5: CROSS_DOMAIN (v2)

**Scope:** Cross-domain transfer suggestions ("this fantasy-author technique adapts to scientific computing").

**What ships:**
- LLM-judged cross-domain relevance (`evaluate` substrate composes here)
- Domain-graph: which domains share structural patterns

**Effort:** ~4-6 weeks (R&D heavy).

**Gates on:** Phase 3 + ample commons content (post-launch maturation).

### §6.6 — Total arc: ~3-5 months engineering across phases

---

## §7 — Paid market under commons-first (cross-cut from sibling sweep F7 + F20)

The dispatcher routes paid jobs to bidders. Under commons-first, two new constraints:

### §7.1 — Public-content paid jobs (no constraint change)

User submits a paid job against a PUBLIC commons branch. Dispatcher claims to highest value-vs-effort bidder. Same as today.

### §7.2 — Private-content paid jobs (new constraint: data-locality)

User submits a paid job against a PRIVATE host-resident branch. Dispatcher MUST route to a host with access. Two cases:

**Case A — User has multiple hosts; one is online.** Dispatcher picks the user's online host. Cost: covered by user's own host (free) or paid market (if user prefers a community host's compute).

**Case B — User has multiple hosts; user wants to PAY for compute.** User specifies "find a willing host with capacity, but the data needs to come from MY host." Two patterns:
- (i) Bidder claims; user's host PUSHES private data to bidder's host transiently for the run; data deleted post-run. Trust pattern: user trusts bidder.
- (ii) Bidder doesn't get the data; user's host RUNS the work but bidder's compute resources are leased remotely. Heavier engineering; less trust burden.

**Recommendation: (i) for v1.** User explicitly trusts bidders; community-rated. Per `project_paid_market_trust_model` cooperative-not-stranger framing.

### §7.3 — Paid hosting market (new market type)

Per sibling design note §2.5: browser-only users buying private hosting. Different market than paid execution.

**Shape:** standing offers from T2 hosts ("I'll host your private universe for $5/mo, 100GB, with 99% uptime"). Browser users browse via `discover` (filtering for `service_type='hosting'`). Settlement via paid-market ledger.

**This is a NEW market type:** paid execution (today's design) vs paid hosting (new). Both ride on the same dispatcher + ledger substrate; differ in offer shape.

---

## §8 — Risk profile

### §8.1 — Low-risk

- **Phase 1 (SEARCH) is mostly mechanical** — backends exist; FTS5 is well-trodden.
- **Attribution chain in git is fork-resistant** — git's append-only log is the substrate.
- **Public commons license enforcement** — license is in YAML frontmatter; tool surface checks at fork time.

### §8.2 — Medium-risk

- **Signal layer is gameable** at the long tail. Star count is the most gameable; weighted low. Verified outcomes are gameable only by faking gate-claims (which require real work).
- **Multi-generation royalty calculation** is non-trivial at scale (graph-walk per payout). Cache aggressively.
- **Cross-host private-data dispatch (Case B-i)** introduces a trust + data-leak window. Mitigate via TTL on transient copies + community reputation.

### §8.3 — High-risk

- **Discover ranking quality determines whether community-evolves-features works at all.** If `discover.top_in` shows mediocre stuff, users won't fork it; the engine sputters. Treat ranking as continuously iterable; ship v1 with naive composite, evolve via user feedback.
- **License compatibility chains.** If a user forks a CC-BY-SA branch and tries to relicense as CC0, that's a license violation. Tool surface MUST enforce license-at-fork time. Per Wikipedia commons model.

---

## §9 — Cross-references with the in-flight work

### §9.1 — Sibling design notes

- `docs/audits/2026-04-27-commons-first-architecture-implications.md` (F4, F12, F13, F14)
- `docs/design-notes/2026-04-27-host-resident-private-data-design.md` (§2.5 community-hosting; §7.3 paid hosting)
- `docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md` — UPDATE per F21: 5+2 becomes 6+2 with `discover` split off

### §9.2 — Existing memories ratified

- `project_designer_royalties_and_bounties` — multi-generation attribution + royalty distribution per §4.2 + §7
- `project_convergent_design_commons` — this design IS the realization
- `project_minimal_primitives_principle` — `discover` earns its 6th-primitive seat
- `project_license_fully_open_commons` — license posture per §3.1 + §8.3

### §9.3 — STATUS row updates needed

- Activate "[deferred] Daemon roster + node soul/ledger/attribution/royalty/outcome/bounty/fair-distribution items" — per F11 in sibling sweep.
- Pin commons license decision (CC-BY-SA-4.0 recommended) per F14.

---

## §10 — Decision asks for the lead → host

1. **Approve `discover` as 6th primitive (5+2 → 6+2)?** Per §1 rationale.
2. **Approve the 7 sub-verbs** of `discover` (search/similar_to/top_in/recommend/trending/explain/cross_domain)? Or trim?
3. **Approve composite ranking formula** (§3.2)? Or pick a different starting weight set?
4. **Approve multi-generation attribution model** with N%/M%/O% royalty split (§4.2)? Or wait for separate spec?
5. **Approve paid hosting market** as a new market type alongside paid execution (§7.3)? Or punt to v2?
6. **Approve implementation roadmap** Phase 1-5 (~3-5 months)? Or sequence differently?
7. **Approve license decision: CC-BY-SA-4.0 for content, MIT/Apache-2.0 for code**? Per §8.3.

---

## §11 — Cross-references

- `project_commons_first_architecture` — Part 3 is the rule this note designs
- `project_designer_royalties_and_bounties` — attribution + royalty engine
- `project_minimal_primitives_principle` — `discover` as 6th primitive
- `project_convergent_design_commons` — this design is the realization
- `project_license_fully_open_commons` — license decision pin
- `project_paid_market_trust_model` — Case B-i trust pattern in §7.2
- `project_q10_q11_q12_resolutions` — community-flagged moderation per §3.3
- `docs/audits/2026-04-27-commons-first-architecture-implications.md` — sibling sweep
- `docs/design-notes/2026-04-27-host-resident-private-data-design.md` — sibling, data architecture
- `docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md` — F21 update needed
- `docs/design-notes/2026-04-26-engine-primitive-substrate.md` — E5 retrieval substrate is the seed for `discover`
- `tinyassets/retrieval/router.py` + LanceDB substrate — Phase 3 SIMILAR_TO backend
- `tinyassets/contribution_events.py` — attribution event substrate

### Web research citations

- [Civitai](https://civitai.com/) — community model-sharing + remix patterns at scale
- [Hugging Face Hub Licenses](https://huggingface.co/docs/hub/repositories-licenses) — license + discovery patterns
- [Commons:Licensing | Wikimedia](https://commons.wikimedia.org/wiki/Commons:Licensing) — content commons license model
- [The 2026 MCP Roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) — discover primitive's roadmap robustness
- [Official MCP Registry](https://registry.modelcontextprotocol.io/) — federation + server-discovery model
- [Recommended practices for attribution | Creative Commons](https://wiki.creativecommons.org/wiki/Recommended_practices_for_attribution) — multi-generation attribution chain norms
- [Distributed Hash Tables (DHT) | IPFS Docs](https://docs.ipfs.tech/concepts/dht/) — federated discovery patterns (cross-ref to host-resident sibling)
