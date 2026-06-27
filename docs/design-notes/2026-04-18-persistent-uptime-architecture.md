---
status: superseded
superseded_by: docs/design-notes/2026-04-18-full-platform-architecture.md
---

# Persistent Uptime Architecture — Control Plane + Data Plane

**Status (2026-04-18 update):** **SUPERSEDED** by `2026-04-18-full-platform-architecture.md`. Host rejected the phased rollout (Phase 1 thin relay → Phase 2 state migration → Phase 3 paid failover) in favor of a single-build collaborative backend. Retained as historical reference for the plane-split analysis, hosting-option matrix, and Cloudflare-front deep-dive, which remain useful input to the successor note.

**Hostname history (2026-04-18 → 2026-04-20):** this doc originally named `api.tinyassets.io` as the MCP gateway hostname; `api.` was never created. Post-P0, a Cloudflare Worker shipped to restore apex `tinyassets.io/mcp` as canonical user-facing; the Worker proxies to tunnel origin `mcp.tinyassets.io`. Body text uses apex URL for user-facing MCP references; tunnel-origin mentions keep the `mcp.` subdomain.

**Original status:** Design note for host review. Proposes the minimum viable always-on piece for v1 and sequences the rest.

**Host directive (2026-04-18):** the long-term system must be accessible 24/7 for node creation and daemon execution even when the reference host is off. At thousands of daily users and daemons, no single host being online can take down the system.

