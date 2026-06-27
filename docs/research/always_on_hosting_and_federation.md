# Always-On MCP Hosting and Federation

**Status:** Superseded 2026-04-12 by the GitHub-as-catalog direction, and further sharpened into `multi_tenant_hosted_runtime.md` before that. Retained as historical reference. See `docs/research/github_as_catalog.md` for the shipping direction.

Reference for sustaining a public TinyAssets surface (`tinyassets.io/mcp`) when individual user daemons are offline, and for many-host federation. Items marked **unconfirmed** need a second-pass live check.

## 1. Live-surface options

| Option | Pros | Cons | ~Cost @100 users | Migration |
|---|---|---|---|---|
| **Cloudflare Workers + Durable Objects** | True always-on, generous free tier, SSE on paid Workers, edge-global. Anthropic's `workers-mcp` ships streamable-HTTP MCP. | Python via Pyodide (slow) — rewrite or thin proxy. CPU caps. No long-lived SQLite — use D1/DO. | $5/mo Workers Paid + $5 storage | High |
| **Fly.io Machines** | Persistent volumes (LiteFS for SQLite), SSE/websockets, scale-to-zero (~300ms cold), Docker-native. | Per-second Machine pricing; cold-starts visible. | $5–15/mo | Low |
| **Render** | GitHub-push deploys, $7 web service, persistent disks. | Free tier sleeps 15 min idle. | $7/mo + disk | Low |
| **Railway** | Container-native, volumes, $5 starter credit. | Usage-based pricing unpredictable. | $10–20/mo | Low |
| **Hetzner CX22 VPS** | Cheapest always-on, full control, runs SQLite/LanceDB natively. | Self-managed (Caddy, systemd, backups). EU-only default. | €4.5/mo | Medium |
| **DigitalOcean Droplet** | Mature, global regions. | Same ops burden; pricier. | $6/mo | Medium |
| **AWS Lambda + API Gateway** | True scale-to-zero. | SSE awkward; session affinity hard for stateful MCP. | $5–20/mo | High |

**Recommendation:** two-tier — Cloudflare Workers for always-on landing/catalog ($5), Hetzner/Fly for coordination service ($5–15). User daemons stay local behind Cloudflare Tunnel.

## 2. Multi-tenant MCP patterns

- **Per-session isolation** — FastMCP streamable-HTTP supports `Mcp-Session-Id` header per MCP spec 2025-03-26. Suitable if state is partitionable in-process.
- **Per-user subdomains** — Cloudflare wildcard DNS routes `alice.tinyassets.io/mcp` to Alice's tunnel. Operationally clean.
- **Per-user namespaces** — single endpoint, OAuth identity → namespace prefix. Simpler ops, harder isolation.
- **Auth:** MCP spec 2025-03-26 standardized OAuth 2.1 + PKCE + RFC 7591 DCR. Reference impls: `mcp-server-python` OAuth helper, Cloudflare `workers-oauth-provider`. **Unconfirmed** real-world DCR client adoption.

## 3. Federation patterns

| Pattern | State movement | Complexity | Analogues |
|---|---|---|---|
| Central catalog + push | Hosts POST artifacts to shared registry | Low | npm registry, Homebrew taps |
| Central catalog + pull | Catalog polls each host's `/.well-known/` manifest | Medium | RSS, ActivityPub relays |
| Federated index | Hosts sign + broadcast; peers subscribe | High | Mastodon, Lemmy |
| Git-backed catalog | Hosts push to shared git repo; GitHub Pages always-readable | Low | Awesome lists, MCP registry itself |
| CRDT sync | Hosts sync via websocket relay | High | Jazz, Liveblocks |

**MCP registry (registry.modelcontextprotocol.io):** purpose is server *discovery* only. Cannot host per-universe goals/branches data. TinyAssets needs its own catalog layer.

**Recommendation:** git-backed catalog for v1 (cheap, always-on via GitHub Pages) + central push API on always-on host for sub-minute updates. *[Note 2026-04-12: this recommendation directly seeded the GitHub-as-catalog pivot.]*

## 4. Cloudflare-only path

Current: GoDaddy → Cloudflare DNS → named tunnel `b59f3cd9-…` → `localhost:8001`. Laptop off → HTTP 530.

**Split surface design:**
1. `tinyassets.io` apex on Cloudflare Worker (route: `tinyassets.io/*`).
2. Worker logic:
   - `/` and `/catalog/*` → cached/static from Workers KV or R2.
   - `/mcp/*` → `fetch()` to tunnel; on failure, graceful "host offline" JSON.
   - `/u/<user>/mcp/*` → per-user tunnel via wildcard-CNAME.
3. Cloudflare Tunnel becomes one of N origins.
4. Cache Rules aggressive on `/catalog/*`; Worker purges on artifact-publish webhook.

**Cost:** Workers Paid $5/mo covers ~10M requests; KV/R2 trivial at this scale.

**Cloudflare Tunnel fallback.** Tunnel has no static-fallback feature. 530 is irreducible without Worker or Load Balancer in front. **Unconfirmed:** CF Load Balancer + Worker backup pool combo.

## 5. Desktop install friction

Current: `packaging/mcpb/` builds `.mcpb` desktop extension; `packaging/claude-plugin/` ships plugin with Python bootstrapper creating venv on first launch.

Friction points:
- **Python prerequisite** — bundle declares `server.type = "python"` with `command = "uv"`. User must have `uv` or Python 3.11+.
- **First-launch venv install** — 30–90s silent wait installing `fastmcp`.
- **Windows autostart** — no Task Scheduler / Startup shortcut wired. Standard pattern: `.lnk` in `shell:startup` or Scheduled Task at install.
- **Cloudflared dependency** — `cloudflared.exe` invoked but not bundled. Major friction.
- **Firewall prompt** — first bind to `:8001` triggers Defender dialog.
- **Claude marketplace install flow** — CLI-gated until Anthropic ships marketplace UI (**unconfirmed** timeline).

**Quick wins:** bundle `cloudflared.exe`, ship one-click `.bat` that installs Python via winget, register Startup shortcut on first run.

## 6. Reference systems

- **ChatGPT Custom GPTs:** OpenAI hosts everything. Model for centralized catalog, not daemon-per-user.
- **LangGraph Cloud / LangSmith:** LangChain hosts long-running graph state. $39/mo developer tier. Demonstrates stateful agent hosting is commercially viable.
- **Anthropic-managed agents (Conway/KAIROS):** speculative; see `docs/conway_readiness_strategy.md`.
- **BettaFish:** file-based shared state, framework-minimal. Doesn't address hosting.

## 7. Open questions for planner

1. Per-user subdomain (`alice.tinyassets.io`) vs path-based (`tinyassets.io/u/alice`)? Wildcard DNS trivial; wildcard TLS via Cloudflare automatic only on paid plans.
2. Catalog authoritative (writes through it) or eventually-consistent (each host authoritative for its slice)?
3. OAuth 2.1 + DCR a v1 requirement, or can alpha ship with bearer-token-from-host-dashboard?
4. Does scale-to-zero (Fly.io) hurt "always-on catalog" enough to justify Cloudflare Workers rewrite cost?
5. Mobile-only/ChromeOS users who can't run a local daemon — hosted-daemon tier?
6. Cloudflare Tunnel token in `universe_tray.py` is hardcoded — multi-user federation needs per-user tokens. Provisioning flow?
