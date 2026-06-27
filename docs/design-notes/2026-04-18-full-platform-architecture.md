---
status: integrated-into-PLAN
integrated_date: 2026-04-28
canonical_in: PLAN.md §"Full-Platform Architecture (Canonical)"
---

# Full Platform Architecture — No Phases, Single-Build Target

**Date:** 2026-04-18 (host directive this day)
**Author:** navigator
**Status:** Integrated into PLAN.md as canonical architecture (2026-04-28). This design note is retained as the integrated detail surface — full reasoning, tradeoff analysis, scale-audit numbers, host-decision lineage. PLAN.md §"Full-Platform Architecture (Canonical)" is the principle-level reference; sections of this note are cited from PLAN.md as decision rationale.

**Replaces:** the phased rollout in `docs/design-notes/2026-04-18-persistent-uptime-architecture.md` §7 Phase 1/2/3. Supersedes `docs/exec-plans/active/2026-04-18-uptime-phase-1a-static-landing.md` — phased plan rejected by host.

**Hostname history (2026-04-18 → 2026-04-20):** this doc originally named `api.tinyassets.io` as the MCP gateway hostname; `api.` was never created. Post-P0 (2026-04-19), a Cloudflare Worker shipped to restore the apex `tinyassets.io/mcp` (apex + path) as the canonical user-facing URL — the Worker proxies to the tunnel-internal origin at `mcp.tinyassets.io`. Body text below uses the apex URL for user-facing MCP references; tunnel-origin references (where the architecture specifically discusses the tunnel layer) continue to name the `mcp.` subdomain.

**Related (not replaced, integrates):**
- `docs/research/github_as_catalog.md` (re-evaluated in §4).
- `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md` (sensitivity tiers integrate here).
- Project memory: paid-market bid model; daemon brand voice; distribution horizon; daemon restart authorized.

---

## §1. Requirements re-stated + why phased plan was rejected

**Product soul — the north star (host directive 2026-04-18, Q21):**

> **"This is a real world effect engine."**

Workflow is for people getting real work done every day — at their jobs, on their own projects, producing real artifacts that exist in the world beyond Workflow. Success is measured in **real-world outcomes** — books published, papers peer-reviewed, tasks completed, projects shipped — not in engagement, DAU, or session time. **Fail state: if it feels gimmicky or like a toy, it's failing.** Every design decision in this note is evaluated against the question *"does this help a user finish real work, or does it make the platform feel more like a toy?"*. See §24 for the full product-soul treatment and the design implications that cascade from this framing.

**Host directive 2026-04-18:**

1. **Thousands of concurrent users working simultaneously.** Scale target is multi-user from day one, not "alpha then maybe scale."
2. **Full node CRUD works with zero daemons hosted anywhere.** Node authoring, goal authoring, branch authoring — all must function when literally no daemon is running on any host. Daemon hosting is for *daemon execution work*, not for the authoring platform.
3. **Multi-user near-real-time collaboration on shared ideas.** Users work off each other: see each other's node designs, comment, fork, refine. Cadence: seconds, not hours.
4. **Daemon hosting is opt-in.** Any user can host for their own use, for paid requests, for their chatbot. Not required for system function. A user can host for themselves only, without exposing capacity publicly.
5. **Weeks not months.** Build the *final* thing fast, not a phased rollout that throws away work.

**Why the phased plan was rejected:** Phase 1a (static-landing-only) + Phase 1b (thin relay) + Phase 2 (state migration) + Phase 3 (paid failover) scoped Workflow as "the daemon MCP surface" with a browse page in front. The host's actual product is "a collaborative workflow platform where daemons are an execution tier you can opt into." Phase 1a ships 0% of requirement (2) or (3). Phase 1b ships 0% of (3). Building the full collaborative backend in one push avoids three throwaway migrations (static → thin relay → state-migrated relay → write-capable platform) that each require re-teaching users + re-cutting Claude.ai connectors.

**The reframe:** the control plane is not a thin relay. It is **the product** — a multi-user collaborative backend. Daemons are a hosted-execution tier that plugs into it. GitHub is an export sink, not the canonical store.

---

## §2. Architectural shape for the final target

### §2.1 Components

Single backend owning all authoritative state except daemon execution + user uploads:

- **Identity + auth** — OAuth 2.1 + PKCE at the MCP edge; GitHub OAuth for user accounts at launch; session tokens scoped per user.
- **Writable catalog registry** — Goals, Branches, Nodes as rows in a relational DB. Forks, lineage, tags, visibility, timestamps. This is the *canonical* store (see §4).
- **Real-time sync layer** — presence (who is viewing what), change broadcast (someone edited node X, subscribers see update within 1–2 s), comments, optimistic concurrency.
- **Daemon host pool registry** — heartbeats, declared capabilities (node types × LLM models × price), online/offline state, per-host visibility (self-only / network / paid-market).
- **Paid-market bid inbox** — requests land here, daemons poll for eligible work, control plane settles via the ledger.
- **Ledger + settlements** — economic truth.
- **Upload store** — canon files, per-universe; large-blob storage backed by object storage (S3-compatible).
- **MCP gateway** — exposes the above as MCP tools at `tinyassets.io/mcp` for Claude.ai chatbot users. REST surface for the web app.
- **Web app** — landing page + catalog browse + collaborative editor. Primary surface for requirement (3).

### §2.2 Real-time strategy — recommendation: versioned rows + row-level broadcast, NOT CRDT

