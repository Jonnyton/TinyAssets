# Daemon Economy — First-Draft Scoping

**Date:** 2026-04-19
**Author:** navigator
**Status:** Scoping doc per host's **"Daemon Economy is Foundation"** standing rule (CLAUDE_LEAD_OPS.md, `557b051`). Identifies the minimum daemon-economy first-draft surface: which tracks, which primitives, which "done" line.
**Lens:** chatbot-leverage. Every primitive answers "does this give the chatbot more leverage to complete a paid daemon-economy transaction end-to-end?"

---

## 1. Why this is foundation, not feature

Per host: *"daemon economy first-draft before chatbot-experience refinement sweeps. Both are needed, but the daemon economy is foundationally important — not a side feature."*

The daemon economy is the load-bearing primitive for the entire platform thesis (`project_paid_requests_model.md`, `project_full_platform_target.md`). Without it:
- Tier-2 hosts have nothing to earn from (`project_user_tiers.md` collapses to "tier-1 free + tier-3 OSS only").
- The cold-start fulfillment paths (`project_cold_start_and_fulfill_paths.md`) only have 3 of 4 (dry-run / free-queue / self-host; paid is missing).
- Network-effect sequencing (capacity attracts demand attracts supply) doesn't bootstrap.
- The §27 autoresearch primitive (`project_node_autoresearch_optimization.md`) has no overnight-bid market to dispatch into.

Self-auditing tools (Track Q), discovery polish, trust primitives — all valuable, but *all assume* a daemon-economy substrate exists for them to instrument or refine.

**First-draft definition:** the minimum surface where a tier-1 user posts a paid request, a tier-2 daemon claims and fulfills it, and the requester sees the output + settlement closes. End-to-end through one full economic transaction. Anything that doesn't sit on the critical path of that loop is out-of-scope for first-draft.

---

## 2. Tracks in scope

From `docs/design-notes/2026-04-18-full-platform-architecture.md` §10 dev-track decomposition:

| Track | What it ships | First-draft scope |
|---|---|---|
| **A — Schema + Auth** | Postgres schema for catalog + host-pool + requests + bids + ledger + comments + presence. RLS. GitHub OAuth. | **MUST.** Foundation for everything else. ~2 dev-days. |
| **D — Daemon host changes** | Tray host-pool registration + capability + visibility toggles. Heartbeat. Bid-polling loop. | **MUST.** Without tray-registers-host, no daemons are visible to claim work. ~2 dev-days. |
| **E — Paid-market flow** | Requests + bids + claim + settlement wiring. Postgres + Realtime glue. | **MUST.** This IS the economy. ~1 dev-day per host estimate. |
| **C — MCP gateway** | FastMCP at `tinyassets.io/mcp` wrapping the backend. Tool surface for paid-market: `submit_request`, `list_my_bids`, `claim_request`, `settle_completed`. | **MUST.** Without MCP-side actions, tier-1 chatbot users can't post requests. ~2 dev-days for MCP gateway full; first-draft slice is paid-market actions only, ~0.5-1 dev-day attributable. |
| **M — Monetization + cold-start + license + crypto** | Wallet-connect, on-chain bid placement, settlement (hybrid threshold), 1% fee to treasury. | **PARTIAL.** First-draft uses **testnet (Base Sepolia)** with test tokens (per `project_testnet_secrets_posture.md`). No real-currency mainnet at first-draft. ~2 dev-days for testnet path. |
| **G — GitHub export sync** | Hourly Action pushes Postgres public-rows to catalog repo. PR-ingest path. | **OUT.** Not on the critical path of one paid transaction. Defer. |
| **B — Web app** | Browse/discover surface. | **OUT.** Tier-1 chatbot path doesn't need web app for first paid transaction. Defer. |
| **F — Realtime presence** | Active-collaborators-on-this-node indicator. | **OUT.** Not paid-market load-bearing. Defer. |
| **H — Discovery + ranking** | `discover_nodes` with full signal block. | **PARTIAL.** First-draft needs *some* node-discovery so requester can pick a node to bid on, but signal-block depth can be minimal at first-draft. ~0.5 dev-day for minimal slice. |
| **I — Onboarding flows** | Tier-1/2/3 install + setup. | **OUT for first-draft.** Tier-2 install can use the existing tray work (already shipped as #23 Tray singleton). |
| **J — Load-test scenarios** | 1k-subscriber fan-out, 500-daemon bid storm. | **OUT for first-draft.** Defer to pre-launch (per v3 Q2 ratification). |
| **K — Convergent commons** | Cross-Branch convergence tools. | **OUT.** Not paid-market load-bearing. |
| **L — Privacy + dual-layer content** | Per-piece visibility + concept/instance split. | **OUT for first-draft.** Defer to post-first-draft (privacy can ship after the basic economy proves out). |
| **N — Vibe-coding authoring** | `/node_authoring.*` MCP family + sandboxed runtime. | **OUT for first-draft.** Authoring vibe-coded nodes is a parallel surface to the economy; not on the critical path. |
| **O — Autoresearch** | Karpathy-style overnight optimization. | **OUT for first-draft.** Depends on the economy existing first; pure consumer of paid-market dispatch. |
| **P — Evaluation layers** | Unified `Evaluator` primitive across surfaces. | **OUT for first-draft.** Refines existing evaluation; doesn't gate the economy. |
| **Q — Self-auditing tools** | `get_status` + 5 successor surfaces. | **OUT for first-draft.** Per host directive: lower priority than daemon economy. Keep moving in parallel where dev capacity allows, but doesn't block first-draft. |

**First-draft tracks:** A, C (slice), D, E, H (minimal), M (testnet path).

### 2.0a Per-primitive Foundation/Feature classification

Per host's "Foundation End-State vs Feature Iteration" rule (CLAUDE_LEAD_OPS.md, `557b051` refined): **the check is "does the next thing we build depend on this being its final shape?"** Foundation = end-state-now, no phases. Feature = iterate-OK, real chatbot-usage signal informs final shape. Every primitive in the first-draft list is classified.

| Primitive | Foundation / Feature | Rationale |
|---|---|---|
| **Multi-daemon registry (Track D)** — `host_pool` table + heartbeat + capability declarations | **FOUNDATION** | Every other daemon-economy primitive (bid routing, claim semantics, settlement attribution) reads from this table. End-state-now. |
| **Bid-routing core (Track E)** — `requests` + `bids` tables + `SELECT FOR UPDATE SKIP LOCKED` claim semantics + realtime broadcast channel | **FOUNDATION** | Schema shape + claim semantics are load-bearing for any future bid-UX iteration. Wrong shape here means migrations later. End-state-now. |
| **Settlement ledger primitive (Track M)** — `ledger.settlement_mode` enum + immutable settlement records + 1% fee transfer | **FOUNDATION** | v1 settlement records must outlive token-launch migration byte-for-byte (per §11 Q4-follow-up RESOLVED). Wrong shape = lost audit trail. End-state-now. |
| **Capability-resolution protocol (Track D + H)** — `(node_type, llm_model)` pair as capability key + matching algorithm | **FOUNDATION** | Every `submit_request` and every host registration depends on the capability-key shape. End-state-now. |
| **Auth/identity (Track A)** — GitHub OAuth + RLS policies + `actor` resolution | **FOUNDATION** | Per CLAUDE_LEAD_OPS.md operationalization list (auth IS foundation). End-state-now. |
| **Moderation hook-point (§2.1 below)** — `state='flagged'` + control-plane routing-pause | **FOUNDATION** | Schema column + state-gate are load-bearing. The *resolution flow* (volunteer-mod queue, rubric, appeals) is feature; the hook-point is foundation. |
| **Specific bid-UX chatbot verbs (Track C-slice)** — `submit_request`, `list_my_bids`, `claim_request`, `settle_completed` | **FEATURE** | The verb set will iterate as chatbot tells us what it needs. Initial set is the minimum viable; expect additions like `compare_bids`, `cancel_request`, `auto_accept_below_X`. Iterate per chatbot signal. |
| **Fulfillment-path choice UI (Track H + Track C-slice)** — chatbot's surfacing of "dry-run / free-queue / paid / self-host" 4-path option | **FEATURE** | Per `project_cold_start_and_fulfill_paths.md` chatbot remembers user preferences. UI shape evolves with use. |
| **Discoverability surfaces (Track H minimal)** — `discover_nodes` field set | **FEATURE** | Per §11 Q11 ratified (a) ship full signal block — but the *ranking weights* + *display order* will iterate. Schema is foundation; ranking is feature. |
| **Wallet-connect UX (Track M testnet)** — first-launch wallet flow vs first-bid-accept wallet flow | **FEATURE** | Per Q-econ-1 (deferred to v5): the *trigger point* for wallet onboarding will iterate. Wallet *primitive* is foundation; the *invitation shape* is feature. |
| **Test-token distribution (Track M testnet)** — faucet button vs airdrop allocation | **FEATURE** | Per Q-econ-2 (deferred to v5): mechanism iterates with use. |

**Implication for "what order to ship" (§6 sequencing below):** Foundation primitives ship first within first-draft, before any Feature on top can iterate. Inside first-draft:
- **Wave 1 (Foundation, must complete before Wave 2):** Track A (schema + auth), Track D (registry + heartbeat), Track E (bid-routing core + claim semantics), Track M (testnet ledger primitive), capability-resolution protocol, moderation hook-point.
- **Wave 2 (Feature, iterates on top of Wave 1):** Track C-slice (specific bid-UX verbs), Track H minimal (discoverability surface), wallet-connect UX, test-token distribution.

Wave 1 cost: ~5-6 dev-days (most of the 8.5 estimate). Wave 2 cost: ~2.5-3 dev-days. Wave 2 ships in parallel with Wave 1 verification + iterates after first user-sim mission against the economy.

### 2.1 Moderation entry point — what's needed at first-draft

Per Q10-host RESOLVED (community-flagged moderation), the full moderation surface ships post-MVP with `flag_content` / `list_review_queue` / `resolve_flag` / `appeal_decision` primitives. **First-draft requires only the entry point:**

- A single `flag_request` MCP action that lets a tier-1 user flag a paid request as abusive (spam, off-topic, malicious payload).
- A single `flag_bid` MCP action for the symmetric case (tier-2 daemon flags a request before fulfilling).
- Flagged items get a `state='flagged'` row and pause routing — control plane stops broadcasting `bids:<capability_id>` for flagged requests; flagged bids stop being claimable.
- Resolution is **manual host-admin only at first-draft**. No volunteer-mod queue, no rubric, no appeal flow. Scale 0-N flagged-items per week handled by host directly via SQL (`UPDATE requests SET state='resolved' WHERE id=?`).

**Cost:** ~0.5 dev-day (just the two MCP actions + state column + control-plane gate). Folded into Track E's 1 dev-day estimate (zero net change).

**Why this is enough:** at first-draft scale (single-host, low traffic, mostly user-sim), volume is zero. Host-admin manual resolution is the right level. Volunteer-mod queue + rubric + appeal flow ship post-first-draft when actual traffic surfaces a real moderation workload.

---

## 3. The "done" line — one full transaction end-to-end

First-draft is complete when this sequence works in production (not just in a test):

1. **Tier-2 host installs the tray** (existing #23 work). Tray registers with control plane via Track D — declares ≥1 capability `(node_type, llm_model)` pair with `visibility=paid` and a price floor.
2. **Tier-1 user opens Claude.ai** + invokes TinyAssets MCP connector. Posts a paid request via `submit_request` (Track C MCP action) for a node matching the tier-2 host's declared capability.
3. **Control plane broadcasts** (Track E + A) on the realtime channel `bids:<capability_id>`. The tier-2 daemon's bid-polling loop sees the request.
4. **Daemon places a bid** (Track D bid-polling) at-or-above the floor, below the requester's max. Bid lands in Postgres `bids` table.
5. **Requester (chatbot) reviews bids** via `list_bids_for_my_request` MCP action (Track C). Picks the winning bid (lowest price meeting requirements, or first-available for time-pressure).
6. **Daemon claims** the request via `SELECT FOR UPDATE SKIP LOCKED` semantics (Track E). Daemon executes the node locally.
7. **Daemon completes**, posts result back to control plane via Track D. Control plane writes to Postgres + notifies requester via realtime.
8. **Settlement** (Track M testnet): test-token transfer from requester wallet to daemon wallet via Base Sepolia smart contract; 1% fee to treasury; `ledger.settlement_mode = 'immediate'` for amounts ≥$1-equivalent, `'batched'` below (Q4-follow hybrid threshold).
9. **Both parties see closed transaction** via Track C MCP `get_my_settled_transactions` action.

**One transaction, one user-visible outcome, one wallet-visible test-token transfer.** That's the done line.

---

## 4. Out-of-scope-but-allowed parallel work

These can run in parallel with the daemon-economy first-draft when dev capacity allows, but **must not block** first-draft completion:

- **R2 / R3 / R7 refactor work.** Module reshape doesn't gate paid-market flow.
- **Layer-3 universe→workflow rename** (post-Q4 ratification per v3).
- **Track Q self-auditing tools** (post-#50 `get_recent_events`, ~6 dev-days remaining). Per host directive: high priority but lower than daemon economy. Recommend ship `get_routing_evidence` next (smallest delta from `get_recent_events` shape, per §10.7 of self-auditing-tools note); other Track Q surfaces queue behind first-draft.
- **#52 Sporemarch C16-S3 diagnostic** (~0.5-1.5 dev-days depending on hypothesis confirmation). Per pre-staged plan.
- **Chatbot-experience polish** (vocabulary hygiene refinements, additional `get_status` evidence fields, etc.). Continue per existing intel-report queue but doesn't block.

---

## 5. Estimated first-draft cost

| Track | Estimate | Notes |
|---|---|---|
| A — Schema + Auth | 2 dev-days | Per §10. |
| C — MCP gateway (paid-market slice only) | ~1 dev-day | Subset of full Track C (~2 dev-days). Just `submit_request`, `list_my_bids`, `claim_request`, `settle_completed`, `get_my_settled_transactions`. |
| D — Daemon host changes | 2 dev-days | Per §10. |
| E — Paid-market flow | 1 dev-day | Per §10. |
| H — Discover_nodes (minimal slice) | 0.5 dev-day | Subset of full Track H. Just enough for requester to find a node to post against. |
| M — Monetization (testnet only) | 2 dev-days | Includes wallet-connect, Base Sepolia smart contract, hybrid settlement threshold. Per §10. |
| **First-draft total** | **~8.5 dev-days** | One contributor serial; ~5-6 dev-days with two devs in parallel. |

**Ratio check:** This is roughly one engineering sprint (1-2 weeks calendar time at typical pace). Aligns with `project_distribution_horizon.md` "weeks not months" framing — the daemon-economy first-draft is sprint-shaped, not quarter-shaped.

---

## 6. Sequencing relative to other host-priority items

**Recommended order:**

1. **Refactor wave (R2 + R3 + R7) lands first** — ~3 dev-days. Establishes Module Layout commitments before daemon-economy surfaces are written into a still-shifting layout.
2. **Daemon-economy first-draft starts** post-refactor. ~5-6 days with two devs in parallel.
3. **Rename end-state commit** (per `docs/exec-plans/active/2026-04-19-rename-end-state.md` Path A) ships *after* daemon-economy first-draft proves out. Cleanup commits don't deserve to block product shipping.
4. **Track Q remaining surfaces** continue in parallel where dev capacity allows.
5. **Layer-3 rename + privacy + autoresearch + vibe-coding** all queue behind first-draft completion.

**Recommended dispatch trigger:** the moment R7 storage split lands + Q4 (PLAN.md.draft) ratifies, dispatch Track A as the first daemon-economy commit.

---

## 7. Open questions for v4 digest follow-up

The v4 §11 residual sweep (in flight) addresses some daemon-economy questions but not all. Specific open items worth a v5 digest entry once first-draft begins:

- **Q-econ-1: Wallet onboarding for tier-2 hosts at first-draft.** Tier-2 daemon accepts test tokens — does the tray UI walk them through wallet-connect on first launch, or defer to "first time you accept a paid bid"? Recommend defer to first-bid-accept; first-launch already crowded with capability declaration.
- **Q-econ-2: Test-token distribution.** How does a tier-1 user get test tokens to spend on Base Sepolia? Faucet link in the web app? Initial allocation via host-controlled airdrop? Recommend: web-app surfaces a faucet button for tier-1 users on first paid-request attempt; host airdrops a starter allocation to seed user-sim.
- **Q-econ-3: Failed-fulfillment settlement semantics.** What happens when a daemon claims, starts work, then fails or times out? Does the bid escrow refund automatically? Recommend: per-bid timeout (configurable, default 1h), automatic refund on timeout, daemon's reputation gets a "failed" tick. Not load-bearing for first-draft if we accept that early failures are manual-resolution.

These are all v5 entries, not first-draft blockers.

---

## 8. Summary for dispatcher

- **First-draft scope:** Tracks A + C (slice) + D + E + H (minimal) + M (testnet) = ~8.5 dev-days serial, ~5-6 with parallel.
- **Done line:** one paid transaction end-to-end (tier-2 declares → tier-1 posts → tier-2 bids/claims/fulfills → settlement closes via testnet).
- **Recommended sequencing:** refactor wave (R2+R3+R7) first → daemon-economy first-draft → rename end-state → other tracks.
- **Out-of-scope (deferred):** Tracks B, F, G, I, J, K, L, N, O, P, Q (continues in parallel where capacity allows).
- **v5 digest entries pre-staged:** Q-econ-1, Q-econ-2, Q-econ-3 — all about wallet onboarding + test-token distribution + failed-fulfillment semantics. Not first-draft blockers.
