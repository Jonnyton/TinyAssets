# Multi-Tenant Hosted Runtime

**Status:** Superseded 2026-04-12 by the GitHub-as-catalog direction. Retained as historical reference in case the hosted-runtime path ever becomes relevant. See `docs/research/github_as_catalog.md` for the shipping direction.

Reference for running TinyAssets daemons on always-on shared infrastructure: any number of users, any number of daemons, host's machine OFF. Hybrid by default — when a user's desktop tray is online, it becomes a worker; when offline, cloud picks up. Self-host stays available but is no longer the only path. All costs are rough order-of-magnitude; items marked **unconfirmed** need live verification.

Current runtime per universe (observed at `output/default-universe/`): `checkpoints.db` (LangGraph SqliteSaver), `knowledge.db`, `story.db`, `world_state.db`, LanceDB vector dir, plus prose/notes files. Roughly 4 SQLite DBs + 1 LanceDB + filesystem artifacts per universe. Multiple universes per user are expected.

## 1. Multi-tenant runtime options

| Option | Tenant isolation | Fit for LangGraph stateful agents | ~100 users | ~1k users | ~10k users | Complexity |
|---|---|---|---|---|---|---|
| **Fly.io Machines + Volumes** | One Machine per tenant; volume per tenant; scale-to-zero (~300ms wake). | Strong — volumes persist SQLite/LanceDB, SSE/websockets native, Docker-native. | $30–80/mo | $300–800/mo | $3k–8k/mo (pool needed) | Medium |
| **Railway** | Per-service containers, volumes. | Works but no per-tenant Machine primitive. | $20–50/mo | Not viable | Not viable | Medium |
| **Render** | Per-service Docker + disk. Free tier sleeps. | Paid tier viable single-tenant. | $20+/mo | $150+/mo | Not viable | Medium |
| **Hetzner CX32 + Docker Compose** | Shared host; per-tenant dir + subprocess/thread isolation. | Cheapest; runs LangGraph, SQLite, LanceDB natively. | €6/mo | €30–60/mo | €150–400/mo | High (ops) |
| **AWS Fargate / ECS** | Per-task containers; EFS shared volumes. | Works. EFS latency hurts SQLite. | $80+/mo | $800+/mo | $8k+/mo | High |
| **Modal** | Per-function serverless with volumes. | Good for burst; long-lived MCP less natural. | ~$30/mo | ~$300/mo | Compute-heavy pricing | Medium |
| **LangGraph Platform (managed)** | Thread model, managed Postgres. | Best architectural fit on paper. **Unconfirmed** MCP transport compatibility. | Dev $39/mo | Unclear | Enterprise | Low (if fits) |
| **Replicate / Beam / RunPod** | Serverless GPU-first. | Poor fit for stateful CPU agents. | — | — | — | — |

**Recommendation:** Fly.io Machines + Volumes for alpha. Hetzner at 500+ users. LangGraph Platform as managed exit ramp if MCP-compatible.

## 2. Storage per-tenant

| Pattern | Isolation | SqliteSaver? | LanceDB? | Complexity |
|---|---|---|---|---|
| Per-tenant dir on shared volume | Filesystem-level | Yes (paths CWD-aware via `_paths.py`) | Yes | Low |
| Per-tenant DBs + LanceDB dirs on object storage (S3/R2) + local cache | Strong | Requires VFS (litestream/LiteFS/Turso) | Native S3 backend | Medium |
| Postgres checkpointer + per-tenant schema | Strong | Swap SqliteSaver → `PostgresSaver` | pgvector or keep LanceDB | Medium |
| One Postgres, `tenant_id` column, row-level security | Weak | Same Postgres swap | Same question | High |
| Turso (libSQL) | Per-tenant logical DB, 500 free | **Unconfirmed** libSQL compatibility | No | Medium |
| LiteFS (Fly.io) | Distributed SQLite replication | Yes | No | Medium |

**Recommendation:** Phase 1 per-tenant dir on Fly volume. Phase 2 swap to `PostgresSaver` (LangGraph-upstream, respects the SqliteSaver-not-Async hard rule), LanceDB per-tenant on object storage with local cache. LanceDB singleton in `tinyassets/retrieval/vector_store.py` must become per-tenant-keyed.

## 3. Auth (OAuth 2.1 + DCR per MCP spec 2025-03-26)

| Option | DCR support | Integration effort | Cost |
|---|---|---|---|
| Clerk | Yes (2024) | Low | Free to 10k MAU, $25/mo+ |
| Auth0 | Yes | Low–medium | Free to 7.5k MAU |
| Ory Hydra (self-host) | Yes | High | Infra only |
| Cloudflare `workers-oauth-provider` | Yes | Medium — most complete public DCR for MCP | Free on Workers |
| WorkOS | Partial (**unconfirmed**) | Low | $125/mo |
| Roll-your-own on FastAPI | Build yourself | High | Infra only |

