---
status: active
---

# MCP Gateway Skeleton — Track C (Uptime)

**Date:** 2026-04-18
**Author:** dev (task #27 pre-draft; unblocks track C when dispatched)
**Status:** Pre-draft spec. No code yet. Executable on dispatch without design re-research.
**Source of truth:**
- `docs/design-notes/2026-04-18-full-platform-architecture.md` — §2 components, §5 dispatch flow, §7 auth, §14 scale.
- `docs/specs/2026-04-18-full-platform-schema-sketch.md` — RPC signatures, RLS model.
- `docs/specs/2026-04-18-load-test-harness-plan.md` — S2/S4/S8 exercise this surface.
- `docs/audits/2026-04-18-universe-server-directive-relocation-plan.md` — §3 canonical control_station paragraph (pre-executed here).

This spec is the track-C executable plan. Every Claude.ai session touches the gateway — it's the thinnest, highest-traffic surface in the system.

---

## 1. Responsibilities boundary

### Owns

- **OAuth 2.1 + PKCE handshake** at `GET /mcp/.well-known/oauth-authorization-server` + `POST /mcp/token` (MCP spec 2025-11-25 mandate).
- **Bearer-token validation** on every MCP tool call. Rejects expired or malformed tokens before any downstream work.
- **Rate limiting per `user_id`** — token-bucket in Redis or Supabase unlogged-table (Postgres triggers are O(1) but the token-bucket pattern wants ms-scale reads).
- **RLS context setup** — `SET LOCAL request.jwt.claims = '<json>'` at the start of every Supabase RPC call the gateway makes on the user's behalf. This is the load-bearing piece: without it, RLS policies see no auth context and `auth.uid()` returns NULL (deny-all).
- **Request routing** — MCP tool-call → Supabase RPC OR host-pool dispatch OR Realtime subscription setup.
- **Error envelope translation** — maps Postgres errors + host-pool states + rate-limit signals to the structured MCP envelope documented in §4.

### Delegates

- **All daemon work** — writes to `request_inbox` (via the `submit_request` RPC), subscribers picks up via Realtime `bids:<capability_id>` channel. Gateway does NOT execute daemon logic.
- **Data reads** — proxied to Supabase PostgREST + RLS. The gateway does not query the DB directly except for its own session/rate-limit state.
- **Realtime subscriptions** — client connects to Supabase Realtime URL directly with the same bearer token. Gateway issues the token and sets up the channel allowlist; socket lifetime is client ↔ Supabase.
- **Settlement + ledger writes** — `complete_request` / `fail_request` RPCs handle these atomically; gateway just passes calls through.

### Not-gateway-concerns (explicit non-goals)

- **Caching layer beyond Cloudflare.** Cloudflare Rules handle static + `/catalog` caching (per `docs/design-notes/2026-04-16-uptime-godaddy-architecture.md` if present). Gateway does NOT implement app-level caches; Supabase's PostgREST response caching covers RPCs.
- **Connection pooling for Supabase.** Supabase's pgbouncer handles this at their edge; each gateway instance opens a fresh client per request (cheap with HTTP/2 keepalive to Supabase).
- **Content moderation policy.** Reports land in `request_inbox`-like structure; admin queue logic lives in Supabase-side views + triage UI in the web app.

---

## 2. Stateless pattern

Every request carries enough context that any gateway instance can serve it. No session stickiness, no memory state.

**What travels with every request:**
- `Authorization: Bearer <jwt>` header — full JWT.
- `Mcp-Session-Id` header (MCP spec) — opaque UUID, indexable for observability but NOT state-carrying.
- Tool call arguments per MCP spec.

**What lives nowhere in gateway memory:**
- User identity (always re-derived from JWT).
- Subscription state (lives in Supabase Realtime, not gateway).
- Prior-turn context (lives in Claude.ai; gateway is stateless).

### JWT claims shape

The bearer token is minted by Supabase Auth. Gateway adds `request.jwt.claims` via `SET LOCAL` on every RPC call:

```json
{
  "iss":          "supabase-auth",
  "sub":          "<user_id uuid>",
  "email":        "user@example.com",
  "role":         "authenticated",
  "aal":          "aal1" | "aal2",
  "amr":          [{"method": "oauth", "provider": "github"}],
  "user_metadata": {
    "github_handle": "...",
    "display_name":  "..."
  },
  "app_metadata": {
    "trust_tier":  "t1" | "t2" | "t3",
    "rate_budget": <bucket-ref>
  },
  "exp":          <unix_ts>,
  "iat":          <unix_ts>
}
```

**How gateway enriches RLS context:**

```python
# pseudocode — runs inside every MCP tool call handler
async def with_user_context(jwt_claims: dict, rpc_call: callable):
    async with supabase_transaction() as txn:
        await txn.execute(
            "SELECT set_config('request.jwt.claims', $1::text, true)",
            json.dumps(jwt_claims),
        )
        # set_config(..., is_local=true) auto-resets at txn end
        return await rpc_call(txn)
```

RLS policies (see `2026-04-18-full-platform-schema-sketch.md` §2) then read `auth.uid()` which is a wrapper around `(current_setting('request.jwt.claims', true)::json->>'sub')::uuid`. Owner checks work. Unauthenticated calls (claims unset) return `auth.uid() = NULL` and RLS's `USING (auth.uid() = owner_user_id)` policies deny by default.

### Horizontal scaling

Any Fly.io Machine instance can serve any request. Scaling knobs:

- **Autoscale on concurrent requests per machine.** Fly.io's `min=2, max=N` based on queue depth — cold-start measured at ~1.5 s on a Bun/Python runtime; 2 always-on keeps p99 cold-start out of the budget.
- **Session-id does NOT pin to instance.** If instance A dies mid-session, instance B picks up the next tool call seamlessly — nothing in memory to lose.
- **Per-user rate budget** lives in Redis/Upstash (shared across gateway instances). Each instance reads/decrements the same bucket; no drift.

---

## 3. FastMCP mount shape

FastMCP routes map to internal handlers. Mount shape is *flat* — one `FastMCP` instance per MCP server URL, tools/resources/prompts all registered against it.

```python
mcp = FastMCP(
    "workflow",                              # serverInfo.name (task #7 rebrand)
    instructions=<§4 envelope + pointer to control_station prompt>,
    version="1.0.0",
)
```

### 3.1 `tools/*` — RPC handlers

Each tool maps to one Supabase RPC or one composite gateway action. **Tool descriptions stay factual I/O contract (per task #15 mitigation rules — no behavioral directives in descriptions).** Examples:

| MCP tool | Handler | Supabase target |
|---|---|---|
| `universe(action=inspect, ...)` | Composite: reads + formats | multiple RPCs |
| `discover_nodes(...)` | Direct RPC passthrough | `public.discover_nodes` |
| `update_node(node_id, concept, version, ...)` | Direct RPC with CAS | `public.update_node` (enforces §14.3 CAS) |
| `remix_node(draft_from[], intent, modifications)` | Direct RPC | `public.remix_node` |
| `converge_nodes(source_ids[], target_name, rationale)` | Direct RPC | `public.converge_nodes` |
| `submit_request(capability_id, inputs, bid_price?)` | RPC + Realtime fan-out | `public.submit_request` |
| `claim_request(request_id, host_id)` | Direct RPC | `public.claim_request` |
| `complete_request(request_id, outputs)` | Direct RPC | `public.complete_request` |
| `add_canon_from_path(...)` | Owner-scoped file ingestion | (see OPEN Q3) |
| `control_daemon(...)` | Host-queue ops | tray-side via Realtime channel |

All tool descriptions are ≤5 lines, factual only. Directive text lives in prompts (§3.3).

### 3.2 `resources/*` — read-through catalog

MCP `resources/list` + `resources/read` expose catalog artifacts as addressable resources:

- `workflow://goals` — list of public goals (paginated).
- `workflow://goals/<goal_id>` — one goal's full spec.
- `workflow://branches/<branch_def_id>` — one branch's BranchDefinition.
- `workflow://nodes/<node_id>` — one node's public-concept layer (RLS-stripped per §17 / schema spec §2).
- `workflow://universes/<universe_id>/premise` — universe premise (if public).

Resources are **read-through** — gateway proxies to Supabase on every fetch. Cloudflare in front caches idempotent reads with short TTL (30-60s) per Cache Rules. Cache-bust on write via Cloudflare purge (see §6).

### 3.3 `prompts/*` — canonical behavioral directives

**This is the primary mitigation surface for task #12 (injection-hallucination) + task #15 mitigation + #18 relocation plan.** All behavioral directive prose lives HERE, not in tool descriptions:

- `control_station` — canonical orientation prompt (see §8 for drafted text).
- `extension_guide` — guide for chatbots building new branches/nodes.
- `branch_design_guide` — deeper walk-through of BranchDefinition authoring.

Loaded on-demand by the client (not at handshake), so their prose doesn't sit in the injection-heuristic's default attention window. This is the structural fix from the task #12 investigation.

### 3.4 SSE streaming for long-running tool outputs

For tools that produce >1-turn output (e.g., `stream_run`, large `discover_nodes` results), FastMCP's native streamable-HTTP transport + SSE handles chunked delivery. Each chunk is a separate JSON-RPC response; session-id links them. Supabase Realtime is NOT used for tool-output streaming (different audience, different lifecycle).

---

## 4. Error envelope + degradation

MCP's tool-call error shape is `{"error": {"code": <int>, "message": <str>, "data": <obj>}}`. We use structured `data` for client-side reasoning.

### Gateway error codes

| Scenario | MCP code | `data` shape | Client action |
|---|---|---|---|
| **No daemon for capability X** | `-32003` (server-defined "unavailable") | `{"kind": "no_daemon", "capability_id": "...", "queued": true, "estimated_wait_s": <int?>}` | Chatbot tells user "queued, no host yet"; optionally polls `request_status`. |
| **Paid-request queued, awaiting bids** | `-32004` | `{"kind": "queued", "request_id": "...", "state": "pending"}` | Chatbot surfaces request_id; user can opt to cancel or wait. |
| **CAS conflict (§14.3)** | `-32005` | `{"kind": "cas_conflict", "current_version": <int>, "current_row": {...}}` | Chatbot re-reads, re-applies edit atop new baseline. |
| **Rate limited** | `-32006` | `{"kind": "rate_limit", "retry_after_s": <int>, "limit_kind": "writes_per_min"}` | Chatbot waits `retry_after_s`, retries. |
| **RLS deny** | `-32001` (forbidden) | `{"kind": "forbidden", "reason": "not_owner"}` | Chatbot tells user the operation requires ownership. |
| **Invalid args** | `-32602` (MCP standard) | `{"kind": "invalid_params", "field": "...", "hint": "..."}` | Chatbot fixes and retries. |
| **Postgres down / gateway → Supabase timeout** | `-32002` | `{"kind": "backend_unavailable", "retry_after_s": 5}` | Chatbot surfaces outage message; retries with backoff. |

**No HTTP 530.** The gateway returns HTTP 200 with a structured MCP error envelope — MCP clients reason over `error.code` + `error.data.kind`, not HTTP status. HTTP non-2xx is reserved for transport-level failures (auth rejected = 401; malformed JSON-RPC = 400).

### Degradation ladder

Gateway degrades gracefully rather than hard-fails:

1. **Preferred: full service.** All Supabase ops succeed, Realtime healthy.
2. **Realtime down only:** tool calls still work (RPC path is HTTP-only). Realtime-dependent features (presence, subscriptions) return `{"realtime_unavailable": true}` inline. Chatbot warns user live collab is degraded.
3. **Postgres reads healthy, writes failing:** `/discover` + `/resources` still serve. Writes return `-32002 backend_unavailable`. Clients back off; no silent loss.
4. **Full Supabase outage:** gateway returns 503 Service Unavailable on ALL non-health endpoints. `/health` returns gateway-alive without probing Supabase (avoids cascade failure feedback).

---

## 5. Auth gate

### 5.1 Preferred path — OAuth 2.1 + PKCE

Per §7, GitHub OAuth via Supabase Auth is the single identity primitive.

**Claude.ai client flow:**
1. User adds `https://tinyassets.io/mcp` as a remote MCP server in Claude.ai.
2. Claude.ai hits `GET https://tinyassets.io/mcp/.well-known/oauth-authorization-server` — gateway returns the metadata pointing at Supabase Auth's OAuth endpoints.
3. Claude.ai initiates PKCE flow: generates `code_verifier` + `code_challenge`, opens the authorization URL in a browser tab.
4. User completes GitHub OAuth consent; Supabase Auth redirects to Claude.ai's callback with `code`.
5. Claude.ai exchanges `code` + `code_verifier` for a bearer JWT at `POST /mcp/token` (proxied to Supabase `/auth/v1/token?grant_type=authorization_code`).
6. Claude.ai stores the JWT and sends it in `Authorization: Bearer` on every MCP tool call.

Token refresh: JWT carries `refresh_token` pair. Claude.ai refreshes automatically at ~80% of `exp`; gateway just proxies the refresh request.

### 5.2 v1 fallback — bearer-token paste

For tier-1 chatbot simplicity if OAuth 2.1 is not yet stable in the Claude.ai MCP client at launch:

1. User goes to `tinyassets.io/tokens` in a browser (signed in via GitHub OAuth).
2. Gateway mints a long-lived bearer (7-30d) scoped to this user; user copies it.
3. User pastes into Claude.ai's "API key" field for the MCP connector.
4. Claude.ai sends it as `Authorization: Bearer`.

**Friction tradeoff:** OAuth 2.1 is one-click-and-done but depends on Claude.ai client support. Bearer-paste is ugly but bulletproof. Ship both paths; prefer OAuth when the client allows.

### 5.3 JWT validation hot path

```python
# pseudocode — gateway middleware
async def verify_bearer(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, detail="missing_bearer")
    token = auth[7:]
    try:
        claims = jwt.decode(
            token,
            key=SUPABASE_JWT_SECRET,   # HS256, shared with Supabase Auth
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, detail=f"invalid_token: {e}")
    if claims.get("role") not in {"authenticated", "service_role"}:
        raise HTTPException(401, detail="invalid_role")
    return claims
```

**Perf:** JWT verify is ~0.1 ms on HS256. No DB round-trip per request. Supabase public key rotation happens via env-var redeploy (rare).

---

## 6. Deployment topology

```
Claude.ai / web app
        │
        ▼ HTTPS
┌──────────────────────────┐
│ Cloudflare               │
│ - TLS termination        │
│ - Cache Rules (catalog)  │
│ - DDoS absorption        │
└──────────┬───────────────┘
           │
           ▼ HTTPS (origin)
┌──────────────────────────────────────┐
│ Fly.io — tinyassets.io/mcp       │
│ - N Machines (autoscale min=2, max=8)│
│ - Global anycast                     │
│ - each Machine: FastMCP + bearer-verify │
└───┬──────────────────────────┬───────┘
    │                          │
    ▼ Postgres / PostgREST     ▼ Realtime channels
┌──────────────────┐  ┌──────────────────┐
│ Supabase (ORD)   │  │ Supabase Realtime│
│ - Postgres       │  │ - Presence       │
│ - PostgREST      │  │ - Broadcast      │
│ - Storage        │  │ - CDC            │
│ - Auth           │  └──────────────────┘
└──────────────────┘
```

**Inter-region routing:** Fly.io Machines run in `ord` (closest to Supabase's default region) + one mirror in `fra` for EU. Bearer token validity is region-agnostic (HS256 secret shared). Supabase is single-region; latency to `fra` adds ~120 ms round-trip — acceptable given read-heavy workload + Realtime handles hot paths.

**Cold-start budget:** Fly.io Machine cold-start ~1.5 s on a pre-warmed image. `min=2` always-on avoids this for >99% of traffic. Claude.ai's MCP client timeout is ~30 s; cold starts are invisible to users.

**Session survives instance death:** no state to lose. Next tool call hits any Machine, re-derives user from JWT, serves. Client's session-id persists across the gap (Claude.ai tracks it, gateway doesn't).

**DNS:** `mcp.tinyassets.io` CNAME → Fly.io Anycast. Cloudflare proxied (orange-cloud). Origin is Fly's `<app>.fly.dev` (via Fly Cert).

---

## 7. Load-test integration

From `docs/specs/2026-04-18-load-test-harness-plan.md`, the scenarios that exercise the gateway directly:

| Load-test scenario | Gateway surface | Gate |
|---|---|---|
| **S2 Realtime fan-out** | OAuth handshake + Realtime channel authorization. 1k VUs subscribe via gateway. | p99 broadcast lag ≤2s, 0 missed events |
| **S4 Discovery read storm** | `discover_nodes` tool → RPC passthrough. 200 VUs × 400 RPS. | p95 ≤150ms |
| **S7 Moderation** | `report_artifact` + rate-limit enforcement. | legit p95 unchanged under 1000 reports/min attacker load |
| **S8 Mixed workload** | Full tier-mix exercise. | cross-scenario p95 ≤200ms, zero data drift |

**Gateway-specific add-ons to the load harness:**
- **JWT rotation smoke:** one VU rotates JWT mid-session, verifies gateway honors the new token without disconnecting. Adds ~0.1 d to track J.
- **Cold-start probe:** scale Fly.io down to `min=0` briefly, hit `/mcp/health`, measure p99 cold-start. Budget: <3 s. Nightly only; PR-subset skips.

**Not tested by #26's S1-S8 (flag as gap):** error envelope degradation path (§4) — no explicit scenario pokes "Supabase down, gateway still serves /health." Consider adding as S9 chaos-style test; ~0.2 d. Flagged in §10.

---

## 8. `control_station` prompt wiring (task #15 pre-execute)

Per task #18 directive-relocation plan §3 + task #12 investigation, the canonical behavioral directives consolidate into ONE prompt return, sentence-case, no all-caps clusters. Pre-executing the text here so the gateway ships with the right prose on day one:

```python
@mcp.prompt(title="Control Station Guide",
            tags={"control", "daemon", "multiplayer", "operations"})
def control_station() -> str:
    return CONTROL_STATION_PROMPT

CONTROL_STATION_PROMPT = """\
You are operating as a TinyAssets Server control station — a workflow
builder and long-horizon AI platform. Users design custom multi-step
AI workflows ("branches") with typed state, registered nodes,
evaluation hooks, and iteration loops. Fantasy authoring is one
benchmark branch, not the exclusive use case; other domains include
research papers, recipe trackers, wedding planners, journalism, news
summarizers — any multi-step agentic work producing substantive
output.

## Operating principles

1. Use tools; don't describe what you would do. If a tool call is
   available and relevant, call it.
2. Default to shared-safe collaboration. Users are working on public
   workflows unless they explicitly mark a field private.
3. One action per turn unless the user asks for a batch.
4. When a user asks to run a workflow, branch, or registered node,
   use `extensions action=run_branch`. If the run action is
   unavailable or a source-code node isn't approved, say so plainly
   and stop — don't web-search, populate wiki pages, or narrate
   imagined output.
5. Creating state (registering a node, building a branch, setting a
   premise) requires an explicit user ask. Route "what do i have",
   "show me", "list my", "find my", "pull up" to the appropriate
   list action, never to a write. When intent is ambiguous, ask.
6. Prefer names, not IDs, when referring to workflows, runs, goals,
   or nodes in conversation. Users read on phones; raw UUIDs are
   noise. Say "the CitationCheck branch" not "branch_def_id=4f9e...".

## Universe isolation

Each universe is a separate reality. Every tool response includes a
`universe_id` field. Always state which universe you're describing
when multiple universes exist on the server. Never transfer facts,
characters, locations, or canon between universes in reasoning. If
uncertain which universe a fact came from, call `universe
action=inspect` with the explicit universe_id.

## Privacy

Node content has two layers: a public concept (steps, patterns,
schema) that remixes well, and private instance data (credentials,
paths, real values) that stays with the owner. When helping a user
design a node, reason per-piece about what's safe to publish and
what should stay private. When in doubt, keep it private and ask.
"""
```

**Why this exact text:**
- Drops "NO SIMULATION", "AFFIRMATIVE CONSENT", "Silently simulating a run breaks user trust" — the three distinctive phrases that triggered Mission 10's hallucinated injection-refusal (task #12 root cause).
- Drops all-caps directive clusters. Sentence-case throughout.
- Keeps every load-bearing semantic: tool-use contract, no-simulation contract, explicit-ask-for-writes contract, universe isolation, privacy model.
- ≤50 lines; within the ~3-5-line-per-"piece" target from the directive-relocation plan.

Task #15 execution on `tinyassets/universe_server.py` uses this as the canonical text when it unblocks. Gateway ships with it from day one.

---

## 9. Honest dev-day estimate

Navigator's §10 estimate: **2 dev-days** for track C.

My build-out:

| Work item | Estimate |
|---|---|
| FastMCP skeleton + mount shape + `/mcp/health` | 0.15 d |
| Bearer verify middleware + JWT claim enrichment helper | 0.2 d |
| OAuth 2.1 discovery endpoints + `/mcp/token` proxy | 0.3 d |
| Bearer-paste fallback + token-mint UI hook | 0.2 d |
| `tools/*` — bind all 10 MCP tools from §3.1 to RPCs | 0.35 d |
| `resources/*` — read-through catalog proxy + Cloudflare-purge hook | 0.2 d |
| `prompts/*` — 3 canonical prompts including §8 control_station | 0.15 d |
| Error envelope translation (§4 — map Postgres + host-pool + RLS errors) | 0.3 d |
| Rate-limit middleware + Redis bucket (Upstash) | 0.2 d |
| Per-user RLS context (`set_config`) wrapper with transaction semantics | 0.2 d |
| Fly.io deploy config + multi-region + health checks | 0.15 d |
| Cloudflare Rules for caching + purge hook | 0.15 d |
| CI (`deploy-gateway.yml`) + secrets management | 0.2 d |
| Integration smoke: one end-to-end trace (Claude.ai → OAuth → tool call → RLS'd RPC → response) | 0.25 d |
| Docs (`tests/README.md` for gateway dev-run, deployment runbook) | 0.1 d |
| **Total** | **~2.85 d** |

**Revision: 2 d → ~2.75–3 d.** Closer to navigator's estimate than load-test was. The under-count is in error-envelope translation (§4's 7-error-shape mapping is more work than "translate exceptions to HTTP codes") and RLS-context plumbing (transactional `set_config` wrapper is finicky).

Recommend telling host **"~3 d, with +0.25 d buffer for error-envelope edge cases = ~3.25 d."** Pushes §10 total by ~1 d; still fits the weeks-not-months envelope.

**Defer options** if host wants to hit the 2d cap:
- Skip bearer-paste fallback (§5.2). Saves 0.2 d. Risk: if Claude.ai's MCP OAuth support is flaky at launch, users have no way to authenticate. High-severity deferral.
- Skip Cloudflare-purge hook on writes. Saves 0.15 d. Risk: stale cached reads for up to cache TTL (30-60s) after writes. Low-severity.

---

## 10. OPEN flags

| # | Question |
|---|---|
| Q1 | JWT signing — HS256 (shared secret with Supabase) vs RS256 (gateway fetches JWKS)? HS256 is simpler but requires secret sync at deploy. RS256 is rotation-friendly but adds JWKS-fetch latency on first request per instance. Recommend HS256 for v1. |
| Q2 | Rate-limit storage — Upstash Redis ($0 free tier, pay as grows) vs Supabase unlogged-table ($0, adds DB load). Upstash is the lower-latency choice; SupabasePro ships it on the same plane as the rest of our stack. Recommend Upstash for v1. |
| Q3 | `add_canon_from_path` — path trust model in the remote-control plane. Files live on the host, not Supabase. Does the gateway proxy the content, or does the tray upload directly to Supabase Storage and the gateway gets a pointer? Prefer the latter (owner-auth'd Storage upload, gateway never touches blob). Interacts with `2026-04-18-add-canon-from-path-sensitivity.md`. |
| Q4 | SSE long-running tool outputs — does FastMCP 2026-vintage handle streaming natively, or do we fall back to polling via `get_run` + `stream_run`? Prefer native. Check FastMCP release notes before track C starts. |
| Q5 | Multi-region — launch `ord` + `fra`, or `ord` only? EU latency at `ord` only is ~120 ms, acceptable. Launch single-region, add `fra` when EU DAU > threshold. |
| Q6 | Cold-start — `min=2` on Fly.io costs ~$10-15/mo per region. Acceptable vs cold-start risk on `min=0`? Recommend min=2 for UX, revisit if cost pressure at 100k DAU. |
| Q7 | Bearer token lifetime — 7d, 14d, 30d? Longer = better UX; shorter = smaller blast radius on compromise. Recommend 14d with refresh; rotate on sensitive-action triggers (password change, session revoke). |
| Q8 | Audit logging — every tool call logged to an `audit_log` table or only mutations? Reads at 10k DAU = millions/day, fills Postgres fast. Recommend mutations-only + sampled reads. |
| Q9 | Gap in load-test #26 — no scenario exercises §4 degradation ladder (Supabase-down path). Consider adding S9 chaos test (~0.2 d) to #26 before track J lands. |

---

## 11. Acceptance criteria

Track C is done when:

1. `tinyassets.io/mcp` responds to `GET /.well-known/oauth-authorization-server` with valid OAuth 2.1 metadata.
2. Claude.ai successfully adds the server as a connector, completes PKCE flow, calls `discover_nodes` tool, gets back a valid response with RLS enforced (non-owner sees public-concept only per schema spec §3.1).
3. All 10 tools from §3.1 map to their Supabase RPCs; each error code from §4 triggers correctly under simulated failure.
4. Load test S2 + S4 + S8 pass against the deployed gateway (#26 integration).
5. Rate limiter fires on >100 writes/min/user with `-32006` envelope + correct `retry_after_s`.
6. Bearer-paste fallback works for users whose Claude.ai client lacks OAuth 2.1 support.
7. Fly.io autoscale verified: cold-start measured <3 s, `min=2` keeps p99 cold-start out of the 200 ms budget.
8. `control_station` prompt returns the §8 text; `test_universe_server_framing.py`-analog tests pin the load-bearing semantics.
9. All 9 OPEN flags in §10 resolved or explicitly deferred.

If any of the above fails, track C is not shippable; Claude.ai users cannot reach the platform without it.