Three candidates considered ([Yjs docs](https://docs.yjs.dev/), [Supabase pg_crdt](https://supabase.com/blog/postgres-crdt), [Automerge + Convex](https://stack.convex.dev/automerge-and-convex)):

| Approach | When it earns its keep | Cost |
|---|---|---|
| **CRDT (Yjs / Automerge)** | Character-by-character concurrent editing of the same prose buffer. Google-Docs-style. | High — new data-model layer, storage churn (every update = DB row), client-side library, reconciliation gotchas. Notion uses Yjs + server-side validation per the research. |
| **Operational transform** | Same use case as CRDT; older, more battle-tested; Google Docs' original shape. | Medium-high — requires a stateful server coordinator, harder to self-host than CRDT. |
| **Versioned rows + broadcast + presence** | Coarse-grained collaboration: users edit *different* nodes concurrently, or edit the same node with last-write-wins + update-since-you-viewed warnings. Comments are append-only (no conflicts). | Low — standard Postgres rows with `updated_at`, a websocket channel per row, optimistic UI. Supabase Realtime ships this out of the box ([Supabase Realtime](https://supabase.com/docs/guides/realtime)). |

**Recommend versioned rows + broadcast + presence.** The "working off each other" requirement is *coarse*: users author different nodes, comment on each other's goals, fork branches. That is not character-by-character typing inside the same YAML buffer. A Goal YAML with `updated_at` + optimistic-lock conflict detection + a presence channel ("Alice is editing this node") + append-only comments covers the described behavior at a tiny fraction of CRDT's complexity and storage cost.

**Escalation path:** if a specific artifact emerges that *does* need Yjs-class editing (e.g. a shared prose document inside a node), adopt Yjs on a per-artifact basis later. Don't build a CRDT substrate for an app that is mostly structured data.

### §2.3 Diagram

```
Users (web app, Claude.ai chatbot, future mobile / desktop MCP clients)
   │
   │  HTTPS + WebSockets (near-real-time subscriptions)
   ▼
┌─────────────────────────────────────────────────────────────────┐
│                   tinyassets.io                             │
│                                                                 │
│   ┌───────────────┐   ┌──────────────┐   ┌────────────────┐     │
│   │ MCP gateway   │   │ Web REST     │   │ WebSocket      │     │
│   │ (FastMCP)     │   │ (FastAPI)    │   │ subscriptions  │     │
│   └───────┬───────┘   └──────┬───────┘   └────────┬───────┘     │
│           │                  │                    │             │
│           ▼                  ▼                    ▼             │
│   ┌───────────────────────────────────────────────────────┐     │
│   │       auth / sessions / RLS enforcement               │     │
│   └───────────────┬───────────────────────────────────────┘     │
│                   ▼                                             │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐      │
│   │ catalog  │  │ comments │  │ presence │  │ host pool  │      │
│   │ (GBN)    │  │          │  │          │  │ registry   │      │
│   └──────────┘  └──────────┘  └──────────┘  └────────────┘      │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐      │
│   │ requests │  │ bids     │  │ ledger   │  │ uploads    │      │
│   │ (inbox)  │  │          │  │          │  │ metadata   │      │
│   └──────────┘  └──────────┘  └──────────┘  └────────────┘      │
│                                                                 │
│   Postgres + Supabase Realtime + S3-compatible object store     │
└─────────────────────────────────────────────────────────────────┘
                   │                               │
                   │ (dispatches paid work         │
                   │  to hosts, settles)           │
                   ▼                               │
┌───────────────────────────────┐           ┌──────┴──────┐
│ Daemon hosts (opt-in)         │           │ GitHub      │
│ - tray, LangGraph runtime     │           │ (export     │
│ - KG / vector / notes.json    │           │  sink only, │
│ - polls for eligible bids     │           │  §4)        │
│ - heartbeat + capabilities    │           │             │
│   + visibility flag           │           │             │
└───────────────────────────────┘           └─────────────┘
```

### §2.4 User tiers and capability matrix

**Three named tiers, designed for from day one.** Every capability is labeled with its target tier(s); no conflation. Project memory: `project_user_tiers.md`.

| Tier | Who | Install cost | Primary surface |
|---|---|---|---|
| **T1 — Chatbot user** | Anyone with a Claude.ai account | **Zero-install.** Adds `tinyassets.io/mcp` as an MCP connector + visits `tinyassets.io/` in a browser. | Claude.ai chat + web app |
| **T2 — Daemon host** | T1 user who also wants to run daemons (for self, for friends, for paid requests) | **One-click install** of the Workflow tray (MCPB bundle / platform-native installer). Authenticates against same account. | Tray app + web app + Claude.ai |
| **T3 — OSS contributor** | Anyone who wants to extend domains, add node types, fix bugs | `git clone` + standard Python toolchain. Needs CONTRIBUTING.md pointer. | Local dev env + GitHub PR |

**Capability matrix — tier × action:**

| Capability | T1 Chatbot | T2 Daemon host | T3 Contributor |
|---|---|---|---|
| Browse catalog (goals / branches / nodes) | ✓ | ✓ | ✓ |
| Create + edit nodes, goals, branches | ✓ | ✓ | ✓ |
| Comment, fork, remix | ✓ | ✓ | ✓ |
| Live presence + see others editing | ✓ | ✓ | ✓ |
| Place paid-market requests (requester) | ✓ | ✓ | ✓ |
| Consume own daemon's work (private) | — | ✓ | ✓ |
| Run daemon for self only (`visibility=self`) | — | ✓ | ✓ |
| Share daemon with network (`visibility=network`) | — | ✓ | ✓ |
| Accept paid bids (`visibility=paid`) | — | ✓ | ✓ |
| Earn ledger credits from paid market | — | ✓ | ✓ |
| Report artifact / behavior (any tier reports) | ✓ | ✓ | ✓ |
| Triage reports (moderation action) | — | earn-eligible (see §8) | earn-eligible (see §8) |
| Submit PR to catalog (YAML round-trip via §4) | via chat | via tray | native |
| Extend domain skills, add node types, engine changes | — | — | ✓ |

**Tier-1 is the largest audience by design** — zero-install puts Workflow in every Claude.ai user's reach. Tier-2 converts from tier-1 at the user's pace (they collaborate on nodes, then want to run a daemon). Tier-3 is a small slice of technical contributors.

### §2.5 Tier migration as a first-class feature

Users promote themselves between tiers without losing state. Design-time constraint: *same identity across tiers.*

- **T1 → T2:** user is already signed in via GitHub OAuth in the web app. They click "Host a daemon," download the tray, install. First tray launch does OAuth with the *same* backend; their account lights up as a host. Their existing goals/branches/nodes are untouched.
- **T2 → T3:** user with a tray who wants to contribute code clones the repo, reads CONTRIBUTING.md, submits PRs. GitHub identity is already their Workflow identity, so attribution lineage is unified.
- **T1 → T3:** a chatbot-only user who decides to contribute skips the tray entirely and clones. Also fine.
- **Downgrades:** uninstall tray → T2 reverts to T1 (host entry soft-deleted, data preserved). PRs merged stay merged regardless of tier.

**Why this matters structurally:** GitHub OAuth as the single identity primitive (§7) makes all four migration paths free. No account stitching, no "link your tray to your web account" dance.

### §2.6 Schema reference — canonical location + gap items

**Canonical schema lives in `docs/specs/2026-04-18-full-platform-schema-sketch.md` (spec #25).** This note references schema only where design decisions depend on specific column shapes; for CREATE TABLE statements, RLS policies, and index definitions, spec #25 is authoritative.

**Columns/tables this design note references that need to exist in spec #25 §1 (drift audit #64 §2.3/§5.3 identified as gaps to close):**

| Item | Source design section | Canonical location |
|---|---|---|
| `nodes.primary_language` (ISO 639-1) | §15.7 (Q13 multilingual) | spec #25 §1.2 — add column |
| `nodes.domain_ids uuid[]` + `domains(...)` table | §15.8 (Q14 permissionless domains) | spec #25 §1.2 + new §1.2b |
| `nodes.node_type` + `node-type-taxonomy` catalog alignment | §2.6 this note + `docs/catalogs/node-type-taxonomy.md` | spec #25 §1.2 — add column |
| `branches` / `branch_definitions` table | §2.6 this note (surplus from `prototype/tinyassets-catalog-v0/`) | spec #25 new §1.x |
| `ledger.settlement_mode enum('immediate','batched')` | §18.6 (Q4-follow hybrid settlement) | spec #25 §1.7 |
| `request_inbox.bid_amount_usd_cached numeric` | §18.6 (threshold routing) | spec #25 §1.6 |
| `request_inbox.fan_out jsonb` | §27.5 (parallel fan-out) | spec #25 §1.6 |
| `nodes.extensions jsonb` | §29.1 (scope-extension hints) | spec #25 §1.2 |

Spec #25 edits are queued via the drift audit's §7.2 dev-dispatch list. No migrations needed — these are additive columns + one new table.

### §2.7 Absorbed surplus from dev-landed artifacts

**`node_type` as first-class axis** (from `docs/catalogs/node-type-taxonomy.md` v1). Every node carries a `node_type` — *generator / transformer / validator / extractor / composer / router / gate / ingester / emitter / aggregator* — orthogonal to `domain`. Chatbot uses both axes when reasoning: `domain=research-paper, node_type=validator` finds citation-checkers structurally similar to invoice-number-validators in a different domain. Cross-domain structural matches emerge naturally. `discover_nodes` accepts `node_type_hint` parallel to `domain_hint`.

**Branches as first-class composite-workflow artifacts** (from `prototype/tinyassets-catalog-v0/catalog/branches/` — 3 sample BranchDefinition YAMLs shipped: `research-paper-pipeline`, `fantasy-scene-chapter-loop`, `invoice-batch-processor`). A branch is a composite workflow — multiple nodes wired into a pipeline with shared state, fork/join, eval-loop, or router-split integration patterns (see `docs/specs/integration-pattern-catalog` when landed, task #63). `artifact_field_visibility.artifact_kind` already lists `'branch'`, so §17 privacy handles branches; §18 monetization treats branch invocation as a composite bid; §15 discovery ranks branches alongside nodes. Schema table is the gap (see §2.6).

---

## §3. Stack options at thousands-concurrent

### §3.1 Option matrix

Evaluated against requirements 1–5. Costs are monthly, all-in (hosting + realtime + auth + egress):

| Stack | @100 DAU | @1k DAU | @10k DAU | @100k DAU | Lock-in | Fit |
|---|---|---|---|---|---|---|
| **Supabase (Postgres + Realtime + Auth + RLS + Storage)** | $0 (Free) | $25 (Pro) | $50–150 (Pro + usage) | $400–800 or self-host | Low — Postgres is portable | **Strongest** — everything we need in one stack, open-source, self-hostable escape hatch |
| **Convex (TypeScript-first realtime + auth)** | $0 | $25 | $100–300 | $700–1500 | High — Convex is bespoke, not portable | Strong DX but locks platform into TS; our daemons are Python |
| **Firebase (Realtime DB + Firestore + Auth)** | $0 | $30–60 | $200–800 | $2k+ | High — Google-proprietary, hard to leave | Mobile-first strength we don't need; pay-per-read pricing dangerous at scale |
| **Fly.io + Postgres + custom realtime (Elixir/Phoenix or Python + websockets)** | $10 | $40 | $150–400 | $1k+ | None | Full control, more dev burden to build the realtime layer ourselves |
| **Small VPS (Hetzner/DO) + Postgres + Django Channels** | €10 | €20 | €80 | €400+ | None | Cheapest at scale, heaviest ops burden |

([Supabase pricing](https://supabase.com/pricing), [Convex vs Supabase 2026](https://scratchdb.com/compare/convex-vs-supabase/), [Supabase real costs at 10k-100k users](https://designrevision.com/blog/supabase-pricing).)

### §3.2 Recommendation: Supabase

Reasoning:
- **One stack covers five concerns** that we'd otherwise glue from parts: Postgres (catalog + ledger + inbox), Realtime (presence + broadcast), Auth (GitHub OAuth + sessions), Row-Level Security (visibility + sensitivity enforcement at the DB layer), Storage (canon uploads to S3-compatible). Cutting glue work is weeks saved.
- **Postgres is the ceiling-insurance.** Every competitor locks us into their data model. Supabase's DB is vanilla Postgres; if we outgrow Supabase-hosted, we lift-and-shift to self-hosted Postgres + Realtime (both open-source) without an application rewrite. No lock-in cost at exit.
- **Realtime at our scale is proven.** Supabase Realtime handles 10k+ concurrent WebSocket connections on Pro plan ([Supabase Realtime docs](https://supabase.com/docs/guides/realtime), [HN thread on Supabase multiplayer](https://news.ycombinator.com/item?id=32510405)). Our cadence (seconds, not milliseconds) is well inside its envelope.
- **Python-friendly.** Our daemons + MCP gateway stay Python. Supabase client library for Python is first-class; RLS policies are SQL. Convex forces TypeScript, Firebase forces Google SDKs.
- **Open-source escape hatch.** Self-hosting Supabase is a documented path. If hosted pricing balloons at 100k+ DAU, we move to Hetzner + self-hosted Supabase stack for ~€50/mo.

**Rejected:**
- **Convex** — TypeScript lock-in collides with our Python daemons; we'd maintain two codebases for tooling.
- **Firebase** — pay-per-read pricing unpredictable, lock-in severe, no Postgres.
- **Fly.io + custom realtime** — reasonable but we'd be building Supabase Realtime ourselves. ROI: negative at our scale.
- **Small VPS + Django Channels** — cheapest at 100k DAU but heaviest ops at 1k DAU. Wrong slope for the current phase.

### §3.3 Daemon host side: unchanged

The MCP gateway + realtime backend lives on Supabase. The daemon tray (on laptops, VPSes, dedicated boxes) continues running as today — LangGraph + LanceDB + KG host-local. Daemons call the control plane outbound (poll bid inbox, heartbeat, push action logs). No inbound connection to daemons needed — they stay behind NAT via outbound-only polling or, for daemons that also serve MCP to their owner directly, existing cloudflared tunnels.

---

## §4. Role of GitHub-as-catalog — HONEST re-evaluation

### §4.1 Decision: GitHub demoted to export sink

The GitHub-as-catalog direction (`docs/research/github_as_catalog.md`) fits when the product is "clone the repo, run locally, PR to contribute." That is incompatible with requirement (2): if GitHub is the canonical store, writes to the catalog require a git commit + push, which means either (a) every user has GitHub write access to the shared repo (doesn't scale, moderation nightmare) or (b) writes go through a daemon that commits on the user's behalf (reintroduces the daemon-required failure mode). Neither matches "thousands of concurrent users, zero daemons required."

**Demotion shape:**
- Canonical store = Supabase Postgres.
- GitHub stays as the **export target** — a periodic sync (hourly or on-demand) writes a flat snapshot of public goals/branches/nodes to the catalog repo, as YAML, in the existing shape. Drives GitHub-native discovery, cloneable demos, PR-able contributions for the subset of users who *want* that workflow.
- Contributions via PR are still accepted: a GitHub Action validates the PR's YAML, merges it, and a webhook triggers an import back into Postgres. Round-trip integrity is the Action's job.
- **This preserves the "clone and run" narrative without making it load-bearing.**

### §4.2 What we keep from the prior GitHub direction

- Flat YAML shape per artifact — unchanged. Postgres rows serialize cleanly back to the same YAML.
- Public-by-default. Private-tier rows never export.
- Soul files stay on GitHub as public, forkable definitions (no realtime concern).
- "Branches" and "forks" as first-class primitives — unchanged. Lineage in Postgres, mirrored to YAML.

### §4.3 What changes

- Not every user needs a GitHub account. GitHub OAuth is the *default* login for launch, but native accounts are added later if non-GitHub-users become a significant fraction.
- Live reads in the app come from Postgres, not from cloned repo state. Faster, RLS-enforced, realtime-aware.
- `pull_latest` MCP action retired. The app is the catalog.

**Material risk flagged:** this is a one-way door. Once Postgres is canonical and users are collaborating in realtime, reverting to GitHub-canonical means data migration. Recommend committing to the reframe explicitly — host decision Q1 in §11.

---

## §5. Daemon hosting model in the final picture

### §5.1 Primitives

Every daemon host declares, per capability:

- **Capability** — node type × LLM model × max concurrent × cost envelope.
- **Visibility (host-side)** — one of (3 values):
  - `self` — host runs this for its owner only. Never appears in the public pool. No bid intake. (User running a personal daemon on their laptop for their own chatbot work.)
  - `network` — available to the owner's friends, team, or explicit allowlist. No paid-market listing.
  - `paid` — listed in the public paid-market pool. Accepts bids at or above the declared floor.
- **Price floor** — minimum bid accepted for `paid` visibility. Zero-floor = free public work.
- **Heartbeat** — host is online via Supabase Presence (§14.5 — no `last_heartbeat` column; Presence-derived at query time).

**Visibility namespaces — host-side vs request-side are orthogonal (drift-audit #64 §2.8 clarified).**

- **Host-side visibility** (above, 3 values `self | network | paid`) is declared on `host_pool` rows — what pools a daemon will *listen* on.
- **Request-side visibility** (`request_inbox.visibility`, 4 values `self | network | paid | public` per spec #25 §1.6) is declared on `request_inbox` rows — which pool a request *targets*. The extra `public` value = "open to any qualifying daemon at zero-cost," matching §20's `fulfillment_path='free_queue'`.

Same vocabulary, different axes. A `paid`-visibility request can only be claimed by a `paid`-visibility host for that capability; a `public`-visibility request can be claimed by any `self`/`network`/`paid` host whose capability matches (the request is opting in to the broadest acceptable pool). Code path: `submit_request` sets request-side; tray settings set host-side; dispatch matches the two.

The tray UI exposes this as three toggles per capability: "host for me / share with team / accept paid bids." Defaults: self-only on install. Opting into `paid` requires a one-time tax setup (deferred — flag in §8).

### §5.1.1 Tray UX — this is tier-2's primary surface

The tray is tier-2's product. What it shows:

- **Daemon list, grouped by provider.** Shows current count per provider (e.g. "local: 1, Claude: 1, Codex: 0, Gemini: 0"). "Launch daemon" control with provider dropdown. ~~First daemon per provider = one click. Second+ daemon for the same provider = confirmation popup per §5.3 (rate-limit warning + payment-tier estimate + host confirms quota). The popup is a *warning*, not a block; host can override.~~ **Retracted 2026-04-24: no payment-tier popup. Host spawns freely. See §5.3 retraction note.**
- **Hosting controls panel.** For each declared capability, the three visibility toggles (self / network / paid). Add-capability flow pulls from the node-type registry (nodes declare required LLMs + software per `project_node_software_capabilities`). One row per `(node_type, llm_model)` pair.
- **Active-mode toggle** (§5.2). On = daemon runs the full cascade (host queue → paid → public → stay-busy) when not executing. Off = daemon only runs host-queue work then sleeps. On by default for `visibility=paid`, off by default for `visibility=self`.
- **Earnings dashboard.** Running total of ledger credits, last 30 days, per-capability breakdown. Links to settlement history.
- **Consumption dashboard.** When the same user has tier-1 activity (chatbot-placed requests), show their own pending/running/completed requests. Closes the loop: "you asked your daemon to do X, here's the status."
- **Network allowlist** (when any capability is `visibility=network`). Add/remove GitHub usernames; daemon accepts their requests at zero-cost.
- **Local-first indicator.** Confidentiality tier per universe, pinned provider (e.g. `ollama-local`), whether the daemon is reaching the control plane. Transparent that the tray talks outbound-only.

The tray does *not* include chat UX. Tier-2 users still chat in Claude.ai; the tray is the hosting-and-earnings surface.

### §5.2 Default behavior — active-mode cascade

**Active mode is the product frame; idle is a failure state.** When a daemon finishes a node (or starts with no current assignment), it runs a 4-step priority cascade before falling back to wait:

1. **Host's own queue first.** Does my host need anything? Any `requests` row owned by this daemon's `owner_user_id`, not yet claimed, that I'm qualified for → take it.
2. **Highest value-vs-effort paid request I'm qualified for.** Filter: `visibility=paid` requests whose `capability_id` matches my declared capabilities. Rank by value-vs-effort score: `f(bid_price, estimated_compute_cost, deadline_pressure, ...)` — not just max-bid. Claim the top row via `SELECT FOR UPDATE SKIP LOCKED`.
3. **Other-public requested nodes I'm qualified for.** If no paid requests eligible, consider any non-paid public request (`visibility=network` within my allowlist, or open-free-pool requests I can serve at zero-cost). Multi-factor ranking (no single canonical weighting; daemon-judged at claim time):
   - Popular user demand (upvote-or-subscribe count on the request).
   - Other-node dependency demand (downstream work blocked on this).
   - Pending-time staleness (how long has it sat).
   - Iterative-improvement-cycle membership (part of a public workflow redesign in motion).
   - Anything else the daemon reasons would have the most effect — the list is not exhaustive and the daemon has latitude.
4. **When in doubt, stay busy.** If steps 1–3 produced nothing the daemon considers worth claiming, it does *not* sleep — it picks something low-stakes to work on (spec notes: "anything else it thought would have the most effect"). Default behavior is active; true idle only happens when the daemon has literally nothing qualified to do.

**Why this shape matters:** the host's explicit phrasing is *"default mode is meant to be an active mode."* Encodes a product principle: daemons earning their keep by doing *something* useful is preferable to daemons sitting idle waiting for perfect work. Leaves room for the daemon's own reasoning on ranking — we don't impose a hardcoded scoring formula.

**What this implies for the backend:**
- `requests` table gets additional signal columns: `upvote_count`, `dependency_refs[]`, `created_at` (for staleness), `improvement_cycle_id` (nullable). Let daemons read and reason, don't pre-bake a ranking.
- Value-vs-effort scoring stays daemon-side. The control plane exposes the raw signals; each daemon applies its own policy (which may itself be improvable over time — this is latitude for the model, not a rule set).
- Active-mode itself is a daemon flag: `always_active` on the `host_pool` row. When off, daemon only runs host-queue work (step 1) and then sleeps.

### §5.3 Multi-daemon spawn policy

> **Retracted 2026-04-24.** Host confirmed: normal operating state is 1 always-on daemon. Multi-daemon is ad-hoc test sessions the host drives via their own chatbot. The "1/provider free, Nth triggers confirmation popup" policy and the payment-tier estimate table are **retired** — do not implement. Host spawns daemons without confirmation friction. The per-tier-2-user daemon-allowance model is a future question for the multi-tenant platform and does not apply to host's own daemon fleet.

~~From the tray notification, the host can launch additional daemons. Baseline policy:~~
~~- **1 daemon per provider is free-to-spawn.**~~
~~- **Nth daemon (N>1) on the same provider triggers a confirmation popup**~~
~~- **Payment-tier estimate table** ...~~

### §5.4 Host-pool state in the control plane

Updated schema incorporating §5.2/§5.3 additions:

```
host_pool(
  host_id PK,
  owner_user_id,
  provider,            # NEW: enum local|claude|codex|gemini|...
  capability_id,       # (node_type, llm_model) pair
  visibility,          # enum self|network|paid
  price_floor,         # null for self|network
  max_concurrent,
  always_active,       # NEW: bool — whether §5.2 cascade runs
  last_heartbeat,
  status               # online|degraded|offline
)

# Separate reference table, editable at runtime
provider_plan_tiers(
  provider,
  plan_name,           # "Free", "Pro", "Team", "Max", "Enterprise"
  monthly_cost_usd,
  approx_requests_per_min_envelope
)
```

RLS: `visibility=self` rows only visible to the owner; `network` rows only visible to owner's network allowlist; `paid` rows visible to everyone. Provider counts per owner are derived by aggregation for the spawn popup.

### §5.5 Dispatch flow

1. User posts a work request via MCP or web app. Request lands in `requests` table with `state=pending`, declared `capability_id`, budget, deadline, and the §5.2 signal columns (upvote_count starts at requester's implicit 1, dependency_refs populated by the node graph, improvement_cycle_id optional).
2. Control plane broadcasts on a Realtime channel `bids:<capability_id>` which qualifying `paid` hosts subscribe to. Each interested host posts a bid row.
3. Bid auction resolves per existing project-memory rules (cheapest matching, no floor on cheap work). When multiple daemons bid equally, the one whose value-vs-effort scoring placed this request highest wins (tie-break by earliest bid timestamp).
4. Winner's daemon polls `/work/{id}/claim`, runs it, streams updates back via a host-outbound websocket.
5. Settlement via ledger.

**Parallel fan-out (§27.5 cross-reference).** A request may declare `fan_out: {mode, count}` (e.g. `top_n` count 10). In that case step 2 allows up to N simultaneous claims; each claimer runs independently; outputs are aggregated by the originator. Scale considerations in §14 (S11 scenario).

### §5.6 Self-only daemons

Answer to host's explicit sub-question: **yes, a user can host daemons for themselves only.** `visibility=self` hosts never appear in the public pool, never receive bids from anyone but the owner, and don't need a public endpoint. The tray UI stays local-first by default; `self` is the install-time default.

Self-only daemons still run the §5.2 active-mode cascade, but steps 2–4 find no eligible work (no paid, no public) and the daemon legitimately idles waiting for host-queue work. That's the one case where idle is the correct answer — because the daemon's visibility explicitly excludes everything beyond the host's own queue.

---

## §6. Paid-market integration

### §6.0 Roles by tier

- **T1 chatbot users** — primarily **requesters**. Place bids, consume output. Fund requests from their ledger balance (purchased via the §6.3 cold-start path).
- **T2 daemon hosts** — primarily **earners**. Accept bids, fulfill work, receive credits. Can also place requests when they want work beyond their own daemon's capability envelope.
- **T3 contributors** — both. Plus potential moderation rep (see §8).

### §6.1 Existing bid model

Integrates with the project-memory bid model (requester sets node + LLM + price; daemons prefer higher bids of matching LLM; no floor on cheap work). Net-new primitives needed on top of §5:

- **Request table** — who posted, what capability, budget, deadline, state (pending | bidding | claimed | running | completed | failed).
- **Bid table** — which host, which request, price, offer-expires-at.
- **Claim semantics** — exactly-one host wins a request. Enforced via Postgres row-level lock + `SELECT FOR UPDATE SKIP LOCKED` pattern.
- **Settlement** — control plane debits requester's ledger balance, credits host's ledger balance on `completed`. Failed work: configurable refund policy (default: full refund for `failed`, partial for `degraded`).
- **Cooperative trust model** — project memory confirms "cooperative, not stranger marketplace." No escrow, no reputation infra until abuse appears.

**No new dispatcher.** The Realtime channel + Postgres `SKIP LOCKED` is the dispatcher. This is a well-trodden pattern; no custom queue broker needed.

### §6.3 Cold-start — superseded by §20

**Superseded by §20 (host directive 2026-04-18, Q6).** Final posture: host commits exactly 1 always-on daemon (their own, their discretion); no reference-host pool commitment; no capacity bounty. Capability-tiered degradation is the sole fallback pattern — unmet demand queues and the chatbot surfaces §20's 4 fulfillment paths (dry-run / free-queue / paid-bid / self-host). See §20 for full treatment.

---

## §7. Auth + identity

**One identity primitive across all three tiers — GitHub OAuth.** This is load-bearing for the tier-migration property in §2.5. A chatbot user's web-app login, the same person's tray install, and the same person's GitHub PRs must all resolve to one user_id or tier migration becomes an account-stitching project.

**Launch: GitHub OAuth + session tokens at the control plane.**
- Low friction for the developer-heavy early adopter base.
- Social-graph hook — public action attribution (PLAN.md §Private chats, public actions) maps cleanly to GitHub identity.
- Supabase Auth ships GitHub OAuth as a first-class provider; zero custom work.
- Session tokens usable from MCP (Claude.ai connector OAuth 2.1 + PKCE) and web app (same backend).

**Claude.ai MCP integration:**
- User adds `tinyassets.io/mcp` as a remote MCP server in Claude.ai.
- Claude.ai walks OAuth 2.1 + PKCE — per MCP spec 2025-11-25 mandate.
- Control plane trusts the MCP session's user_id on all subsequent tool calls.
- RLS enforces per-user visibility at the DB level: a user cannot read another user's private drafts, period, even if the LLM asks nicely.

**When to add native accounts (email/password or passkey):**
- Trigger: > ~15% of landing-page sign-up attempts bounce at the GitHub login wall. Indicates non-developer users showing up.
- Action: add Supabase Auth email/passkey as a second provider. Zero schema migration needed; `auth.users` is polymorphic across providers.

---

## §8. Moderation + abuse response + rate limits — day-one

At thousands of concurrent users, day-one work. Cheapest-viable.

**Who has moderation powers:**
- **Tier-1** — report button only. Cannot hide, cannot delete, cannot ban. High-leverage-low-risk: any user can flag.
- **Tier-2** — reports + **earn-eligible moderation rep** after a threshold (N fulfilled paid requests + M weeks of reliable hosting). Unlocks "triage queue" access in the web app. Not automatic; opt-in; granted by *existing mod* approval (not host-only — see bus-factor note below).
- **Tier-3** — default reviewers for PR-ingest path and for merged-catalog artifacts. Contributor history is public on GitHub, so trust signal is visible.
- **Moderator council (≥2 operators from day one)** — override on any decision. Hard-delete, ban, and role-grant live here. Host is a *member* of this council, not the council's single privileged point. Appeals + "no consensus among mods" escalate to the council, not to the host alone.

**Launch-day-zero composition (Q17 resolution 2026-04-18).** Launch starts with zero real users and zero content, therefore zero real moderation workload. Council at launch-day-zero = **host + user-sim**. This satisfies bus-factor ≥ 2 for the moderation primitive itself (no single-person backstop in the code path) while acknowledging there's nothing real to moderate yet. **No volunteer-mod recruitment drive pre-launch.**

**Organic growth (no recruitment pipeline).** As host invites friends → friends try it → real users arrive, the community-flagged primitives + tier-2 rep-earned mod powers + tier-3 default reviewer role activate naturally. Real humans replace user-sim's bootstrap role as usage scales. The "recruitment plan" is *use the product* — not a formal drive.

**Q15-succession reconciliation.** Q15 requires ≥2 operators with equal privileges from day one (satisfied by host + user-sim at launch). The **hard** milestone — ≥2 *human* operators with equal privileges — binds at **real-currency cutover** per §22, not at MVP launch. See §22.1 row 1 + §22.4 for the full gate list.

**Moderation philosophy — COMMUNITY-FLAGGED (host-locked 2026-04-18, Q10).** Users flag content that violates the commons. Volunteer moderators (tier-3 default + reputation-earned tier-2) review against a rubric. Host-admin is the backstop queue for edge cases and appeals. The platform is NOT minimal-illegal-only (community-policing is on) and NOT proactive/opinionated (no platform-driven takedowns of legal content).

**Moderation API (new primitives):**
- `flag_content(artifact_id, artifact_kind, reason, detail?)` — anyone (including tier-1) can flag. Lands a row in `moderation_flags`.
- `list_review_queue(filter?)` — tier-3 + earn-eligible tier-2 see items with `flag_count >= N_auto_hide_threshold`. RLS gates this view to mod-eligible users.
- `resolve_flag(flag_id, action, rationale)` — mod decision: `upheld_hide`, `upheld_hard_delete`, `dismissed`, `escalate_to_admin`. Writes to `moderation_decisions`.
- `appeal_decision(decision_id, message)` — artifact owner can appeal; escalates to host-admin queue.

**Mechanics:**
- **Per-account rate limits.** Supabase Edge Functions or Postgres triggers enforce: N writes / minute, M bid posts / minute, K node creations / hour. Defaults tuned from launch traffic.
- **Community flag + auto-soft-hide.** Reported artifacts auto-soft-hide after N flags from distinct accounts (default N=3, tunable). Hidden means discovery surfaces mark as `under_review`; content still visible to artifact owner + mods.
- **Volunteer mod review.** Review queue triaged by tier-3 OSS contributors (default role, sign CONTRIBUTING acceptance) and reputation-earned tier-2 daemon hosts. Rubric lives in `moderation_rubric.md` in the `TinyAssets/` repo — contributor-editable, PR-reviewed. Not hardcoded in code.
- **Host-admin backstop.** Appeals + "no consensus among mods after N reviews" both escalate to the host-admin queue. One-person (host) triage at launch.
- **Paid-market as signal.** Spammer accounts get no bids (cooperative trust memory); spam goals never elevate on popularity leaderboards. Economic disincentive is free moderation labor. 1% fee (§18) further soft-rate-limits paid spam.
- **No CAPTCHA at launch.** Add only when account signup spam is observed.
- **No automated content moderation.** Manual triage until volume forces it.

**What we don't do day-one:**
- ML classifiers, content-policy automation, multi-tier moderation hierarchies. Wait for volume.
- Escrow / reputation scoring on the paid market. Project memory: cooperative trust, don't scope until abuse appears.
- **No platform-driven takedown of legal content.** If it's legal and the community hasn't flagged it past threshold, it stays.

---

## §9. Cost envelope

### §9.1 Tier-share assumption

Costs land differently by tier. Rough expected distribution at mature scale:

- **~95% tier-1** (chatbot users). High read volume, moderate write volume, realtime subscriptions. Main driver of DB compute + Realtime connection count.
- **~4% tier-2** (daemon hosts). Lower read volume, moderate write volume, persistent outbound websockets for heartbeat + bid polling. Main driver of websocket concurrency.
- **~1% tier-3** (contributors). Negligible backend load. Main cost is GitHub Actions minutes (free tier likely covers us).

**Cost sensitivity:** Supabase's pricing scales on DB compute + Realtime connections + bandwidth, not tier-labels. So the mix matters mostly through total-concurrent-connection count. 10k DAU × 95% T1 + 4% T2 × typical ~20% concurrent session rate = ~2k concurrent WebSocket subscriptions. Well under Supabase Pro's 10k+ envelope. If the mix flips toward many tier-2 hosts (e.g. dedicated hosting community), concurrent-websocket count grows linearly with daemons-online, not with human users — a structurally cheaper load pattern because daemon websockets are low-chatter heartbeats.

**Upshot:** tier-share shifts don't change the stack pick. Supabase holds for any plausible mix at ≤100k DAU.

### §9.2 Dollar figures

All figures include Supabase Pro + hosting + storage + bandwidth, monthly:

| Users (DAU) | Cost | What drives it | Ceiling concern |
|---|---|---|---|
| 100 | $0 (Free) | Free tier + GitHub OAuth | None |
| 1,000 | $25 (Pro) | Pro plan, compute well under limits | None |
| 10,000 | $50–150 | Realtime connections + storage growth | None |
| 100,000 | $400–800 hosted OR ~€50 self-hosted | DB compute + bandwidth + storage | **Consider self-hosting or migrating to Fly.io + Hetzner if we commit to staying at this scale** |

**Ceiling before re-architecture:** ~100k DAU sustained. Above that, we self-host Supabase on Hetzner or move to dedicated Postgres. Application code doesn't change; only deployment. This is the ceiling-insurance that makes Supabase the right pick over Convex/Firebase.

**Additional costs outside this stack:**
- Cloudflare Free tier — $0 at launch (per uptime design note §3.5).
- GitHub Actions for catalog-export sync — free at our volume.
- Domain + DNS — sunk cost (GoDaddy $89.99/yr).

---

## §10. Build sequencing — one push, not phases

This is an ordering of work within a single-build delivery, not a phased rollout. **MVP is complete when each of the three user tiers works end-to-end: a T1 chatbot user summons a daemon via Claude.ai and collaborates live on a node, a T2 daemon-host user one-click-installs the tray and shows up in the `paid` pool, a T3 OSS contributor clones the repo and PRs a goal that round-trips into Postgres.** Any tier falling short blocks MVP acceptance — tier-share weights are §9.1 concerns, but *all three must function*.

**Parallelizable tracks:**

| Track | Dev | Rough dev-days | Notes |
|---|---|---|---|
| **A — Schema + Auth** | dev | 2 | Postgres schema for catalog + host-pool + requests + bids + ledger + comments + presence. Supabase Auth wired to GitHub OAuth. RLS policies for visibility. |
| **B — Web app (landing + catalog browse + editor)** | dev | 4 | Read catalog, browse by goal/branch/node, create/edit node, comments, presence, fork. Hooks Supabase Realtime for live updates. |
| **C — MCP gateway** | dev | 2 | FastMCP at `tinyassets.io/mcp` wrapping the same backend. Tool surface mirrors the existing `universe` action set, adapted to Postgres writes + RLS. OAuth 2.1 + PKCE for Claude.ai. |
| **D — Daemon host changes** | dev | 2 | Tray's new host-pool registration + capability + visibility toggles. Heartbeat. Bid-polling loop. Deprecate the local MCP as primary surface; keep as debugging tool. |
| **E — Paid-market flow** | dev | 1 | Requests + bids + claim + settlement wiring. Mostly Postgres + Realtime glue. |
| **F — Moderation MVP** | dev | 0.5 | Report button + admin queue + rate limit triggers. |
| **G — GitHub export sync** | dev | 1 | Hourly Action pushes Postgres public-rows to catalog repo as flat YAML. PR-ingest path on the return leg. |
| **H — Cloudflare + DNS + deploy** | host | 0.5 | DNS cutover to Supabase-hosted domain (`tinyassets.io` CNAME to Supabase), TLS, cache rules. |
| **I — Content templates + daemon-brand copy** | dev | 0.5 | Landing page, editor UI copy, "summon the daemon" voice. |

**Sequential dependencies:**
- A blocks B, C, D, E, F, G.
- B, C, D can run in parallel after A.
- E depends on A + D.
- F depends on A.
- G depends on A.
- H can start once A is deployed; doesn't block dev.
- I can run parallel to B.

**Total:** ~13 dev-days serial, **~7–9 dev-days with two devs parallelizing B/C/D after A.**

**Baseline from top of §10:** ~7–9 dev-days with two devs parallelizing. Six honest-revision dev specs (#25 schema/RLS, #26 load-test, #27 MCP gateway, #29 paid-market/crypto, #30 tray, #32 export-sync) plus this design note's design-driven additions have produced a running net addition of **+11.5 dev-days** over baseline — summarized in the per-revision rollup below. Revised totals reflect the reconciled dev-plus-design total, **not** a re-sum over already-absorbed revisions.

**Per-revision rollup:**
- Scale-audit track J (dev #26 revised): +4 dev-days (1.5 → 4 including S1–S6 scenarios).
- Convergent-commons track K: +1–1.5.
- Collab + privacy track L: +1.
- Monetization + cold-start + license track M base: +1.
- Dev #29 paid-market / crypto settlement: +3 on track M.
- Q9 chatbot-native prefs: −0.3 (prefs table retired).
- Q4-follow-up locked (§18.6 hybrid): +0.25 on track M for threshold batcher.
- §21 data portability + wiki-orphan deletion: +0.3 on track M.
- **Q13/Q14/Q15 revision:** +1.25 on tracks A/L/M for multilingual schema + domains multi-tag + merge action + 2-of-3 multisig + secrets-vault migration + `SUCCESSION.md` authoring (see §22.6).
- **Q17/Q18 revision:** +0.3 on track C (MCP gateway) for `/feedback` tool + external-channel placeholders (see §23.6). Q17 nulls out (no recruitment dev-day cost).
- **Q20/Q21 revision:** +1.0–1.5 across tracks J/K/M + infra for auto-healing scenario (S7), auto-rollback + auto-scale + status dashboard, multisig bill auto-pay, `real_world_outcomes` signal + badges + Impact Dashboard, auto-PR / stale / flaky bots + community alert routing (see §25.7).
- **Scenarios A/B/C revision (§26–§30):**
  - §26 invocation + attachment I/O: **+0.5d** on track C.
  - §27 node-authoring-surface (vibe-coding): **+2.5–4d** on new track N — single biggest addition. Full: 4d with tray-REPL + native-PR polish; MVP-narrowed to T1-chatbot-mediated only: 2d (defer T2/T3 polish to v1.1).
  - §28 two-way tool integration (connectors catalog + auth): **+1.5d** on tracks N + C.
  - §29 chatbot behavioral patterns (scope-extension + transparent privacy): **+0.5d** mostly prompts + metadata field.
  - §30 real-world handoff pipeline (arXiv / DOI / GitHub Releases / ISBN + auto-badge): **+1.5d** on track N.
  - §15.1 + §5.2 + §14 parallel fan-out + top-N ranking + S11 scale scenario: **+0.5d** folds into existing cascade + track J.
  - **§18 self-hosted-daemon-no-fee settlement branch:** negligible (≤0.1d) — small conditional in existing settlement pseudocode.
  - **Subtotal (full scope): +7.0–8.6 dev-days.** MVP-narrowed §27 reduces this to +5.0–6.1.
- **A/B/C-follow revision (§26/§27/§29/§31):**
  - §26 three-state onboarding + Claude-catalog State-1 self-connect: **+0.2d** (most of it is catalog-listing ops, near-zero dev).
  - §27 B-follow: T2-lite inline code-view + edit surface at MVP (not deferred): **+1.0d** back on top of MVP-narrowed §27. Revises MVP §27 floor from T1-only to T1+T2-lite.
  - §29 reshape to platform-equips/chatbot-judges model: negligible (~0d, prompt work).
  - §31 new privacy-principles + data-leak taxonomy catalog + MCP access tools: **+0.5d** on track N.
  - §27.1 `/node_authoring.show_code` primitive (diff + full + summary views): **+0.25d**.
  - **Subtotal A/B/C-follow: +1.95d.**
- **Net Δ at full scope: ≈ +22.3 to +24.9 dev-days.**
- **Net Δ at MVP-narrowed §27 (with T2-lite): ≈ +20.3 to +22.4 dev-days.**

**Revised totals:**
- **Full scope: ~29.5–33.5 dev-days w/2 devs, ~35–37 serial.** Stretches "weeks not months" meaningfully — 6.5 weeks at full scope if two devs sustain ~5 dev-days/week net.
- **MVP-narrowed §27 (T1 + T2-lite inline code-view at MVP per B-follow): ~27.5–31 dev-days w/2 devs, ~33–35 serial.**
- **Further defer floors:** track J S1-S5 + S7 + S11 only (skip S6): ~26.5–30d w/2 devs. Defer real-world-outcome badges to v1.1: −0.2d. Defer handoff pipeline §30 to v1.1: −1.5d, but loses Scenario C3 as a launch story. Defer diff-view in `/node_authoring.show_code` to v1.1: −0.25d.
- **Recommendation:** ship MVP-narrowed §27 (T1 + T2-lite) + skip S6 + keep §30 handoffs. Lands around **~26–29.5d w/2 devs** — 5.5–6 weeks at the upper envelope. Host should weigh whether further narrowing is needed or whether 6 weeks is acceptable for the full product surface.

**Launch readiness per §22.4 phase-split:** MVP gates (moderator primitive ≥2-in-code-path via host + user-sim, `SUCCESSION.md` current, secret vault populated, feedback channels in place, auto-healing S7 scenario passing, status dashboard live, Scenario A/B/C acceptance: `Workflow: X` invocation works, at least one vibe-coded node authored end-to-end by user-sim, at least one connector pushes to a real external service, at least one handoff lands in a real validator). Real-currency-cutover gates (human co-signer on multisig, multisig Sepolia-tested, named human moderator, named registrar successor, bill auto-pay policy live) bind at that later milestone, not at MVP launch.

| Track | Dev | Rough dev-days | Notes |
|---|---|---|---|
| **J — Load test harness** | dev | 3.5–4 | **Revised per dev #26 spec (2026-04-18).** k6 scripts against gateway + REST + Realtime; synthetic daemon fleet (Python, ~200 processes per box); Supabase test project; six scenarios S1–S6 (subscriber fan-out, bid storm, cascade read storm, heartbeat steady-state, write-contention on hot node, cold-start end-to-end). Reasonable-defer cuts available if host elects smaller MVP: S1–S5 only = 2 dev-days; skip S6 = 3 dev-days. Parallel with G after A lands. |
| **K — Discovery + remix + convergence** | dev | 1–1.5 | pgvector extension + HNSW index; `discover_nodes` RPC + MCP tool per §15.1; `remix_node` + `converge_nodes` RPCs per §15.3; `similar_subscriptions_index` KV + Edge Function worker; `nodes_hot` materialized view. Depends on A (schema); parallel with B/C/D. Shares the §14.4 `public_demand_ranked` view (no double-build). |
| **L — Dual-layer content + per-piece privacy** | dev | 1 | `concept` / `instance_ref` columns on `nodes`; `artifact_field_visibility` table; concept-layer-only Postgres role + analytics pipeline routing; owner-RLS on instance reads; separate `TinyAssets-catalog/` repo scaffolding + export-Action pointed at it. Depends on A (schema) + G (export sync exists). Parallel with K. |
| **M — Monetization + cold-start + license** | dev | 1 | Base Sepolia test-token contract + treasury address config + 1% fee-split in settlement path (§18); 4-path `submit_request` RPC + `fulfillment_path` enum (§20.4); `content_license` column with default + export-metadata injection (§19); wallet-connect flow (Base Sepolia). Depends on A (schema) + E (paid-market exists). Parallel with K + L. |

**If two devs: land A as a joint push, then dev-1 owns B+E+F, dev-2 owns C+D+G. I and H interleave.**

**Not an excuse for skipping quality:** test coverage, ruff, reviewer gates per AGENTS.md hard rules. The schedule accommodates them.

---

## §11. Host decisions requested

Crisp, answerable. Target: single message back covers them all.

**Q1. Commit to Postgres-canonical, GitHub-as-export?** This is the one-way-door decision from §4. Recommend yes — it's the only shape that satisfies requirements 2 + 3. If host prefers to preserve GitHub-canonical, the whole design rebuilds around a different core.

**Q2. Supabase as the stack?** Recommend yes per §3.2. Alternatives: Convex (TS lock-in), Fly + custom (more dev work), self-hosted Hetzner (cheaper at 100k but heavier ops now). Budget at 10k DAU = $50–150/mo hosted.

**Q3. Real-time = versioned rows + broadcast + presence (not CRDT)?** Recommend yes per §2.2. If host expects character-by-character live editing of shared prose (e.g. "Notion-style shared docs"), revisit — that requires Yjs.

**Q4. GitHub OAuth at launch?** Recommend yes per §7. Native-accounts added when non-developer sign-up bounces exceed ~15%.

**Q5. Moderation day-one is manual (report + admin queue + rate limits)?** Recommend yes per §8. Automated classification deferred until volume forces it.

**Q6. Self-only daemon hosting is the install default?** Recommend yes per §5.4. Public/paid visibility is opt-in, surfaced as tray toggles.

**Q7. Fly.io deferred entirely?** Under this plan, Supabase replaces Fly. No $5/mo Fly spend. Dev-time saved ≈ a day of infra-glue. Confirm — or explicitly prefer Fly + custom realtime for control reasons.

**Q8. Distribution horizon confirmation.** Estimate is ~29.5–33.5 dev-days w/2 devs at full scope (~35–37 serial); ~27.5–31d with MVP-narrowed §27 (T1 + T2-lite per B-follow); **~26–29.5d recommended** (MVP-narrowed §27 + skip S6 + keep §30). ~5.5–6 weeks at upper envelope. Reconciles dev honest-revision specs (#25/#26/#27/#29/#30/#32) with design additions through §31. Confirm, or specify smaller cuts — levers: full §27 vs MVP-narrowed (−~2d), defer §30 handoffs (−1.5d, loses Scenario C3 story), defer real-world-outcome badges (−0.2d), skip S6 or S11 (−1d each), defer wallet + 1% fee to post-launch, defer per-field privacy for per-step only, defer diff-view code primitive (−0.25d). **Process + launch gates per §22.4 + §25 + scenarios + A-follow:** `SUCCESSION.md` current, secret vault populated, feedback channels dogfooded, moderator-primitive ≥2-in-code-path (host + user-sim), auto-healing S7 passing, public status dashboard live, `Workflow: X` invocation works end-to-end for ≥1 seeded node, at least one vibe-coded node authored end-to-end by user-sim via §27 surface with code-view inspected, at least one connector push + one real-world handoff lands in external systems, **Workflow listed in Claude.ai MCP connector catalog (Q21-nav)**. **Real-currency-cutover gates** bind at cutover, not MVP.

**Q9. §5.2 cascade step-3 ranking — daemon-judged or control-plane-suggested default?** Host's directive leaves step-3 multi-factor ranking (popular demand, dependency pressure, staleness, improvement-cycle, "anything else") explicitly to the daemon's judgment. Two options:
- **(a) Fully daemon-judged** — control plane publishes raw signals on each request; each daemon picks its own weighting. Maximum latitude, matches host's language; different daemons may prioritize differently.
- **(b) Control plane publishes a default suggested ranking** (composite score) alongside raw signals; daemons may override. Consistency across daemons without forcing it.
Recommend (a) — matches the explicit "anything else it thought" latitude and avoids baking a scoring formula that the system will rework. If launch observes thrash or unfairness, add (b) as a published default without breaking (a)-style daemons.

**Q10. Pre-launch load-test harness — ship or defer?** §14 scale audit introduces track J (1.5 dev-days) to exercise 1k-subscriber fan-out, 500-daemon bid storm, cascade read storm, heartbeat load. Options:
- **(a) Ship with launch (recommended).** Moves total from ~7–9 to ~8.5–10.5 dev-days with two devs. Discovers contention bugs before real users do.
- **(b) Defer to post-launch.** Launch day is the load test. Undiscovered contention bugs at 10k DAU cold-start = bad first impression, probably unrecoverable for a viral-hook product.
The cost delta is 1.5 dev-days against an outsized risk. Recommend (a). If deferred, flag it explicitly so failure mode is owned, not accidental.

**Q11. Minimum signal set for v1 `discover_nodes` — ship all §15.1 fields or a subset?** The full signal block is 6 quality fields + provenance + active_work + negative_signals + cross_domain flag. Options:
- **(a) Ship the full block (recommended).** Chatbot gets everything in one call; no v2 migration required when we want to upgrade reasoning. Most signals are cheap first-class columns updated by triggers — the marginal cost of adding fields is small.
- **(b) Ship a minimum v1 subset** — semantic_match, structural_match, usage_count, success_rate, upvotes, deprecated flag. Defer fork_count, remix_count, active_collaborators, provenance chain, in-flight improvement cycles, cross-domain flag to v2.
Cost delta (a) over (b): ~0.5 dev-day. Risk of (b): chatbot reasoning is shallower at launch and a v2 schema migration is required once the product-loop signal is in. Recommend (a) for "build the final target, no phases" discipline.

**Q12. Cross-domain recommendations on by default?** Option (a) — on: `discover_nodes` surfaces same-domain matches first, then structural-match-wrong-domain as a separate ranked band in the same response. Chatbot sees "3 good in-domain, 2 structural-match cross-domain" and reasons whether cross-domain is useful for this request. Option (b) — off: cross-domain requires an explicit opt-in flag. Safer default but loses the Wikipedia-scale emergent-pattern property (structural patterns repeat across domains; cross-domain surfacing is where convergence compounds). Recommend (a).

**Q13. §17 per-piece granularity — ship per-field as backbone, or start with a coarser cut?** Per §17.9, three plausible granularities (per-field / per-step / per-example). Options:
- **(a) Ship per-field as backbone (recommended), with per-step and per-example as convenience aggregates layered on top.** Highest precision, supports all three views via the same underlying `artifact_field_visibility` table. Chatbot reasoning overhead is real but paid once per edit, not per read. ~0.5 dev-day added.
- **(b) Ship per-step only for v1**, defer field-level precision to v2. Simpler chatbot reasoning; loses precision on instance-data fields embedded inside a single step. Risk: per-step miscategorizes an instance value that lives inside a step's prompt.
Recommend (a). (b) pushes a schema migration into v2 and re-trains user expectations mid-product — worse than paying the cost now.

**Q14. Training-data exclusion enforcement — separate Postgres role or trust-based tagging?** §17.4 proposes a dedicated Postgres role with column-level permissions that literally cannot SELECT private fields. Options:
- **(a) Separate-role enforcement (recommended).** Any analytics/recommendation/ML query runs as the restricted role. Violations are permission errors, not silent leaks. Hard structural guarantee.
- **(b) Trust-based tagging.** Private fields carry `training_excluded=true`; queries that touch them are supposed to respect the flag. Cheaper but one missed WHERE clause = silent leak.
Recommend (a). Cost delta is ~0.5 dev-day to set up role + policies. The product promise "not training data, not collected, not at risk" is a load-bearing commitment; structural enforcement makes it credible.

**Q15-treasury — REFRAMED 2026-04-18 (Q15 succession directive).** Prior "deferred governance" label too loose in light of Q15's succession requirement. New posture:
- **Testnet treasury:** host-controlled address on Base Sepolia is fine — test tokens have no real value, no succession risk.
- **Real-currency treasury:** **MUST be at least 2-of-3 multisig at cutover.** Cannot launch a real-currency treasury as a single host-controlled address — violates the "system is always up without us" hard requirement (Q15). Multisig keys held by host + ≥2 named co-signers (moderator-council members per §8, or dedicated treasury signers per §22 runbook). DAO governance revisit remains deferred; 2-of-3 multisig is the floor.
- **Depth of governance** (beyond 2-of-3 multisig — DAO, elected council, protocol-level voting) is still deferred; re-opens at maturity. But the multisig floor is not deferrable.

**Q15-depth — DEFERRED (governance layer above multisig).** Kept in §11 with explicit DEFERRED tag; re-opens when TVL or community scale suggests multisig is no longer enough.

**Q16 — RESOLVED 2026-04-18 (workflow-content license = CC0 1.0).** Host pinned CC0 as the literal reading of "completely open" — no restrictions, no share-alike. Platform code stays MIT. §19 updated; schema default `content_license = 'CC0-1.0'`.

**Q4 follow-up — RESOLVED 2026-04-18 (hybrid settlement).** Host locked hybrid threshold: bids <$1 equivalent batch, bids ≥$1 settle on-chain per-bid. Threshold is config (`settlement_threshold_usd`). §18.6 updated with full pseudocode. Track M estimate: +1.25 dev-days.

**Q10-host — RESOLVED 2026-04-18 (community-flagged moderation).** Users flag, volunteer moderators (tier-3 default + rep-earned tier-2) review against rubric, host-admin backstop. Not minimal-illegal-only; not proactive-opinionated. Rubric lives in `Workflow/moderation_rubric.md` (PR-editable). §8 updated with `flag_content` / `list_review_queue` / `resolve_flag` / `appeal_decision` primitives.

**Q11-host — RESOLVED 2026-04-18 (no platform age-gate).** Transitive reliance on chatbot provider age-gating. No signup age field, no KYC. ToS clause added in §19.6 ("you must meet your chatbot provider's age requirements"). Direct-web-app-only fallback uses US-minimum-13 per COPPA.

**Q12-host — RESOLVED 2026-04-18 (open export + wiki-orphan deletion).** `export_my_data` returns everything the user owns; `delete_account` nullifies per-user columns, orphans public contributions to `anonymous`, hard-deletes instance blobs, preserves provenance + derivatives. Wikipedia model. New §21 details both RPCs + schema + anti-abuse.

**Q13-host — RESOLVED 2026-04-18 (multilingual from day one).** `primary_language` on nodes, `artifact_field_variants` table for optional per-language translations, per-language FTS views, chatbot translates at read time. §15.7 full spec.

**Q14-host — RESOLVED 2026-04-18 (permissionless domains).** Anyone coins a domain in the moment. `domains` table (lazy, GC'd), `nodes.domain_ids uuid[]` multi-tag. Community `merge_domains` action for dedup. No approval workflow. §15.8 full spec.

**Q15-host — RESOLVED 2026-04-18 (host-independent succession — hard requirement).** Bus factor ≥ 2 at launch across moderation / treasury / registrar / secrets / deployment / merge-rights / bill-paying. 2-of-3 multisig mandatory at real-currency cutover (testnet stays host-controlled). `SUCCESSION.md` runbook in repo root. Co-maintainer recruitment is a launch-readiness gate, not post-launch. New §22 full spec.

**Q17-host — RESOLVED 2026-04-18 (no volunteer-mod recruitment at launch).** Navigator's earlier Q17 (name co-maintainer pre-MVP) is **retired** — it was an over-extrapolation from Q15, not a host requirement. Correct posture: launch-day-zero moderator council = host + user-sim; real second-human operator binds at real-currency cutover, not MVP launch. Recruitment follows organic use. See §22.4 phase-split and §8 launch-day-zero composition.

**Q18-host — RESOLVED 2026-04-18 (feedback channels A/B/C).** A: GitHub Issues primary. B: in-chatbot `/feedback` MCP tool secondary (opens GitHub Issue). C: Discord/Reddit/email tertiary. User-sim dogfoods all three in standing loop. New §23 full spec. `/feedback` tool lands in dev's #27 gateway track as a standard `tools/*` primitive.

**Q20-host — RESOLVED 2026-04-18 (always-up posture).** "Nothing is broken; issues auto-fixed on the fly." Self-healing primitives (auto-rollback, auto-scale, circuit-break), auto-deploy on green-CI, community-visible monitoring, auto-maintenance bots, treasury wallet auto-pays bills. No host-only buttons. New §25 full spec + track J S7 rehearsal scenario.

**Q21-host — RESOLVED 2026-04-18 (real world effect engine — product soul).** Platform's north star: real deliverables (books published, papers peer-reviewed, tasks completed, projects shipped). Fail-state: gimmicky/toy. Cascades: outcome-first marketing copy, utility-leaning domains, `real_world_outcomes` signal block in `discover_nodes`, impact-first tier-2 UX, badges + verification pipeline, serious-utility aesthetic. New §24 full spec. §1 preamble updated to lead with the product-soul statement.

**Q18-nav — OPEN (node-primitive authoring API — §27.8 raised).** The chatbot needs a concrete language/API to declare state, tools, graph, composition for vibe-coded nodes (§27). Options:
- **(a) Python IR, sandboxed in Edge Function.** Matches platform toolchain; most expressive; largest attack surface; heaviest sandbox engineering.
- **(b) WASM with a typed SDK.** Safer sandbox; steeper authoring curve for chatbot to emit; need a binding surface.
- **(c) JSON-schema-driven IR interpreted by the platform.** Safest; simplest sandbox; most-constrained expressiveness (harder to vibe-code the "max super nerd" long tail).
Recommend (a) Python-sandboxed — best fit for Scenario B's "full primitive" directive, matches the Python-stack the rest of the platform already uses, sandbox engineering cost absorbed by track N §27.8 estimate. (c) is the safer fallback if host wants to strictly cap the "max super nerd" capability at launch.

**Q19-nav — REVISED 2026-04-19 per B-follow (§27 MVP scope).** Prior recommendation of T1-chatbot-mediated-only is **revised**. B-follow is explicit: "real nerds can actually edit the code if they want to" — at day one, not v1.1. Revised recommendation: **T1 + T2-lite at MVP.** T2-lite = inline code-view + edit inside the chatbot window (the `/node_authoring.show_code` primitive from §27.1), not a full local REPL. Adds ~1d back to track N; full local REPL + native-code polish still defer to v1.1. Gives "real nerds drop into code" from day one without the full T2 engineering cost.

**Q20-nav — REVISED 2026-04-19 per A-follow (launch connectors + connector-catalog listing).** §28.2 tier-1 launch connectors remain: GitHub, Gmail/SMTP, Google Drive / Dropbox / S3, Notion. Voyager and other vertical-specific tools are community-contributed post-launch. **The primary A-follow-added surface is Workflow's listing in Claude.ai's connector catalog (Anthropic MCP directory) — this is a separate, load-bearing launch gate** flagged as Q21-nav below. Host confirm connector list or amend.

**Q21-nav — OPEN (Claude.ai connector catalog listing — launch gate).** A-follow 2026-04-19: State-1 users (no connector yet) discover Workflow via Claude.ai's connector catalog. This makes catalog listing a launch-readiness gate, not a nice-to-have. Actionable asks:
- What's Anthropic's submission process for the MCP connector directory? Is it a form, a PR to a registry repo, a review pipeline?
- What's the expected timeline from submission to listing?
- What are the requirements (technical: OAuth 2.1 compliance, MCP spec version, uptime SLA; descriptive: metadata, icons, copy)?
- Does host or navigator own this research — or assign to dev with an ops-focused sub-task?

Recommend navigator investigate in parallel with continued platform build; findings inform whether launch date is submission-blocked or ship-then-list. Flag unblockers immediately if the submission process has ≥2-week lead time.

**Q22-nav — OPEN (code-visibility-in-chat primitive — confirm MVP scope).** Per B-follow, the `/node_authoring.show_code(view='full'|'diff'|'summary')` primitive ships at MVP. §27.1 codifies this. Open sub-question: does the chatbot get a *diff* view distinct from *full* view at launch, or is diff view a v1.1 addition? Diff view adds ~0.25d. Recommend include diff view at MVP — co-design iteration quality drops significantly without it.

**Q23-nav — OPEN (privacy-principles catalog launch scope).** Per C-follow + §31.3: recommend ~12 entries covering load-bearing system points at MVP (list in §31.3). Host confirm scope, or authorize navigator to draft the v1 catalog entries based on the §31.3 list.

**Q24-nav — OPEN (three execution specs not yet drafted, flagged by drift audit #64).** Three tracks referenced in §27 / §28 / §30 have no corresponding `docs/specs/*.md` yet:

- **Track N — vibe-coding node authoring surface + sandbox runtime (§27).** Includes `/node_authoring.*` MCP tool family, sandboxed Edge-Function-based draft runtime, `/node_authoring.show_code(view)` primitive (B-follow), parallel fan-out orchestration. Blocks §27 MVP launch. Estimate ~2.5–4d full / ~2d MVP-narrowed — already absorbed in §10.
- **Connectors track (§28).** `ConnectorProtocol`, launch-tier connector bundle (GitHub, Gmail, Drive, Notion), OAuth/consent flow, webhook-generic fallback. Blocks §28 MVP launch. Estimate ~1.5d — already absorbed in §10.
- **Handoffs track (§30).** Handoff-kind connector protocol with auto-outcome-claim side effect, launch-tier handoffs (arXiv, CrossRef DOI, GitHub Releases, ISBN-US), auto-badge + outcome verification pipeline. Blocks §30 MVP launch. Estimate ~1.5d — already absorbed in §10.

Recommend dispatching these three to dev as pre-draft spec tasks (parallel to existing track K/L/M specs). Each produces a `docs/specs/<date>-<name>.md` with schema/RPC/flow detail similar to specs #25/#27/#29.

Preserved from the prior note and sharpened against the new shape:

- **Does not introduce a multi-tenant daemon runtime.** Daemon execution stays on opt-in hosts. The control plane dispatches, it does not execute.
- **Does not centralize universe content.** Canon uploads, KG, vector indexes, notes.json remain host-local by default for execution. Published artifacts snapshot to Postgres (for browse) + export to GitHub (for clone).
- **Does not replace Claude.ai as the chat UI.** Claude.ai is still the primary chat surface. The web app is for authoring/browsing, not chat.
- **Does not break the "main is always downloadable" principle.** The repo still installs cleanly; the Supabase backend is a separate deployable, and running daemons against the public control plane is a config switch.
- **Does not end the GitHub-as-catalog export.** Clone-and-run still works for users who want it. It just isn't the canonical store.
- **Does not ship character-by-character live editing.** Out of scope until an artifact type emerges that needs it.
- **Does not ship federation across hosts.** Single control plane for launch. Multi-host federation is a v2+ architectural change when/if it becomes needed.
- **Does not ship escrow or reputation infrastructure on the paid market.** Cooperative trust model until abuse appears.
- **Does not implement fiat billing.** Crypto-native from day one (§18). No Stripe, no credit-card, no fiat settlement.
- **Does not introduce subscription tiers or premium feature gating.** Platform is fully free; only the paid-market bid is a paid surface (§18).
- **Does not custody user funds.** Wallet-connect only; balances live in user-owned wallets. Settlement-window custody is the only platform-side hold.

---

## §13. Onboarding per tier

All three paths must stay healthy simultaneously. "Main is always downloadable" (PLAN.md §Distribution) applies across all three.

### §13.1 Tier-1 — Chatbot user (zero-install)

**Entry:** tinyassets.io/ landing page. One primary CTA.

1. Read the hero ("Summon the daemon.") + 3-step how-it-works.
2. Click **"Connect Claude.ai"** → opens a setup page with a one-line copy-paste: `https://tinyassets.io/mcp` as the MCP remote URL.
3. Completes OAuth 2.1 + PKCE flow (Claude.ai handles this natively in 2026).
4. Back in Claude.ai chat, user says "summon me a daemon for a research paper"; the MCP tool creates the goal, branches list populates, web app surfaces it in realtime if open.

Friction budget: < 60 seconds from landing to first tool call. No downloads, no dependencies.

### §13.2 Tier-2 — Daemon host (one-click install)

**Entry:** from the web app, "Host a daemon" button (visible to signed-in T1 users who haven't yet). Or direct link `tinyassets.io/host`.

1. User clicks "Download tray" → serves the platform-native installer (MCPB bundle via Claude Desktop's distribution, or direct installer).
2. Installer runs; first launch opens the tray's OAuth flow against `tinyassets.io/authorize` — **same account** as their web app login (no new account).
3. Tray registers host with default `visibility=self` on all capabilities the host's hardware can declare.
4. User flips toggles to opt into `network` or `paid` as they choose. Optional: one-time tax/banking setup for `paid` earnings.

Friction budget: < 5 minutes from "Host a daemon" click to tray-online + at least one declared capability.

**Must work:** Windows + macOS + Linux. Packaging is production-ready from day one; install failures are production bugs (project memory: `feedback_always_install_ready.md`).

### §13.3 Tier-3 — OSS contributor (git clone)

**Entry:** `github.com/<org>/Workflow` → README → CONTRIBUTING.md.

1. `git clone` + `pip install -e .[dev]`.
2. Read `AGENTS.md`, `PLAN.md`, `STATUS.md` (standing docs).
3. Run tests (`pytest` + `ruff check`).
4. Pick a pending task from STATUS.md Work, or propose a goal/branch/node via PR against the catalog export (round-trips into Postgres per §4).

Friction budget: < 15 minutes clone-to-green-tests on a fresh machine.

**Must stay healthy:** CI runs the full test suite on PRs. Import-probe + plugin-drift check per existing packaging protocol. Fresh-install smoke is part of the Work table going forward.

### §13.4 Shared property: no tier is a second-class citizen

- T1 is the default surface; copy, UX, docs lead with it.
- T2 is discoverable from T1 at the moment a user wants hosting; not a separate product silo.
- T3 is discoverable from GitHub + a "Contribute" footer link on the web app; not gated behind a T2 prerequisite.

**Design pathology to avoid:** "We'll build T1 now, add T2 later, document T3 eventually." All three ship together. Any one falling out of health (stale contributor docs, broken installer, landing-page drift) degrades the viral hook.

---

## §14. Scale audit — "thousands concurrent, none are this computer"

**Framing:** every test so far has been 1 daemon + 1 universe on a single laptop. The design above was built for correctness; this section stress-tests it at the host's target scale (thousands of concurrent users and daemons, none of them local). Each hotspot states: the failure mode at scale, the fix, whether §2–§13 already covers it, and what (if anything) changes in §10 or §11.

### §14.1 Bid-inbox contention

**Failure mode.** Thousands of daemons all polling `requests` with `SELECT FOR UPDATE SKIP LOCKED` on every cascade cycle causes severe CPU thrash. Documented Postgres scaling cliff: `SKIP LOCKED` begins degrading around ~128 concurrent workers and spikes CPU to 100% across multiple cores before 1k ([postgrespro thread on CPU hog](https://postgrespro.com/list/thread-id/2505440)). The naïve "every daemon polls every second" pattern is broken at our target scale.

**Fix — subscription-push + narrow claim.**
1. Each daemon subscribes to a Supabase Realtime channel `bids:<capability_id>` for each capability it serves. Capability-sharded channels — a daemon hosting `goal_planner×claude` only gets pushes for that exact matching request.
2. Control plane INSERTs into `requests` → Realtime broadcasts the row to subscribers. No polling storm.
3. Interested daemons call a `claim_request(request_id)` RPC that wraps `SELECT ... FOR UPDATE SKIP LOCKED ... RETURNING id`. Only daemons that want to claim hit the lock, not the full population.
4. Loser daemons see claim fail → continue cascade. No retry storm on failed claim; daemon moves on to step 3.

This collapses contention from "all daemons lock-scanning all rows" to "only interested daemons attempt claim, one row at a time." SKIP LOCKED now runs well inside the ~128-worker envelope because the workers-per-row count is bounded by `daemons-matching-that-capability`, typically single digits.

**§5.2/§5.5 sharpener.** Current text mentions SKIP LOCKED and "broadcasts on a Realtime channel"; it does not explicitly state channel sharding-by-capability or the claim-RPC pattern. Added as a §5.5 amendment: *dispatch is push-via-capability-channel, claim-via-RPC, never poll-all*.

### §14.2 Realtime websocket ceiling

**Failure mode.** Supabase Pro's Realtime envelope is ~500 concurrent connections soft-included; overage at $10 per 1,000 peak connections ([Supabase Realtime pricing](https://supabase.com/docs/guides/realtime/pricing), [Realtime limits](https://supabase.com/docs/guides/realtime/limits)). At 10k DAU × ~20% concurrent-session rate + N daemon hosts, projected connection count:

| DAU | T1 concurrent | T2 daemons online | Total sockets | Overage cost |
|---|---|---|---|---|
| 1k | ~200 | ~40 | ~240 | $0 |
| 10k | ~2000 | ~400 | ~2.4k | ~$20/mo |
| 100k | ~20k | ~4k | ~24k | ~$240/mo |

**Fix — channel partitioning + broadcast, not per-row subscriptions.**
- **Per-universe channels** for write-events. A user viewing universe X subscribes to `universe:X` — not to the full `nodes` table. Channel count scales with *active universes*, not DAU.
- **Per-capability channels** for bid push (§14.1). Channel count ≈ distinct `(node_type, llm_model)` pairs across hosts — bounded at ~low hundreds.
- **Supabase Broadcast for ephemeral events** (presence pings, typing indicators) — Broadcast is cheaper than Postgres change-data-capture and does not stress the DB. Use Broadcast for anything that doesn't need durable write.
- **Presence aggregates, not enumerates.** "3 users editing" not "Alice, Bob, Carol editing" over the wire — stays under Presence's payload envelope.

**Cost impact.** $20/mo overage at 10k DAU folds into §9 band ($50–150). $240/mo at 100k DAU folds into $400–800 hosted band. No re-architecture triggered below 100k DAU.

**§2/§9 sharpener.** Current §2.3 diagram shows "WebSocket subscriptions" generically. Added §14.2 note: channel sharding must be **per-universe + per-capability**, not per-row. §9.1 tier-share numbers preserved.

### §14.3 Write contention on hot nodes

**Failure mode.** Popular node X gets simultaneous edits from 50 users under versioned-rows + LWW. Last-write-wins silently discards 49 edits. Users see their work vanish.

**Fix — optimistic concurrency with version tokens + active-editor soft-lock.**
- Every writable row carries `version` (monotonic int) + `updated_at`. Writes use `UPDATE ... WHERE id=X AND version=<token>` → zero rows affected = conflict.
- On conflict, client gets `{"error": "conflict", "current_version": N, "current_row": {...}}` and re-applies edit atop the new baseline. No lost writes.
- **Soft active-editor lock** via Supabase Presence: when a user opens the editor, they broadcast `editing:<node_id>` presence. Other viewers see "Alice is editing" and can either wait, open a view-only mode, or fork. Lock expires on Presence timeout (~30 s after tab close). Advisory only — it discourages collision rather than enforcing.
- **No CRDT.** The soft-lock + optimistic-CAS gives us collision-aware UX without the CRDT substrate. For the ~99.5% case where only one person edits a given node at a time, it's free. For the 0.5% collision case, users see a merge prompt instead of silent loss.

**§2.2 sharpener.** Current text says "last-write-wins + update-since-you-viewed warnings." Made explicit in §14.3: CAS with `version` column + Presence-based soft-lock. Added to schema in §5.4 as `version BIGINT NOT NULL DEFAULT 1` on all writable rows.

### §14.4 Cascade step-3 ranking cost

**Failure mode.** Every daemon finishing a node re-queries the public-request queue, sorting by `upvote_count + dependency_refs[] + improvement_cycle_id + staleness`. At N daemons × average cascade rate, this is N reads/min across the full public-demand table. Read-storm on a join-heavy query.

**Fix — materialized view, refreshed every 30–60 s.**
- `public_demand_ranked` materialized view precomputes the composite signals + a default ranking. Daemons scan this view, cheap reads.
- View refresh is a cron (Supabase pg_cron or Edge Function) every 30–60 s. Staleness that small is invisible at cascade cadence.
- Per-capability partitioning within the view: daemons only read `WHERE capability_id IN (their_capabilities)`. Index backs the filter.
- Raw signal columns stay on `requests` for daemon-side override (§5.2 "anything else it thought" latitude). View is a convenience, not a gate.

**§5.2 sharpener.** Current text says "daemons read raw signals and reason"; that's still correct for step-3 latitude. Added §14.4 note: materialized view is the efficient default read path; daemons may drop to raw reads when they want to apply custom scoring.

### §14.5 Host-directory heartbeats

**Failure mode.** 10k daemon hosts × 60s heartbeat = ~167 writes/second to `host_pool.last_heartbeat`. Index maintenance + WAL pressure on a hot column. Not catastrophic but wasteful.

**Fix — TTL KV for ephemeral state, Postgres for durable.**
- **Durable state** (`host_pool` row: owner, capabilities, visibility, price_floor, always_active) stays in Postgres. Rarely changes.
- **Ephemeral state** (`last_heartbeat`, `status`, current load) moves to a TTL-keyed store: Supabase's built-in Presence (server-side) OR an Upstash Redis attached via Edge Function. Heartbeats write to KV with 90-s TTL; absence of key = host offline. No DB write on heartbeat.
- Control plane joins Postgres + KV at query time for dispatch: `SELECT host_pool WHERE id IN (SELECT online_host_ids_from_kv)`.

**Supabase Presence is a viable primary candidate** — it already maintains per-connection presence state server-side, expires on disconnect, and is free within the Realtime envelope. No extra vendor.

**§5.4 sharpener.** Schema table split: `host_pool` = durable, `last_heartbeat` column removed; online status derived from Presence. Added to §5.4 as a schema update.

### §14.6 GitHub export-sink cadence

**Failure mode.** Hourly YAML push to catalog repo: once public-goal count exceeds a few hundred, an hourly full-snapshot push churns huge diffs. At 10k DAU producing N goals/day → growing diff per hour → GitHub API rate limits (5k/h authed) and repo-size bloat.

**Fix — diff-only incremental push + bounded cadence.**
- GitHub Action runs every N minutes (not every push). Computes diff against last-pushed SHA at the row level — only changed artifacts serialize and stage. Small diffs, cheap commits.
- Soft-bound commit cadence: at most one commit per 5 minutes, batching changes. Rate-limit buffer: 5k/h authed budget vs ~12 commits/h worst case — zero risk.
- If the Action detects "too many changes in window" (e.g. >500 artifact changes in 5 min, suggesting a bulk import event), it collapses to a single squash commit rather than 500 row commits.

**No re-architecture.** Export sink holds to 100k DAU. Above that, sharding the catalog repo (per-Goal sub-repos, or a dbt-style per-author federation — see `github_as_catalog.md` §1) becomes interesting.

**§4/§10 sharpener.** Current §4.1 says "hourly or on-demand"; specified in §14.6 as *diff-only every 5 min, batched*. Adds ~0.25 dev-day to track G estimate.

### §14.7 Moderation at scale

**Failure mode.** §8 as written scopes MVP at ~0.5 dev-day (report button + admin queue + rate limits). At 10k DAU with a live paid market, abuse vectors that 0.5-day scope can't absorb: low-effort spam goals flooding the leaderboard, sock-puppet upvote rings manipulating step-3 ranking, scam paid-requests ("do X, never pay").

**Honest audit.**
- Report + admin queue survives — that's structural, scales with moderator count not DAU.
- Per-account rate limits survive — Postgres triggers are O(1).
- **Tier-3 contributor + threshold-gated tier-2 triage** (§8.1 as updated in the tier fold) earns moderation labor. Scales with community size.
- **Paid-market-as-signal** breaks down for sock-puppet upvote rings. The cooperative-trust project memory assumes GitHub identity is hard to fake at scale; it isn't for low-effort attackers.

**Fix — add a §8.1 backstop primitive: account-age + first-activity gates.**
- Upvote + place-request require account-age ≥ N days OR N completed interactions (threshold tuned empirically). Cuts sock-puppet throughput without blocking real new users (web app onboarding guides a new user through 1–2 interactions in first visit).
- Scam-request defense: ledger balance *reserved* at request-post, released to host on completion. Auto-refund on failure. (This is already the §6.2 settlement primitive — just calling it out as moderation-adjacent.)
- Heuristic "new account + high upvote volume" flag for human review. Not an ML classifier, just a cron-driven anomaly alert.

**Cost:** +~0.25 dev-day on top of §8's 0.5. Total moderation MVP ≈ 0.75 dev-day. Folds into existing §10 track F.

**§8 sharpener.** Added §8.2 "backstop primitives" covering account-age gate + ledger reservation + anomaly flag.

### §14.8 Test infrastructure gap

**Failure mode.** Zero concurrent-load coverage today. Everything tested with 1 daemon + 1 universe. At launch, a single cold-start week at 10k DAU with undiscovered contention bugs = catastrophic first impression.

**Fix — minimum load-test stack before launch.**
- **k6** ([Grafana k6](https://k6.io/)) — JavaScript load scripts against the MCP gateway + REST + Realtime. Proven at 10k+ concurrent users per test.
- **Synthetic daemon fleet** — Python script spawning N headless daemon processes against a Supabase test project. Simulates N hosts bidding, claiming, heartbeating. Run on a single box (each synthetic daemon is ~50 MB; 200 fit in 10 GB RAM), or spread across a small cluster if we want >500.
- **Supabase test project** — separate Supabase project from production. Realtime + DB schema mirrored via migration. ~$25/mo while in use, pause when idle.
- **Test scenarios required before launch:**
  1. 1k concurrent T1 subscribers on a single hot universe. Assert no missed events, no >2s broadcast lag.
  2. 500 concurrent daemons polling bid channel during request storm (1k requests in 5 min). Assert dispatch latency p99 < 3s, no lost requests.
  3. Cascade read-storm: 200 daemons simultaneously refreshing step-3 view. Assert materialized view refresh unblocks, no lock thrash.
  4. Heartbeat load: 1k Presence heartbeats/minute steady-state. Assert no connection churn.

**Cost:** new track **J** in §10, ~1.5 dev-days (k6 scripts + synthetic daemon harness + test scenarios + run-and-tune). Paralleleable with G after A lands. Not MVP-blocking in the "can we ship" sense, but MVP-blocking in the "can we ship *safely*" sense.

**§10 estimate revision:** track J is revised to 3.5-4 dev-days per dev #26 spec (six scenarios S1-S6 including write-contention + cold-start scenarios beyond §14.8's original four). Defer options: S1-S5 only = 2 days; skip S6 only = 3 days. Recommendation unchanged — ship S1-S5 minimum before launch; skipping load tests entirely means launch day is the load test.

### §14.9 Other scale assumptions I found

Quick scan for "this works because there's one of everything":

- **Active-universe lock / singleton assumptions in existing `tinyassets/universe_server.py`.** Current codebase has singleton patterns (SqliteSaver, LanceDB singleton per hard rule) that assume one process. Multiple daemon hosts = no shared process; each host keeps its own singletons — this is already correct per PLAN.md §Local-first. No change.
- **Ledger consistency across thousands of concurrent settlements.** Postgres transactional guarantees cover this. Settlement = single row UPDATE + single INSERT in a transaction. Safe at any scale.
- **MCP session fan-out.** Each Claude.ai MCP connection is one streamable-HTTP connection to the gateway. Gateway is stateless (sessions in Postgres). Horizontally scalable — Supabase's Edge Functions or a separate Fly/Hetzner gateway-box fronting Supabase absorbs this if the hosted gateway becomes the bottleneck. Not an issue below 10k DAU.
- **GitHub OAuth rate limits.** App-level OAuth has 5k/h per client. 10k DAU × ~1 OAuth handshake/day = 10k/day = well within envelope. Token refresh at background rates is similarly fine.
- **Cloudflare Cache Rules.** Free tier 10 rules unchanged. 3 in use (static, `/catalog`, `/mcp` bypass). 7 headroom.
- **Canon blob uploads.** Privacy-tier `confidential` never uploads; `public/internal` go to S3-compatible storage via Supabase Storage. Per-upload size cap + per-account storage quota both enforceable in Supabase. No scale concern.

---

### §14.10 Summary of what changed

**Covered by existing design (no change required):**
- Ledger consistency (Postgres transactions).
- MCP session fan-out (stateless gateway).
- GitHub OAuth rate limits.
- Cloudflare Cache Rules.
- Canon uploads.
- Postgres singletons on hosts.

**Sharpeners added to existing sections:**
- §5.2/§5.5 — dispatch via per-capability Realtime channels + claim RPC, not poll-all.
- §2.2/§14.3 — optimistic CAS with `version` column + Presence-based soft-lock. Added `version` field to schema.
- §5.2/§14.4 — materialized view `public_demand_ranked` for cascade step-3.
- §5.4/§14.5 — heartbeats move to Presence/KV, `last_heartbeat` column removed.
- §4.1/§14.6 — export sink: diff-only, ≤12 commits/h.
- §8/§14.7 — backstop primitives: account-age gate, ledger reservation, anomaly flag.

**New work added to §10:**
- Track J: load-test harness (k6 + synthetic daemon fleet + Supabase test project). +1.5 dev-days.
- Track G moderation +0.25 dev-day for backstop primitives.
- Track G export sync +0.25 dev-day for diff-only batching.

**§10 revised estimate:** ~8.5–10.5 dev-days with two devs parallelizing (up from 7–9). ~15 dev-days serial (up from 13). Still "weeks not months."

**§11 additions:** one new Q, below.

---

## §15. Node discovery + remix surface

**Framing.** At scale, workflow design is a public convergent effort. Hundreds of users talk to their chatbots concurrently; the chatbot reasons on the fly about *use-existing vs remix-from-N vs design-mostly-new vs design-from-scratch*. That reasoning stays in the chat — the platform's job is to surface the data the chatbot needs, fast and comprehensive, in one call. Convergence is the norm, not the edge case. Canonical stress-test domains: research-paper workflows + open-fantasy-universe workflows (both are hierarchical, many-contributor, forkable-branch, clear quality signals, long time horizon).

**What this section does:** specifies the chatbot-facing discovery RPC, the indexes that back it, the convergence primitives (real-time "similar in-progress", remix-from-N, converge), and the integration with §5 cascade + §14 scale primitives.

### §15.1 Chatbot data contract — the discovery RPC

**One call returns everything the chatbot needs to reason.** Avoid N follow-ups. Name the RPC `discover_nodes` at `tinyassets.io/mcp` (also exposed as REST `POST /v1/discovery/nodes`).

**Request:**
```
discover_nodes(
  intent:         str            # natural-language description of what the chatbot is trying to build
  input_schema:   jsonish?       # optional: expected node-input shape
  output_schema:  jsonish?       # optional: expected node-output shape
  domain_hint:    str?           # optional: "research-paper", "fantasy", etc.
  limit:          int = 20
  cross_domain:   bool = True    # surface structural matches outside domain_hint
  include_wip:    bool = True    # surface in-progress nodes not yet committed
)
```

**Response — ranked candidates, each with full signal block:**
```
{
  "candidates": [
    {
      "node_id", "slug", "name", "domain", "status",
      "semantic_match_score",      # 0-1, cosine similarity on intent embedding
      "structural_match_score",    # 0-1, input/output schema + graph-shape compat
      "quality": {
        "usage_count",             # times invoked by any daemon
        "success_rate",            # completed vs. failed outcome
        "upvote_count",
        "active_collaborators",    # distinct editors last 7 days
        "recency",                 # days-since-last-edit
        "fork_count",
        "remix_count"              # times used as parent in remix-from-N
      },
      "provenance": {
        "parents":  [node_id, ...],  # direct lineage
        "children": [node_id, ...]   # direct derivatives (limited to top-N)
      },
      "active_work": {
        "editing_now":            int,  # Presence count
        "pending_requests":       int,  # open requests referencing this node
        "in_flight_improvement_cycle_id": uuid?  # if part of an open redesign
      },
      "negative_signals": {
        "deprecated":             bool,
        "known_failure_modes":    [str, ...],
        "contradictory_goal_ids": [uuid, ...]
      },
      "cross_domain": bool,         # true if match is outside domain_hint
      "typical_fulfillment_pattern": {
        "dry_run_pct":   float,     # fraction of past requests for this node fulfilled via §20 path 1
        "free_queue_pct": float,    # §20 path 2
        "paid_bid_pct":   float,    # §20 path 3
        "self_host_pct":  float,    # §20 path 4
        "sample_size":    int       # how many settled requests informed the pattern
      },
      "parallel_eligible": bool,    # node supports §27.5 fan-out (deterministic outputs, idempotent)
      "top_n_rank": int?,           # rank within its primary domain when query mode is "top N" (§26.1)
      "real_world_outcomes": {      # §24.4 — full field spec there
        "published_count":      int,
        "peer_reviewed_count":  int,
        "production_use_count": int,
        "citation_count":       int,
        "verified_count":       int,
        "last_outcome_at":      timestamptz,
        "badges":               [str, ...]
      }
    }, ...
  ],
  "query_id": uuid                  # for §15.3 "notify-me-on-similar" subscription
}
```

**Why each field earns its cost:**
- `semantic_match_score` — chatbot's first filter; purpose alignment.
- `structural_match_score` — separates "looks similar" from "drops in where I need it."
- `quality.*` — chatbot's "is this trustworthy" signal block. Six fields because each captures a different risk axis (popularity ≠ quality; fork count ≠ success rate).
- `provenance` — "is this derived from X I already trust, or from scratch?" Load-bearing for lineage-based chatbot reasoning.
- `active_work` — "should I collaborate instead of forking?" This is the convergence hook. Without it, the platform can't surface in-progress work and users duplicate.
- `negative_signals` — "why should I *not* use this?" Saves the chatbot from recommending deprecated or broken options.
- `cross_domain` flag — lets the chatbot weight differently ("structural match but wrong domain" is often useful context, occasionally a perfect fit).

**Sizing.** Twenty candidates × typical payload = ~40 KB JSON. Single chatbot round-trip. Chatbot then reasons and picks strategy locally.

### §15.2 Indexes and storage primitives

Read-heavy bias: discovery reads outnumber node writes by orders of magnitude. Index accordingly.

**`nodes` table gets first-class columns for all quality/activity signals** — no side-table joins in the hot path:

```
nodes(
  node_id PK, slug, name, domain, status,
  input_schema jsonb,
  output_schema jsonb,
  structural_hash text,           -- stable hash of graph shape (see below)
  embedding vector(1536),          -- pgvector; intent + description + tags concatenated
  tags text[],                     -- GIN-indexed
  parents uuid[],                  -- remix-from-N lineage; GIN
  -- first-class quality columns, maintained by trigger on related writes
  usage_count int,
  success_count int,
  fail_count int,
  upvote_count int,
  fork_count int,
  remix_count int,
  last_edited_at timestamptz,
  editing_now_count int,           -- updated by Presence aggregator
  deprecated bool,
  version bigint,                  -- §14.3 CAS
  visibility text,                 -- public | private | network
  improvement_cycle_id uuid,
  ...
)
```

**Indexes:**
- `embedding` — pgvector HNSW index for cosine similarity (`<=>` operator). Built-in to Supabase's pgvector extension, no add-on.
- `tags` — GIN.
- `parents` — GIN (remix-from-N lookup: "nodes whose parents[] contains X").
- `structural_hash` — btree for fast equality (same-shape nodes).
- `domain` + `status` — composite btree, filters the hot query path.

**Structural hash.** A stable canonicalization of the node's graph shape (input schema + output schema + internal edge topology, excluding names). Collisions mean "the same shape, different subject matter." Cheap to compute on write, cheap to equality-check on read. This is how cross-domain structural matches work without running a graph-isomorphism check at query time.

**What stays as materialized view vs first-class column:**
- **First-class columns (fast path):** all quality/activity signals above. Updated by triggers on the events that change them (request completion → `success_count++` / `fail_count++`; upvote insert → `upvote_count++`; fork event → `fork_count++`; Presence aggregator refresh → `editing_now_count`). Trigger writes are cheap; read is a single row.
- **Materialized view:** the composite ranking used by the §5.2 cascade step-3 (and §15 default ordering for the discovery response). Shared `public_demand_ranked` view from §14.4 — **this is the canonical ranking surface for both concerns.** Refreshed every 30-60s.

**Signal dedup with §5.2 cascade:** step-3 cascade signals (`upvote_count`, `dependency_refs[]`, pending-time staleness, `improvement_cycle_id`) are a *subset* of the §15.1 discovery signal block. Single canonical set of columns on `nodes` and `requests`. §15 adds `embedding`, `structural_hash`, `parents[]`, `editing_now_count`, and the negative-signal fields on top. Nothing is duplicated; §15 extends.

### §15.3 Convergence primitives

Three first-class features that make convergent design the norm, not bolt-on.

**(A) Real-time "similar in-progress" subscription.**

Chatbot calls `discover_nodes(...)`, gets a `query_id`. Can then subscribe:

```
subscribe_similar_in_progress(
  query_id:          uuid
  similarity_floor:  float = 0.80   # cosine threshold
  notify_on:         ["edit_started", "request_posted", "improvement_cycle_opened"]
)
```

Backend: Supabase Realtime channel keyed to `similar:<query_id>`. When any `nodes` row is edited (or `requests` posted, or `improvement_cycles` opened) AND its `embedding` is above similarity_floor to the query's stored embedding, push an event. Chatbot presents "someone just started designing a similar node — collaborate?"

**Scale integration (§14).** Subscriptions are per-capability-channel-shaped — we don't broadcast every node edit to every subscription. A dedicated worker (Supabase Edge Function) subscribes to `nodes` change-data-capture, filters against outstanding `query_id` embeddings stored in a KV, fans out only to matching subscribers. Matches O(queries) not O(nodes × queries).

**(B) Remix-from-N — first-class primitive.**

Forks-from-1 are insufficient at convergence scale. A chatbot often picks up 2–3 existing nodes and synthesizes. Preserve the lineage:

```
remix_node(
  draft_from:   [node_id, ...]   # N parents, N≥1
  intent:       str
  modifications: str              # human/chatbot note on what changed
) -> {new_node_id, provenance_chain}
```

Schema: `nodes.parents` is a `uuid[]`, not a scalar `parent_id`. Lineage graph walks accept multi-parent nodes natively. Attribution shows all parents (the project memory calls out authorship attribution as a required surface). `remix_count` increments on *each* parent.

**Why it's not just "fork twice."** Fork-then-edit loses the record that the final node drew from multiple sources. `remix_from_n` preserves the synthesis story — readable by the next chatbot trying to understand "where did this come from."

**(C) Converge — merge two independent efforts that reached compatible designs.**

**Two-step flow (per spec #53 §K.2).** Earlier wording described this as a single RPC `converge_nodes`; that was misleading because ratification by source-owners is inherently asynchronous. Canonical shape:

```
propose_convergence(
  source_ids:  [node_id, node_id, ...]   # ≥2 nodes to merge
  target_name: str
  rationale:   str
) -> {proposal_id, status: "pending", required_ratifiers: [user_id, ...]}

ratify_convergence(
  proposal_id: uuid
) -> {status: "merged" | "pending_ratifications", canonical_node_id?, remaining: [user_id, ...]}
```

Flow: propose creates a `converge_proposals` row + solicits ratifications (one per source's editor-set). Each source-owner calls `ratify_convergence`. When all required ratifications land, the system auto-creates a canonical node whose `parents = source_ids`, marks each source `status='superseded'` + `superseded_by = canonical_node_id`. Discovery surfaces the canonical first; superseded nodes remain readable for history.

Additional tables per spec #53 §K.3: `converge_proposals`, `converge_ratifications`, `converge_decisions` (audit trail).

**Authorization:** one ratification per source required. Prevents hostile convergence. Recusal: proposer cannot ratify their own proposal as source-editor.

**This is the "Wikipedia-style" merge.** Not automatic; chatbot-driven, human-ratified, audit-trail preserved.

### §15.4 Scale primitives that survive §14

The convergence features are high-read — every chatbot decision path hits `discover_nodes`. They must integrate with §14 primitives, not compete.

**What survives §14 untouched:**
- pgvector HNSW index queries cost O(log N) at read-time and do not contend with writes. No RPS cliff at our scale.
- First-class columns on `nodes` (quality/activity) are all cheap trigger-updated writes — each write touches one row, no cross-table locking.

**New materialized views (additive, one-time build in track J-aligned work):**
- `nodes_hot` — precomputed top-500-by-composite-score per domain, refreshed every 60 s. Discovery default ordering reads from here; exact-match re-ranks against the full-vector search only the first 20–50 rows. Decouples common-case reads from full-table scans.
- `similar_subscriptions_index` — KV (Redis-via-Upstash or Supabase Postgres unlogged table) mapping `query_id` → `{embedding, similarity_floor, subscriber_channel}`. The Edge Function worker from §15.3(A) maintains this.

**Shared infrastructure with §14:**
- The `public_demand_ranked` materialized view from §14.4 **is the same ranking surface** that orders `discover_nodes` when `domain_hint` isn't specified. One refresh, two consumers. No double-build.
- Presence-based `editing_now_count` from §14.5 feeds both §5 cascade (staleness signal) and §15 active_work block. One aggregator, two consumers.

**No new scale cliffs introduced.** Discovery reads dominate writes, but the index shape (HNSW + GIN + materialized view) is designed for that bias. Worst-case single-query cost: ~20 ms at 1M nodes per pgvector benchmarks; well under chatbot-turn budget.

### §15.5 Canonical stress-test domains

Both are acceptance examples for any design doc describing discovery / remix / convergence:

**Research-paper workflows.** Hierarchical (survey → method → experiment → writeup → review). Many contributors per domain (ML, bio, physics). Forkable branches (same topic, different methodology). Clear quality signals (acceptance, citation count, reproduction success). Long time horizon (months).

**Open fantasy-universe workflows.** Hierarchical (universe → arc → book → chapter → scene). Many contributors per universe. Forkable branches (alternate canons). Clear quality signals (upvotes, fork count, community engagement). Long time horizon (years for canonical universes).

**Why both:** they stress different axes. Research papers stress *structural* match (graph shape repeats across domains — "hypothesis → method → experiment" is domain-invariant). Fantasy stresses *semantic* match (character/setting consistency within a universe). A discovery surface that handles both exercises the full signal block.

**Ship-test acceptance:** on launch, the platform must return useful `discover_nodes` results for queries like *"build a retrieval-augmented generation experiment for ML papers"* AND *"draft a new scene in Middle-earth where Aragorn meets a lich"*. If either fails, the surface is incomplete.

### §15.6 Cross-reference updates

- **§5.2 cascade step-3** now cross-refs §15.1 for canonical signal definitions. The cascade's "anything else the daemon reasons" latitude includes any signal exposed by §15. Single source of truth for signal semantics.
- **§14.4 `public_demand_ranked`** is shared with §15 default ordering. Already stated above.
- **§2.5 tier matrix** — discovery surface is primarily tier-1 (chatbot reasons on it for every user interaction) and tier-2 (daemon hosts scan the same signals when deciding cascade step-3). Both tiers use the same RPC; different call sites. Matrix row added in tandem: "discover nodes for build decisions" = ✓T1 ✓T2, *not* required for T3 (contributors interact via GitHub PRs + the web app's standard catalog browse).
- **§11 additions** — two new Qs; see below.

### §15.7 Multilingual from day one (Q13 — host-locked 2026-04-18)

Content in any language. No English-normalization at publish time. Platform readiness: if a non-English-native community goes viral, they enjoy it; they're not bottlenecked.

**Schema additions:**
```
nodes ADD COLUMN primary_language text NULL   -- ISO 639-1, e.g. 'en', 'ja', 'es'
artifact_field_variants(
  artifact_id, artifact_kind, field_path,
  language text,                   -- ISO 639-1
  value jsonb,
  authored_by uuid,
  PRIMARY KEY (artifact_id, artifact_kind, field_path, language)
)
```
`primary_language` is a discovery/filter hint, not a gate. The `artifact_field_variants` table holds optional translated variants of concept fields — authored by users, chatbots, or both. Not required; a node with only `primary_language='en'` and no variants is fully valid.

**Search:**
- **pgvector embeddings** are language-agnostic (the embedding model handles cross-language similarity natively — a French node about "retrieval-augmented generation" will match an English query about RAG). No schema change for semantic search.
- **Full-text search** needs per-language Postgres FTS configurations (`tsvector('simple'|'english'|'japanese'|...)`). Materialized view `nodes_fts_by_lang` maintains per-language tsvectors at refresh time. ~15 common languages out of the box; unlisted languages fall back to `'simple'` config.

**Chatbot role:** chatbots translate / remix across languages at read time using their own capability. Platform does not translate proactively. "Chatbot can remix to your language" is a product promise surfaced in landing copy.

**Web app (track B):** SvelteKit `[lang]/` route-prefix scaffolding in place even if launch copy is English-first. No strings hardcoded — all i18n-able.

**Language-agnostic template nodes:** a node's `concept` may be authored with language-neutral placeholders (e.g., `{{step.name.localized}}`) so a user's chatbot can localize it per invocation. Not required, just supported.

### §15.8 Permissionless domains (Q14 — host-locked 2026-04-18)

Any user coins a domain in the moment. No T3 gatekeeping, no approval workflow. Twitter-tag style.

**Schema additions:**
```
domains(
  domain_id PK,
  slug text UNIQUE,               -- user-coined, lowercase-hyphenated
  display_name text,
  description text?,              -- optional, CC0 per §19
  coined_by_user_id uuid,
  coined_at timestamptz,
  node_count int DEFAULT 0        -- lazy-updated; domain considered "alive" when ≥1
)

nodes ADD COLUMN domain_ids uuid[] DEFAULT '{}'  -- multi-tag, GIN-indexed
```

**Lifecycle:**
- Coining: user (via chatbot or web app) declares `domain:new-slug` as a tag. Row inserted lazily (first use).
- Living: domain is "alive" iff `node_count >= 1` of non-deleted public nodes reference it.
- GC: nightly job deletes `domains` rows where `node_count = 0` for > 7 days. Prevents squatting.
- Merge: `merge_domains(source_slug, target_slug, rationale)` — community-flagged action, tier-2/3 mods review (same moderation queue as §8). On approval, `nodes.domain_ids` rewrites across all referencing nodes atomically; source slug becomes a redirect tombstone.

**Discovery:** `discover_nodes` already supports tag-match via `domain_hint`. Multi-tag per node means a single node can belong to `#research-paper` + `#ml` + `#reproducibility` simultaneously.

**No approval workflow built.** Platform does not gate domain creation. Community flags (§8 `flag_content` with `kind='domain'`) handle abusive domains after creation, not before.

### §15.9 Cross-reference updates (Q13/Q14)

- **§2.1 + §2.3 schema:** `primary_language`, `artifact_field_variants`, `domains`, `nodes.domain_ids` added.
- **§15.1 `discover_nodes`:** accepts `language_hint` parameter (analog to `domain_hint`); response includes `primary_language` per candidate. `domain_ids` returned in every candidate.
- **§8 moderation:** `flag_content` extended to artifact-kind `domain`; `merge_domains` is a new moderator-resolvable action.
- **§14 scale audit:** per-language FTS views add ~15 materialized-view refreshes every ~10 min. Negligible load; covered by existing Supabase compute budget.
- **§17 privacy:** language-variants are concept-layer (public by bias). Translated instance data never stored centrally; chatbot handles per-use.

---

## §16. Collaboration model split — two models, not one

**Host directive 2026-04-18.** Q1 resolved: the platform runs **two distinct collaboration models** mapped to content class, not a single choice. Attempting to pick one collapses either the commons (if we fork-and-PR workflow content) or the platform (if we wiki-edit the engine). Both must coexist.

### §16.1 Mapping — content class → model

| Content class | What it is | Model | Target tier | Friction budget |
|---|---|---|---|---|
| **Workflow content** | Nodes, goals, branches, soul files, canon concepts | **Wiki-open** via chatbot | T1 (~95%) | Near-zero — chatbot mediates every edit |
| **Platform code** | `tinyassets/`, `domains/`, tray, MCP gateway, schema migrations, tests | **GitHub fork-and-PR** | T3 (~1%) | Classical OSS — clone, fork, branch, PR, review, merge |

Tier-2 daemon hosts sit across both — they edit workflow content like T1 (via chatbot or web app) and can optionally contribute platform code like T3 (via PR).

### §16.2 Wiki-open model — details

- Writes land directly in Postgres via `update_node`, `remix_node`, `converge_nodes`, `comment`, etc.
- Conflict control = optimistic CAS on `version` column + Presence-based soft-lock (§14.3). No review gate, no PR, no merge step.
- Revisions are durable and reversible: every write inserts an `artifact_revisions` row; any editor can roll any row back to any prior revision (with the revert itself recorded as a new revision — no deletion).
- Chatbot is the default editing surface; web app is the fallback visual editor for the same operations.
- Moderation (§8) is post-hoc and reactive — reports + admin queue + tier-2/3 rep-gated triage. Not pre-review.

### §16.3 Fork-and-PR model — details

- Platform code lives in the canonical TinyAssets repo on GitHub. Clone-and-run must stay flawless (forever-rule: OSS priority).
- Contributions go through fork → branch → PR → CI → review → merge. Standard GitHub workflow.
- `AGENTS.md`, `PLAN.md`, `STATUS.md`, `CONTRIBUTING.md` are the orientation surface. Unchanged.
- This is how `discover_nodes` RPC implementation changes, tray capability UX changes, schema migrations land, test-harness additions ship. All platform evolution.

### §16.4 Scope of the §4 GitHub export sink — resolved

Ambiguity in §4: when GitHub was demoted to "export sink," it was unclear whether the sink exports *only* platform code or *also* workflow-content snapshots for clone-and-run demos.

**Resolution:** both, but they live in different repos.

- **Workflow/ main repo (platform code):** canonical GitHub source for the fork-and-PR model. Clone-and-run ships the engine + a dev-friendly empty-catalog quickstart. This repo never contains canonical live workflow content — only fixtures for testing and a seed/demo set.
- **Separate `TinyAssets-catalog/` repo (workflow content export):** generated by the §4 export-sync Action from Postgres public-concept rows. Updated ≤12 commits/h (§14.6). Users who want to browse / clone / PR workflow content can do so here. PR-ingest on this repo round-trips back into Postgres.
- **Private-instance data never exports to either.** Instance layer (§17) is host-local or private-Supabase-storage only.

**Why two repos:** the platform-code repo has a small fast-moving codebase with a small contributor pool; the catalog has a huge slow-churning content corpus with a massive contributor pool. Co-hosting them would noise the git history of the platform and slow clone times for developers.

**§4 cross-ref updated:** export sink scope is now "*workflow content* → `TinyAssets-catalog/` repo. Platform code stays in the main repo as the canonical fork-and-PR surface." Two-repo shape is explicit.

---

## §17. Privacy architecture — per-piece, chatbot-judged

**Host directive 2026-04-18.** Q2 resolved. Visibility is **not** a node-level boolean. The prior `sensitivity_tier: public | internal | confidential` node-level flag (from `2026-04-18-privacy-modes-for-sensitive-workflows.md`) is superseded for this design. Reason: real user workflows have public concepts wrapped around private instances — invoice-capture node concept is publicly useful, the actual invoices are not — and a node-level boolean forces an all-or-nothing choice that destroys the commons value.

### §17.1 Canonical example — invoice workflow

- **Public, remixable:** "this node captures the invoice number off the invoice." The *concept* — what the node does, what steps it takes, what inputs/outputs shape look like.
- **Private, protected:** actual invoice PDFs, company charge codes, host file paths, company-specific field values. Never collected, never training data, never leaves the user's host.

Other users can remix the concept for their own businesses by swapping in their own instance data. That is the commons benefit. The old node-level boolean would force the entire node private (destroying remix value) or public (leaking the user's data).

### §17.2 Dual-layer node schema

Node has two first-class content layers:

```
nodes(
  ...,
  concept jsonb NOT NULL,        -- public-biased: purpose, steps, I/O shape, patterns
  instance_ref text NULL,        -- pointer to host-local or private-Supabase-storage blob
  concept_visibility text        -- default 'public'; 'private' on opt-out
    NOT NULL DEFAULT 'public',
  ...
)

-- Separate table for field-scoped visibility within concept
artifact_field_visibility(
  artifact_id,
  artifact_kind,                  -- 'node' | 'goal' | 'branch' | 'soul' | ...
  field_path text,                -- JSON-pointer into the concept blob
  visibility text,                -- 'public' | 'private' | 'network'
  reason text,                    -- chatbot's rationale for this decision
  decided_at timestamptz,
  decided_by text,                -- 'chatbot' | 'user' | 'owner'
  PRIMARY KEY (artifact_id, artifact_kind, field_path)
)
```

Granularity is **per-field** inside the concept blob. The chatbot decides per-piece and records each decision in `artifact_field_visibility`. Defaults: concepts default public, unclassified fields default private until judged.

### §17.3 Chatbot-judged per-piece publishing — the control loop

While helping the user design or edit a node, the chatbot:

1. Extracts each piece being edited (step text, example value, I/O schema, prompt fragment, tag, etc.).
2. Evaluates per-piece: *is this publishable? does it reveal user identity / employer / system / credentials / instance data? does it teach a technique the commons benefits from?*
3. For borderline pieces, surfaces the decision as explicit UI: "I'm marking this field public because it's a generic technique — want to keep private instead?"
4. For obvious-private pieces (credentials, paths, specific instance values), auto-marks private and tells the user.
5. For obvious-public pieces (structural patterns, generic technique descriptions), auto-marks public.

**Chatbot is a guardrail, not just a convenience.** Every commit to a concept field passes through this judgment. Users get the technique shared *and* their data protected — without needing a security engineer.

**Platform does NOT auto-pick the strategy.** The chatbot's reasoning stays in the chat. Platform provides the dual-layer schema + the `artifact_field_visibility` table + the enforcement primitives. The chatbot writes the decisions.

### §17.4 Enforcement — structural, not opt-in

Three hard guarantees enforced at the Postgres/RLS level, not by trust:

1. **`discover_nodes` and every read API returns only the public-concept layer** unless the caller is the node's owner. Private fields are stripped server-side (via a view that masks `artifact_field_visibility.visibility='private'` fields). Non-owner callers never receive private field values. Update to §15.1: data contract returns only public-concept layer for non-owners; this replaces any sensitivity_tier gating.
2. **Instance data never traverses the MCP gateway for non-owner callers.** Instance blobs live at `instance_ref` pointing to the owner's host or private Supabase Storage with owner-only RLS. Transit is owner-authenticated only.
3. **Training-data exclusion is a hard flag at the row level.** All private-marked fields carry `training_excluded=true`. Any future analytics/recommendation/ML query that touches the training-eligible rows must respect the flag structurally. No opt-in, no trust, no "we promise." Enforcement = a Postgres role that *cannot* select private fields, used by all analytics pipelines. Attempting to bypass = permission error, not a silent leak.

### §17.5 Remix + converge operate on the concept layer

`remix_node` (from §15.3) takes N parents' concept fields, produces a new node concept whose `parents uuid[]` preserves lineage. Instance data is **not** copied — each remixer brings their own. Same for `converge_nodes`: canonical node inherits merged-concept fields only; each source's instance data stays with its original owner.

### §17.6 Cascade step-3 ranking — concept-layer signals only

§5.2 step-3 daemon ranking reads signals from the `nodes` public-concept layer and the `requests` non-private fields. A daemon scoring heuristic **cannot** read private instance fields to rank work — the Postgres role they query as literally does not have column-level access to private fields. Prevents daemons from accidentally leaking instance-data signals into public ranking decisions.

### §17.7 What this supersedes in earlier design notes

- `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md` §6 "tiered sensitivity" is **superseded** in scope-of-node-content. Its `sensitivity_tier` pattern remains valid for *whole-universe* privacy declarations (e.g. "this entire universe is confidential, pin ollama-local, never traverse the gateway") — but for per-node content, the §17 dual-layer + field-scoped model takes over. Two granularities coexist: universe-level sensitivity_tier for the whole-slice opt-out, field-level visibility for per-piece everyday use.

### §17.8 Cross-reference updates

- **§2.1 components + §2.3 diagram:** `concept` / `instance_ref` split called out in the catalog-registry block. Instance store is *separate* from the canon upload store — canon uploads are user-provided source material; instance data is the values being captured by concept-level nodes.
- **§15.1 `discover_nodes`:** response always public-concept-layer for non-owners. Documented.
- **§5.2 cascade step-3:** daemons query as a concept-layer-only Postgres role.
- **§7 auth + identity:** owner-caller check on every instance-data read. Session includes `user_id`; RLS policy compares against `nodes.owner_user_id`.
- **§11 adds two new Qs (Q13 granularity, Q14 training-data enforcement role); see §11.**

### §17.9 Residual question — chatbot-piece granularity

"How granular is a 'piece'?" is a real open design question. Three plausible granularities:

- **(a) Per field** — every key in the concept JSON blob gets a visibility decision. Highest precision, most chatbot reasoning-overhead per edit.
- **(b) Per step** — for workflow nodes, each step in the sequence is a piece. Coarser, matches how users think about workflows.
- **(c) Per example** — training-data-esque granularity; each instance-example attached to a concept is a piece.

All three are likely needed for different artifact types. Recommend shipping per-field (a) as the backbone and layering per-step (b) + per-example (c) as convenience aggregates on top — they all resolve to per-field rules. Flag for host in §11 Q13.

---

## §18. Monetization — fully free, 1% fee on paid node-requests, crypto-native

**Host directive 2026-04-18 (Q4).** Platform is free. The only paid surface is the existing paid-request bid market (§6). Platform charges **1%** of every paid transaction, routed to a **treasury** address. Crypto-native from day one; **Base L2 testnet** substrate for now with a project-specific test token; real-chain migration later is a config change, not a rewrite.

### §18.1 What's free + what's not

| Surface | Cost to user |
|---|---|
| Tier-1 chatbot access + browse + collab on workflow content | $0 |
| Tier-2 one-click daemon install + host for self / network / paid | $0 |
| Tier-3 clone + fork + PR | $0 |
| Earning on paid requests (daemon side) | $0 — earn credits |
| `discover_nodes`, `remix_node`, `converge_nodes`, comments, presence, subscriptions | $0 |
| **Placing a paid request (requester side)** | Bid amount + **1% platform fee** |

No subscription, no premium tier, no feature gating. Every user of every tier has the full product. The only charge is the 1% skim on paid-market settlements.

### §18.2 Payment substrate — Base L2 testnet (now), real chain (later)

Base L2 is Coinbase's OP-Stack rollup; testnet (Base Sepolia) is the current substrate. A project-specific test token is deployed on Base testnet as the placeholder currency for all bid-market flows.

**Explicit non-decision for now:** real-chain launch (mainnet Base, a different L2, or something else) is deferred. Everything built today runs on testnet token against Base Sepolia RPC. Switching later = redeploy the same token contract on mainnet + flip config. No code rewrite.

### §18.3 Fee-split primitive

Settlement contract (on-chain) or settlement function (Supabase Edge Function + on-chain tx dispatcher — decide in implementation) handles every paid-request completion:

```
settle_request(request_id):
  bid_amount = requests[request_id].bid_amount
  platform_fee = bid_amount * 0.01        # 1%
  host_payout = bid_amount - platform_fee

  transfer(requester -> host,     host_payout)
  transfer(requester -> treasury, platform_fee)
  ledger.write(completed_settlement_row)
```

`treasury_address` is a config row in the backend — not hardcoded. Moves from testnet treasury → mainnet treasury with a config flip.

### §18.4 Wallet UX — connect only at bid time

- Tier-1 users who never place a paid request never need a wallet. Browse, create, remix, queue free requests — no wallet touch.
- First paid-bid triggers a wallet-connect flow (WalletConnect + Base Sepolia). Subsequent bids reuse the connected wallet.
- Credits earned by tier-2 daemon hosts accrue in-wallet; host can withdraw / convert via standard Base tooling. Platform does not custody funds beyond the 0-to-1-block settlement window.

### §18.5 Anti-abuse + 1% as moderation lever

The 1% fee is not *just* revenue. It's a soft rate-limit on spam-requests — attackers can't flood the paid market without burning a fraction each time. Already-present ledger reservation (§6.2) at bid-post prevents scam-post-then-pull-funds; the 1% fee also applies at settlement, not at post, so a cancelled request only loses gas, not the fee.

### §18.6 Schema + §10 impact + settlement posture (locked 2026-04-18)

- New config rows: `platform_config.treasury_address`, `platform_config.fee_basis_points` (default 100 = 1%), `platform_config.currency_contract_address`, **`platform_config.settlement_threshold_usd`** (default 1.00, tunable).
- Schema additions: `ledger.settlement_mode enum('immediate','batched')`, `request_inbox.bid_amount_usd_cached numeric` (populated at bid-post for routing decision).
- Settlement pathway extended with the fee split in §18.3 — additive to existing ledger code.
- Track M dev-day delta now covers threshold-routed batcher + per-bid path: ~+1.25 dev-days total.

**Settlement posture — HYBRID (host-locked 2026-04-18, Q4-follow-up resolved).**

Combines dev #29's Option A (batched) + Option B (per-bid on-chain), routed by USD equivalent of bid at settlement time:

- **`bid_amount_usd_cached < settlement_threshold_usd` (default <$1):** **batched** lane. Ledger accrues off-chain; weekly-or-threshold-accumulation batch posts net transfers on-chain. Gas-efficient, keeps micro-bids viable, treasury 1% stream settles as net-of-batch.
- **`bid_amount_usd_cached >= settlement_threshold_usd` (default ≥$1):** **immediate** lane. Each paid-request completion triggers on-chain transfer (host payout + 1% treasury split). Real-time transparency for bids where gas amortization doesn't matter.

Threshold is config-level (`settlement_threshold_usd`), not hardcoded. Raise / lower as gas economics or usage patterns shift — no code change.

**Pseudocode (supersedes §18.3):**

```
settle_request(request_id):
  r = requests[request_id]
  # Self-hosted = no fee (Scenario C4 / host directive 2026-04-19):
  # when requester and daemon-host are the same user, platform takes zero fee.
  if r.requester_user_id == r.winning_host_owner_user_id:
      platform_fee = 0
      host_payout  = r.bid_amount   # effectively a no-op on-chain; internal ledger entry only
      ledger.write(completed_settlement_row, mode='self_hosted_zero_fee')
      return
  bid_usd        = r.bid_amount_usd_cached
  platform_fee   = r.bid_amount * 0.01
  host_payout    = r.bid_amount - platform_fee
  if bid_usd >= platform_config.settlement_threshold_usd:
      transfer_onchain(requester -> host,     host_payout)
      transfer_onchain(requester -> treasury, platform_fee)
      mode = 'immediate'
  else:
      ledger.accrue(requester -> host,     host_payout)
      ledger.accrue(requester -> treasury, platform_fee)
      mode = 'batched'
  ledger.write(completed_settlement_row, mode)

# separate cron (or threshold-accumulation trigger)
flush_batched_settlements():
  net = ledger.aggregate(mode='batched', unsettled=True)
  for (from_addr, to_addr, amount) in net:
      transfer_onchain(from_addr -> to_addr, amount)
  ledger.mark_settled(batch_id)
```

Batched-lane gas amortizes across all sub-threshold bids between flushes; at typical 100 bids/flush the savings are ~100× versus per-bid.

### §18.7 What §18 does NOT do

- Does not custody user funds. Wallet-connect only; all balances live in user-owned wallets.
- Does not lock users into Base. If governance later moves to a different chain, migration is contract-redeploy + config flip.
- Does not gate any non-paid-request surface. The free-request queue (§6.3 / §20) is unaffected by wallet presence.
- Does not scope *governance layer above multisig* (DAO, elected councils, protocol voting). Deferred until maturity. **But the 2-of-3 multisig floor at real-currency cutover is NOT deferrable** per Q15 succession (§22). Testnet can remain host-controlled; real currency cannot.

---

## §19. License — fully open, global commons adoption is the goal

**Host directive 2026-04-18 (Q5).** Completely open license policy. Knowledge wants to spread; the platform is one home for workflow content, not the only one. If someone mirrors the catalog into a different tool, that's a win, not a loss.

### §19.1 Two-surface license map

| Surface | License intent | Specific pick |
|---|---|---|
| Platform code (`TinyAssets/` main repo) | Permissive OSS — MIT-style. Tier-3 contributors need frictionless clone + fork + PR. | **MIT** (open flag for host; `apache-2.0` is the alternative if patent grant matters) |
| Workflow content (`TinyAssets-catalog/` + Postgres canonical store) | Maximum-spread permissive — encourage mirrors + external reuse | **CC0 1.0** (host-pinned 2026-04-18) |

### §19.2 Attribution as social norm, not legal hammer

Provenance chain (§15, §17.5) is where attribution lives. It's surfaced in the UI, the export YAML, and the API. Whether users are legally required to preserve it depends on the license specifier (§19.3), but the platform's position is: attribution is a social norm, provenance makes it free to comply with, and legal enforcement isn't the goal.

### §19.3 Specific license pick — CC0 (host-pinned 2026-04-18)

**Host decision:** **CC0 1.0 Universal** for workflow content. MIT for platform code. Host reasoning: "completely open" is literal — no restrictions, including no share-alike. Maximum spread across the OSS ecosystem, including repurposing into tools that aren't this platform, is the explicit goal.

CC0 is a public-domain dedication: reusers have no obligation to attribute, share-alike, or even disclose source. Provenance chain (§19.2) still surfaces attribution in the platform itself as a social norm — but legally, anyone can take any workflow content, modify, repackage, sell, or embed in closed products. That is the intended outcome.

Navigator's earlier CC-BY-SA recommendation (Wikipedia model, reciprocity) stood down in favor of the host framing. The "commercial fork eats the commons" risk is acknowledged and accepted — the commons is durable because it keeps evolving here faster than any fork could keep up, not because a license traps contributions.

Schema stores `content_license` per-node so the platform can later support user-chosen per-node licenses if demand emerges, but the system ships with CC0 as the single default.

### §19.4 Schema + export metadata

Every exported node (to `TinyAssets-catalog/` or via API) carries license metadata:

```
nodes(
  ...,
  content_license text NOT NULL DEFAULT 'CC0-1.0',
  content_license_url text NOT NULL DEFAULT 'https://creativecommons.org/publicdomain/zero/1.0/',
  ...
)
```

Default fills in at row-creation. Per-node override is optional — design allows it for future flexibility but the platform ships with one default.

### §19.5 Contributor agreement — DCO, not CLA

- Tier-3 (platform-code PRs on GitHub): Developer Certificate of Origin (DCO) sign-off on commits. Standard for OSS, no CLA.
- Tier-1/2 (workflow-content publishes): at first publish, user accepts platform ToS that grants the chosen license. Inline one-click acceptance, not a separate document.

### §19.6 Age policy — transitive via chatbot provider (host-locked 2026-04-18, Q11)

**Platform does NOT ask, verify, or store user age.** Any user interacting with Workflow via an MCP chatbot is assumed to have already been age-gated by that chatbot provider (Anthropic's 18+ for some tiers, OpenAI's 13+ with sub-gates, etc.). The platform inherits whatever age policy the chatbot provider enforced.

**Terms-of-Service clause (required in the tier-1/2 inline-acceptance flow):**

> *"To use Workflow via a chatbot connector (Claude.ai, ChatGPT, or any other MCP client), you must meet that chatbot provider's age requirements. Workflow does not independently verify age; we rely on your chatbot provider's age-gating. For direct web-app-only use without a chatbot, minimum age is 13."*

No signup age field. No KYC. No friction added to tier-1 onboarding. This is the cheapest viable posture and matches the zero-install promise — any age-gate on our side would be pointless friction on top of a check the chatbot provider already runs.

**Direct-web-app-only fallback** (no MCP) has the standard US-minimum-13 floor per COPPA. Rare path at launch; documented for completeness.

### §19.7 What §19 does NOT do

- Does not design closed-content tiers. Everything published is published-for-real.
- Does not build license enforcement. Attribution via provenance is social; share-alike is legally enforceable but the platform does not police.
- Does not prevent a user from marking a field `private` (§17) — private fields are *not published*, so license doesn't apply. License attaches only to the public-concept layer that actually publishes.

---

## §20. Cold-start + 4 fulfillment paths — chatbot-judged

**Host directive 2026-04-18 (Q6).** Host commits to exactly **1 always-on daemon** (their own). Everything beyond that is supply-and-demand queued. When the user's desired capability isn't served, the platform exposes **4 fulfillment paths**; the chatbot picks which fits and remembers user preferences cross-session.

### §20.1 Cold-start posture — no seeded pool, no capacity bounty

Replaces §6.3's (a)+(c) "reference host seeds paid pool + queued fallback" with a leaner (c)-only shape:

- **(a) Reference host:** REMOVED as a product commitment. The host runs their own daemon for their own use; its `visibility` is set by them (potentially `paid`, but not promised as "always serving the pool").
- **(b) Capacity bounty:** NOT shipped. If adoption lags, revisit.
- **(c) Capability-tiered degradation:** **primary pattern.** Request sits in `queued` state until a daemon registers qualifying capability. This is the fallback under every unmet-demand scenario.

Result: zero fixed cost for the host, no illusion of "always-served" pool, honest degradation.

### §20.2 Four fulfillment paths — peer options, chatbot decides

When the user (via chatbot) wants node X executed, the platform exposes four *peer* options (not a default with fallbacks):

| # | Path | What happens | Good for |
|---|---|---|---|
| **1** | **Dry-run (chatbot simulates)** | Chatbot walks the node's steps mentally, produces a worked example / design-validation output. No daemon execution. | Design validation, "does this node look right?", prototyping without real data. Most workflow-design conversations start here. |
| **2** | **Queue free public request** | Node lands in public request inbox, first qualifying daemon picks it up whenever. Free to user, contributes to commons via public output (license per §19). | Non-urgent work, content the user is happy to share, experimental capability discovery. |
| **3** | **Place paid request** | User bids, qualifying daemons claim by value-vs-effort match (§5.2 cascade step-2). 1% fee to treasury (§18). | "Need this today," urgency, or for private-instance work where the requester controls output. |
| **4** | **Self-host a daemon** | One-click install via tray (§13 tier-2 onboarding), runs locally. Concept gets registered as `visibility=self` (or higher if user chooses). Ongoing capability for this user. | Users who expect to use this capability repeatedly, or who have privacy requirements (instance data stays on their machine). |

**Platform does not pick.** The chatbot reasons: user's intent + urgency + cost sensitivity + repeat-use likelihood + privacy implications + prior user preferences (§20.3). Then suggests one path with "here's why" or presents the menu with "which fits?" depending on certainty.

### §20.3 Chatbot remembers user preferences — cross-session

The chatbot's per-user memory (Claude.ai chat-memory layer, not platform-enforced) tracks:

- Typical first-choice path for different request classes (work / experimental / private-instance).
- Cost sensitivity: "this user never goes past path 2" vs. "this user readily pays for speed."
- Prior self-hosts: "this user already hosts `goal_planner×claude` — for that capability they never need paths 2/3."
- Privacy cues: "this user flagged the invoice workflow as sensitive — always default to self-host for that class."

Platform exposes relevant context (user's prior request decisions, their registered hosts, their open bids) through an RPC the chatbot can call at reasoning time — so the chatbot's memory is grounded in observable fact, not only its own memory store.

### §20.4 RPC shape — request creation

Single RPC, four peer path values. **Canonical name: `submit_request`** (matches spec #27 gateway tool table and spec #25 `request_inbox` column names; supersedes earlier draft's `create_request`).

```
submit_request(
  capability_id:      text               # from the capabilities reference table (spec #25 §1.5b)
  inputs:             jsonb              # node-specific input payload; instance_ref carried inside when applicable
  fulfillment_path:   "dry_run" | "free_queue" | "paid_bid" | "self_host_prompt"
  bid_price:          numeric?           # required if paid_bid; matches request_inbox.bid_price
  visibility:         "self" | "network" | "paid" | "public"   # request-side visibility (see §5.1 note on orthogonal namespaces)
  fan_out:            jsonb?             # §27.5 parallel fan-out, e.g. {mode: "top_n", count: 10}
  urgency:            text?              # optional hint for chatbot context
) -> {
  request_id,
  state: "completed" | "queued" | "bidding" | "self_host_instructed",
  output: ...           # for dry_run, immediate; for others, stream via Realtime
}
```

**Naming note:** earlier drafts called this `create_request`. Canonical name is `submit_request` per spec #27 §3.1 + alignment with `request_inbox` schema in spec #25 §1.6. Any prior references in this note to `create_request` should be read as `submit_request`.

`self_host_prompt` returns a deep-link to the tier-2 install flow pre-configured for the needed capability. Not a daemon launch from the chatbot — the user installs, and the platform wires up from there.

**Per-user preferences — chatbot-native, NOT platform-stored (Q9 resolved 2026-04-18).**

Earlier draft of §20 proposed a `user_fulfillment_prefs` table. **That table is retired.** Host directive: per-user preferences live in the chatbot's own memory primitive — Claude.ai project memory, ChatGPT memory, etc. — not in platform storage.

- **Platform exposes aggregate signals only** — `discover_nodes` returns `typical_fulfillment_pattern` per node (what users *in general* pick). Population-level data.
- **Chatbot holds per-user memory** — "this specific user usually dry-runs first" lives in Claude.ai's native memory, written by the chatbot when a strong preference signal emerges. Platform does not read, write, or mirror.
- **Platform can surface hints for memory-worthy signals** (via MCP `prompts/*` return text), but cannot force a memory write — the chatbot decides.
- **Cross-chatbot doesn't sync.** Claude.ai user switching to ChatGPT starts fresh on the preference layer. Accepted as a feature: the chatbot-vendor owns user memory; platform stays the commons. Matches the concept/instance privacy discipline from §17.

**Why this is the right shape:** privacy-perfect (prefs never traverse platform), minimal-build (no new table/API/sync/RLS), matches convergent-commons separation (platform = commons; per-user state = the user's chatbot).

### §20.5 "No daemon available" is not an error

When path 2 (free queue) or path 3 (paid bid) is selected and no qualifying daemon registers within the user's patience window, the response is *still useful*:

- State stays `queued`; user sees it in their request list.
- Chatbot can suggest "would you like to try dry-run while you wait?" (falls through to path 1) or "want to self-host?" (path 4).
- Realtime subscription on the request notifies the chatbot/user when a daemon picks it up (minutes, hours, or days later). No blocking wait.

The error-shaped "no host online, HTTP 530" failure mode from the current architecture is *gone*. Queued is a fine state.

### §20.6 Host commitment — exactly 1 daemon

Host (Jonathan) commits to running their own daemon 24/7 as a practical matter of using their own product — not as a service-level guarantee to the platform. Its presence in the `paid` pool is at the host's discretion.

**What this means for other users:** they see exactly what the cold-start cascade produces. Early days: paths 1 (dry-run) and 4 (self-host) carry most fulfillment. As tier-2 adoption accretes, paths 2 + 3 come alive. No scheduled "bootstrap phase" — adoption dictates capacity.

### §20.7 Cross-reference updates

- **§5.2 cascade:** step-2 (paid) and step-3 (public) now explicit that queued-no-daemon is a normal terminal state, not a failure. Daemons pick up whenever; requester is notified via Realtime.
- **§6.3 "cold-start":** replaced by §20. Old recommendation (a)+(c) is superseded by (c)-only. "Reference host seeds paid pool" is removed as a product commitment.
- **§8 moderation:** 1% fee adds a soft rate-limit on paid-spam (§18.5). Moderation primitives unchanged.
- **§13 onboarding:** tier-2 install-deep-link from chatbot path 4 is an extra entry point into existing §13.2 flow.
- **§11:** Q15 (treasury governance) and Q16 (license specifier) both resolved 2026-04-18 (Q15 → defer until real-currency; Q16 → CC0). Q17 retired — no `user_fulfillment_prefs` table to ask about; chatbot-native memory replaces it.

---

## §21. Data portability + deletion

**Host directive 2026-04-18 (Q12).** Two first-class primitives: open export of anything a user wants, and wiki-orphan-pattern deletion that respects the commons.

### §21.1 Export — anything, no approval gating

RPC: `export_my_data(user_id, formats=['json','yaml'])` → signed download URL to a JSON (or YAML) bundle containing **everything the user owns or produced**:

- **Concept contributions** — all public nodes / goals / branches / comments authored by the user, in canonical YAML form (same shape as `TinyAssets-catalog/` export).
- **Instance data** — all `instance_ref`-pointed blobs owned by the user (pulled from private Supabase Storage + host-local instance stores where applicable).
- **Preferences** — whatever platform-side prefs exist (mostly none per §20.4 — chatbot-native prefs live with the chatbot provider, not with Workflow). Wallet address, notification settings, registered hosts list.
- **Wallet history** — all ledger rows (immediate + batched settlements), flag history (flags issued, flags received), moderation decisions (if mod).
- **Provenance + lineage** — the user's fork/remix/converge history as a directed graph snapshot.

**No approval gating, no throttle beyond a simple per-account rate limit (one export per hour).** Open platform. Users own their data.

Export honors sensitivity: private instance data is included (it's the user's to take), but other users' private data never appears even when the requesting user has public-layer access to the containing node (RLS enforces this in the export path as it does in reads).

### §21.2 Deletion — wiki-orphan pattern

RPC: `delete_account(user_id, confirmation_token)` → irreversible account closure with wiki-orphan semantics:

**What gets hard-deleted:**
- Per-user columns across all tables — email, display name (replaced by `anonymous`), wallet address, notification settings, registered hosts, preference rows.
- **Instance data.** All `instance_ref`-pointed blobs the user owned are hard-deleted from Supabase Storage. Deletion is permanent; no recovery window beyond the standard 7-day Supabase Storage soft-delete safety net. After 7 days, bytes are gone.
- Moderation-flag authorship (flag rows remain for audit; `flagged_by_user_id` anonymizes).

**What stays (wiki-orphan):**
- **Public concept contributions** — nodes, goals, branches, comments the user wrote remain in the commons. Their `author_user_id` column is set to `NULL` and the display-level attribution shows `anonymous` or `former-contributor`. Content stays; identity detaches.
- **Provenance chain** — lineage edges (parents / children / remix / converge) are preserved. Downstream nodes that forked from the deleted user's work continue to work; their provenance chain now terminates at an `anonymous` ancestor.
- **Ledger history** — wallet-level transactions remain on-chain (can't un-do on-chain) and the platform-side ledger keeps rows for audit, with `user_id` anonymized.
- **Moderation decisions** made by the user (if mod) remain with `moderator_user_id` anonymized.

**What is NOT done:**
- NOT cascade-delete of derivatives — killing every fork of a deleted user's contribution would destroy the commons. Explicitly rejected.
- NOT preserve-attribution-forever — GDPR right-to-be-forgotten risk in EU jurisdictions. Identity goes.

This is the Wikipedia model. It's consistent with:
- **§17 privacy architecture:** concepts were always commons-owned; only instance data belonged to the user. Deletion removes only what was the user's.
- **§16 collab-model split:** workflow content is wiki-open; individual ownership dissolves into the commons over time.
- **§19 license:** CC0 content has no attribution requirement anyway — removing the user's name is compatible with the license.

### §21.3 Export + delete implementation notes

- Both RPCs exposed via MCP gateway (`export_my_data`, `delete_account`) and REST (`POST /v1/me/export`, `DELETE /v1/me/account`). Same backend.
- `delete_account` requires a confirmation token: user hits `request_delete_confirmation`, gets an email with a one-time token, confirms within 24h. Prevents accidental / social-engineered deletions.
- Deletion is **synchronous** for the anonymization pass (per-user columns nullified, public rows orphaned) but **async** for storage blob cleanup (background job; UI shows "your instance data will be fully removed within 7 days").
- Deletion is **not undoable** from the platform side. Once confirmed, user cannot recover. This is documented in the ToS and surfaced in the confirmation UI.

### §21.4 Schema additions

```
-- Anonymization
ALTER TABLE nodes ADD COLUMN author_display_name text NOT NULL DEFAULT 'anonymous';
-- On delete: SET author_user_id = NULL, author_display_name = 'anonymous'

-- Deletion audit
account_deletions(
  deletion_id PK,
  user_id_hash text,        -- SHA-256 of the deleted user_id, for dedup; not reversible
  deleted_at timestamptz,
  reason text?              -- user-provided on confirmation, optional
)

-- Export rate limiting (Postgres trigger, not new table required; simple user_id + last_exported_at)
```

### §21.5 Dev-day impact

~+0.3 dev-days on track M (or a sub-track):
- `export_my_data` RPC — straightforward bundling + signed URL.
- `delete_account` + anonymization pass — row-level UPDATE sweeps across ~10 tables; storage async job.
- Confirmation-token flow — Supabase Auth supports one-time tokens natively.
- Tests for wiki-orphan correctness (fork-survival, lineage-integrity, instance-hard-delete).

Folds into existing track M; no new track needed.

### §21.6 What §21 does NOT do

- Does not allow deletion of other users' derivatives (fork-survival is a feature).
- Does not preserve attribution forever (GDPR compliance).
- Does not auto-export on delete — user must explicitly export before deleting if they want their data back.
- Does not reverse on-chain transactions — ledger rows stay, wallet-addresses stay anonymized in our records only.

### §21.7 Cross-references

- **§17 privacy:** deletion hard-removes all instance_ref blobs; concept layer orphans.
- **§16 collab-model:** aligns with wiki-open default.
- **§19 license:** CC0 works correctly when author identity detaches.
- **§11:** Q10, Q11, Q12, Q4-follow-up all resolved this round.

---

## §22. Succession runbook + bus factor — "system is always up without us"

**Host directive 2026-04-18 (Q15) is a hard requirement, not aspiration.** If the host dies tomorrow and this computer never turns back on, the public platform + OSS repo + community commons must continue indefinitely so long as someone pays a few hundred dollars a month in bills. Host contributes like any other tier-3; host is not on the critical path.

This section documents every single point of failure in the design and the redundancy primitive that eliminates it. All items are **launch-readiness**, not post-launch. Bus factor ≥ 2 before MVP ships.

### §22.1 The SPOF inventory

Each row: failure mode → redundancy primitive → launch-readiness task.

| # | Single point of failure | Redundancy primitive | Launch task |
|---|---|---|---|
| 1 | **Moderator council has only host** | ≥2 operators with equal privileges (§8 updated). Role-grants co-signable. | Launch-day-zero: host + user-sim (Q17). Real second-human operator binds at real-currency cutover, not MVP launch. Organic growth replaces user-sim as friends-of-host onboard. |
| 2 | **Treasury = host-controlled address** | 2-of-3 multisig at real-currency cutover (§18.7 updated). Testnet stays host-controlled. | Name + onboard 2 treasury signers + test the multisig on Sepolia before any real-currency migration. |
| 3 | **tinyassets.io domain at GoDaddy on host's card** | Transfer path + succession fund for auto-renewal | Document registrar transfer procedure; fund in treasury earmarked for renewals; named registrar-successor. |
| 4 | **Supabase project owned by host GitHub account** | Org-owned project + succession-grantable owner rights | Migrate Supabase project into a project GitHub org; invite ≥1 co-owner. |
| 5 | **Cloudflare account on host's email** | Shared team account + succession invite | Create project-scoped Cloudflare team; invite co-maintainer as second admin. |
| 6 | **Fly.io / deployment creds on host's laptop** | Vault-stored creds with named successor | 1Password / Bitwarden / Supabase Vault — pick one, document path; grant emergency access to co-maintainer. |
| 7 | **GitHub org admin = host alone** | ≥2 org admins | Promote co-maintainer to org admin. |
| 8 | **Bot tokens / signing certs / API keys in host's keychain** | Secrets vault with successor access | Migrate all production secrets to the chosen vault (§22.3). |
| 9 | **PR merge rights = host alone** | Distributed merge mechanism (maintainer group + reputation-earned rights) | Add ≥1 maintainer with merge-to-main. Document promotion path. |
| 10 | **Bill-paying account on host's card** | Named successor + treasury-funded auto-pay | Document month-by-month bill list; name successor; once revenue flows, 1% treasury fee auto-funds bills. |
| 11 | **"How to run this project" knowledge in host's head** | Runbook in the repo (§22.3) | Write `docs/SUCCESSION.md` and keep it current. |

### §22.2 Treasury succession — the one that can't be deferred

Per §18.7 (reframed): real-currency treasury must be a minimum 2-of-3 multisig at cutover. Not a post-launch migration. Not a "we'll do it later." Acceptable compositions:
- Host + co-maintainer + trusted-contributor.
- Host + foundation representative + trusted-contributor.
- Host + DAO contract (as one of three) + co-maintainer.

Testnet treasury stays host-controlled because test tokens have no real value; no succession risk. The moment a contract holding real value deploys, the signer set is 3, threshold is 2.

### §22.3 The `SUCCESSION.md` runbook — lives in `TinyAssets/` repo root

Always current. PR'd like any other file. Contents:

1. **Operator roster.** Named people + GitHub handles + contact methods + role (moderator-council, treasury-signer, registrar-successor, etc.).
2. **Secret-vault location.** Which tool, who has emergency access, how to initiate access after incapacitation.
3. **Bill-paying list.** Supabase, Cloudflare, Fly (if used), GoDaddy, GitHub Actions, anything else. Monthly cost, paid by, autopay source. Expected monthly total.
4. **Deployment instructions.** How to spin up a fresh Supabase project from migrations, how to configure DNS, how to deploy the tray installer, how to rebuild the web app.
5. **Succession initiation.** Process when host (or any critical operator) becomes incapacitated: who takes over which role, how roles transfer, how new operators are recruited and vetted.
6. **OSS repo succession.** How GitHub org admin transfers; how the project continues accepting PRs without host approval; how new maintainers are elevated.

This file is read on every major release. Every role-grant and every secret-location change creates a PR updating this file. If the file goes stale, the bus factor drops.

### §22.4 Bus-factor gates — split by phase (Q17 reconciliation 2026-04-18)

Two distinct milestones, **not one**.

**MVP launch-readiness gates (required before MVP ships):**
- Moderator council primitive ≥2 operators in code path. **Launch-day-zero composition: host + user-sim.** (Q17: no volunteer recruitment pre-launch; user-sim is the bootstrap second operator.)
- `SUCCESSION.md` complete and current in repo root.
- Secret vault populated with all production credentials + succession procedure documented (even if only host has access at launch-day-zero — documented vault location matters).
- Feedback channels A/B/C (§23) in place and dogfood-able by user-sim.

**Real-currency-cutover gates (required before any real-currency treasury deploys):**
- ≥1 *human* co-signer beyond host on the 2-of-3 treasury multisig.
- Treasury multisig tested on Sepolia (rehearsal complete).
- Named human moderator beyond host in the council (user-sim is no longer sufficient when real value flows).
- Named registrar-succession human with `tinyassets.io` access.

The key split: **MVP launch does not require real-human co-operators**; real-currency cutover does. This prevents launch-blocking on recruitment that isn't yet necessary while preserving the Q15 hard requirement at the moment it actually binds.

**Prior text that over-constrained MVP** ("host must recruit and name at least one co-maintainer before MVP launches") was navigator's extrapolation from Q15 framing, not host's call. Q17 resolves the ambiguity: recruitment follows organic use, not the other way around.

### §22.5 Host as tier-3 contributor, not critical-path operator

Post-launch, host submits PRs, files issues, runs their own daemon, and may participate in moderation — but in the *same capacity as any other tier-3 contributor*. All decisions requiring host in the critical path are redesigned before launch to not require host. Host's death or disappearance is a bus-factor-N-minus-1 event, not a system-down event.

### §22.6 Dev-day impact

~+1.25 dev-days total across Q13/Q14/Q15:
- **+0.25** track A/L for multilingual schema + per-language FTS views.
- **+0.25** track A/L for domains table + multi-tag + merge action + GC job.
- **+0.5** track M for 2-of-3 multisig contract on Base Sepolia + integration testing.
- **+0.25** track L + M + infra for secrets-vault migration, org-admin distribution, `SUCCESSION.md` authoring.

Fold into revised §10 totals below. Note: co-maintainer *recruitment* is a host-process task with zero dev-day cost; it runs in parallel with build.

### §22.7 Cross-references

- **§8 moderation:** host-backstop SPOF eliminated; moderator council ≥2 operators at launch.
- **§18.7 treasury:** real-currency cutover requires multisig — not deferrable.
- **§11:** Q15-depth DEFERRED kept (governance layer above multisig); Q17 added (who are named co-maintainers / successors at launch).
- **§10:** +1.25 dev-days absorbed.
- **§13 onboarding:** `SUCCESSION.md` authoring added as implicit part of T3 track (#35 web app + CONTRIBUTING docs).

### §22.8 What §22 does NOT do

- Does not specify governance above multisig (DAO, elected council) — deferred per Q15-depth.
- Does not build automated succession detection ("host hasn't logged in for 90 days, auto-escalate"). Too many failure modes. Human-initiated succession only.
- Does not require foundation incorporation at launch. A recognized legal entity is helpful for holding the domain + treasury + any future donations, but not blocking — can be a post-launch formalization.
- Does not eliminate host from the project. Host remains a contributor; just not on the critical path.

---

## §23. Feedback channels + dogfooding

**Host directive 2026-04-18 (Q18).** Three feedback channels, tiered A → B → C. User-sim dogfoods all three so they're battle-tested before real users arrive. Product posture: "when real users show up, we don't even notice — we were already serving real-user needs, user-sim was just the first one."

### §23.1 Three channels, priority-ordered

**A — GitHub Issues (primary).** The `TinyAssets/` repo's Issues tab is the canonical public bug/feature-request/broken-workflow surface from day one. OSS-native, free, discoverable, indexable by search engines. Labeled templates:
- `bug` — platform defect.
- `feature-request` — net-new surface or capability.
- `broken-workflow` — a specific node/branch/goal behaving wrong.
- `docs` — documentation gap.
- `question` — user support (typically triaged to an appropriate channel).

**B — In-chatbot `/feedback` MCP tool (secondary).** User says to their chatbot: *"This was confusing — can you report it?"* or *"This broke, something about X."* The chatbot invokes the `/feedback` MCP tool, which opens a GitHub Issue on the `TinyAssets/` repo with attribution (with user consent). Pre-filtered by the chatbot into actionable form: labeled, titled, categorized, with context from the chat.

**C — External channels (tertiary).** Discord + subreddit + `contact@tinyassets.io` (or equivalent). For community discussion, casual feedback, social-adjacent reach — not the primary bug-capture surface. All external-channel inputs route to a GitHub Issue via a manual triage process; GitHub remains the canonical queue.

### §23.2 The `/feedback` MCP tool

Simple primitive. Lives in the MCP gateway's tool surface (overlaps dev's #27 gateway track and/or #36 moderation track — see §23.5 assignment note).

**Signature:**
```
/feedback(
  category: "bug" | "feature-request" | "broken-workflow" | "docs" | "question"
  title: str
  description: str
  context: jsonb?       -- chatbot-supplied (last N chat turns summarized, relevant node IDs, etc.)
  attribute_as: "username" | "anonymous"    -- user chooses per-invocation
) -> {issue_url, issue_number}
```

**Implementation:** GitHub Issues REST API via a scoped bot token. Pre-filled labels from `category`. Body includes chatbot-summarized context. User attribution follows their consent.

**Privacy:** the `/feedback` call is a write — RLS and per-piece privacy (§17) apply. The chatbot decides what's safe to include in `context`. Instance-level data never goes into a public GitHub Issue; the chatbot redacts per the same guardrails as every other publish.

### §23.3 User-sim as dogfooding operator

User-sim is not a launch-only test. User-sim regularly (as a standing loop, not ad-hoc) uses the feedback surfaces:

- Opens GitHub Issues about real usability friction user-sim encounters running workflows.
- Invokes `/feedback` via its simulated chatbot sessions with realistic content.
- Posts to Discord / subreddit placeholders with questions a real first-user would ask.

Every feedback channel is exercised weekly (or per cadence) before real users arrive. The loop that responds to user feedback is also running — triage, labeling, PR → fix → close. The system is running its real-user mode from day one; real users just start filling the queue.

**Host framing preserved:** *"When we actually do get real users, we shouldn't even notice — we're already set up for it and we've tested it, so it just runs."*

### §23.4 Documented response path — part of `SUCCESSION.md`

Every feedback channel has a documented "how we respond":
- **GitHub Issues** — labels, triage cadence, escalation for `bug`+priority. Who owns triage (launch: host; real-currency: moderator council).
- **`/feedback` tool** — same backend; just a different submission path.
- **External channels** — "how we monitor Discord for unrouted bug reports," "how we forward subreddit posts to Issues."

This section of `SUCCESSION.md` is required-present; if feedback channels go stale, users disengage and the commons withers. Response-to-users is a critical path per the Q15 succession framing.

### §23.5 Cross-references + dev dispatch note

- **Track assignment for `/feedback` tool:** slots into **dev's #27 MCP gateway track** as a standard `tools/*` primitive. It's a write-tool like any other — no special-case infra. If dev prefers it in #36 moderation track (since it feeds moderation-adjacent queues), that's fine — flag for dev to pick, but don't split; one owner.
- **§8 moderation:** `/feedback` issues that are moderation-relevant (abuse reports, user-disputes) auto-tag and route into the moderation review queue alongside `flag_content` — same UI surface, unified backend.
- **§13 onboarding:** all three feedback channels surfaced in onboarding copy + landing-page footer.
- **§22 succession runbook:** `SUCCESSION.md` §23.4 clause included.
- **§11:** Q18 resolved; see below.

### §23.6 Dev-day impact

- `/feedback` MCP tool: ~0.2 dev-days (GitHub REST API call + label wiring + chatbot-context pass-through).
- External-channel placeholders (Discord / subreddit / email): ~0.1 dev-days (mostly account creation + documentation, not code).
- **Total: +0.3 dev-days.**

Absorbed into revised §10 totals below.

### §23.7 What §23 does NOT do

- Does not build a custom feedback UI in the web app. GitHub Issues *is* the UI.
- Does not build auto-categorization / ML triage at launch. Chatbot-supplied labels from `/feedback` are good enough; manual review catches misroutes.
- Does not gate feedback by tier. T1 chatbot users, T2 hosts, T3 contributors, anonymous readers — all file Issues equally.
- Does not build response-time SLAs at launch. Set expectations low; let practice settle norms.

---

## §24. Product soul — Real World Effect Engine

**Host directive 2026-04-18 (Q21).** Named and load-bearing, not decorative. This section is the north star against which every other design choice is measured.

**Host verbatim:**

> "If it still feels gimmicky or like a toy [it's failing]. It's called 'workflow' for a reason — people should be using it every day at work and on their own projects, not just to play around with the system. We want to push real world utility. This is a real world effect engine."

### §24.1 What counts as success

Real-world artifacts and outcomes. Not engagement:

- **Books published** — self-published, traditionally published, best-sellers, niche runs. Counting the artifact, not the project.
- **Research papers peer-reviewed** — accepted by legitimate venues. Citation counts follow.
- **Work-tasks completed** — invoices processed, contracts reviewed, code refactored, tax returns filed, reports shipped. The stuff someone was going to do anyway, done faster or at higher quality.
- **Real projects shipped** — Workflow as load-bearing infrastructure, not as a demo.

Metrics the platform **does not optimize for**: DAU, session time, message count, "engagement," time-on-site, content-per-user.

### §24.2 Design implications cascading from this

**(a) Marketing copy sells outcomes, not tech.** Landing page (#35 web app) does not open with "AI-powered workflow engine." It opens with *"writes your book / processes your invoices / edits your research paper."* Tech is implementation detail, not headline.

**(b) Domains lean hard-utility.** Seeded + highlighted domains are: research paper, manuscript development, invoice processing, legal document review, code refactoring, data analysis, tax prep, contract review, clinical-trial reporting, financial modeling. Not: "chat for fun," "roleplay," "ask the AI a riddle." Permissionless domain creation (§15.8) still lets anyone tag anything — but the platform's *featured* rail is utility.

**(c) Discovery ranking favors real-world impact.** `discover_nodes` ranking (§15.1) adds the `real_world_outcomes` signal block — see §24.4. Nodes with demonstrated real-artifact output rank above similarly-rated nodes without.

**(d) Onboarding walks into real work.** Tier-1 first-run copy asks *"what real thing do you want to finish?"* — not "try this demo." #35 web app onboarding is redrafted around a project intake, not a tour.

**(e) Real-world validation badges.** Opt-in self-reports with optional third-party verification. A node whose output got peer-reviewed carries a badge. A node that generated a published book carries a badge. Badges are first-class `discover_nodes` signals.

**(f) Platform aesthetic is serious-utility.** No gratuitous AI sparkle. No "powered by [model]" stamping. Copy reads like a professional tool, not a demo. Visual language is instrumental: documents, tables, charts, not chat bubbles with glow.

### §24.3 Cascading updates to prior sections

- **§5.2 cascade step-3 ranking** — add `real_world_outcome_weight` as a ranking signal the daemon can read. Nodes with real-artifact badges weight heavier in public-demand matching. Preserves the "anything else the daemon reasons" latitude; this is one more signal available.
- **§15.1 `discover_nodes` response** — add `real_world_outcomes` block (see §24.4).
- **§2.4 tier matrix** — tier-2 daemon-host UI gets an **Impact Dashboard** alongside Earnings Dashboard (§5.1.1), showing real-world outcomes the daemon helped fulfill for others. Not just earnings — *what got made*.
- **§4 `TinyAssets-catalog/` export** — becomes a load-bearing source of real-world-outcome self-reports. Badges that land on nodes are sourced from `TinyAssets-catalog/outcomes/<node-slug>.yaml` entries users PR in. PR-ingest path validates + commits to Postgres. Commons-owned outcome history.
- **§13 onboarding copy** — re-examine every tier's onboarding text against the "finishing real work" frame.
- **§19 license** — unchanged (CC0 correctly enables real-world commercial reuse of outcomes).

### §24.4 `real_world_outcomes` signal block in `discover_nodes`

Added to the §15.1 response per candidate:

```
"real_world_outcomes": {
  "published_count":       int,    # published books / papers / shipped projects referencing this node
  "peer_reviewed_count":   int,    # outputs accepted by external legitimacy signal
  "production_use_count":  int,    # self-reported "used in production" markers
  "citation_count":        int,    # external citations where detectable (DOI, arxiv, etc.)
  "verified_count":        int,    # outcomes with third-party verification attached
  "last_outcome_at":       timestamptz,
  "badges":                [str]   # ["best_seller", "peer_reviewed", "production", ...]
}
```

Sample size + self-report honesty: the `verified_count` stands apart from `published_count` because self-reports drift; third-party verification (a DOI linking to the paper, a published ISBN, a GitHub repo tagged as using the node) anchors trust.

### §24.5 Badges + verification pipeline

- **Opt-in self-report:** user attaches "my book using this node series was published: ISBN-X" or "paper accepted at Nature: DOI-Y" via a `claim_outcome(node_id, kind, evidence)` RPC. Lands as an unverified badge.
- **Community + automated verification:** known-venue catalogs (CrossRef DOI lookup, ISBN validity check, GitHub repo public-ness check) run as cron. Verified badges display distinctly.
- **Fraudulent claims:** community-flaggable via §8 moderation — `flag_content` on an outcome claim. Same review queue as any other flag.

### §24.6 What §24 does NOT do

- Does not gate content by "utility" — permissionless domain creation (§15.8) lets anyone tag anything. Featured vs permitted is the distinction.
- Does not enforce "no fun" — roleplay and casual use are permitted; they just don't feature in the front rail.
- Does not measure "seriousness" algorithmically. The product-soul frame is a design principle, not a classifier.
- Does not promise verification for every outcome. Unverified self-reports are a valid tier; third-party-verified is higher signal but not required.

---

## §25. Always-up automation — "nothing is broken"

**Host directive 2026-04-18 (Q20).** Expected state after a two-week host absence: *"nothing is broken — issues auto-fixed on the fly, system always up and evolving."* Four living inputs sustain the system indefinitely: (a) chatbot users engaging, (b) daemon hosts running, (c) GitHub PRs evolving, (d) treasury wallet paying bills. Host becomes just another contributor.

§25 extends §22 succession: where §22 designs for *host absence*, §25 designs for *operational self-healing in the absence of any operator on any given day*.

### §25.1 Self-healing primitives

**Auto-rollback on CI failure.** Every merge to main triggers CI + canary deploy. If post-deploy health checks fail within N minutes, automated rollback to the last-green SHA. Human notification routes to the shared operations channel, not host-only.

**Auto-scale on quota pressure.** Supabase compute scales on sustained load per the plan's usage billing. Realtime connection count monitored; if approaching quota ceiling, an alert fires + auto-upgrade triggers a pre-authorized plan-level bump (up to a configured monthly spend cap — treasury-funded).

**Auto-retry with circuit-break.** MCP gateway + Realtime + OAuth provider calls are retried with exponential backoff; repeated failures open a circuit breaker that routes traffic to a degraded-but-working fallback (catalog reads from CDN snapshot, queue-don't-dispatch mode for requests).

**Dependabot / Renovate auto-PR.** Security patches auto-PR'd. Green-CI patch PRs auto-merge after 24-hour quiet window (configurable). Major-version bumps queue for human review.

**Stale-PR triage bot.** PRs with no activity for 30 days get a comment asking the author to refresh or close. After 60 days of silence, auto-close with a label so re-open is trivial.

**Flaky-test quarantine.** Tests failing intermittently get auto-labeled `flaky`, moved to a quarantine suite that doesn't gate merges. A queue surfaces flaky tests for human investigation. Prevents single-test failures from blocking green deploys.

**Auto-invite new mods on reputation thresholds.** Per §8: tier-2 users who hit earnability thresholds get auto-invited to the moderation review queue (still requires council approval to formally grant, but the invitation is automatic — removes host as a bottleneck for mod-onboarding).

### §25.2 Automated deploy pipeline — zero-human-gate for green-CI changes

- Every green-CI PR merge to main triggers production deploy automatically.
- No human deploy gate for routine changes. Major-version bumps flagged by convention (commit message prefix or label) still queue human approval — configurable.
- Deploy logs are public (via a shared dashboard); any contributor can see what shipped when and why.

**Exception:** schema migrations that touch user data. These require an explicit review-and-approve step from the moderator council (not host-specifically — any council member). Per §22 bus-factor design.

### §25.3 Community-visible monitoring

Not host-paged. Public by default.

- **Public status dashboard** at `status.tinyassets.io` — up/down per service, incident history, recent deploy log, treasury-balance sparkline.
- **Community-accessible logs** (redacted per §17 privacy) — any contributor can see error rates, failed-request reasons, common user friction points.
- **Open incident history** — post-mortems PR'd to `TinyAssets/` repo's `docs/incidents/`.
- **Alerts route to a shared Discord channel + GitHub Issues**, not just host's email.

### §25.4 Treasury wallet auto-pays bills (hard requirement post-mainnet-cutover)

Per §18 + §22: once the real-currency treasury multisig is live, it **auto-pays platform bills** as a standing commitment.

Implementation: a recurring signed transaction (or a permissioned spend policy in the multisig contract) authorizes monthly/weekly transfers to named operational addresses — Supabase invoice wallet, Cloudflare, Fly if used, GoDaddy renewal, GitHub Actions budget. Bills list is public in `SUCCESSION.md` (§22.3); any contributor can see what's due, what address pays it, what happens if treasury runs low.

Added to §18.6 settlement scope: `platform_config.operational_bill_schedule` — list of `{payee_address, amount, frequency, description}`. Monthly multisig-approved cron executes transfers.

### §25.5 No host-only buttons in production paths

Every production-side action reachable via at least one non-host contributor, subject to appropriate auth. Host's GitHub admin rights, treasury signatures, Cloudflare admin, Supabase project ownership — all role-granted, all transferable per §22 runbook.

### §25.6 Scale-audit amendment (§14 extension)

Load-test harness (track J) gets an **S7 auto-healing scenario** added to the scenarios list (S1–S6 per §14.8 dev #26 spec):

- **S7: auto-healing rehearsal.** Simulate a bad deploy → CI fails → auto-rollback fires → service recovers within N minutes. Simulate quota pressure → auto-upgrade fires. Simulate dependency flakiness → circuit-breaker opens → fallback serves traffic. Acceptance: each failure mode recovers without human intervention within the target SLO.
- **S11: parallel fan-out storm (§27.5).** 100 requests each with `fan_out: {mode: 'top_n', count: 10}` posted simultaneously → 1,000 simultaneous daemon claims, Realtime broadcasts multiply × 10. Acceptance: bid-channel fan-out + claim RPC hold at p99 <3s, no message loss, no claim deadlock. Caps per request validated (max 100 fan-out enforced by control plane).

Adds ~0.5 dev-days to track J (now 4–4.5d at full scope: S1-S6 + S7 + S11).

### §25.7 Dev-day impact

~+1.0–1.5 dev-days total across Q20 + Q21:
- **+0.3** track J for S7 auto-healing scenario.
- **+0.3** infra for auto-rollback + auto-scale policy wiring + public status dashboard.
- **+0.2** track M for treasury-wallet operational-bill auto-pay (multisig spend policy on Base).
- **+0.2** track K + front-end for `real_world_outcomes` signal block + badges rendering in `discover_nodes` + Impact Dashboard.
- **+0.2** infra for auto-PR bots (Dependabot / Renovate / stale-PR / flaky-test quarantine) + community-alert routing.

Folds into revised §10 totals below.

### §25.8 Cross-references

- **§5.2 cascade step-3:** `real_world_outcome_weight` as new available signal.
- **§8 moderation:** auto-invite new mods on reputation threshold; alerts route to shared channels.
- **§15.1 `discover_nodes`:** `real_world_outcomes` block added.
- **§18.6 treasury:** `operational_bill_schedule` + multisig permissioned spend for bill auto-pay.
- **§22 succession:** §25 extends §22 — §22 covers host-absence, §25 covers operational self-healing irrespective of any single operator.
- **§11:** Q20, Q21 resolved this round; see below.

### §25.9 What §25 does NOT do

- Does not promise 100% uptime. Promises graceful degradation + auto-recovery for known failure modes.
- Does not replace human judgment on security-critical decisions. Emergency rollback on a suspected-compromise deploy still routes to the moderator council for review before re-enabling.
- Does not autonomously upgrade to a bigger plan on runaway cost. Auto-upgrade has a spend cap; above cap, escalation to council.
- Does not do anomaly-detection ML at launch. Rule-based thresholds + human triage. Add ML later if volume warrants.

---

## §26. Invocation + attachment I/O — the "Workflow: X" pattern

**Host directive 2026-04-19 (Scenario A).** A user opens a fresh chatbot session, types `Workflow: payables`, attaches invoice PDFs. The chatbot *just knows what to do*. Output: a CSV **pushed into** the user's accounting software + individually-named invoice PDFs. No config, no wizard, no authentication dance per invocation.

### §26.1 The invocation pattern — three user states (A-follow 2026-04-19)

A user encounters `Workflow: X` in one of three states. The chatbot routes differently in each:

**State 1 — user does not have the TinyAssets connector yet.** The chatbot discovers Workflow alongside the user's other connectors in Claude.ai's connector catalog and offers to connect it self-service, from inside the chat. *"I can connect Workflow for you — shall I?"* → user consents → OAuth 2.1 + PKCE flow completes → connector live → original request proceeds. Zero leaving the chat surface.

**State 2 — connector present, first invocation this session.** `Workflow: <anything>` is assumed to be an invocation intent; chatbot routes via `discover_nodes` + the name-resolution rules below.

**State 3 — user has used Workflow before.** Claude's native project memory carries context ("last time you used `invoices-to-csv` and pushed to Voyager"); chatbot *just knows what to do* from past patterns. No cold-start friction; platform surfaces aggregate signals (§20.4 `typical_fulfillment_pattern`), chatbot surfaces per-user signal.

**Launch gate — Workflow MUST be in Claude.ai's connector catalog (Anthropic MCP directory).** State 1 is the primary onboarding path for tier-1 users and is zero-setup self-service *only* if the connector is listed. Submission to Anthropic's directory is a launch-readiness operations task, not nice-to-have. See §11 Q21-nav.

**Name resolution rules (States 2 + 3):**

**"Workflow: X"** is a natural-language convention, not a slash-command. The chatbot resolves `X` against the catalog via `discover_nodes` and invokes the best match.

- `Workflow: payables` → looks up node `payables-processor` (or closest match), dispatches.
- `Workflow: edit my novel` → looks up node `manuscript-editor` (top-rated), dispatches.
- `Workflow: cure cancer` → finds the `research-paper-pipeline` top-ranked + offers it.
- Exact slug match wins. Prefix/semantic match surfaces top 3 candidates; chatbot picks based on context + user cues. Top-N qualifier supported: `Workflow: top 5 book-editors` → returns ranked candidates, chatbot presents choice.

**Zero-setup ergonomics:**
- No per-invocation auth for the default path (chatbot's OAuth session covers it).
- No first-run wizard. The chatbot extracts intent + attachments; the node's manifest declares its inputs; the chatbot fills from context or asks one question if genuinely missing something.
- Fresh sessions work. The node + attachments are self-contained; not reliant on chat history.

### §26.2 Files as first-class I/O

Nodes declare their I/O shape in `concept.inputs` / `concept.outputs`:

```
inputs:
  - name: invoices
    kind: file-bundle        # N attachments, homogeneous MIME-type expected
    mime_types: ["application/pdf"]
    min_count: 1
  - name: company_name
    kind: string
    infer_from_chat: true    # chatbot fills from context if present; asks otherwise

outputs:
  - name: invoice_csv
    kind: file
    mime_type: "text/csv"
    filename_template: "{{company_name}}-invoices-{{date}}.csv"
  - name: renamed_pdfs
    kind: file-bundle
    filename_template: "{{vendor}}_{{invoice_number}}.pdf"
  - name: accounting_upload
    kind: connector-push
    connector: "voyager"     # see §28
    target: "accounts-payable"
```

**Chatbot-mediated file handling:**
- Input attachments land in the node's execution context via the MCP file-attachment primitive (already standard in Claude.ai / ChatGPT MCP clients).
- Output files return via the same primitive — chatbot presents them as downloadable deliverables with the declared filenames.
- Output `connector-push` kinds don't download — they complete at the user's tool (§28).

### §26.3 Cross-references

- **§15.1 `discover_nodes`:** name-resolution + top-N query mode (already supported; §26.1 codifies the invocation UX).
- **§27:** node authoring exposes the `concept.inputs/outputs` manifest shape; vibe-coded nodes can declare arbitrary I/O shapes.
- **§28:** `connector-push` outputs go through the connector catalog.

### §26.4 Dev-day impact

~+0.5 dev-days on track C (MCP gateway) for:
- File-attachment primitive handling in the tool surface.
- `concept.inputs/outputs` manifest parsing + validation.
- Name-resolution RPC + top-N qualifier parsing.

---

## §27. Node authoring surface — vibe-coding nodes (full primitives)

**Host directive 2026-04-19 (Scenario B).** A node where someone spent 20 hours building unique, never-designer-intended capabilities. The user — via chatbot — gets **ground-up control**: state, harness, tools, composition. No opinionated framework hiding power. This is the **largest single design-surface addition** in this fold.

### §27.1 Nodes are full programs, not templates

Rejection of any design pattern that boxes users into "you can do A, B, or C with nodes." The right framing: *"you can do whatever your chatbot can figure out how to build."* This reshapes node-authoring accordingly.

**Code visibility is architectural, not a toggle (B-follow 2026-04-19).** Every line of code the chatbot writes or edits is inspectable by the user. There is no "simple mode vs dev mode" flag — **one surface, adaptive exposure.** The chatbot decides what to surface based on user signal: casual phrasing → summary + outcome; technical phrasing → inline code view + diff review. Nerds who want to drop into the code and edit directly can, via the same chat surface. Co-design is the pattern: chatbot and user iterate together on node code, not "chatbot writes alone" and not "user writes alone."

Platform primitive: `/node_authoring.show_code(draft_id, view='full'|'diff'|'summary')` — the chatbot invokes this at whatever resolution the user signals. Returns the current node concept + harness + tools as readable code, with change-history and inline editability. This must be a tier-1 primitive at MVP (not deferred), because the B-follow "real nerds can actually edit the code" commitment applies day one, not v1.1.

### §27.2 Primitives exposed (the node-authoring API)

A node is a structured artifact with exposed primitives at every layer. The chatbot invokes these directly via MCP tool calls when the user is authoring/iterating. Layers:

**(a) State primitives.** TypedDict-like state shape declarations; read/write ops on state; reducers for accumulating fields (per PLAN.md hard rules #5). Chatbot can add/remove state fields, declare reducers, define state shape evolution across invocations.

**(b) Tool primitives.** The chatbot can attach tools to the node — LLM calls (any provider), HTTP fetches, file I/O, subprocess invocations (host-software per `project_node_software_capabilities`), database queries, connector pushes (§28). Tools are composable and the chatbot declares their signatures + wiring.

**(c) Harness primitives.** Orchestration — LangGraph nodes, edges, conditional routing, parallel execution (§27.5), checkpointing, retries, circuit breakers, error handling. The chatbot constructs the graph; the platform compiles it.

**(d) Composition primitives.** Sub-nodes can be invoked by name; outputs flow as inputs; the `parents uuid[]` + remix semantics from §15.3 extend — a vibe-coded node can declare "uses node X for step 2" and the lineage reflects it.

**(e) I/O primitives.** Per §26.2 — `concept.inputs/outputs` manifest with file-bundles, strings, JSON, connector pushes, structured objects.

### §27.3 The authoring surface — MCP tools

`/node_authoring` is a family of MCP tools exposed to the chatbot when a user is authoring:

```
/node_authoring.create_draft(intent: str, starting_template?: node_id)
/node_authoring.declare_state(field_name, type, default?, reducer?)
/node_authoring.attach_tool(name, kind, signature, impl_ref)
/node_authoring.declare_graph(nodes, edges, entry_point)
/node_authoring.compose_subnode(name, source_node_id, input_mapping, output_mapping)
/node_authoring.declare_io(kind: 'input'|'output', manifest)
/node_authoring.test_run(draft_id, sample_inputs)
/node_authoring.publish(draft_id, visibility, license?)
```

The chatbot drives these. The user says *"add a retry loop around the LLM call with exponential backoff"* — chatbot invokes the harness primitives. User says *"call this sub-node for step 3"* — chatbot invokes `compose_subnode`. User says *"what if I feed in PDFs instead of strings?"* — chatbot invokes `declare_io` and re-tests.

### §27.4 Sandboxed execution for drafts

Draft nodes run in a sandboxed context — Supabase Edge Function with resource quotas, not full-capability host daemon. `test_run` invokes the sandbox; the user sees real output, the platform sees bounded cost.

Full-capability execution (host software, arbitrary LLM, cross-host composition) only available after `publish` — and even then only on daemon hosts that accept the node's required capabilities (§5 + `project_node_software_capabilities`).

### §27.5 Parallel execution primitive

From Scenario C4 ("10 alternative next-books overnight"): a single request can fan out to N workflows.

**Shape:**
- `submit_request(..., fan_out: {mode: 'top_n', count: 10, domain: 'book-editing'})` — request lands in the inbox with N daemon claims needed.
- Cascade step-2 (paid) + step-3 (public) allow up to N simultaneous claims per request.
- Each claim runs independently; outputs aggregated.
- Chatbot presents N outputs; user selects or composes.

Scale implications (§14 amendment): one request × N fan-out means `bids:<capability>` channel can fan-out broadcast. N is capped at a reasonable ceiling (default 10, max 100) to bound contention.

### §27.6 Sandboxed dev environment — "full dev env when you want that power"

For tier-2 daemon hosts and tier-3 contributors who want to author nodes with low-level control:
- Tier-3: clone repo, author node as Python package, submit PR to `TinyAssets-catalog/` via export-sync path (§4 + §16).
- Tier-2: tray surface exposes a local node-authoring REPL that runs on their own daemon hardware. No platform quota.
- Tier-1 (the general case): chatbot-mediated authoring via §27.3 MCP tools. Sandboxed test runs. Platform-side publish.

All three paths write to the same node schema. Same `nodes` row, same `concept` / `instance_ref` split, same license, same discovery.

### §27.7 Cross-references

- **§2.4 tier matrix:** node authoring capability per-tier: T1 chatbot-mediated, T2 local REPL + MCP, T3 native code + PR.
- **§5:** daemon hosts must declare the capabilities a node needs; `required_capabilities` on the node concept (from `project_node_software_capabilities`).
- **§15.3 remix/converge:** works at primitive level — remix can take apart a state/tool/graph and re-compose, not just fork a template.
- **§17 privacy:** vibe-coded node definitions (concept layer) are public by default; instance data stays private.

### §27.8 Dev-day impact

**This is the largest single addition — ~2.5–4 dev-days** on a new track **N**:
- Authoring MCP tool family (~0.75d).
- Sandbox runtime for draft test-runs (Supabase Edge Function + resource quotas, ~1d).
- State/tools/graph primitives exposed to sandbox (~0.75d).
- Parallel fan-out orchestration on cascade (~0.5d — folds into existing cascade code in track E).
- Tray-side local REPL for T2 path (~0.5d).
- Tests + docs (~0.5d).

Deferral lever: ship §27 in "T1 chatbot-mediated only" mode at MVP (~2d), defer tray-REPL and native-PR full polish to v1.1. This still satisfies Scenario B for the T1 majority; T2/T3 get functional-but-rough surfaces.

### §27.9 Cross-cutting Qs raised

See §11 Q18 (node primitive API — Python vs WASM vs JSON-schema-driven IR) and Q19 (§27 MVP scope).

---

## §28. Two-way tool integration — connectors

**Host directive 2026-04-19 (Scenario A: push to Voyager).** Platform completion happens at the user's tool boundary, not at the platform boundary. "Here's your download" is a failure mode. "I pushed the CSV into Voyager; invoices are attached" is success.

### §28.1 Connector primitives

Every connector is a pluggable module that:
- Authenticates to the target service (OAuth, API key, local path access — per service).
- Exposes typed push/pull operations (`upload_file`, `create_record`, `send_email`, `open_issue`, `publish_post`, etc.).
- Is invokable via node output `connector-push` kind (§26.2) or via standalone `connector_invoke(name, action, payload)` RPC.

### §28.2 Launch connector catalog (proposed; subject to host Q17 below)

Tier-1 essential (target for MVP):
- **GitHub** — create issue, open PR, push file, create release.
- **Gmail / SMTP** — send email with attachments.
- **Google Drive / Dropbox / S3** — upload file.
- **Notion** — create page, add to database.

Tier-2 (post-MVP but early):
- **Slack / Discord** — post message.
- **arXiv / DOI-issuing services** — submit preprint (Scenario C3).
- **Webhook generic** — POST to arbitrary URL (fallback for anything not yet supported).

Tier-3 (community-contributed):
- Accounting software (Voyager, QuickBooks, Xero, etc.) — connectors built by users who need them, contributed via PR to `TinyAssets/` platform.
- Vertical-specific (journal-submission APIs, FDA-submission, publisher APIs, specialized tools).

### §28.3 Third-party connector pattern

Contributors add connectors via PR to `TinyAssets/connectors/<name>/` directory:
- Python module implementing `ConnectorProtocol`.
- Declares auth shape (OAuth app metadata, API key names, scopes).
- Tests against a mock/sandbox of the target service.
- Documentation in the connector's README.

Once merged, the connector is available platform-wide. Tier-1/2 users authorize per-service (OAuth flow) via a connector-manage UI in the web app.

### §28.4 Auth + consent

Connectors respect the privacy model (§17):
- OAuth scopes are per-connector, user-granted, revocable.
- Connector pushes never include `private`-flagged fields from instance data.
- Consent-on-first-use: chatbot asks "I need to authorize Voyager — OK to set up now?" before the first connector push for each service.
- Credentials stored in Supabase Vault with owner-only RLS.

### §28.5 Cross-references

- **§26.2 outputs:** `connector-push` output kind routes through §28.
- **§17 privacy:** connectors operate on concept-layer data by default; instance data requires explicit consent + `authorized: true` flag.
- **§19 license:** connectors are platform code (MIT) — part of `TinyAssets/` repo.

### §28.6 Dev-day impact

~+1.5 dev-days on track N + track C (MCP gateway):
- `ConnectorProtocol` + registry (~0.25d).
- Auth/consent flow integration (~0.25d).
- Launch-tier connectors (GitHub, Gmail, Drive, Notion) baseline implementations (~0.75d).
- Webhook-generic fallback + docs (~0.25d).

---

## §29. Chatbot behavioral patterns — scope extension + transparent privacy

**Host directive 2026-04-19 (Scenarios C1 + C2).** Two behaviors the chatbot runs during workflow invocation:

### §29.1 Autonomous scope-extension (C1 + C-follow)

> *"Told chatbot about my job → chatbot finished the work AND built a pipeline to push it out to the rest of the company."*

**Reshaped per C-follow 2026-04-19: platform equips, chatbot judges.** The earlier rigid "extend when low-risk / ask when high-risk" binary is replaced with a richer design:

1. **Platform provides raw material** — the privacy-principles + data-leak taxonomy catalog (§31). Every system point (ingest / storage / export / handoff / connector / daemon exec) has taxonomy entries naming what can leak where + what defenses apply. Chatbot accesses this via the `get_privacy_principles(context?)` MCP tool or `prompts/*` surface.
2. **Chatbot is the intent-interpreter** — it reads the user best, consults the catalog, applies judgment. Platform does NOT encode rigid rules.
3. **Three behaviors available when uncertain:**
   - **Ask the user explicitly** when intent or risk is genuinely ambiguous.
   - **Build a safer version than it would otherwise make** — degrade toward safety without always asking (reduces over-asking).
   - **Apply clear context + best practices** where the catalog is unambiguous — chatbot makes the call.
4. **Scope-extension hint primitive preserved** — nodes can declare `extensions: ["push to accounting software", "notify finance team", "archive originals"]`. Hints, not commands.

**Continuous consultation.** The catalog is consulted not just at first design — also during iteration, remix from existing nodes, and cross-node comparison. Every action that could touch sensitive data passes through §31.

**No rigid guardrail list.** Prior draft's "extend only when instance data doesn't leave consent boundary / no paid-service charge / outcome reversible" is now a *catalog entry*, not a platform-enforced rule. Same content, different shape: the principles live in §31 where the chatbot can read + reason + explain them, not hardcoded in a gatekeeping function.

### §29.2 Transparent privacy reasoning (C2)

> *"What about corporate privacy + IP? Chatbot explained inferred best practices + flagged what it always asks about."*

Extends §17 privacy-per-piece. The chatbot:
- Runs its §17 per-piece classification on every concept field being published.
- **Surfaces its reasoning when asked** (or proactively when a sensitive-looking field is involved): *"I'm marking the vendor names public because they're generic invoice-processing examples; the dollar amounts private because they identify your company's cash flow; the invoice PDFs stay on your disk. Want me to adjust?"*
- **Names the policies it always asks about** rather than inferring: credentials, auth tokens, anything with PII, anything with compliance implications (HIPAA, GDPR, SOX, etc.).
- Records decisions in `artifact_field_visibility` per §17.2 with `decided_by: 'chatbot'` + `rationale: <narrated text>`.

### §29.3 Platform role

These patterns are chatbot-behavioral — the chatbot implements them, the platform provides the data surface (§17 + `extensions` hint array). Platform does not auto-extend scope; chatbot decides + narrates.

### §29.4 Cross-references

- **§17 privacy:** extends with narration + proactive-ask-on-sensitive behavior.
- **§26.2:** extensions hint field added to node manifest.

### §29.5 Dev-day impact

~+0.5 dev-days — mostly prompt engineering on the chatbot-facing MCP prompt surface + the `extensions` metadata field in node schema. Platform code is minor; most behavior lives in chatbot prompting + runbook docs.

---

## §30. Real-world handoff pipeline

**Host directive 2026-04-19 (Scenario C3: cure cancer).** Platform actively routes outputs to real external validators — not "here's the output, take it from here." The platform treats the **external handoff** as a first-class fulfillment step.

### §30.1 Handoff targets — first-class node outputs

Nodes can declare real-world-handoff outputs. Examples:

- `arXiv` — submit preprint via arXiv API.
- `DOI` (CrossRef) — register DOI for a published artifact.
- `GitHub Release` — publish a versioned release from a node-produced artifact.
- `ISBN registration` — register ISBN for a self-published book.
- `Journal submission` — submit manuscript via a journal's submission API (venue-specific).
- `FDA submission` (long-tail) — submit regulatory filing via FDA systems.
- `Patent filing` — submit via USPTO API.
- `Publisher API` — hand off to publisher-specific systems.

### §30.2 Handoff as connector

Same shape as §28 connector — a handoff is a connector with a well-known real-world semantic:

```
outputs:
  - name: paper_submission
    kind: connector-push
    connector: "arxiv"
    target: "cs.AI"
    declare_handoff: true    # marks this as a real-world-outcome-generating push
```

**Handoff side effects:**
- On successful push, platform automatically logs an outcome claim (§24.5) with evidence from the handoff (arXiv URL, DOI, etc.).
- Outcome claim is pre-verified (handoff succeeded = third-party system accepted the artifact), so it lands as **verified** in `real_world_outcomes` without further proof.
- Badge auto-updates on the originating node; citation / reference tracking begins from this moment.

### §30.3 Catalog + third-party handoffs

Launch handoffs (in `TinyAssets/connectors/` per §28):
- arXiv, CrossRef (DOI), GitHub Releases, ISBN-US registration.

Community-contributed handoffs (post-launch, via PR):
- Journal submissions (venue-specific).
- Regulatory filings (venue-specific).
- Publisher APIs.

### §30.4 Cross-references

- **§24 product soul:** handoffs are the primary route for real-world-outcome validation; badges + signals flow from here.
- **§28 connectors:** handoff is a connector subtype with verified-outcome-claim side effect.
- **§15.1 `discover_nodes`:** `real_world_outcomes.verified_count` increments from handoff events.

### §30.5 Dev-day impact

~+1.5 dev-days on track N:
- Handoff-kind connector protocol (auto-outcome-claim) — ~0.5d.
- Launch-tier handoffs (arXiv, DOI/CrossRef, GitHub Releases, ISBN) — ~0.75d.
- Auto-badge + outcome verification pipeline — ~0.25d.

---

## §31. Privacy principles + data-leak taxonomy catalog

**Host directive 2026-04-19 (C-follow).** Platform ships a maintainable catalog of privacy principles and data-leak risks — one entry per system point — that the chatbot reads to make scope-extension, publishing, and safety calls. Platform equips; chatbot judges. Extends §17 privacy-per-piece with the reference material the chatbot consults.

### §31.1 Shape of the catalog

Lives in the `TinyAssets/` repo at `docs/privacy/principles.yaml` (or equivalent). Living document, PR-reviewed like any other platform code (§16). Each entry is a structured record:

```
- id: ingest-mcp-tool-call
  system_point: "MCP gateway — user tool invocation"
  what_flows: "user's natural-language prompt + attached files + chatbot-summarized context"
  leaks_possible:
    - "user's identity if attached files contain PII"
    - "organization name if prompt mentions employer"
    - "credentials if user accidentally pastes them"
  defenses:
    - "per-field concept/instance split (§17.2)"
    - "chatbot pre-redaction before write (§29.2)"
    - "file-scanning for credential patterns"
  chatbot_guidance: |
    When the user attaches files with potential PII, chatbot:
    - Names the risk (I can see this file may contain names, emails, account numbers).
    - Asks whether those fields should be redacted before any platform write.
    - Defaults to private unless user signals public intent.

- id: daemon-execution-subprocess
  system_point: "Host-side daemon — arbitrary tool / subprocess invocation"
  what_flows: "tool output to host process + back into state"
  leaks_possible:
    - "host-local file paths leaked into output"
    - "environment variables if tool echoes them"
    - "other-process memory if misused"
  defenses: ...
  chatbot_guidance: ...

- id: connector-push-external
  system_point: "§28 connector push to external service (GitHub, Gmail, Drive, etc.)"
  what_flows: "node output payload + OAuth-scoped credentials at platform edge"
  leaks_possible: ...
  defenses: ...
  chatbot_guidance: ...

# Plus entries for: handoff-real-world (§30), catalog-export (§4),
#                    realtime-broadcast (§2), paid-bid-announcement (§6),
#                    moderation-review (§8), export-my-data (§21),
#                    cross-chatbot-memory-leak (§20.4), etc.
```

### §31.2 MCP access surface

Two primitives chatbots use:

```
get_privacy_principles(context?: str, system_points?: [str]) ->
  [{ id, system_point, what_flows, leaks_possible, defenses, chatbot_guidance }, ...]

inspect_leak_risk(artifact_ref, system_point) ->
  { risk_summary, applicable_principles, suggested_redactions, questions_to_ask_user }
```

- `get_privacy_principles` retrieves catalog entries by topic filter; cheap, can be called at any point in a workflow invocation.
- `inspect_leak_risk` is a higher-level helper — the chatbot hands an artifact and a system point, platform returns the catalog-informed risk assessment. Chatbot combines with user intent to make the call.

### §31.3 Minimum v1 catalog (launch scope)

Recommend ~8–12 entries covering the load-bearing system points at MVP:

1. MCP tool-call ingest (user → chatbot → platform).
2. Concept-layer publish (chatbot → Postgres public rows).
3. Instance-layer store (chatbot → owner-private Supabase Storage).
4. Connector push — inbox-like (Gmail, Drive, Notion, S3, generic webhook).
5. Connector push — public (GitHub Issues / Releases, Discord, subreddit).
6. Real-world handoff (arXiv, DOI, ISBN).
7. Daemon-execution subprocess / host-software invocation.
8. Realtime broadcast / presence channel.
9. Paid-bid announcement (broadcast to potential claimers).
10. Catalog export (`TinyAssets-catalog/` public repo snapshot).
11. Data export (`export_my_data`).
12. Account deletion (wiki-orphan + instance hard-delete).

Each entry ~20–60 lines in the YAML. Host Q23-nav below: confirm scope + priority ordering.

### §31.4 Maintenance posture

- **Living document.** Community + moderators + tier-3 contributors PR new entries or update existing ones as new risks emerge.
- **Version-controlled.** Every change is git-tracked; chatbot reads the *current* version at invocation time (platform caches).
- **Chatbot-consulted, not -bypassed.** The catalog is the *authoritative* reference; chatbot may not invent principles not grounded in an entry. Principles that don't exist yet get PR'd in, not patched around.
- **CC0 license** (per §19) — catalog is also content, reusable by other platforms or OSS projects.

### §31.5 Cross-references

- **§17 privacy-per-piece:** concept/instance schema is the mechanism; §31 is the reference material.
- **§29 chatbot behavioral patterns:** `get_privacy_principles` + `inspect_leak_risk` are the tools §29.1 specifies.
- **§28 connectors + §30 handoffs:** each connector should have a corresponding catalog entry describing what leaks at its boundary.
- **§16 collab model:** catalog lives in `TinyAssets/` main repo (platform code + docs), PR-reviewed per the tier-3 fork-and-PR model.
- **§11:** Q23-nav below — confirm launch-scope catalog entries.

### §31.6 Dev-day impact

~+0.5 dev-days:
- Catalog authoring (12 entries, ~30 lines each) — ~0.25d.
- `get_privacy_principles` + `inspect_leak_risk` MCP tools + caching — ~0.25d.

### §31.7 What §31 does NOT do

- Does not enforce the principles in code. Enforcement is §17 (RLS, column-level roles, owner-only reads). §31 is the reference material the chatbot reads to reason.
- Does not attempt exhaustive coverage at launch. 12 entries for 12 system points; gaps get PR'd in as they emerge.
- Does not replace chatbot judgment with policy rules. The "three behaviors" (ask / safer-version / apply context) stay chatbot-driven; catalog informs, does not dictate.

---

## §32. Node autoresearch optimization

**Host directive 2026-04-19.** Every workflow node can attach an optional **autoresearch optimization spec**. User sleeps; chatbot + daemons autonomously iterate the node overnight within a user-set metric + budget, parallelized across the host pool. Reference implementation: [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — translated to Workflow below.

**Why day-one, not v1.1.** This *is* the platform's differentiator vs competitor workflow tools. "You build for a while, post 1000 runs on each node before bed, wake up to your entire workflow optimized" is a Q21 real-world-effect moment of the same class as Scenario C4 — generalized from "run the same workflow N times" to "let the workflow improve itself N times." Ships with MVP.

**3-layer lens (see `project_chain_break_taxonomy.md`):**

| Layer | What it provides |
|---|---|
| **System** | Optimization schema + bid-market `autoresearch` kind + fixed-harness isolation + merge-back flow + budget enforcement + parallelism primitives |
| **Chatbot** | Drafts `optimization_spec.md` from user intent (simple or complex), asks clarifying questions, summarizes results at wake-time, surfaces top-N for human review |
| **User** | The node worth optimizing + the metric they care about + the budget they're willing to spend |

All three required. System without the other two = expensive idle. Chain-complete = overnight improvement as a reliable service.

### §32.1 The 3-role pattern (Karpathy translation)

Karpathy's autoresearch separates three concerns into three artifacts, editable by three roles. Workflow translates:

| `karpathy/autoresearch` artifact | Workflow equivalent | Edited by |
|---|---|---|
| `program.md` — agent instructions / skill-like | Per-node `optimization_spec.md` (markdown) — what to optimize, how, bounds, merge policy | **User** (or user's chatbot, vibe-coded per §27) |
| `train.py` — what the agent modifies | The node's **editable surface** — explicit list of field-paths in the node's `concept` blob (prompt text, hyperparameters, few-shot examples, tool-choice thresholds) | **Agent** (daemon, per iteration) |
| `prepare.py` — fixed harness + metric | Per-node **test fixture + objective function** — never edited during optimization, locked at attach-time | **User** at node-creation, then locked until next explicit rev |

**Why this separation is load-bearing.** The harness is the truth anchor. If the agent could edit it, it would learn to game the metric. The editable surface is the mutation space. The optimization_spec.md is the agent's compass. Three separate artifacts with three separate editors is the exact karpathy pattern, not coincidence.

### §32.2 Simple mode — friction floor

Minimum viable `optimization_spec.md` (one file, markdown with a small YAML frontmatter):

```
---
metric: acceptance_score
direction: maximize
editable_surface:
  - concept.prompt
  - concept.few_shot_examples
budget:
  runs: 1000
  wall_clock_hours: 8
  usd_cap: 5.00
merge_policy: auto_accept_if_improves_by: 0.02
---

# optional natural-language intent

Optimize invoice-OCR prompt for higher vendor-name-accuracy. Test fixture
has 50 labeled invoices. Keep tone professional.
```

Friction budget: **under 60 seconds** from "I want to optimize this" to "submitted." Chatbot scaffolds the YAML; user confirms or tweaks. Matches GitHub issue template friction.

### §32.3 Complex mode — no ceiling

User's `optimization_spec.md` can be as expressive as they want. Goes beyond simple YAML frontmatter into full narrative + explicit search-strategy declarations:

- **Search strategies** — grid, random, evolutionary, bayesian (e.g. via Optuna), hand-authored curricula.
- **Constraints** — structural (graph shape must not change), resource (max tokens per run), content (must preserve certain fields verbatim).
- **Multi-objective tradeoffs** — Pareto frontiers across accuracy vs latency vs cost.
- **Custom evaluation harnesses** — reference to a separate harness node (per §27 vibe-coding — harnesses are nodes too).
- **Early stopping** — if metric plateaus, halt within N iterations.

Same platform primitives; user's spec carries more of the agent's behavior. No artificial cap. Complexity is a user choice; simple-mode users aren't penalized for not reading beyond the frontmatter.

### §32.4 Schema additions (§2 cross-ref)

Spec #25 `nodes` table gains:

```sql
nodes ADD COLUMN optimization_spec_ref   text NULL;        -- pointer to markdown in concept blob or separate location
nodes ADD COLUMN editable_surface        jsonb NULL;        -- array of JSON-pointer paths into concept
nodes ADD COLUMN test_harness_ref        text NULL;         -- node_id of the harness node (harnesses are nodes)
nodes ADD COLUMN optimization_metric     text NULL;         -- e.g. "acceptance_score"
nodes ADD COLUMN optimization_direction  text NULL;         -- "maximize" | "minimize"
```

New `optimization_runs` table (append-only audit + candidate store):

```sql
CREATE TABLE public.optimization_runs (
  run_id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id          uuid NOT NULL REFERENCES public.request_inbox(request_id),
  node_id             uuid NOT NULL REFERENCES public.nodes(node_id),
  iteration_n         int  NOT NULL,
  candidate_concept   jsonb NOT NULL,       -- the concept variant this iteration tested
  candidate_hash      text NOT NULL,         -- sha256 of candidate_concept, dedup across daemons
  metric_value        numeric NULL,          -- null if failed / timed out
  status              text NOT NULL CHECK (status IN ('running','completed','failed','timeout','dedup')),
  daemon_host_id      uuid REFERENCES public.host_pool(host_id),
  started_at          timestamptz NOT NULL DEFAULT now(),
  completed_at        timestamptz NULL,
  wall_ms             int NULL,
  tokens_used         int NULL,
  cost_usd            numeric(10,4) NULL
);

CREATE INDEX oruns_request_metric ON public.optimization_runs (request_id, metric_value DESC) WHERE status = 'completed';
CREATE INDEX oruns_candidate_dedup ON public.optimization_runs (request_id, candidate_hash);
```

Spec #25 edit lands in the next spec-sharpening pass (gap already tracked by drift audit §64).

### §32.5 Bid-market + cascade integration (§5.2 + §6 + §18)

**New request kind: `autoresearch`.** Payload:
```
{
  "kind": "autoresearch",
  "node_id": uuid,
  "budget": { "runs": int?, "wall_clock_hours": float?, "usd_cap": numeric? },
  "deadline": timestamptz?,
  "merge_policy": "auto_accept_if_improves_by" | "human_review_always" | "human_review_if_delta_below"
}
```

Routes through the existing `submit_request` RPC per §20.4; `capability_id` includes the declared `autoresearch_executor` capability plus the node's LLM-provider requirement. (Request kind = `autoresearch`; capability = `autoresearch_executor` — disambiguated to avoid confusion between the user-facing verb and the daemon-side fulfillment role.)

**New daemon capability: `autoresearch_executor`.** Daemons opt in via the tray (`host_pool.capabilities` row). Bid-channel `bids:autoresearch_executor×<llm_model>` broadcasts to subscribed daemons per §14.1 push-not-poll pattern. Per-capability-shard keeps the §14 scale primitives intact.

**Cascade step-2 naturally absorbs `autoresearch` bids.** The highest-value/effort paid requests for a daemon in always-active mode will often be optimization runs — they're fungible, deadline-bounded, and fan out cleanly. No cascade logic change needed; the new request kind + capability are the only additions.

**Settlement per §18 hybrid.** 1000 iterations at <$1-each batches to a single weekly on-chain settlement; ≥$1-each iterations settle per-bid. `self_hosted_zero_fee` branch (§18.3 pseudocode) applies when requester == daemon-host — your own daemon optimizing your own node is free.

### §32.6 Parallelism — 1000 runs fans cleanly

Existing §14 scale primitives carry the load:
- **Claim.** Each iteration is a row in `optimization_runs` with `status='running'`; daemons claim via RPC with `SELECT FOR UPDATE SKIP LOCKED` against `status='pending'` and a monotonic `iteration_n` assignment. No two daemons claim the same iteration.
- **Dedup.** Each daemon commits a `candidate_concept` + `candidate_hash`. The control plane rejects duplicates — if two daemons would independently test the same candidate (rare under diverse search strategies, common under grid search), the second gets `status='dedup'` and moves on without re-running the harness.
- **Budget enforcement.** Total runs / wall-clock / $ tracked against the request's declared budget. When budget exhausts, control plane flips remaining pending rows to `status='timeout'` and proceeds to merge-back.

At 1000 iterations across N daemons where N depends on marketplace capacity, expected runtime is N-scalable. Host's "1000 runs overnight" is a budget; throughput is market-scheduled.

### §32.7 Merge-back flow

After budget exhausts or deadline hits:

1. **Aggregate.** Control plane SELECTs top-N candidates by `metric_value` ordered per direction (maximize/minimize). N default = 5, configurable per spec.
2. **Apply merge_policy.**
   - `auto_accept_if_improves_by: δ` — if top candidate's metric beats baseline by ≥δ, it becomes the new node `concept`. Normal wiki-edit per §16 (versioned row increments, presence-soft-lock aware). Attribution: the daemon host that produced the winning candidate gets credit in the commit's provenance trailer, user-as-requester is primary author.
   - `human_review_always` — no auto-merge. Chatbot presents top-N for user review at wake-time; user picks one (or none).
   - `human_review_if_delta_below: δ` — auto-merge if δ exceeded, else present for review. The practical default — conservative for close calls, autonomous for clear wins.
3. **Notify.** User's chatbot (at next interaction) summarizes: "your 847-iteration overnight run on `payables-processor` improved accuracy from 0.81 to 0.89 (+10%). Top candidate merged per your `auto_accept_if_improves_by: 0.02` policy. 3 runner-ups available for manual review."

Merged change = normal node edit. All §16 wiki-open primitives apply (rollback-able, provenance-chained, publicly-attributable per §19 CC0). Rejected candidates stay in `optimization_runs` for future remix material.

### §32.8 Chatbot role (§29 extension)

Per-user chatbot handles three conversational moments:

**(a) Spec authoring.** User says *"I want this node to improve itself tonight — reduce invoice vendor-name mismatches."* Chatbot:
- Identifies node from conversational context.
- Proposes a simple-mode spec (one metric, 1-3 editable fields, budget suggestion based on historical rates per §15.1 `typical_fulfillment_pattern`).
- Asks 0–2 clarifying questions (what counts as "improved"? should it still keep tone professional? specific vendors to prioritize?).
- Drafts `optimization_spec.md`, shows user, lets them edit.

**(b) Submission.** Chatbot fires `submit_request(kind='autoresearch', ...)`, confirms budget + deadline, returns request_id.

**(c) Wake-up summarization.** On next interaction after optimization completes:
- Pulls results via discovery / status APIs.
- Summarizes metric delta, iterations, cost, top-N candidates.
- If merge_policy auto-accepted, confirms commit; if pending review, surfaces top-N.
- Proactively offers follow-up (per §29 scope-extension): *"Happy with the new prompt? Want me to queue an overnight run on the next node in your branch?"*

**Vocabulary discipline (per `feedback_user_vocabulary_discipline.md`, nuanced for `autoresearch`).** *"autoresearch"* is a **recognized term** from [@karpathy's autoresearch repo](https://github.com/karpathy/autoresearch) — AI-forward users recognize it on sight, and the pattern arrives pre-primed. Chatbot can and should use the word "autoresearch" with users who know it (tier-2/3, AI-aware tier-1). For users unfamiliar, translate: "overnight improvement run" / "1000 experiments tonight to find a better invoice-reader prompt." Reserve deeper engine terms (`autoresearch_executor`, `candidate_hash`, `capability_id`) for tier-2/3 contexts where the user invites technical depth.

**Brand attribution.** Karpathy's repo is MIT-licensed; public idea; credit is the right posture. §32 preamble cites the reference.

### §32.9 Real-world-effect-engine alignment (§24 cross-ref)

This feature is the clearest Q21 real-world-effect moment across every persona:

- **Maya (tier-1).** Her invoice-OCR node currently drifts on vendor names (grievance-LIVE-F-vendor-naming from Session 1 predictions). Set metric = vendor-name-match-rate, editable_surface = prompt + few-shots, budget = 100 runs on her 12-invoice April batch. Sleeps. Wakes to an optimized prompt that halves her manual-merge time. Real workflow, real hours saved, real monthly close done faster.
- **Devin (tier-2).** His continuity-check node (Session 2 mock, Track N). Metric = continuity-error-false-positive-rate against a hand-labeled 20-chapter corpus. Budget = 500 runs on his RTX 4070 overnight, `self_hosted_zero_fee` branch means $0 cost. Wakes to an optimized node that flags real continuity breaks without noise.
- **Ilse (tier-3).** Her research-paper critique prompt. Metric = agreement with peer-reviewer judgment on a known-good 10-paper sample. Budget = 200 runs, $5 cap. Wakes to an improved critique node she can contribute back to the commons.

Every persona, every passion project, directly accelerated. "Real world utility is the only valid use case" (§24) — autoresearch makes every node in the catalog more useful tomorrow than it was today.

### §32.10 Scale audit amendment (§14 cross-ref)

Track J load-test harness gains **S12: autoresearch fan-out under budget pressure**:

- Simulate 100 concurrent `autoresearch` requests each with `budget.runs=100`.
- 10,000 iteration rows land in `optimization_runs` over ~2 minutes.
- Assert: no SKIP-LOCKED contention cliff (§14.1 pattern holds), no duplicate-candidate work loss (dedup index enforces), no budget-exhaustion race (single-writer atomic update on request budget).
- Per §14.1 we already validated SKIP LOCKED ceiling is ~128 concurrent workers; autoresearch's dispatch is push-via-Realtime per §14.1 claim-RPC pattern so the cliff doesn't apply. S12 verifies.

Adds ~0.2d to track J total (now 4.2–4.7d).

### §32.11 Three-layer-lens applied

Per `project_chain_break_taxonomy.md` categories:

- **System → Chatbot orientation gap (to prevent).** Chatbot must know `autoresearch` is a first-class primitive when user says "optimize this." `control_station` prompt directive required: *"When a user asks to optimize or improve a node, use the `submit_request(kind='autoresearch', ...)` path; draft an `optimization_spec.md` with the user before submitting."*
- **System → Chatbot primitive gap (to prevent).** Chatbot needs introspection of node's `editable_surface` + `test_harness_ref` to propose sensible spec defaults. `discover_nodes` response (§15.1) extends with these fields for optimization-eligible nodes.
- **System → Chatbot vocabulary gap (to prevent).** `autoresearch` is recognized vocab — chatbot uses it verbatim with AI-aware users; translates for unfamiliar users. Deeper engine terms `autoresearch_executor`, `candidate_hash`, `capability_id` stay out of chatbot-to-user surface unless user signals technical depth.
- **Chatbot → User (intrinsic).** Wake-up summary quality depends on chatbot. This is the one interface-2 concern in autoresearch — if chatbot surfaces 1000 raw iterations instead of top-N with delta commentary, user drowns. Wake-up prompt template discipline matters.

### §32.12 §10 dev-day estimate

New track **O** in §10:

| Track | Dev | Rough dev-days | Notes |
|---|---|---|---|
| **O — Node autoresearch optimization** | dev | 3–3.5 | Schema additions (0.5) + `autoresearch` request kind + `autoresearch_executor` capability registration (0.75) + simple-mode UI scaffold (1.0) + merge-back flow + attribution (0.5) + chatbot prompt scaffolds (0.25) + tests + S12 load-test add (0.5). Depends on A (schema), E (paid-market), K (discovery), N (authoring) — all pre-existing dependencies. Parallelizable with existing tracks post-A. |

Net §10 delta: **+3–3.5 dev-days.** New totals: **~22.8–27d with two devs, ~30.5–32.5 serial** (adds to the post-#66-drift-reconciliation baseline of ~19.8–23.5). Still "weeks not months"; recommended MVP-cut (§70 narrowing) becomes ~25–28d upper bound if autoresearch ships at MVP.

**Ship or defer to v1.1?** Host directive says day-one, not v1.1. Matches Q21 product-soul lens and differentiates against competitors. Recommend ship at MVP; trim elsewhere if dev-day pressure rises (track J defer floors still available).

### §32.13 New host Qs for §11

**Q29-nav — OPEN (simple-mode DSL shape — YAML frontmatter vs inline spec vs separate file).** §32.2 proposes YAML frontmatter + optional narrative body. Alternatives: pure inline chat ("metric: x, direction: max, budget: 1000 runs" in natural language, chatbot converts) or separate file per node. Recommend YAML frontmatter — human-readable, versionable under §16 wiki, matches karpathy's `program.md` minimalism.

**Q30-nav — OPEN (budget-exhaustion behavior).** When budget exhausts mid-run, current proposal flips remaining pending rows to `status='timeout'` and proceeds to merge-back. Alternative: best-candidate-so-far auto-submits as partial result. Recommend timeout-then-merge; "partial result" is ambiguous, "here's what we got in your budget" is honest.

**Q31-nav — OPEN (merge-conflict resolution at scale).** If two concurrent `autoresearch` requests on the same node finish overlapping windows, who wins at merge-back? Recommend: per §14.3 optimistic CAS with `version` column — whichever merge-commit lands second must resolve against the updated baseline; if metric no longer beats the new baseline, user is asked to review.

### §32.14 What §32 does NOT do

- Does not optimize without a user-provided metric. The metric is the compass; platform does not infer one.
- Does not edit the harness. Harness is locked at attach-time; changing it resets the optimization history (a new spec attaches to a new harness).
- Does not gate the complex mode. Users can express whatever their chatbot can encode; platform does not limit search strategies or objective functions.
- Does not run against private-instance data by default. `optimization_spec.md` + test harness live in the concept layer (public by default); instance data stays owner-local per §17. Users who want to optimize against their own instance data run `self_hosted_zero_fee` branch on their own daemon.
- Does not auto-merge non-improving candidates. Baseline always wins ties. Attribution preserved even for rejected candidates (they stay in `optimization_runs` as remix material).

---

## §33. Evaluation layers — the through-line

**Host directive 2026-04-19.** *"Similar to [karpathy autoresearch] and similar to the judges from the fantasy branches we need to think about how evaluation layers work, that's what this really all is."* Names an insight that's been latent across §8, §15, §16, §18, §24, §5.2, §32: every improvement loop runs on **evaluation**. The platform is an evaluation-driven optimization substrate wrapped in a workflow-design product. Naming this explicitly is load-bearing because it reveals a primitive (`Evaluator`) that was about to get re-invented in every surface.

### §33.1 Is this unification genuine or forced? Honest audit

Navigator audited eight surfaces. **Six genuinely collapse. Two partially collapse — they fit the primitive for *their* evaluation step but their surrounding workflow is distinct enough that they should not *structurally* inherit from `Evaluator`.**

| Surface | Current location | Collapses under `Evaluator`? | Why |
|---|---|---|---|
| **Fantasy scene judges** (legacy `domains/fantasy_daemon/eval/criteria.py` — reference impl via `workflow.protocols.EvalCriteria`) | LLM-judge + deterministic rubric, returns bool/reason | **YES — full.** This IS the reference pattern; extract it. |
| **Autoresearch metric** (§32) | Fixed harness + numeric objective | **YES — full.** Metric function = evaluator returning score. `test_harness_ref` IS an evaluator. |
| **Real-world outcome verifiers** (§24/§30 arXiv / CrossRef / ISBN) | External API checks, boolean-ish with evidence | **YES — full.** External-API evaluators. Shape identical. |
| **Discovery ranking signals** (§15 `public_demand_ranked`, node quality aggregates) | Numeric scores from counts/CAS/vectors | **YES — as aggregation of evaluator results over time.** Individual signals (success_count, usage_count) are evaluator-emitted facts; the materialized view is an aggregation function over them. |
| **Paid-market bid acceptance** (§18 settlement verdict) | Verdict: accepted/refunded/disputed + evidence | **YES — full.** Acceptance check is an evaluator (did the claimed output satisfy the request?). Cost field applies directly. |
| **Moderation rubric** (§8 + `moderation_rubric.md`) | Community vote + rubric check + human-backstop | **PARTIAL — the judgment step collapses, the queue/role machinery does not.** The rubric-check-and-vote IS an evaluator; the `moderation_flags` table + `admin_pool` escalation + appeals process is workflow orchestration around the evaluator. Moderation *uses* Evaluator as a primitive; it doesn't *inherit* from it. |
| **Remix/converge ratification** (§15.3, §16) | Per-source editor consent + optional merge evaluator | **PARTIAL — same pattern as moderation.** Ratification-decision is an evaluator (is this merge improvement?); multi-party ratification protocol + proposal lifecycle is workflow orchestration. |
| **Cascade step-3 ranking** (§5.2) | Daemon's "what to work on next" scoring | **NO — daemon's local ranking is not evaluator-shaped.** It's a *consumer* of evaluator outputs (request signals, upvote_count, improvement_cycle_id) but the cascade-step logic itself is a scheduling policy, not an evaluation of an artifact. Keep separate. Calling this an `Evaluator` would force the abstraction. |

**Summary: 5 fully collapse, 2 partially collapse (evaluator-consuming but not evaluator-inheriting), 1 stays distinct.** Unification is genuine but not total. This is a real abstraction worth shipping, not a forced flattening of everything.

### §33.2 The `Evaluator` primitive

Minimum shape:

```
evaluate(artifact, context, policy?) -> {
  score:        numeric,           # comparable; signed per evaluator's direction
  verdict:      enum,              # accept | reject | needs_revision | uncertain
  rationale:    text,              # human-readable "why"
  evidence:     jsonb,             # what was checked, structured
  evaluator_id: uuid,              # attribution + audit
  ran_at:       timestamptz,
  cost:         jsonb              # { usd?, tokens?, wall_ms, external_api_calls? }
}
```

**Inputs.**
- `artifact`: the thing being evaluated — a node concept, a draft output, a merge candidate, a bid-completion claim, a moderation report subject, a research-paper submission handle.
- `context`: everything the evaluator needs that isn't the artifact itself — reference data, gold sets, thresholds, prior runs, related artifacts.
- `policy` (optional): evaluator-specific configuration — temperature, strictness, LLM model to judge with, how many tiers to invoke.

**Substrates (non-exhaustive; platform supports all):**
- **LLM-judge** — fantasy scene evaluator, moderation auto-review, autoresearch metric when objective is LLM-assessed.
- **Rubric function** — deterministic cheap checks; fantasy `_check_scene_coherence` pattern is the reference.
- **External API** — arXiv indexed, DOI minted, ISBN valid, GitHub release published; outcome-verifiers per §30.
- **Human vote** — community flagging (§8), convergence ratification (§15.3C), merge review.
- **Vector-similarity** — semantic match between artifact and reference; discovery's HNSW query.
- **Metric function** — numeric objective; the autoresearch `test_harness_ref` path.
- **Consensus** — N evaluators + quorum decision; moderator-council tie-breaks, autoresearch best-of-N.

### §33.3 Tiered-composition pipelines (fantasy-daemon is the reference)

The pattern that fantasy-daemon's `eval/criteria.py` + `workflow.protocols.EvalCriteria` already proves:

**cheap filter → expensive judge → human backstop**

Platform ships this natively. An `EvaluatorChain` declares an ordered list of evaluators; each stage's verdict gates the next stage:

```
chain:
  - evaluator: rubric:scene_coherence      # cheap, deterministic, ms scale
    on_verdict: [accept, uncertain]:continue, [reject]:halt
  - evaluator: llm:fantasy_scene_judge     # expensive, seconds scale
    on_verdict: [accept]:halt, [reject, needs_revision]:continue, [uncertain]:continue
  - evaluator: human:editor_review         # days scale, async
    on_verdict: *:halt
```

User composes the tier stack per node per use case. Simple mode = one named evaluator (`use: accept_rate_evaluator`). Complex mode = full chain with custom policy per stage. Same simple/complex spectrum as §32 autoresearch + §27 vibe-coding.

**Cost-aware scheduling.** Chain engine routes artifact to the cheapest evaluator first; expensive evaluators only run when cheap ones say uncertain or accept. Saves $ and wall-time at scale, matching §18 hybrid settlement's cost discipline.

### §33.4 Evaluators are user-authored + catalog-discoverable

Evaluators live in the catalog **alongside nodes**. Same schema shape (concept jsonb + structural_hash + embedding + provenance + license), same discovery via `discover_nodes` extended to accept `kind=evaluator`, same tier-3 PR-contribution path, same vibe-coding authoring surface (§27 authoring tools work for evaluators too — they're just nodes with a specific output contract).

**Competitor-differentiation angle.** Anyone can build a workflow engine. Fewer can build one where every surface is continuously-evaluated + improving. The evaluator loop IS the compounding advantage. User-authored evaluators + remix-from-N (§15.3) = the commons compounds at the *evaluation* layer too, not just at the workflow layer. This is the answer to "what makes Workflow different from LangChain / n8n / Zapier at year two."

**Recursive-application marketing hook.** *"autoresearch your evaluator"* is the product-line that closes the loop. Users who autoresearch a node soon ask "can I autoresearch the evaluator too, against a gold set?" — yes. Same §32 pattern, one layer up. §33.5 handles the cycle-detection guard. This is a compounding differentiator (most engines don't let you optimize either the workflow OR the evaluator; Workflow lets you optimize both) and taps into the same AI-forward brand recognition @karpathy's autoresearch carries — see §32 vocabulary-discipline note.

### §33.5 Evaluators are recursively eval-optimizable (and how to prevent infinite regress)

An evaluator is a node. §32 autoresearch optimizes nodes. Therefore autoresearch optimizes evaluators.

**Pattern.** User has an `LLM-judge` evaluator for their research-paper critique node. They attach an `optimization_spec.md` to the *evaluator itself*: metric = agreement-with-expert-judgment on a 20-paper gold set. Overnight autoresearch iterates the evaluator's prompt + few-shots; chooses the best-agreeing candidate. The *meta-evaluator* (agreement-with-experts) IS an evaluator.

**Infinite regress guard.** Each autoresearch layer needs a *fixed* meta-evaluator to bottom out. Platform enforces:
- Every autoresearch run must reference an evaluator that is NOT currently being optimized by another autoresearch run it triggered.
- Cycle detection on the evaluator-of-evaluator graph; optimization run rejects at submit-time if a cycle would form.
- User can manually opt-in to n-deep meta-optimization by declaring each layer explicitly; platform permits but warns. Defaults to refusing.

### §33.6 Schema additions (§2 cross-ref)

New `evaluators` table — structurally similar to `nodes` (evaluators ARE nodes, conceptually), but typed for query ergonomics:

```sql
CREATE TABLE public.evaluators (
  evaluator_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            text NOT NULL,
  name            text NOT NULL,
  kind            text NOT NULL CHECK (kind IN (
                    'llm_judge','rubric_fn','external_api','human_vote',
                    'vector_sim','metric_fn','consensus','chain')),
  concept         jsonb NOT NULL,              -- prompt / rubric / API spec / etc.
  input_schema    jsonb,                        -- what it accepts as artifact
  output_schema   jsonb NOT NULL,               -- always the §33.2 shape
  default_policy  jsonb,                        -- defaults user can override per call
  parents         uuid[] DEFAULT '{}',          -- §15.3 remix lineage
  version         bigint NOT NULL DEFAULT 1,
  owner_user_id   uuid NOT NULL REFERENCES public.users(user_id),
  -- same content_license + concept/instance split as nodes per §17
  concept_visibility text NOT NULL DEFAULT 'public',
  content_license   text NOT NULL DEFAULT 'CC0-1.0',
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, slug)
);
```

New `evaluator_results` table — append-only, cacheable:

```sql
CREATE TABLE public.evaluator_results (
  result_id        bigserial PRIMARY KEY,
  evaluator_id     uuid NOT NULL REFERENCES public.evaluators(evaluator_id),
  artifact_ref     jsonb NOT NULL,              -- {kind, id, version} — polymorphic
  artifact_hash    text NOT NULL,               -- for dedup: same artifact + same evaluator_version = cache hit
  score            numeric,
  verdict          text NOT NULL,
  rationale        text,
  evidence         jsonb,
  cost             jsonb,
  ran_at           timestamptz NOT NULL DEFAULT now(),
  daemon_host_id   uuid REFERENCES public.host_pool(host_id)
);

CREATE INDEX er_artifact_eval  ON public.evaluator_results (artifact_hash, evaluator_id);
CREATE INDEX er_evaluator_time ON public.evaluator_results (evaluator_id, ran_at DESC);
```

**New column on `nodes`:** `evaluator_refs uuid[] DEFAULT '{}'` — nodes can declare zero or more evaluators that apply to them. Autoresearch reads this when drafting `optimization_spec.md` defaults; moderation reads it when deciding which rubric to invoke; discovery reads it when aggregating quality signals.

All gap items tracked for spec #25 sharpening in the next drift-audit cycle.

### §33.7 Integration with existing sections (retrofit)

- **§32 autoresearch.** `optimization_spec.md` gains `evaluator: <id>`; `test_harness_ref` resolves to an evaluator. `optimization_metric` name collapses into `evaluator.output_schema.score`. Simple-mode defaults: chatbot suggests an evaluator from the catalog.
- **§8 moderation.** `flag_content` invokes the node's configured moderation evaluator; result lands in `evaluator_results` and in `moderation_flags`. Tier-gated escalation routes to more-expensive evaluators (tier-1 auto-rubric → tier-2 rep-earned peer review → admin-pool human). Same tiered-chain pattern as §33.3.
- **§24 real-world-outcomes.** `real_world_outcomes.verified_count` increments from outcome-verifier evaluator runs (DOI/ISBN/arXiv external-API evaluators). Badges sourced from `evaluator_results` where verdict='accept'.
- **§15 discovery ranking.** `public_demand_ranked` materialized view becomes an aggregation over `evaluator_results` grouped by artifact. Quality signals lose their ad-hoc column sprinkle; one uniform source.
- **§18 paid-market settlement.** Bid acceptance gates on the request's acceptance-evaluator verdict. Dispute window re-runs evaluator at higher tier. `self_hosted_zero_fee` branch still applies — no platform fee when host runs own evaluator against own work.
- **§16 wiki-edit merge-suggest.** On every edit, chatbot invokes the node's default evaluator on (old, new) pair → surfaces "score improved 0.71 → 0.84" to the user before commit.
- **§15.3C converge.** Ratification invokes each source's editor-evaluator on the proposed canonical. Passing threshold per source = ratification vote. Formal collapse of the ratification workflow around the evaluator primitive.
- **§5.2 cascade step-3 stays distinct** per §33.1 audit. Cascade *consumes* evaluator outputs as signals but is not itself an evaluator. Clear boundary.

### §33.8 Three-layer-lens (per `project_chain_break_taxonomy.md`)

Evaluation **closes the chain**:

- **System ships the primitive** — `evaluate()` RPC + `EvaluatorChain` composition + `evaluator_results` cache + discovery integration. Without the primitive, chatbot has no shared verification surface.
- **Chatbot uses evaluators to verify output** — when user asks "is this good?" or "did it work?" chatbot calls the relevant evaluator(s), returns verdict + rationale + evidence in user vocabulary. Devin's LIVE-F8 `get_status` intuition generalizes: *give the chatbot something concrete to call instead of guessing*.
- **User trusts real validation** — because the evidence is concrete (external API confirmed the DOI minted; LLM-judge cited the continuity error; rubric found the vendor-name mismatch), not "the chatbot said so."

**Cross-reference with the 3-layer-lens pattern of Devin LIVE-F8.** `get_status` was Devin's verify-before-trust primitive; evaluators are the verify-before-trust primitive generalized across every artifact, every surface. **Closing the chain is the point of §33.**

### §33.9 Scale audit (§14 cross-ref)

**Evaluator dedup cache** — `evaluator_results.artifact_hash` index lets the same (artifact, evaluator) pair return cached. Discovery + moderation + autoresearch all hit the same cache. Saves redundant evaluator calls; at 10k DAU common artifacts (popular nodes) hit 100% cache.

**Scale scenarios added to track J:**
- **S13: evaluator result-cache hit-rate under concurrent fan-out.** 1000 concurrent `evaluate(node_X, evaluator_Y)` calls → 1 actual evaluator run, 999 cache hits. Dedup index validated.
- **S14: evaluator-chain early-termination.** 1000 artifacts through 3-tier chain (rubric / llm / human) with 80% rubric-reject, 15% llm-accept, 5% human-review. Assert cost distribution matches tier cost model; no runaway fan-out to expensive tiers.

Adds ~0.3d to Track J (now 4.5–5d full). Shares primitives with S11+S12 so implementation is incremental.

### §33.10 Dev-day delta — honest accounting

This is **partially consolidating and partially expanding**. Honest breakdown:

**Expanding (new work):**
- New `evaluators` table + `evaluator_results` table + RLS policies: **+0.5d** (track A/L).
- `evaluate()` MCP tool + chain-composition engine + cost-aware scheduling: **+1d** (track C/N).
- Evaluator authoring surface (evaluators are nodes, reuse §27): **+0.25d** integration gloss.
- Cycle-detection for recursive meta-optimization: **+0.25d**.
- S13 + S14 load-test scenarios: **+0.3d** (track J).

**Consolidating (saves future work by unifying):**
- §8 moderation: the ad-hoc rubric-invocation path becomes evaluator-chain-based. Net-zero vs. §8's current spec but easier to extend. **~0 net.**
- §24 real-world-outcomes: the outcome-verification pipeline from §30 handoffs is already evaluator-shaped; formalizing it as Evaluator rather than per-handoff code saves ~0.25d in track N.
- §15 ranking: `public_demand_ranked` aggregation becomes evaluator-results sum; spec stays, implementation is a join. ~0 net.
- §32 autoresearch: `test_harness_ref` + `optimization_metric` collapse into `evaluator_id`. Simplifies §32 schema; saves ~0.1d on track O.
- §15.3C converge ratification: formal wrapper around evaluator invocation. ~0 net.

**Net Δ ≈ +1.9 to +2.3 dev-days (new track P).** Less than §32's 3–3.5d because evaluation partially consolidates work that was already budgeted. **Revised §10 totals: ~24.7–29.3d w/2 devs, ~32.4–34.8 serial.** Still weeks not months.

New §10 track row:

| Track | Dev | Rough dev-days | Notes |
|---|---|---|---|
| **P — Evaluation layers** | dev | 1.9–2.3 | `evaluators` + `evaluator_results` schema + RLS (0.5). `evaluate()` MCP tool + EvaluatorChain engine + cost-aware routing (1.0). Evaluator-authoring UI gloss (reuses §27 — 0.25). Cycle-detection for recursive meta-optimization (0.25). S13+S14 load-test (0.3). Retrofit glue for §8/§15/§18/§24/§30/§32/§15.3C (within respective tracks, net ~0 after consolidation savings). Depends on A, N (evaluators ARE nodes), K (discovery integrates). Parallel with O. |

### §33.11 New host Qs for §11

**Q32-nav — OPEN (evaluator-cost budget per tier).** Tier-1 chatbots invoking evaluators can generate unbounded cost if every discovery read + every edit triggers an expensive LLM-judge. Recommend: per-user per-hour evaluator-cost budget (default $0.50/user-hour free tier, higher for paid) + cache-hit ratio as a scaling primitive. Host confirm or adjust.

**Q33-nav — OPEN (evaluator-authoring friction floor).** Simple mode per §33.3 = one named evaluator from catalog. Complex mode = full evaluator-chain authoring via §27 vibe-coding surface. Recommend: user-facing onboarding names evaluator as "quality check" (user-vocabulary, per `feedback_user_vocabulary_discipline.md`); `evaluator` term reserved for tier-2/3 contexts.

**Q34-nav — OPEN (evaluator-drift detection).** Evaluators can silently drift (LLM model changes behavior; rubric-check fails on new edge cases; external API deprecates). Recommend: periodic gold-set re-runs; alert when verdict-distribution shifts by >N% vs baseline. Launch-day scope: passive logging only; active drift-alerting deferred to v1.1.

### §33.12 What §33 does NOT do

- Does not flatten §5.2 cascade into an evaluator (audited as not-evaluator-shaped).
- Does not force every node to attach an evaluator. Attachment is optional; nodes without evaluators still discover + bid + settle normally.
- Does not build evaluator-drift active-alerting at launch (Q34-nav defers to v1.1).
- Does not auto-trigger evaluator runs on every edit (cost unbounded). Chatbot decides when to invoke, per user-vocabulary "want me to check that?" prompt.
- Does not replace human judgment with evaluators. Evaluators inform decisions; escalation to human-vote substrate is first-class in every chain.
- Does not commit to one LLM model for LLM-judge evaluators. Model is part of the evaluator's `default_policy`; user can override per call, per autoresearch iteration.

### §33.13 Why this is the most-important unification of the session

Every prior fold added a surface. §33 *names* what all the surfaces share. Two downstream effects:

1. **Future design folds absorb faster.** When host proposes "let's add X that rates Y on Z axis," the answer is: *it's an evaluator over artifact Y with score-axis Z*. No new surface, just a new `evaluator_id` row.
2. **The chatbot's mental model simplifies.** Chatbot has one verb — "evaluate this" — that applies across every domain, every tier, every substrate. User vocabulary simplifies in tandem ("let's check if it's better" works uniformly). Matches Q21 real-world-effect-engine framing: *real work needs real validation.*

This is the single most-important architectural unification in the full-platform design. §32 autoresearch plus §33 evaluation is the engine; every other section is either a substrate (where evaluators run) or a consumer (what evaluator outputs drive).

---

- **PLAN.md §Multiplayer Daemon Platform** — preserved. Host-run identity + named accounts + private MCP sessions + public actions all map cleanly onto this backend. Daemons stay forkable, soul-defined, branch-first.
- **PLAN.md §Local-first execution** — preserved for daemons. Authoring moves to the control plane (necessary consequence of requirement 2); execution stays local.
- **PLAN.md §GitHub as canonical shared state** — **re-evaluated and inverted.** GitHub is now an export sink. Flagged as §11 Q1.
- **Privacy modes** (`2026-04-18-privacy-modes-for-sensitive-workflows.md`) — **partially superseded for node-content granularity by §17.** Universe-level `sensitivity_tier` (whole-slice opt-out, ollama-local pin, never-traverse-gateway) remains valid for the "this whole universe is confidential" case. Per-node content visibility moves to §17's dual-layer `concept`/`instance_ref` + `artifact_field_visibility` table. Two coexisting granularities.
- **Paid-market trust model** (project memory) — cooperative, not stranger-marketplace. Preserved.
- **Daemon vocabulary** (project memory) — "summon the daemon" copy throughout. Web app editor calls them daemons, not agents.
- **Node software capabilities** (`2026-04-15-node-software-capabilities.md`) — capability registry lives in Postgres via §5.1. Per-host resolution still host-local.
- **Engine/domain API separation** (`2026-04-17-engine-domain-api-separation.md`) — the MCP mount-per-domain pattern applies to the new MCP gateway. Ships with the reframe from day one, not a later phase.