**Three hard requirements, restated:**
1. Always-on for node work — users create, browse, edit nodes 24/7 even when zero daemons are hosted.
2. Full capability when any host is serving — if ≥1 host is online serving a capability, users who need that capability get it.
3. Host-independence — the reference host (Jonathan's laptop) being off must not take down the system.

**Alignment constraints (non-negotiable):**
- *Main is always downloadable* (PLAN.md §Distribution). The control plane must not worsen fresh-install.
- *Distribution horizon: weeks, not months* (project memory). Recommend the minimum viable always-on piece for v1; defer the rest.
- *Paid-request bid model exists* (project memory: requester sets node+LLM+price; daemons prefer higher bids). Integrate, don't duplicate.
- *Daemon is the user-facing brand* (project memory). Design copy keeps daemon vocabulary.
- *Rebrand in-flight: Universe Server → TinyAssets Server.* This note uses "TinyAssets Server" and "Workflow control plane."

**Prior research this supersedes / builds on:**
- `docs/research/always_on_hosting_and_federation.md` — hosting-option and federation patterns (hosting matrix, multi-tenant MCP patterns, Cloudflare-only path).
- `docs/research/github_as_catalog.md` — the shipping direction for shared state: GitHub is canonical, hosts clone and run locally, contributions flow via PR.

Both are retained; this note imports their conclusions and sharpens them against the 2026-04-18 host directive.

---

## §1. Current State — What Breaks When the Host Is Offline

Today's topology:

```
User (Claude.ai webchat)
  -> MCP connector at https://tinyassets.io/mcp
     -> Cloudflare DNS + named tunnel (token hardcoded in universe_tray.py:50)
        -> cloudflared on Jonathan's laptop
           -> FastMCP on localhost:8001 (tinyassets/universe_server.py)
              -> per-universe files under output/<universe>/ (SQLite + LanceDB + notes.json)
              -> per-host SQLite: ledger, bid_ledger, settlements
              -> one or more Daemon processes (fantasy_daemon.__main__)
```

`universe_tray.py` starts three things: N provider-pinned Daemon processes, the TinyAssets Server (FastMCP on :8001), and cloudflared routing `tinyassets.io` → `localhost:8001`.

**What breaks when the host laptop is off (today, reproducible):**
- `tinyassets.io/mcp` returns HTTP 530 (no-origin). The MCP connector in every Claude.ai account is dead until the laptop is back.
- Zero read access to *any* universe. No browse, no catalog, no landing page, no "what goals exist." The tunnel has no static fallback.
- No node creation or editing. Draft operations happen through MCP tool calls that terminate at the offline origin.
- No daemon bidding, no request queue, no request intake — the `/v1/universes/{uid}/requests` surface and bid market live inside the offline process.
- Identity broken. Chatbot-tied identity via Claude.ai works only when MCP responds.
- `cloudflared.exe` is also a per-host dependency (not bundled — friction flagged in the prior research file).

**Failure mode is total.** There is no reduced-capability mode, no read-only fallback, no queue-and-retry. One laptop being asleep is equivalent to the product not existing.

This is the problem statement. The fix is a durable always-on service that owns the minimum state required for (1) and (2) above, while preserving the GitHub-as-catalog direction and the local-first daemon-execution model.

---

## §2. Control Plane vs Data Plane — The Split

**Principle.** Separate what *must never be down* from what *can degrade gracefully.* Put the first in a boring, cheap, always-on service. Leave the second on hosts.

### §2.1 What must be always-on (Workflow control plane)

- **MCP entrypoint.** `https://tinyassets.io/mcp` must respond 24/7, even if no host is up. When no host serves a needed capability, it returns a structured "no daemon available" response (not HTTP 530). This is the difference between "the product is offline" and "the product is awake and waiting."
- **Node / Goal / Branch catalog reads.** Browse, search, fetch-by-slug. These are already GitHub-native per the GitHub-as-catalog research — they can be served directly from a CDN cache of the repo. The control plane is a thin read-through over the catalog repo.
- **Identity + session.** OAuth 2.1 issuer (MCP spec 2025-03-26 mandate — confirmed live in the FastMCP and Cloudflare MCP stacks per the 2026 docs). Tokens minted here are honored by every host.
- **Request inbox + bid matching.** A user posts a paid request ("I want node X run against LLM Y at price Z"); the control plane stores it until a qualifying host claims it. Daemons poll for eligible bids; cheapest-matching-LLM wins per the existing bid model. This inbox is the *one* piece of new durable state v1 absolutely needs.
- **Host directory.** Who is online right now, which capabilities they serve, TTL heartbeats. Stateless-ish: a small KV with 60s expiry.
- **Landing page + copy.** Static; served from the CDN. "Summon the daemon" copy stays.

### §2.2 What stays host-contributed (data plane)

- **Daemon execution.** LangGraph runs, LLM calls, tool invocations. Opus is expensive and diverse per host; no reason to centralize.
- **Universe content store.** LanceDB, SQLite, notes.json, the commit packet stream. Large, per-universe, local-first (PLAN.md §Local-first execution).
- **Soul files, KG, vector indexes.** Host-local by design.
- **External tool invocation.** Unreal, Ollama, local binaries (PLAN.md §Software surface). Intrinsically host-bound.
- **Draft files.** Per the GitHub-as-catalog `drafts/` scheme: lives on the host until explicitly `share_branch` promotes it.

### §2.3 Diagram

```
                      ┌───────────────────────────────────────┐
                      │         Workflow Control Plane        │
                      │          (always-on, ~$5-15/mo)       │
                      │                                       │
Users (Claude.ai ─────┼──► MCP gateway (FastMCP or proxy)     │
or other MCP          │    ├─ identity / OAuth 2.1            │
clients)              │    ├─ catalog read-through (CDN)      │
                      │    ├─ request inbox + bid matching    │
                      │    ├─ host directory (heartbeat KV)   │
                      │    └─ capability router               │
                      │              │                        │
                      │              │ (dispatches to host)   │
                      └──────────────┼────────────────────────┘
                                     │
                     ┌───────────────┼────────────────┐
                     ▼               ▼                ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │ Host A       │  │ Host B       │  │ Host N ...   │
            │  (laptop,    │  │  (VPS,       │  │              │
            │   intermitt.)│  │   always-on) │  │              │
            │  - Daemons   │  │  - Daemons   │  │              │
            │  - Content   │  │  - Content   │  │              │
            │  - KG/Vector │  │  - KG/Vector │  │              │
            └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                   │                 │                 │
                   └─────────────────┼─────────────────┘
                                     ▼
                    ┌─────────────────────────────────┐
                    │   GitHub catalog (goals,        │
                    │   branches, nodes — canonical)  │
                    │   Git LFS / releases for large  │
                    └─────────────────────────────────┘
```

**Key property:** when *all* hosts are offline, the control plane still serves catalog reads (from GitHub cache), accepts queued requests for future execution, and returns a structured "no host online for this capability" response. Requirement (1) is satisfied without any host.

---

## §3. Options for Control-Plane Hosting

Inherits the matrix from `always_on_hosting_and_federation.md` §1. 2026 updates below.

| Option | Cost @1k DAU | Cost @10k DAU | Cost @100k DAU | Complexity | Lock-in | Python? | Fit |
|---|---|---|---|---|---|---|---|
| **Cloudflare Workers + Durable Objects + D1/KV** | $5 | $10–20 | $50–150 | Low | Medium | Poor (Pyodide) | Strongest for edge + stateful sessions |
| **Fly.io Machines + volumes** | $5–15 | $15–40 | $100–300 | Low | Low | Native | Simplest port of current Python FastMCP |
| **Hetzner CX22 VPS** | €4.5 | €4.5–9 | €20–50 | Medium (self-ops) | None | Native | Cheapest, full control |
| **DigitalOcean Droplet** | $6 | $12–24 | $50–200 | Medium | None | Native | Like Hetzner, easier ops |
| **Railway / Render** | $5–10 | $20–50 | $100–400 | Low | Medium | Native | Fast to deploy, usage-pricing risk |
| **AWS Lambda + DynamoDB + API Gateway** | $5–20 | $30–100 | $150–600 | High (SSE awkward) | High | Native | Scale-to-zero, but session affinity painful |

**2026 SOTA updates (verified 2026-04-18):**
- **Cloudflare Durable Objects is now on the free tier** and has first-class MCP hibernation support via the Agents SDK. Each MCP session can be a Durable Object that sleeps during inactivity and wakes with state preserved. This is structurally the cleanest MCP-native host *if* you accept Workers/TS for the control plane.
- **FastMCP streamable-HTTP** is production-standard as of the 2026 MCP spec; OAuth 2.1 + PKCE is mandated. Any host we pick must support long-lived HTTP (SSE / streamable HTTP).
- **Fly.io + LiteFS** is mature for small SQLite DBs but has a ~100 txn/s write ceiling and conflicts with autostop. Usable for the host directory and request inbox; not a fit for heavy per-universe writes (those stay host-local anyway).

### §3.1 GoDaddy-first option (existing infra, sunk cost)

**Directive:** use GoDaddy + the owned `tinyassets.io` domain as much as is useful before recommending new vendors. This is the starting option, not a fallback.

**What GoDaddy sells (2026 public-plan survey):**

| GoDaddy tier | What it supports | Fit for Workflow control plane |
|---|---|---|
| **Economy / Deluxe / Ultimate shared hosting** | PHP 7/8, MySQL/MariaDB, cPanel, .htaccess, static files. No long-running daemons, no arbitrary ports, no WebSockets / SSE beyond what Apache+PHP allows. | **Static catalog + landing page: YES.** Dynamic MCP control plane: **NO.** FastMCP streamable-HTTP needs persistent Python 3.11+ with long-lived connections; shared PHP tiers can't host it. |
| **Managed WordPress** | PHP + MySQL + WP runtime, CDN. | Landing page only. Not a control plane. |
| **Business Hosting** | Dedicated resources, still LAMP-shaped. Cron jobs, SSH. | Could run a Python process with effort but no official Python runtime; long-lived streamable HTTP is fragile here. Not recommended. |
| **VPS (Standard / Ultimate / Pro self-managed)** | Full root Linux (Ubuntu/CentOS/AlmaLinux), arbitrary ports, systemd, persistent disk. Tiers roughly $7–40/mo. | **Yes — full control plane fits here.** Functionally equivalent to Hetzner/DigitalOcean. |
| **Dedicated servers** | Full hardware. | Overkill until 100k DAU. |

**Subdomains on `tinyassets.io` are free leverage** regardless of tier:
- `tinyassets.io/` — static landing page. Cheapest GoDaddy shared tier can host it.
- `tinyassets.io/catalog/*` — static snapshot of the catalog repo, served from GoDaddy or GitHub Pages CNAME.
- `tinyassets.io` — dynamic control plane (MCP gateway, OAuth issuer, request inbox). Needs the Python-capable tier.
- `host-<slug>.tinyassets.io` — per-host tunnel ingress; wildcard CNAME for federation in v2+.
- `tinyassets.io` or keep the path `tinyassets.io/mcp` — MCP entrypoint for clients. Both work.

**Three concrete GoDaddy-first scenarios:**

1. **Host has only shared hosting.** Then GoDaddy hosts static landing + static catalog at `tinyassets.io/` and `tinyassets.io/catalog/*`. Dynamic control plane goes on the cheapest external Python-capable host (Fly.io $5/mo, or upgrade GoDaddy to VPS). Even this split is a real partial win on requirement (1) — users hitting the domain when the laptop is off get a working landing page instead of HTTP 530.

2. **Host has or upgrades to GoDaddy VPS.** Then the entire Phase 1 control plane lives on `tinyassets.io` under one GoDaddy bill. Cloudflare optionally stays in front for TLS/CDN of static surfaces. Cleanest "one vendor" outcome.

3. **Host has Business Hosting.** Possible but fragile for streamable HTTP. Upgrading to VPS within GoDaddy is better than wrestling Business Hosting into a daemon-shaped role.

**Do not force-fit.** If the current tier is Economy shared and host doesn't want to upgrade, static-on-GoDaddy + dynamic-on-Fly is a legitimate answer. What we must not do is cram a Python MCP server into a PHP shared tier and pretend it works.

### §3.2 External-host options (matrix)

Inherits from `docs/research/always_on_hosting_and_federation.md` §1, with 2026 SOTA updates.

| Option | Cost @1k DAU | Cost @10k DAU | Cost @100k DAU | Complexity | Lock-in | Python? | Fit |
|---|---|---|---|---|---|---|---|
| **GoDaddy VPS (Standard tier upgrade)** | ~$7 | $15–25 | $40–80 | Medium (self-ops Linux) | None | Native | Best if host accepts the upgrade — single vendor, sunk domain |
| **Cloudflare Workers + Durable Objects + D1/KV** | $5 | $10–20 | $50–150 | Low | Medium | Poor (Pyodide) | Structurally cleanest for MCP sessions, but TS rewrite cost |
| **Fly.io Machines + volumes** | $5–15 | $15–40 | $100–300 | Low | Low | Native | Simplest port of current Python FastMCP |
| **Hetzner CX22 VPS** | €4.5 | €4.5–9 | €20–50 | Medium | None | Native | Cheapest, full control |
| **DigitalOcean Droplet** | $6 | $12–24 | $50–200 | Medium | None | Native | Like Hetzner, easier ops |
| **Railway / Render** | $5–10 | $20–50 | $100–400 | Low | Medium | Native | Fast to deploy, usage-pricing risk |
| **AWS Lambda + DynamoDB + API Gateway** | $5–20 | $30–100 | $150–600 | High (SSE awkward) | High | Native | Scale-to-zero, session affinity painful |

**2026 SOTA updates (verified 2026-04-18):**
- **Cloudflare Durable Objects is now on the free tier** and has first-class MCP hibernation support via the Agents SDK. Each MCP session can be a Durable Object that sleeps during inactivity and wakes with state preserved. Structurally cleanest MCP-native host *if* Workers/TS is acceptable.
- **FastMCP streamable-HTTP** is production-standard as of the 2026 MCP spec; OAuth 2.1 + PKCE is mandated. Any host must support long-lived HTTP.
- **Fly.io + LiteFS** mature for small SQLite DBs but ~100 txn/s write ceiling; conflicts with autostop. Fine for the control-plane state.

### §3.3 Honest comparison at 10k DAU (monthly)

| Setup | Cost | Ops burden | When to pick |
|---|---|---|---|
| **GoDaddy VPS + Cloudflare front** | ~$15–25 | Self-managed Linux | GoDaddy VPS is already in play, or host is willing to upgrade within GoDaddy |
| **GoDaddy shared (static) + Fly.io Machine (dynamic)** | GoDaddy sunk + $5–15 | Low | GoDaddy tier is shared and host doesn't want to upgrade |
| **Fly.io only (GoDaddy holds DNS, nothing else)** | $5–15 | Low | GoDaddy plan genuinely can't host anything useful *and* host prefers one dynamic vendor |

### §3.4 Revised recommendation

1. **Answer first:** what tier does the host currently pay for on GoDaddy, and is upgrading within GoDaddy preferred over switching vendors? (§8 Q1.)
2. **If GoDaddy VPS is in play** — deploy the Phase 1 control plane at `tinyassets.io` on GoDaddy VPS. One vendor, sunk cost. Cloudflare optionally in front for DNS/TLS/CDN.
3. **If only shared/managed hosting and upgrading is off the table** — put the static landing + static catalog snapshot on `tinyassets.io/` immediately (immediate partial win on requirement (1)), and put the dynamic control plane on Fly.io Machine at `tinyassets.io` via CNAME.
4. **Cloudflare Workers rewrite — deferred to v2 regardless.** Structurally cleanest but the migration cost isn't justified at the weeks-not-months horizon.
5. **Rejected: serverless (Lambda), Railway, Render.** SSE / session affinity costs outweigh any simplicity gain at our scale.

### §3.5 Cloudflare-front deep-dive (Phase 1 specifics)

Every §3 option recommends Cloudflare in front for DNS/TLS/CDN. This section pins down what that actually means at the knob level.

#### §3.5.1 What the Cloudflare Free tier gives us

**Included on Free ([Cloudflare pricing](https://costbench.com/software/cdn-edge/cloudflare/free-plan/)):**
- Unlimited DNS records, unlimited bandwidth on proxied traffic.
- Automatic Universal SSL for the apex + one level of subdomain (`tinyassets.io` + `*.tinyassets.io` — one-level wildcard is included).
- Cloudflare CDN with default "cache everything static" heuristics.
- **3 Page Rules** (legacy) and **10 Cache Rules** (the modern replacement — verify current Free-tier count at deploy time; recent docs indicate Free is adequate for our 2-rule need).
- **Asynchronous stale-while-revalidate** — shipped to all Free/Pro/Business zones in Feb 2026 ([changelog](https://developers.cloudflare.com/changelog/post/2026-02-26-async-stale-while-revalidate/)). First request after TTL expiry gets stale content immediately with revalidation happening in the background. This is exactly the behavior we want for catalog reads.
- **Cache Response Rules** (March 2026) — lets us rewrite origin `Cache-Control` headers including `stale-while-revalidate` values, directly at the edge ([changelog](https://developers.cloudflare.com/changelog/post/2026-03-24-cache-response-rules/)). Useful for GitHub Pages origins that don't set long TTLs by default.
- **Cache Purge API** — unrestricted on Free for single-tag / single-url purges.

**Not on Free, and we don't need for v1:**
- Multi-level wildcard SSL (`*.host.tinyassets.io` for 3-level subdomains) — Advanced Certificate Manager, $10/mo. Not needed in Phase 1; `host-<slug>.tinyassets.io` is one level deep and Universal SSL covers it.
- Image optimization / Polish — not relevant.
- Argo Smart Routing ($5/mo) — marginal latency win, defer to v2 if daemon roundtrips become the bottleneck.
- Workers paid tier ($5/mo) — deferred with the Workers-rewrite itself to v2.
- Load Balancer ($5 base + per-origin) — not needed with a single control-plane origin; becomes interesting only at the multi-origin stage (v2+ federation).

**Conclusion:** Free tier is sufficient for Phase 1. No paid Cloudflare plan needed. This holds even at 10k DAU; paid features only matter at v2 federation or extreme traffic.

#### §3.5.2 Cloudflared tunnel vs Cloudflare proxy — topology

These are distinct concepts and the design uses both.

- **Cloudflare proxy (orange-cloud on DNS records)** — Cloudflare's edge receives requests for the hostname and forwards to the origin IP. Origin must be publicly reachable. TLS terminated at CF; optionally re-encrypted to origin (Full/Strict mode).
- **Cloudflared tunnel (named tunnel)** — a daemon on the origin (today: `universe_tray.py` running `cloudflared` on the laptop with a hardcoded token at `universe_tray.py:50`) establishes an outbound persistent connection to Cloudflare. Origin doesn't need a public IP or open inbound ports. DNS record is a CNAME to `<tunnel-uuid>.cfargotunnel.com`.

**Post-Phase-1 topology (recommended):**

```
tinyassets.io (apex)
  └─ A or CNAME (orange-clouded)  →  GoDaddy static hosting or GitHub Pages
                                      (static landing + /catalog/*)

tinyassets.io
  └─ A (orange-clouded)           →  Control plane origin IP
                                      (GoDaddy VPS or Fly.io)
                                      TLS mode: Full (strict)

host-<slug>.tinyassets.io (one per host)
  └─ CNAME (orange-clouded)       →  <tunnel-uuid>.cfargotunnel.com
                                      (cloudflared on that host's machine)
```

**So: proxy for the always-on control plane, tunnel for the per-host daemon exposure.**

**Why keep tunnels for hosts:**
- Hosts are residential/laptop/VPS with intermittent IPs, behind NAT, behind ISP dynamic DNS. Outbound-only tunnels sidestep all of it. This is the *original* reason the tunnel exists.
- Per-host tunnels mean per-host auth and per-host DNS. Control plane dispatches to `host-<slug>.tinyassets.io/mcp`; the control-plane-signed host assertion (§6.2) authorizes the request.
- Hardcoded `TUNNEL_TOKEN` in `universe_tray.py:50` is a Phase 2 migration target — each host should provision its own tunnel at first-install, not share one.

**Why switch the control plane to proxy (not tunnel):**
- Control plane is public-hosted with a static IP and real inbound TCP. No NAT traversal problem. Adding a tunnel to it buys nothing.
- Direct proxy is simpler ops: one fewer cloudflared process, one fewer token to rotate, standard HTTP health checks.
- TLS Full (strict) between Cloudflare and the control-plane origin keeps transit encrypted. Origin certificate via Cloudflare Origin CA (free, auto-rotating) or Let's Encrypt.

**Transition:** Phase 1 retains the existing tunnel → laptop as `host-jonathan.tinyassets.io`. `tinyassets.io/mcp` at the apex is retired as a connector URL; clients migrate to `tinyassets.io/mcp`. For one release, the apex `tinyassets.io/mcp` can 301-redirect to `tinyassets.io/mcp` so existing Claude.ai connectors don't break abruptly.

#### §3.5.3 Per-subdomain layout — DNS, TLS, cache

| Subdomain | Record | Orange-cloud | TLS mode | Origin | Cache |
|---|---|---|---|---|---|
| `tinyassets.io` (apex) | A or CNAME-flattened | Yes | Full (strict) | GoDaddy static / GitHub Pages | Default "cache everything static" + 1 day edge TTL |
| `tinyassets.io/catalog/*` | (same apex) | Yes | Full (strict) | GoDaddy static / GitHub Pages | Cache Rule: match `/catalog/*`, cache 5 min edge TTL with stale-while-revalidate 24 h |
| `tinyassets.io` | A | Yes | Full (strict) | Control plane (GoDaddy VPS or Fly) | Default cache behavior |
| `tinyassets.io/mcp` | (same subdomain) | Yes | Full (strict) | Control plane | Cache Rule: match `/mcp*`, **bypass cache**. MCP is stateful streamable HTTP; caching is wrong. |
| `tinyassets.io/authorize` | (same subdomain) | Yes | Full (strict) | Control plane | Bypass cache (auth flow). |
| `host-<slug>.tinyassets.io` | CNAME to `<uuid>.cfargotunnel.com` | Yes | Full (strict) — Cloudflare<>cloudflared is automatically strict | Host's cloudflared daemon | Bypass cache (tool calls). |

**Gotchas:**
- **Apex CNAME** — DNS doesn't allow real CNAMEs at the apex. Cloudflare offers CNAME-flattening (free) which resolves this transparently. No action needed beyond adding the record.
- **Universal SSL covers one subdomain level** — `tinyassets.io` and `host-<slug>.tinyassets.io` are both one-level, both covered. If we later want `host-<slug>.subdomain.tinyassets.io` (two levels deep), Universal SSL does *not* cover it and we'd need Advanced Certificate Manager ($10/mo). Stay one-level deep in Phase 1.
- **TLS Full vs Full (strict)** — always use Full (strict). Full alone accepts any origin cert (self-signed, expired); that's effectively unencrypted from a trust standpoint. Cloudflare Origin CA certs are free, valid 15 years, and work with Full (strict).
- **GitHub Pages as origin for `/catalog/*`** — supported and common. GitHub Pages sets its own TLS cert for `tinyassets.io`; with Cloudflare proxy in front, terminate TLS at CF and use Full (strict) back to Pages. Follow Cloudflare's GitHub Pages setup guide to avoid redirect loops.
- **Cloudflared ingress wildcard rules** — if a single host exposes multiple services (e.g. laptop runs both MCP server and a future dashboard), one cloudflared can handle both via ingress rules. Wildcards match leftmost label only (`*.example.com`, not `a.*.example.com`).

#### §3.5.4 Catalog cache invalidation — freshness strategy

Catalog reads are the CDN's main job in this design. Strategy:

**Tier 1 — TTL with async stale-while-revalidate (default).** Cache Rule on `/catalog/*`:
- Edge TTL: 5 minutes.
- `stale-while-revalidate`: 24 hours.
- Behavior: first visitor after TTL expiry gets the old version instantly; revalidation happens in the background; subsequent visitors get the fresh version. The async behavior shipped Feb 2026 and is on Free. Worst-case staleness is ~5 minutes for the typical reader, ~24 hours if the origin is down during revalidation (acceptable — content is still served).

**Tier 2 — Push-purge on catalog-repo merges.** GitHub Action on merge to main in the catalog repo:
1. Regenerate the static catalog snapshot.
2. Publish (GitHub Pages deploy, or rsync to GoDaddy static).
3. Call the Cloudflare Cache Purge API for `/catalog/*` — a purge-by-URL or purge-by-prefix on `https://tinyassets.io/catalog/*`. Uses a scoped API token stored as a GitHub Actions secret.

Combined result: catalog edits visible at the edge within seconds of merge (via purge), with a 5-minute TTL safety net if purge fails. No pathological all-stale-all-the-time behavior and no minute-by-minute origin hits.

**What not to do:**
- **Don't cache `/mcp*`.** MCP is stateful streamable HTTP; caching MCP responses would break sessions. Explicit bypass Cache Rule.
- **Don't rely on origin `Cache-Control` alone.** GitHub Pages defaults to short TTLs; use Cache Response Rules (Free tier) to override at the edge to 5 min + swr.
- **Don't purge everything on every commit.** Purge-by-prefix for `/catalog/*` is precise; global purge is slow and noisy.

#### §3.5.5 New or sharpened host decisions

No new paid-plan decisions for v1 — Free tier is sufficient. Two sharpened questions fold into existing §8 Qs:

- **Static origin for `tinyassets.io/catalog/*`** — GitHub Pages (CNAME'd from the domain) or GoDaddy shared hosting? Pages is simpler, free, and has a clean GitHub-Action deploy path. GoDaddy already paid for and leaves one vendor fewer. Recommend GitHub Pages unless GoDaddy static hosting is explicitly preferred. Treat this as a sub-question under §8 Q1.
- **Per-host tunnel provisioning** — Phase 1 keeps the hardcoded `TUNNEL_TOKEN` model (single tunnel, just relabeled as `host-jonathan.tinyassets.io`). Multi-host requires per-host tokens provisioned at first-install. Recommend deferring to Phase 2 alongside the §6.2 OAuth 2.1 migration — both touch the same "identity on first-install" surface. Cross-reference in §8 Q8 cloudflared-bundling.

---

## §4. Data-Plane Failover Patterns

The data plane is daemon execution + universe content. When *no host* is serving a capability, what happens?

Four patterns considered:

**(a) Reference host guarantee.** Always run at least one host — Jonathan's laptop today, eventually a dedicated VPS or cloud box. Simple but contradicts requirement (3) ("reference host being off must not take down the system"). Useful as a *service-level commitment backstop*, not a structural answer.

**(b) Capability-tiered degradation — recommended primary.** When no host serves capability X, the control plane returns a structured response: "no daemon available for <node_type>; your request is queued and will execute when a host comes online." Read-only operations (browse catalog, view universe content if it's in the catalog repo, view static goal/branch metadata) still work because they never needed a daemon. This *is* the (1)+(2) requirement expressed as a behavior, not a workaround.

**(c) Paid-market failover — recommended fallback.** If a user's request is urgent and no free host is bidding, the control plane can elevate the request into the paid market automatically (or the user elevates it manually). The existing bid model (project memory: requester sets node+LLM+price; daemons bid) handles this. When fees are attached, hosts have a direct economic reason to wake up. Integrates cleanly with (b): (b) is "queue forever until someone picks it up," (c) is "queue with a bounty attached."

**(d) Warm-standby cloud daemon.** A control-plane-owned daemon process spun up on demand when no host is online. Rejected for v1: expensive, reintroduces the multi-tenant hosted runtime problem the GitHub-as-catalog direction explicitly avoided, and creates a privileged provider that undercuts the paid-market incentive.

### §4.1 Recommendation

**Primary pattern: (b) capability-tiered degradation.** Control plane exposes `heartbeat` and `capabilities` endpoints; every host announces. A user request either finds a live host and dispatches, or gets a structured "queued" response. This is the minimum viable shape and directly satisfies requirements (1) and (2).

**Fallback pattern: (c) paid-market failover.** A queued request can be elevated to the paid market. This is an additive layer over the existing bid model and *does not require new infrastructure* — the bid ledger lives in the control plane alongside the request inbox.

**Explicitly deferred: (a) reference-host commitment.** Running a dedicated always-on VPS host is a valid service-level improvement post-v1, but it is not architecturally required if (b) + (c) are implemented. Flag for host decision: do we commit to one in v1 as a soft backstop, or trust (b)+(c) to stand alone?

---

## §5. Node / Daemon State Split

This is the sharpest question. Centralizing universe content on the control plane risks "big blob" storage and makes the control plane the bottleneck. Keeping everything host-local means hosts offline = content unavailable (violates (1)).

**Proposed split:**

| State type | Home | Reasoning |
|---|---|---|
| Node / Goal / Branch definitions (schema, metadata, prompts) | **GitHub catalog repo** | Canonical per GitHub-as-catalog direction. Read-cached by control plane + Cloudflare. Never unavailable. |
| Universe identity, branch list, current daemon status, sensitivity tier | **Control plane (Fly SQLite)** | Small, always needed, must be queryable even when hosts are offline. |
| Notes (`notes.json`) | **Host-local + snapshot to catalog on `share_branch`** | Active-universe notes stay fast locally. Published branches snapshot a redacted notes view into the catalog. |
| KG / vector indexes / LanceDB | **Host-local** | Large, high-write, expensive to move. If the host is offline, semantic search for that universe is unavailable — acceptable because the universe content is a daemon-execution input, not a browse target. |
| Canon uploads (source files, PDFs, large blobs) | **Host-local by default, opt-in Git LFS mirror** | Preserves "user uploads are authoritative" (AGENTS.md hard rule #9). Large files don't belong in the hot catalog. Host can opt into LFS mirroring if they want the content browsable when offline. |
| Ledger, bid ledger, settlements | **Control plane (economic truth must be cross-host)** | The paid market needs one authoritative ledger. This is a control-plane concern by definition. |
| Request inbox (pending paid requests) | **Control plane** | Durable, cross-host, polled by daemons. |
| Host heartbeat / capabilities | **Control plane (KV, TTL 60s)** | Ephemeral, small, read-hot. |
| Soul files (daemon identity) | **GitHub catalog repo** | Public, forkable, per PLAN.md. |
| Drafts | **Host-local only** | Per GitHub-as-catalog §2. No git, no control plane. |

### §5.1 The key property

*For the control plane to satisfy (1), it only needs to own: identity, catalog-read cache, request inbox, host directory, and bid ledger.* That's ~1000 rows of SQLite at 1k DAU, ~100k at 100k DAU. Fly-scale state.

Universe content (the big data) stays host-local, surfaced into the catalog only when the user explicitly publishes. The control plane never needs to transfer large blobs.

This is the "thin control plane, fat hosts" shape. It matches the GitHub-as-catalog direction, preserves PLAN.md §Local-first execution, and gives us requirement (1) without a distributed storage problem.

---

## §6. Auth + Identity Across Providers

Today: chatbot identity is tied via Claude.ai's MCP connector — the user is "whoever Claude.ai says is connected to `tinyassets.io/mcp` right now." This is implicit and works because there is one origin.

When the control plane is a separate service in front of many hosts, identity must survive:
- User opens Claude.ai → MCP connector to Workflow control plane → control plane dispatches to Host B.
- Host B must know "this request comes from user `jonathan` with session `...`" and enforce sensitivity / ACL accordingly.
- Requests placed today must still be the same user tomorrow on a different client.

### §6.1 Subdomain split of the surface

Using the owned domain's free subdomains lets auth / static / dynamic boundaries stay clean without new DNS costs:

- `tinyassets.io/` — public landing page (static). No auth. Cheapest GoDaddy tier.
- `tinyassets.io/catalog/*` — static catalog snapshot. Public-by-default; optional signed-read tokens later.
- `tinyassets.io/authorize` — GitHub-OAuth sign-in flow (v0) and OAuth 2.1 issuer (v1+). Returns tokens.
- `tinyassets.io/mcp` — authenticated MCP gateway for clients. What users add to Claude.ai. All requests past this point carry a bearer or OAuth token.
- `host-<slug>.tinyassets.io/mcp` — direct per-host tunnel entrypoints (federation, v2+). Control plane issues signed assertions authorizing a subdomain for user X.

Clients still use a single published entrypoint (`tinyassets.io/mcp` or `tinyassets.io/mcp`; host decides in §8 Q6). Subdomain split is an internal architecture choice exposed through that entrypoint.

### §6.2 Recommended flow

**OAuth 2.1 + PKCE at the control plane** (per MCP spec 2025-03-26 — mandatory for streamable HTTP in 2026). Control plane is the identity provider.

1. User adds `https://tinyassets.io/mcp` as an MCP connector in their client (Claude.ai, Claude Desktop, Code, any other MCP client).
2. Client does OAuth 2.1 dance with the control plane — PKCE, device flow, or DCR per RFC 7591.
3. Control plane issues a short-lived access token + long-lived refresh token, scoped to `user_id = ...`.
4. Every MCP tool call from the client includes the token.
5. When the control plane dispatches a tool call to a specific host, it attaches a signed *host assertion* — a short-lived JWT signed by the control plane saying "this request is from `user_id = jonathan`, authorized for `universe = ...`, expires in 5 minutes."
6. The host verifies the control-plane signature (public key well-known), trusts the user identity, enforces sensitivity/ACL locally.

This gives us:
- **Consistent identity across clients.** Same user on Claude.ai and Claude Desktop if they authenticated both to the control plane.
- **Host cannot forge identity.** The control-plane signature is the trust anchor.
- **Host can still enforce policy.** The host decides whether to serve user X based on its local allowlist; the control plane only certifies who X is.

### §6.3 v0 simplification

OAuth 2.1 + DCR is non-trivial. For the first shippable v1, **start with bearer tokens minted by the control plane via a one-click "authorize this client" flow on a landing page** (user opens `tinyassets.io/authorize`, logs in via GitHub OAuth, receives a token to paste into their MCP client config). This is what the prior research flagged as acceptable alpha. Migrate to full OAuth 2.1 once the shape stabilizes.

The paid-market trust model (project memory: "treat market as cooperative, not stranger-marketplace") means v0 can lean on GitHub identity and skip escrow/reputation infrastructure. Defend against abuse when it appears.

### §6.4 Claude.ai-specific constraint

Claude.ai's MCP connector UI handles OAuth 2.1 for remote MCP servers natively as of 2026. This path works. Bearer-token-paste is a fallback for Claude Desktop and custom MCP clients.

---

## §7. Migration Path

Three phases, each shippable independently.

### Phase 1 — Thin relay (v1)

Split into two sub-phases so partial value lands early. Whether they can ship in parallel or serialize depends on §8 Q1 (GoDaddy tier answer).

**Phase 1a — Static landing + static catalog on tinyassets.io (target: days).**
- Put a real landing page at `tinyassets.io/` served from whatever GoDaddy tier the host already has (or GitHub Pages CNAME'd to the domain if GoDaddy's tier is too constrained for even static assets). Copy: "Summon the daemon — try the demo or clone in 3 commands."
- Publish a periodically regenerated static catalog snapshot at `tinyassets.io/catalog/*` (goals, branches, nodes, rendered Markdown/JSON). A GitHub Action on catalog-repo merge regenerates it.
- **Result:** when the laptop is off, users hitting the domain get a working browseable site instead of HTTP 530. Partial win on requirement (1) — no dynamic node creation yet, but catalog reads and demo link work 24/7. **This sub-phase alone is worth shipping even before the dynamic control plane.**

**Phase 1b — Dynamic control plane at tinyassets.io (target: 1–2 weeks after 1a).**
- Deploy a slim FastMCP at `tinyassets.io/mcp`. Host: GoDaddy VPS if in play, else Fly.io Machine. Exposes dynamic catalog tools + dispatch logic. Identity via v0 bearer tokens from `tinyassets.io/authorize`.
- When a tool call needs a daemon (`summon_daemon`, `request_node_run`, any write action), control plane checks the host directory.
  - Host registered + online → proxy to the host's tunnel (current cloudflared tunnels stay, reachable as `host-<slug>.tinyassets.io`).
  - No host → structured `{"status": "queued", "reason": "no host serving capability X"}`.
- DNS: `tinyassets.io` apex stays on GoDaddy; `tinyassets.io` CNAME to the dynamic host; the current laptop tunnel becomes `host-jonathan.tinyassets.io`.
- `universe_tray.py` registers itself with the control plane on startup, heartbeats every 30s, deregisters on shutdown.

**What works after Phase 1:**
- All read operations (browse, catalog, goal/branch/node listings, static universe metadata) work 24/7 regardless of host state. **Requirement (1): satisfied for reads.**
- Write operations work when any registered host is online and serves the capability. **Requirement (2): satisfied.**
- Host laptop off → catalog still browseable. **Requirement (3): satisfied for reads.**

**What's still broken:** write operations when no host is online. Explicitly deferred to Phase 3.

### Phase 2 — State migration (v1.5, target: 2-4 weeks)

**Goal:** Move durable coordination state from host-local SQLite to the control plane.

- Migrate universe registry, ledger, bid ledger to control-plane SQLite on Fly volume.
- Migrate request inbox — new requests land at the control plane; hosts poll for eligible work rather than receiving direct tool calls.
- Snapshot published notes and branch metadata to the catalog repo on `share_branch`.
- Roll out OAuth 2.1 + PKCE, deprecate bearer tokens.

**What works after Phase 2:** request queue persists across host sleep / wake. Economic ledger is one authoritative source. Identity is spec-compliant.

### Phase 3 — Capability bidding + failover (v2, target: 1-2 months)

**Goal:** Requirement (1) for writes. When no free host is serving capability X, the request enters the paid market; any qualifying host earns by claiming it.

- Elevate queued requests into the bid market after configurable timeout.
- Host scheduler on every host polls control-plane bid inbox; claims based on existing bid-model rules (matching LLM, price >= floor, capability available).
- Settlement flows via the control-plane ledger.
- Optional: warm-standby cloud daemon as last resort (pattern (d) from §4). Re-evaluate if (b)+(c) prove insufficient.

**What works after Phase 3:** near-total write availability, economically self-sustaining. Requirement (1) complete.

### Phase alignment with other in-flight work

- **Author→Daemon rename** (task #3, in progress) — lands first. No new control-plane work touches files under `fantasy_daemon/` until rename lands cleanly.
- **Engine/domain API separation MCP track** (task #11, §5.2 of the design note) — the MCP mount-per-domain pattern is what gets deployed on Fly. Land Phase 1 control plane with the current single-tool shape; Phase 2 gets the mount-split migration.
- **Privacy modes** (docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md) — `sensitivity_tier=confidential` universes pin to `ollama-local` and never leave the owning host. Control plane **must not** proxy confidential-tier requests; it returns "host-local only" immediately if asked. Align in Phase 1.
- **Memory-scope Stage 2c flag flip** — unaffected; memory scope is host-local.

---

## §8. Host Decisions Requested

Before starting build, host should decide:

**Q1. GoDaddy plan tier + upgrade preference.** *What GoDaddy plan does the host currently pay for, and is upgrading within GoDaddy preferred over switching vendors?* This is the single biggest input to §3 and drives the whole Phase 1 shape.
- If VPS tier (or willing to upgrade to it) — deploy the Phase 1 control plane at `tinyassets.io` on GoDaddy VPS. One vendor, sunk cost. ~$15–25/mo at 10k DAU.
- If shared/managed only and upgrading is off the table — Phase 1a (static landing + static catalog) on GoDaddy, Phase 1b (dynamic control plane) on Fly.io Machine at `tinyassets.io` via CNAME. GoDaddy sunk + $5–15/mo.
- Regardless, defer Cloudflare Workers rewrite to v2.

**Q2. Reference-host commitment.** Do we commit to running at least one always-on cloud host as a soft backstop (pattern (a) from §4) in v1, or rely entirely on (b) capability-tiered degradation + (c) paid-market fallback? The design works either way; the commitment changes service-level expectations.

**Q3. v1 scope.** Recommend Phase 1 only for v1 — "thin relay, catalog reads 24/7, dispatch-when-host-online, queued-when-not." Accept, or push more of Phase 2 into v1?

**Q4. Budget ceiling.** Target a $20/mo ceiling through 10k DAU? That's comfortable on the Fly+CF recommendation. State the ceiling explicitly so migration triggers (e.g. "move to Workers if Fly tops $50/mo") are legible.

**Q5. Paid-market role in failover.** Does (c) paid-market failover *replace* or *supplement* a reference host? Replacing keeps the market as the sole economic signal (cleaner). Supplementing gives a sub-bounty service level.

**Q6. Identity.** Ship v1 with bearer-token-paste from a GitHub-OAuth landing page, or wait for full OAuth 2.1 + DCR? Recommend bearer-first; OAuth 2.1 as a Phase 2 migration.

**Q7. Data-plane blob storage.** Does published-branch canon go into Git LFS in the catalog repo, or stay host-local even after `share_branch`? LFS makes published branches browseable when the author is offline; costs are low (GitHub LFS is cheap at this scale). Host-local only means "host must be online to read this branch's uploads." Recommend: Git LFS for published canon, host-local for private-tier.

**Q8. Cloudflared bundling.** `cloudflared.exe` is still per-host and not bundled (flagged in the prior research). Does Phase 1 include bundling + auto-install, or is that separate install-experience work?

---

## Appendix A — Integration with Existing Design Decisions

- **PLAN.md §Multiplayer Daemon Platform:** preserved. "Host-run server with named accounts" remains; control plane is a coordination layer *above* hosts, not a replacement for them.
- **PLAN.md §GitHub as canonical shared state:** preserved and strengthened. Control plane is a read-through + dispatch layer over the GitHub catalog; it does not introduce a new canonical store.
- **PLAN.md §Local-first execution:** preserved. Daemon execution stays local; only coordination crosses the network.
- **PLAN.md §Private chats, public actions:** preserved. OAuth 2.1 identity and signed host assertions let hosts enforce private-chat boundaries while still allowing public action attribution.
- **PLAN.md §Branch-first collaboration:** preserved. Branches remain first-class and host-local during drafting; published branches snapshot into the catalog.
- **Distribution horizon:** Phase 1 is weeks, not months. The control plane *improves* fresh-install (new users get a working `tinyassets.io/mcp` even before they run a daemon) rather than worsening it.

## Appendix B — What this note does NOT do

- Does not redesign the daemon. Daemon is unchanged; only its relationship to external traffic changes.
- Does not replace GitHub as the catalog. GitHub is still canonical for public goals/branches/nodes.
- Does not introduce a hosted multi-tenant daemon runtime. Daemons stay on hosts. Warm-standby (§4d) is explicitly deferred.
- Does not change the soul-file / fork / branch identity model. Those are catalog-shape decisions, separate concern.
- Does not address moderation, rate-limiting policy, or abuse response beyond noting the paid-market trust model. Real abuse response is post-v1.