**Recommendation:** Clerk or Cloudflare `workers-oauth-provider` for alpha.

## 4. Rate limits and quotas

Enforcement points in current codebase:
- **LLM tokens:** provider router with per-tenant counter (Redis/Upstash).
- **Concurrent runs:** `tinyassets/runs.py` semaphore per tenant.
- **Storage:** on-write check of per-tenant dir size.
- **Request rate:** Cloudflare in front.

Mirror patterns: Supabase (per-project quotas), Vercel (per-project invocation budgets), Modal (per-workspace spend caps). Enforce at control plane, not worker.

## 5. Hybrid cloud-local compute (user machine as optional worker)

Runtime is logical; compute is a pool of workers including cloud fleet + every online user-tray. Scheduler picks by data locality, cost, user preference. Worker death → another resumes from checkpoint.

**Prior art:**
- **Ray** — distributed actors + object store. Cleanest fit; overkill for alpha.
- **Celery + Redis/RabbitMQ** — battle-tested task queue with priority routing, ACK timeouts, worker registration. Trays and cloud are separate Celery pools.
- **Temporal** — durable workflows, at-least-once, activity heartbeats, automatic retry. Strongest guarantees; heavy self-host.
- **Dask distributed** — lighter Ray; less mature for stateful long-running work.
- **LangServe + remote graphs** — **unconfirmed** mid-step failover quality.
- **BOINC / Folding@home** — embarrassingly parallel batch, not stateful agents. Wrong shape.
- **torch.distributed / Accelerate** — GPU training; wrong shape.

**LangGraph checkpoint portability (the decisive question).** SqliteSaver checkpoints are SQLite files. Moving mid-run requires graceful stop + file ship + resume. SQLite format is forward-compatible; LangGraph checkpoint schema across minor versions **unconfirmed**. Safer: serialize to neutral blob on transfer, or use shared `PostgresSaver` so no file transfer is needed. **Hybrid effectively forces `PostgresSaver` adoption earlier than single-tenant analysis suggested** — shared Postgres makes stop-move-resume 1–3s vs 5–15s file transfer.

**Work-assignment scheduler:** data locality, user preference flag, LLM cost, latency, worker capacity. Heartbeats + leases: worker takes N-minute lease, heartbeats every 15–30s; expired lease re-queued. Celery + Redis for alpha; Temporal when durability matters.

**LLM key routing:** BYO key per user (tagged on run, provider router reads from context not env); OR host-paid key + quota.

**Tray-as-Ollama-worker:** tray advertises `{ollama_models, endpoint}` to scheduler; cloud routes LLM calls back to tray over persistent connection. Outbound websocket from tray is NAT-friendlier than inbound tunnel.

**Security model:**
- Cross-tenant scheduling restricted to cloud workers in v1. User-tray runs scoped to tenant's own universes (`run.tenant_id == worker.tenant_id`).
- Never ship tenant A's data to tenant B's tray.
- User-contributed custom node code only on owner's tray or sandboxed cloud worker.
- All tray↔hub traffic TLS; per-user token bound to OAuth identity.

## 6. Migration path

- **Self-host → hosted:** export universe dir tarball via MCP action; host import endpoint unpacks into tenant-scoped dir; OAuth claim on first connect.
- **Hosted → self-host:** reverse; run local MCPB bundle; CLI import populates `output/`.
- **Hosted → hybrid:** tray opens persistent authenticated websocket, registers capacity + LLM endpoints + universe locality; scheduler may route to tray; cloud resumes on tray drop.
- **Hybrid → hosted-only:** automatic — scheduler stops dispatching to offline tray.

## 7. Cloudflare's role

- DNS (GoDaddy → Cloudflare name servers).
- Edge caching for landing / catalog.
- WAF + per-IP rate limiting.
- Workers for OAuth flow (if using `workers-oauth-provider`).
- Tunnel: self-host path + inbound route to user-tray acting as hybrid worker.

## 8. Open questions for planner

1. LangGraph Platform MCP-transport compatibility — decides whether it's a real exit ramp.
2. Per-tenant Fly Machine vs shared Machine with keyed SqliteSaver + LanceDB — at what tenant count does per-Machine pricing break?
3. Commit to `PostgresSaver` before or during hybrid rollout? Hybrid effectively forces it.
4. Per-tenant LLM cost pass-through (BYO key) vs absorbed (quota-gated)?
5. DCR adoption in real MCP clients today — Claude.ai, Claude Desktop? If most use bearer tokens, DCR is future-proofing.
6. Scheduler: Celery+Redis (alpha), Temporal (durable, heavier), or Ray (opsy)?
7. v1 allow tray to execute runs for *other* tenants (volunteer pool)? Recommend strict-owner.
8. Tray↔hub protocol: persistent outbound websocket (NAT-friendly) vs inbound tunnel?
9. Soft-delete / recovery window for evicted tenants?
10. GDPR / data residency — hybrid complicates (tray=EU, hub=US — where does "processing" happen legally)?
