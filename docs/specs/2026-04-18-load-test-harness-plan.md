---
status: active
---

# Load-Test Harness Plan — Track J (Uptime Scale Proof)

**Date:** 2026-04-18
**Author:** dev (task #26 pre-draft; unblocks track J when dispatched)
**Status:** Pre-draft spec. No code yet. Executable on dispatch without design re-research.
**Source of truth:** `docs/design-notes/2026-04-18-full-platform-architecture.md` §14 (scale audit), §10 (track J row).
**Schema context:** `docs/specs/2026-04-18-full-platform-schema-sketch.md` — table shapes + RPC signatures.

> **Track label note.** The dispatching task (#26) references "track K" in its subject, but the design note §10 labels the load-test harness **track J** (track K is discovery+remix). This spec uses **track J** to match the design-note source of truth. Raise if the dispatch intended the discovery work instead — different scope, different spec.

This spec turns navigator's 1.5 dev-day estimate into a concrete executable plan: stack, scenarios with success thresholds, harness structure, cost, and honest dev-day revision.

---

## 1. Stack choice

Three candidates considered. Criteria: Python-project-fit, Supabase Realtime WebSocket support, CI integration, cost.

| Tool | Websocket | Python-fit | CI-native | Cost | Notes |
|---|---|---|---|---|---|
| **k6** (Grafana) | First-class via `k6/experimental/websockets` module | Foreign (Go binary, JS scripts) | Native GitHub Action (`grafana/setup-k6-action`), Grafana Cloud k6 optional | OSS; Grafana Cloud k6 free tier 500 VUh/mo | Design-note recommended. Websocket throughput proven at 10k+ VUs. |
| **Locust** | Partial — websocket-client add-on (`locust-plugins`), less battle-tested at >1k VUs | Native Python (same language as project) | Dockerable; no bespoke Action | OSS; self-host only | Scenarios as Python classes — reusable code with repo helpers (e.g. Supabase client). |
| **Artillery** | First-class (Artillery Plugins: WebSocket, Socket.IO) | Foreign (Node) | GitHub Action available | OSS core; Artillery Cloud is paid | YAML-first config is fast to read but hides logic when scenarios get conditional. |

**Pick: k6** — matches the design note's commitment, strongest websocket load capability, Realtime scenarios S2/S5 are the dominant risk, and the Python-fit deficit is addressed by a **thin Python sidecar**:

- **k6** owns the HTTP + WebSocket load generation (VU-heavy work, Go-native performance).
- **Python sidecar** (`tests/load/sidecar/`) owns the synthetic-daemon fleet per §14.8: spins up N daemon processes that share the real project's MCP-client + Supabase-client code. This is where project code reuse lives. Each sidecar daemon POSTs bids via the same auth path real daemons do — no mock client to drift.

**Why not Locust:** at 1k+ VUs Locust's per-worker GIL+asyncio bottleneck pushes you into multi-worker clusters (Locust-master + N Locust-workers); that's operational complexity we don't need when k6 does single-binary 10k VUs. Reusing Python code for the daemon fleet is the actual need Locust solves — handled by the sidecar.

**Why not Artillery:** Node-based + YAML-heavy + its websocket plugin isn't as proven at scale. No decisive win over k6.

---

## 2. Scenarios

Each scenario names: (a) what it exercises, (b) target workload, (c) success metric, (d) blocks-merge threshold.

### S1 — Bid-inbox claim contention (§14.1)

- **Exercises:** `claim_request(request_id, host_id)` RPC + partial-index on `request_inbox(state='pending')`. Validates the §14.1 claim-RPC pattern replaces poll-all.
- **Workload:**
  - Seeder inserts 10,000 `request_inbox` rows at `state='pending'` for capability `goal_planner×claude-4-opus`.
  - 500 synthetic daemons (sidecar processes) race to claim. Each calls `claim_request(request_id, host_id)` picking request_ids from the Realtime broadcast they subscribe to on `bids:goal_planner×claude-4-opus`.
  - Run 60s.
- **Success metrics:**
  - **Throughput ≥ 1000 claims/sec** sustained.
  - **Zero double-claims** — every `request_inbox` row ends with exactly one `claimed_by_host`.
  - Claim-RPC p95 latency ≤ 200 ms.
- **Blocks merge if:** any double-claim, throughput < 500 claims/sec, or p95 > 500 ms.

### S2 — Realtime presence + broadcast fan-out (§14.2)

- **Exercises:** Supabase Realtime per-universe channels + Presence. Validates channel-sharding and the ~2.4k-socket Pro-tier envelope at 10k DAU.
- **Workload:**
  - 1,000 concurrent k6 VUs subscribe to `universe:hot_test_universe` (a single seeded hot universe).
  - Writer process issues 10 writes/sec to `nodes` rows in that universe.
  - Presence: every VU also broadcasts `viewing:<node_id>` every 30s.
  - Run 5 min.
- **Success metrics:**
  - **Broadcast lag p99 ≤ 2 s** (write committed → VU receives event).
  - **Zero missed events** — each VU receives every write.
  - Socket churn rate < 1% (no disconnect storms).
- **Blocks merge if:** p99 > 5 s, any missed-event run, or socket churn > 5%.

### S3 — Hot-node CAS contention (§14.3)

- **Exercises:** `version bigint` optimistic CAS on `nodes` row. Validates last-writer-loses semantics + no-reader-blocking.
- **Workload:**
  - 50 concurrent VUs issue `UPDATE nodes SET concept = ..., version = version + 1 WHERE id = X AND version = <read_version>` against one hot node.
  - 200 concurrent read VUs issue `SELECT * FROM nodes WHERE id = X` at 5 req/sec each.
  - Run 3 min.
- **Success metrics:**
  - **Every writer either succeeds OR gets zero-row-affected** (no silent overwrites).
  - **Reader p95 latency ≤ 30 ms** — writes do not block reads.
  - Conflict rate ≈ expected (49 writers lose out of every 50 attempts).
- **Blocks merge if:** any silent overwrite, reader p95 > 100 ms, or writer-success rate deviates > 5% from expected.

### S4 — Discovery read storm (§14.4 + §15)

- **Exercises:** `discover_nodes` RPC + `public_demand_ranked` materialized view + pgvector HNSW index. Validates MV serves cascade + discovery without contention.
- **Workload:**
  - Seed: 50,000 `nodes` rows with varied embeddings, 5k active `request_inbox` rows.
  - 200 concurrent k6 VUs call `discover_nodes(p_intent=<varied>, p_limit=20)` at 2 req/sec each (≈400 RPS).
  - Concurrent pg_cron refresh of `public_demand_ranked` every 30s.
  - Run 5 min.
- **Success metrics:**
  - **p95 latency ≤ 150 ms** for `discover_nodes` (chatbot-turn budget).
  - **Zero failed calls** (no MV-refresh blocking).
  - Cache-hit on HNSW index inferred from `EXPLAIN ANALYZE` on a sampled query < 20 ms.
- **Blocks merge if:** p95 > 300 ms, any failure rate > 0.1%, or refresh-interval stalls detected.

### S5 — Host-pool heartbeat scale (§14.5)

- **Exercises:** Supabase Presence TTL expiry + the explicit no-`last_heartbeat`-column decision. Validates 10k-host scale doesn't hit the 167 writes/sec cliff the column would have caused.
- **Workload:**
  - 1,000 sidecar "host" processes connect to Supabase Realtime and broadcast Presence every 30s on `host_pool:online` channel.
  - Query `SELECT * FROM host_pool JOIN <presence_online_view>` every 5s.
  - Randomly kill 10% of hosts every 60s; new ones join.
  - Run 10 min.
- **Success metrics:**
  - **Zero writes** to `host_pool.last_heartbeat` (column doesn't exist; any write = regression).
  - **Presence online count reconciles with kills** within TTL window (90s default).
  - Dispatch-query p95 ≤ 50 ms.
- **Blocks merge if:** any write to a heartbeat column, reconciliation lag > 120 s, or p95 > 200 ms.

### S6 — Export-sink burst (§14.6)

- **Exercises:** GitHub Actions diff-only batcher + ≤12 commits/hr throttle. Validates §14.6 the catalog-repo export-sync doesn't melt under burst load.
- **Workload:**
  - Simulate 500 `nodes` INSERTs + 1,000 UPDATEs + 200 DELETEs in a 5-min window (bulk-import event).
  - Trigger the export-sync Action.
- **Success metrics:**
  - **≤ 12 commits/h** regardless of event volume (squash-batch policy holds).
  - **No GitHub API rate-limit 429s** (5k/h authed budget).
  - Catalog repo's final state after sync matches Postgres state (diff = 0 on a replay).
- **Blocks merge if:** > 12 commits/h observed, any 429, or state drift.

### S7 — Moderation triage at scale (§14.8)

- **Exercises:** report queue + rate-limit triggers. Validates admin queue doesn't starve under paid-market abuse pattern.
- **Workload:**
  - 100 synthetic "attacker" users post 10 reports/min each on varied artifacts (1000 reports/min).
  - 10 legit users place paid requests at 1/min.
  - 5 synthetic moderators (tier-2 threshold met) triage from the queue.
- **Success metrics:**
  - **Legit paid-request latency unaffected** (p95 unchanged from baseline).
  - **Rate-limit triggers fire** on attackers (configured threshold).
  - **Triage queue drainage rate ≥ report rate** at 5 moderators.
- **Blocks merge if:** legit-request degradation > 20%, triggers silent, or queue growth unbounded.

### S8 — Mixed-workload full-system (tier-share realistic)

- **Exercises:** the composition of S1-S7 at the §9.1 tier mix. This is the MVP ship-gate.
- **Workload** (at 1× scaled to 1,000 DAU-equivalent):
  - 95% T1 chatbot: 200 VUs subscribe to Realtime + 40 discover_nodes/min aggregate + 5 node edits/min.
  - 4% T2 daemon: 40 sidecar daemons running the full cascade (host-queue → paid → public) at 1 cascade/min each.
  - 1% T3 PR-ingest: 1 synthetic PR-ingest event every 5 min to catalog Action.
  - Run 30 min.
- **Success metrics:**
  - **All S1-S5 individual gates still pass** when running concurrently.
  - **Cross-scenario p95 ≤ 200 ms** for chatbot-facing RPCs.
  - **Zero data drift** between Postgres + catalog export after the run.
- **Blocks merge if:** any component gate fails under load, cross-scenario p95 > 500 ms, or drift detected.

---

## 3. Harness structure

```
tests/load/
├── README.md                    # run-book: how to kick off local + CI
├── k6/
│   ├── lib/
│   │   ├── auth.js              # shared JWT mint + user-token fixture
│   │   ├── fixtures.js          # seeded universe/node IDs
│   │   ├── supabase.js          # REST + Realtime client helpers
│   │   └── thresholds.js        # shared merge-blocking metrics
│   ├── s1_bid_claim.js
│   ├── s2_realtime_fanout.js
│   ├── s3_hot_node_cas.js
│   ├── s4_discover_storm.js
│   ├── s5_heartbeat_scale.js
│   ├── s6_export_sink.js        # triggers GH Action via API
│   ├── s7_moderation.js
│   └── s8_mixed_workload.js
├── sidecar/                     # Python daemon-fleet harness (§14.8)
│   ├── __init__.py
│   ├── daemon_factory.py        # spawn N synthetic daemons
│   ├── cascade_runner.py        # §5.2 cascade against test project
│   └── host_beacon.py           # Presence beacon loop for S5
├── fixtures/
│   ├── seed_universe.sql        # hot_test_universe + node seeds
│   ├── seed_requests.sql        # bid-inbox fodder for S1
│   └── seed_embeddings.jsonl    # precomputed embeddings for S4
└── ci/
    └── load-test.yml            # GitHub Actions workflow (see §4)
```

**Shared fixtures (`k6/lib/fixtures.js`, `fixtures/*.sql`):**
- 1 hot_test_universe with 50,000 nodes pre-seeded, varied embeddings.
- 100 pre-minted user tokens, 50 pre-minted daemon tokens, 10 moderator tokens.
- Capability reference data: 5 `(node_type, llm_model)` entries with pre-registered hosts.
- Seed SQL run before each k6 run; teardown after (or use Supabase branching — see §4 cost).

---

## 4. CI wiring + Supabase test project

**GitHub Actions workflow `load-test.yml`:**

- **Trigger 1 — on merge to `main`.** Full S1-S8 run. Blocks next deploy if any fails. ~30 min.
- **Trigger 2 — nightly cron 02:00 UTC.** Full S1-S8 run with extended durations (+30% window). Catches slow-drift regressions.
- **Trigger 3 — on PR label `load-test`.** Subset S1+S4+S8 (the three highest-leverage gates). ~5 min.

**Supabase project choice** (cost tradeoff):

| Option | Cost | Fit |
|---|---|---|
| **(a) Dedicated `workflow-loadtest` project, always-on** | $25/mo Pro tier | Simplest; schema migrations track production. Recommended for nightly. |
| **(b) Ephemeral-per-run via Supabase Branching** | ~$0.50/run (branches billed by hour); currently in beta | Cheapest; isolates runs. Risk: beta feature, Realtime-on-branches may be flaky. Revisit after Supabase GAs branching. |
| **(c) Self-hosted Supabase on a Hetzner box** | ~€6/mo | Full control; migration work to run Supabase Docker stack. |

**Recommend (a) for launch + evaluate (b) in month-2.** (b) looks ideal once GA.

**Test-project schema mirror:** same migration pipeline as production. The `load-test.yml` runs `supabase db push --db-url $LOADTEST_DB_URL` before each scenario.

---

## 5. Target-metric table

Consolidated blocks-merge thresholds (verifier's ship-gate numbers):

| Scenario | Workload | Success metric | Blocks merge if |
|---|---|---|---|
| S1 Bid claim | 500 daemons × 10k requests | ≥1000 claims/s, 0 double-claim, p95 ≤200ms | any double-claim, <500/s, p95>500ms |
| S2 Realtime | 1k VUs × 10 writes/s × 5min | p99 ≤2s, 0 missed, <1% socket churn | p99>5s, any missed, churn>5% |
| S3 CAS | 50 writers + 200 readers × 3min | 0 silent overwrites, reader p95 ≤30ms | any overwrite, reader p95>100ms |
| S4 Discovery | 200 VUs × 400 RPS × 5min | p95 ≤150ms, 0 fail | p95>300ms, fail>0.1% |
| S5 Heartbeat | 1k hosts × 10min | 0 heartbeat-column writes, TTL reconcile | any heartbeat write, lag>120s |
| S6 Export | 1700 mutations in 5min | ≤12 commits/h, 0 rate-limit, 0 drift | >12 commits/h, any 429, drift>0 |
| S7 Moderation | 1000 reports/min × 10 min | legit p95 unchanged, triggers fire, queue drains | legit degrade>20%, silent triggers |
| S8 Mixed | tier-mix × 30min | all S1-S5 gates hold, cross p95 ≤200ms | any gate fail, cross p95>500ms |

These are ship-gates, not goals. Defense-in-depth: S8 composition catches cross-cutting failures that individual scenarios miss.

---

## 6. Execution runtime + cost

**Runtime (full S1-S8):**
- S1 60s + S2 5min + S3 3min + S4 5min + S5 10min + S6 5min + S7 10min + S8 30min = ~68 min raw.
- Parallelize non-conflicting (S3+S4 on separate universes, S6+S7 on separate queues) → **~45 min full pass**.
- Subset (S1+S4+S8-at-1/6-scale) for PR-label trigger → **~8 min**.

**Runtime target:** subset ≤ 10 min (PR feedback loop); full ≤ 60 min (merge/nightly).

**Cost per run:**
- GitHub Actions runner (ubuntu-latest, 8-core large runner if needed): ~30-60 CI min × $0.008/min = **~$0.25-0.50 per full run**.
- Supabase Pro test project: $25/mo flat (option (a)). Sunk cost, no per-run add.
- k6 Grafana Cloud (optional): free up to 500 VUh/mo; we'd consume ~200 VUh per full run → 1 full run/day fits free tier. Nightly + PR-subset fits. Merge-driven full runs beyond 2/day push into paid tier (~$49/mo).
- **Per-run total: ~$0.50** during free-tier phase; ~$0.80 after.

**Annual envelope:** $25 × 12 (Supabase) + $49 × 12 (Grafana Cloud paid if we cross threshold) + CI-minute spend ~$200 = **~$1,100/year** worst case. Folds into §9 cost envelope (host's laptop hosts nothing here).

---

## 7. Staging fleet — simulating thousands of daemons

**Three candidate approaches:**

| Approach | Capacity | Cost | Fit |
|---|---|---|---|
| **(a) One-machine k6 + Python sidecar multiplex** | ~1k VU (k6) + ~200 sidecar daemons (each ~50MB × 200 = 10GB) | CI-runner cost only | Fits launch target (10k DAU). Recommended. |
| **(b) Cloud-dispatched worker pool** (Fly.io Machine fleet briefly) | 10k+ | Fly billed by seconds — ~$2-5 per full run | Needed only if we push past 10k DAU target. |
| **(c) Mock-daemon containers** (lightweight Python containers, ~10MB each) | ~1k on a single runner | Free | Loses fidelity — no real Supabase-client code path. Avoid. |

**Recommend (a) for launch.** The §14.8 scale audit targets are 1k subscribers, 500 daemons, 1k heartbeats — all fit one k6 runner + one sidecar-python host. (b) becomes interesting only when we lift the launch envelope past 10k DAU.

**Sidecar multiplex details:** single Python process spawns 200 asyncio tasks, each running a minimal Supabase-authenticated daemon loop. Memory budget 10 MB/task × 200 = 2 GB — well under an 8-core GitHub runner's 16 GB. Each task uses the **real project's MCP-client and supabase-py code paths** — no mocks. This is how we avoid "tests pass, production fails" drift.

---

## 8. Honest dev-day estimate

Navigator's §10 estimate: **1.5 dev-days**. My build-out below:

| Work item | Estimate |
|---|---|
| Stack setup (k6 install, project skeleton, fixtures, Supabase test project bootstrap) | 0.3 d |
| S1 bid-claim script + seeder + assertions | 0.3 d |
| S2 Realtime fan-out script + Presence fixture | 0.3 d |
| S3 CAS contention script | 0.15 d |
| S4 discovery storm + embedding fixture + MV refresh probe | 0.3 d |
| S5 heartbeat/Presence script + sidecar host-beacon loop | 0.25 d |
| S6 export-sink simulator (GH Action trigger + drift check) | 0.2 d |
| S7 moderation scenario + rate-limit fixtures | 0.2 d |
| S8 mixed-workload composer (shared fixtures across scenarios) | 0.25 d |
| Python sidecar daemon factory + cascade runner | 0.4 d |
| CI wiring (`load-test.yml`, 3 triggers, secrets, metric export) | 0.3 d |
| Initial run-and-tune (expect to uncover 2-3 real bugs) | 0.5 d |
| Docs (`tests/load/README.md`, run-book) | 0.15 d |
| **Total** | **~3.6 d** |

**Revision: 1.5 d → ~3.5-4 d.** Navigator's estimate materially underweights (a) the Python sidecar (~0.4d), (b) S6/S7 moderation+export scenarios that weren't in the §14.8 four-scenario minimum, and (c) run-and-tune time (always discovers bugs — that's the point). The 1.5d number fits "k6 scripts for 4 scenarios and hope" but not "MVP ship-gate harness."

**Flag to host/navigator:** the +2 dev-day revision pushes §10's "8.5-10.5 dev-days with two devs" to roughly **10-13 dev-days with two devs**. Still fits "weeks not months." Worth confirming host is comfortable with the revision before track J starts — this is the honest number.

**Reasonable-defer options** if host wants to hit 8.5-10.5 cap:
- Ship S1-S5 only (the §14.8 originals) → ~2 d. Defer S6/S7/S8 to post-launch. Risk: S8 mixed-workload composition blind-spot.
- Ship without S6 (export-sink test, lowest-leverage pre-launch since traffic is low) → ~3 d.

**Do NOT:** ship without S1+S2+S4. Those three are the §14 highest-probability contention bugs.

---

## 9. OPEN flags

Flag these before track J start; don't invent answers:

| # | Question |
|---|---|
| Q1 | k6 Grafana Cloud (free tier 500 VUh/mo) vs self-hosted k6 + Prometheus — which does host prefer for metrics export? Nightly-full-run fits free tier at 200 VUh/run × 1/day = 6000 VUh/mo → over cap. Bumps to paid unless we skip Grafana Cloud and roll metrics to Postgres or Prometheus self-host. |
| Q2 | Supabase test-project option (a) always-on $25/mo vs (b) Branching beta? Lead decision pre-launch; low-stakes to revisit post-launch. |
| Q3 | S6 export-sink scenario requires a real GitHub Actions trigger — do we test against the real catalog repo or a dedicated `TinyAssets-catalog-loadtest/` repo? Host call. Recommend the latter; avoids production commit pollution. |
| Q4 | S7 moderation scenario — do we need real ledger reservation logic, or is a mock-ledger acceptable? If the real ledger is load-bearing for S7's paid-request scam defense, scope creeps (~0.3 d). |
| Q5 | On-PR subset (S1+S4+S8-small) vs on-merge full — confirm the cadence. Subset ~8 min is survivable on every PR; full on merge only. |
| Q6 | §1 stack pick (k6) — does verifier have a blocking preference for Locust for Python-team-cohesion reasons? This spec assumes no but worth confirming. |
| Q7 | S8 tier-share scale — 1000 DAU-equivalent is 10% of launch target (10k). Is that enough confidence? Scaling to 10k DAU-equivalent ups runner requirements and runtime (~2h). |
| Q8 | Nightly failures — who gets paged? Slack webhook? GitHub Issues auto-open? Ownership policy needed. |

---

## 10. Acceptance criteria

Track J is done when:

1. `tests/load/` directory ships with all 8 scenario scripts + sidecar + fixtures + CI workflow.
2. On a dedicated test Supabase project, a full S1-S8 run completes within 60 minutes with all 8 blocks-merge thresholds green.
3. `load-test.yml` triggers on merge-to-main and nightly; failure blocks the next production deploy.
4. README documents local-run command, test-project seed/teardown, and ship-gate interpretation.
5. At least one real bug surfaced during run-and-tune is fixed in-tree (confirms the harness actually stresses).
6. The 8 OPEN questions in §9 are resolved or explicitly deferred.

If any of the above fails, track J is not shippable; the uptime MVP cannot exit pre-launch without it (per forever-rule: §14 scale proof is mandatory on uptime-track features).
