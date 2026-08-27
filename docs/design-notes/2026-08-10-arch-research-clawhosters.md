# Architectural research: ClawHosters (clawhosters.com) — module-by-module vs TinyAssets

Date: 2026-08-10 (all web citations accessed 2026-08-10). Status: **research note — no code
touched**. Produced per the `external-research-implications` skill. Companion to
`2026-08-10-subscription-platform-precedents.md` (which covers ClawHosters only as a
policy/enforcement precedent; THIS note is the full architecture study).

`initial_provider: claude` (Claude Code, Fable 5). **Required reviewer: Codex** — any build,
push, or live rollout derived from this note is gated on an opposite-provider review artifact
per AGENTS.md § Project Skills. Task constraint for this session was "one deliverable,
read-only"; the pickup packet in §9 is therefore ready-to-paste rather than already landed in
`STATUS.md` — the first session to act on §9 should land the row.

Evidence labels: **[E]** = cited/quoted from a primary or independent source.
**[I]** = inference from evidence. **[V]** = vendor claim, not independently verified.

---

## 1. Executive judgment

ClawHosters is the closest live analog to TinyAssets's hosted-universe shape: a
solo-founder German SaaS (launched Feb 2026) that gives each customer a **dedicated Hetzner
VPS running one OpenClaw agent in a Docker container**, provisioned from pre-baked snapshots
in 30–60 seconds, reachable over Telegram/WhatsApp/Discord/Slack/web, billed as an
**infra fee (€19–59/mo) with the model unbundled** (free loaner models, BYOK, or managed
token packs, incl. Claude-subscription setup-token). Its architecture is deliberately boring
— Rails 8 monolith + Sidekiq + Postgres + Traefik/Redis routing, no Kubernetes — and it
works: one person operates the whole platform next to a 40-hour job.

The headline lesson for TinyAssets is not any single feature — it's that **hard per-user
isolation is commodity-priced**. ClawHosters solves the entire "agent sandbox" problem
TinyAssets carries as an open P1 by buying a ~€4–8/mo VPS per customer and never letting two
customers share a kernel. Meanwhile ClawHosters is weakest exactly where TinyAssets is
strongest: durable memory (their backups *exclude chat history*; rebuild wipes everything),
agent-level authority/safety (independent review scores "agent going rogue" 2/10 — no spend
caps, no approval workflows), user-facing observability (admin gets Telegram alerts; the
customer gets nothing), and platform primitives (no marketplace, no lineage, no
collaboration, no outcome evaluation). They sell a box that runs an agent; we build the
civilization layer. Copy their infra economics; do not copy their state model.

## 2. Canonical source + freshness

- Canonical URL: https://clawhosters.com — "Managed OpenClaw Hosting". Docs at `/docs`
  (~60 pages), blog at `/blog`, roadmap at `/roadmap`. No public GitHub for the platform
  itself (the custom `clawhosters/openclaw-ssh` Docker image is referenced but the Rails
  platform is closed). [E]
- Operator: **Daniel Samer** (Yixn.io), German *Kleinunternehmer* (sole proprietor),
  Rails developer 10+ years; built ClawHosters solo alongside a 40-hour job. Launched
  **February 2026**. [E: dev.to/yixn_io "From Side Project to Product"; yixn.io/en;
  bestclawhosting.com/provider/clawhosters]
- Primary technical sources: founder deep-dives
  "How I Built 60-Second VPS Provisioning" and "Docker + Traefik + SSE: Managed AI Hosting
  Platform" (clawhosters.com/blog/posts/…, mirrored on Medium, Feb 2026). [E]
- Independent sources: bestclawhosting.com provider review (security score 28.5/100,
  rank #34); betterclaw.io competitor comparison; Trustpilot (4.5 claimed on homepage;
  direct fetch 403'd — reviews reached via search snippets only). [E]
- Scale, two snapshots: founder posts (Feb 2026): "~50 paying customers, ~25 in trial,
  sourced from Reddit, no marketing budget" [E]. Homepage (2026-08-10): "39+ Instances
  Running" and "1186+ Happy Customers" [E/V]. The 1186-customers vs 39-running-instances
  gap reads as total-signups vs currently-paying — i.e. heavy trial churn and/or
  pause-on-zero-balance attrition [I].
- What OpenClaw is (their upstream): open-source "gateway between LLM providers and
  messaging platforms" — 24/7 personal agent framework with channels, skills/plugins,
  conversation context, cron jobs in `openclaw.json`. Community-maintained Docker image. [E]

## 3. ClawHosters system map (the ten research questions)

### 3.1 Product shape + target user
Managed hosting for one OpenClaw personal-assistant instance per customer. Target: (a)
non-technical users who want "their own AI assistant" without DevOps; (b) developers tired
of self-hosting a VPS. Pitch: "click a button and get a running OpenClaw instance in about
60 seconds." GDPR/German-data-sovereignty is a primary differentiator. [E]

### 3.2 Instance architecture — provisioning, isolation, uptime
- **One dedicated Hetzner Cloud VPS per customer** (Falkenstein, DE) — single-tenant at the
  hypervisor level, "not shared multi-tenant containers." Inside the VPS, OpenClaw runs in
  **one Docker container** with tier-enforced memory limits (1/2/4 GB container limit on
  4/8/16 GB VPS — note the container gets only ~25% of the box; the rest covers Playwright
  browsers, nginx sidecar, ZeroTier sidecar, OS). [E]
- **Snapshot provisioning:** pre-baked Ubuntu 24.04 snapshot with Docker, the ~2 GB
  OpenClaw image pre-pulled, Playwright Chromium volume, iptables/fail2ban hardening, and a
  custom SSH-enabled image. Cloud-init does only host-key regen + machine-id + service
  restarts. Cold path 60–90 s. [E]
- **Pre-warmed VPS pool:** idle VPSs provisioned ahead of demand; a customer order *claims*
  one via a database update + Hetzner metadata rename (no API create on the hot path), then
  SCPs config and `docker-compose up`. Claim 15–20 s + config 20–30 s → ~30–50 s
  user-facing. `PrewarmReplenishJob` refills the pool; pool manager checks every 10 min,
  seasonally adjusted minimums. [E]
- **Routing (5 layers):** Cloudflare wildcard DNS + SSL → main nginx (regex subdomain
  capture, `proxy_buffering off` for SSE) → **Traefik with Redis-backed dynamic config**
  (per-instance router + bcrypt basic-auth middleware; "within a second or two, Traefik
  picks up the new keys") → per-VPS nginx sidecar (Host-header validation → OpenClaw on
  18789) → Hetzner Cloud Firewall (inbound only from the production server IP) + fail2ban.
  [E]
- **Updates:** "In-Place Instance Updates: zero-downtime updates that apply new versions
  without reprovisioning" (roadmap: shipped). Before any restart, `CommitContainerService`
  runs **`docker commit`** on the running container and subsequent deploys use the
  committed image — preserving customer-installed packages in the writable OverlayFS layer
  across restarts/updates (cleared only when the VPS is destroyed). Snapshot rebuilds are
  manual rake tasks (founder admits they should be CI). [E]
- **Uptime model:** "99.9% uptime" marketed, **no formal SLA** [E: bestclawhosting]. Docker
  healthchecks every 30 s (3 fails → unhealthy; 60 s startup grace). Platform-side health
  service makes real HTTP requests through the full routing stack every 5 min; route-sync
  reconciles Traefik/Redis every 10 min; a manager job polls every 5 s for instances stuck
  in "deploying" (>20 min → manual-review flag). [E]

### 3.3 Credential custody — setup-token flow
- Flow: user runs `claude setup-token` locally → browser OAuth → pastes token into
  instance settings → LLM config → Anthropic. Framed as "use your existing Claude
  subscription (Pro or Max) to power instances, instead of paying for separate API
  access." [E]
- Storage: "Your token is encrypted with AES-256 and stored on German servers. ClawHosters
  never accesses or reads your token" [V]; security docs specify **AES-256-GCM via Rails
  encrypted credentials** in the platform DB, then passed to the customer's instance.
  Passwords bcrypt; payments entirely on Stripe. [E]
- Warning given: "Treat this token like a password. Anyone with your setup-token can use
  your Claude subscription." **No revocation procedure documented** — only "rerun
  `claude setup-token` when it stops working." [E]
- Gap [I]: "never accesses or reads your token" is marketing, not architecture — the
  platform decrypts to deploy it into the instance config; there is no per-user key
  ceremony, no HSM claim, no session-scoped-token architecture. This is exactly the custody
  model the conservative hosted vendors (Hermes, OpenClaw Launch) refuse (see companion
  precedents note §2A).

### 3.4 Channels
Telegram, WhatsApp, Discord, Slack + built-in web UI ("Mission Control" dashboard on
Balanced+), all configured from the dashboard, multi-channel simultaneously from one
instance. No Teams/Signal/iMessage/email (competitor BetterClaw claims 15+ channels vs
their 4). **No user-facing notification/alert model at all** — monitoring docs confirm "no
mention of automated alerts or notifications sent to users." [E]

### 3.5 Memory / persistence per instance
- Conversation memory = OpenClaw's default in-instance context ("remembers what was said
  earlier in a chat"); no platform memory layer, no cross-channel long-term memory product
  (BetterClaw differentiates with "90-day memory shared across all channels"). [E]
- **Config backups** (free, automatic 2×/day 05:00/17:00 UTC): `openclaw.json` (LLM
  settings, channels, personality, skills, cron jobs) + API keys/bot tokens.
  **Explicitly excludes chat history, uploaded files, custom packages, pairing data.**
  Retention: 7 days full, then 14-day + 31-day singletons, gone at 37 days. [E]
- **Full-server Backup add-on: "Coming Soon"** — i.e. as of today a rebuild "wipes all
  configuration and data," and chat history/files have NO restore path. [E]
- Pause-on-zero-balance: Hetzner snapshot of the whole disk, kept **3 days**, then the
  instance is deleted; top-up within the window auto-restores. Independent review calls
  the 3-day window "short and risky." [E]

### 3.6 Automations / scheduling
Automation lives at the OpenClaw layer, not the platform: cron jobs exist inside
`openclaw.json` (they're in config backups) but there's **no dashboard surface yet** —
"Cron Dashboard Interface" and "Agent Dashboard Interface" are roadmap-planned. "Instance
Hibernation & Scheduling" (shipped) is about scheduling the *server* on/off to save Claws,
not about agent tasks. No heartbeat cost-management (a BetterClaw call-out). Skills:
platform-managed activation by editing `openclaw.json` from the dashboard; custom skills
via SSH into the container — unsupported, wiped on rebuild, "broken custom skills can
affect instance stability." **No marketplace, no vetting.** [E]

### 3.7 Billing model
- **Infra fee ≠ model cost — cleanly unbundled.** Tiers €19/35/59/mo (2/4/8 vCPU,
  4/8/16 GB). Alternative: pay-as-you-go in **"Claws"** prepaid credits (65 Claws/€;
  tiers burn 60/105/175 Claws/day; instance-creation setup fee 150–450 Claws; volume
  bonuses to 25%). Zero balance → pause → snapshot → 3-day grace. [E]
- Model options: (a) **free bundled models** (Kimi K2.5, DeepSeek R1/V3, Gemini 2.5 Flash
  Lite — "ClawHosters covers API expenses") with daily/monthly token limits; (b) **BYOK**
  (Anthropic incl. subscription setup-token, OpenAI, Google, DeepSeek, OpenRouter,
  Mistral, Groq — "no extra cost from ClawHosters," no markup, but no failover); (c)
  **managed token packs** (Eco/DeepSeek €3–25, Standard/Gemini €5–40, Premium/Claude-Haiku
  €12–70 per month, real-time token metering, automatic failover through a backup
  provider, hard-stop error on pack exhaustion). [E]
- LLM proxy internals: SSE streaming proxy with re-framing buffer split on `\n\n`; usage
  billed by pattern-matching a 4 KB ring buffer of SSE tail for token counts (byte-size
  estimation fallback); per-request rows (instance, provider, model, in/out tokens, exact
  cost); provider price normalization via a hand-updated lookup table; auth to the proxy
  **by source IP** (IPv4 index, IPv6 /64 CIDR containment in Postgres); rate limits 60
  req/min (10 for reasoning models); automatic failover to OpenRouter on 5xx. [E]
- Founder's own verdict on Claws: "I probably should have started with simple Stripe
  subscriptions and added the credit system later." [E]

### 3.8 Onboarding funnel
Signup (~1 min, free trial, card not charged until trial ends) → New Instance → billing
mode → tier + instance name (immutable — a documented friction point) → pay/review
(~1 min) → provision (~60 s incl. hardening + health check) → connect a channel (~5 min,
the longest step — bot tokens/QR pairing) → chat. **~11 minutes signup→first
conversation**; the free bundled model means no credential is required before first chat.
[E]

### 3.9 Ops — updates, monitoring, support burden
- Stack: **Rails 8 monolith, PostgreSQL, Sidekiq (5 processes/50 threads), Clockwork
  scheduler, single platform server**, Hetzner API. "No Kubernetes, no ECS, no managed
  database." [E]
- Self-heal ladder: healthcheck failures 1–3 monitored → **4 consecutive → automatic
  config-repair service** (pattern-matches container logs, applies targeted fixes: invalid
  bind values, missing keys, permissions) → **5+ → Telegram + email alerts to the admin**.
  Config writes are guarded three ways: critical-flag verification after each change
  (`controlUi`/gateway must stay true), automatic repair, dashboard transparency (config
  state, health, container logs, node_exporter CPU/RAM/disk/net). Config migrations are a
  **pull-based registry** — "what did I miss from version X to Y?" — setting only missing
  keys so customizations survive. [E]
- Founder lessons, verbatim: monitoring "added after the fact" (should be day-one on every
  VPS); "validate before write, not after crash — early validation prevents dozens of
  support tickets"; retrofitting token metering into a running streaming proxy "was
  painful"; Docker = "70% of all technical problems"; on the security build-out: "I sleep
  well." Support response <20 min claimed by the independent review. [E]
- ZeroTier one-way networking: sidecar joins the customer's private network, routes
  injected via `nsenter` into OpenClaw's netns — outbound-only, enables home/local LLMs
  (Ollama/LM Studio) without public exposure. [E]

### 3.10 Weaknesses / complaints (independent + structural)
- bestclawhosting security review, 28.5/100: **no MFA**; "no mention of prompt injection
  defenses, sandboxing for code execution beyond Docker, human-in-the-loop approval
  workflows"; **"agent going rogue" 2/10** (no spending limits, no approval workflows, no
  behavioral monitoring); misinformation 1/10; supply chain 2/10 (no SBOM/dependency
  scanning); "regular security audits" claimed in the privacy policy with no evidence;
  solo-founder bus factor; no formal SLA; 3-day deletion window. [E]
- Trustpilot (via search; direct page 403): mixed — praise for setup ease + support;
  complaint that "OpenClaw agents would not work due to ClawHosters' own restrictions on
  the service" with support replying the system was up and "nothing could be done" [E] —
  plausibly the outbound SMTP/IRC blocks or gateway-only mode without the LLM add-on
  biting real use [I].
- Structural [I]: chat history is unbackupable today (add-on unshipped); no user-facing
  alerting; custom skills die on rebuild; container gets ~25% of the advertised RAM;
  1186-signups vs 39-running gap suggests weak trial→paid conversion or high churn.

## 4. Adjacent-market signals (from their blog + ecosystem, 2026-06)

- **ClawHub marketplace: 824 malicious skills, 7.7% infection rate** in the *official*
  OpenClaw skills marketplace. Direct warning for TinyAssets's public agent-definition /
  node commons: an unvetted remix marketplace becomes a malware channel at ecosystem
  scale. [E]
- **"500,000 exposed OpenClaw instances, zero kill switch"** enterprise-security-crisis
  post — self-hosted agent sprawl leaks credentials; a hosted platform with real custody
  discipline is the fix being demanded. [E]
- **Microsoft Agent 365 specifically detects and blocks OpenClaw deployments**; OpenAI
  launched Workspace Agents (hosted enterprise agents) — first-party platforms are moving
  on this demand from above. [E]
- **Five OpenClaw hosting providers listed for sale simultaneously** (2026-06-01);
  ecosystem ~186 companies peaked ~$400K *total* monthly revenue in Q1 — consolidation
  underway; thin-wrapper hosting alone is a weak business. [E]

## 5. Module-by-module comparison vs TinyAssets

TinyAssets module list per `PLAN.md` § Module Map; live-state facts from `STATUS.md` +
project memory, stamped 2026-08-10.

| TinyAssets module | ClawHosters | TinyAssets today | Learn / Copy / Avoid |
|---|---|---|---|
| **Engine & Domains** | No engine — vendors the community OpenClaw image unmodified; product = ops around it. | Own engine (`tinyassets/`, LangGraph), domain-agnostic, user-built automations. | LEARN: vendoring upstream = zero engine leverage but zero engine cost; their whole roadmap is UI over someone else's agent. Our engine is the moat *and* the burden — keep it earning its keep via primitives no host can wrap. |
| **Daemon Platform (runtime, tenancy)** | 1 customer = 1 VPS = 1 container = 1 agent. No fleet, no dispatch, no multi-daemon. Tenancy solved at the hypervisor. | Multi-tenant by design; universes share one droplet + one daemon process; runtime instance allocation is a designed-but-not-hardware-backed boundary. | **COPY (adapted): per-universe VM/container as the runtime allocation unit.** Snapshot + pre-warmed pool makes it a 30–60 s operation; €4–8/mo COGS at Hetzner [I from their pricing]. Solves noisy-neighbor + blast-radius + the R2-1 credential-bleed class structurally. |
| **Sandbox / isolation** (STATUS P1 "no OS engine sandbox"; memory `universe-engine-sandbox-p0`) | Genuine kernel-level isolation per customer, by purchase order. Inside the box: Docker `no-new-privileges`, outbound SMTP/IRC blocked, SYN-flood limits, fail2ban, inbound only from the control server. But *agent-level* safety = 0 (no approval flows, no spend caps). | In-process confinement only (WebFetch-only, cwd-pin, rot-prone denylist); #1485 fail-closed seam; OS sandbox deferred. | **The headline LEARN: hard isolation is commodity-priced; stop treating "OS sandbox" as a hard research problem — it's a provisioning-pipeline problem.** Their 4-layer network model (cloud firewall allowing only the control-plane IP + host iptables egress filtering) is directly liftable. AVOID their gap: infra isolation without agent-authority controls scored 2/10 externally — our permissions/authority work is the differentiator, keep it. |
| **Brain (memory/knowledge)** | None as a product. In-chat context only; chat history not even backupable today; rebuild wipes it. | Typed memory catalog, promotion state machine, durable session-anchored `conversation_store` (PR #2394), wiki commons, learning write-back. | AVOID their model entirely — it's our clearest product differentiation ("an agent with no memory between turns is not an agent," proven live). Market it explicitly against the hosting class: *your agent's memory survives rebuilds, moves, and providers.* |
| **Goals & Gates / Evolution & Evaluation** | Absent. No outcomes, no evaluation, no leaderboards, no optimization. | Full outcome-gate ladder, Evaluator primitive, lineage/attribution. | LEARN (negative space): the hosting class competes on €/GB; nobody in it has an improvement loop. Also: **ClawHub's 7.7% malicious-skill rate** is the failure mode our commons must pre-empt — evaluator-gated + provenance-gated publication for shared definitions/nodes is a security control, not just quality control. |
| **Providers (routing + serving)** | 9 BYOK providers; free loaner models (Kimi/DeepSeek/Gemini) so day-0 chat needs no credential; managed packs with cross-provider failover; SSE proxy with ring-buffer token metering; failover to OpenRouter on 5xx; per-request cost rows. | Router with fallback chains, subscription-only default, `allowed_providers`, writer-pin; R2-1: vault currently fails OPEN (missing cred inherits host token) — active work. | **COPY: the "day-0 loaner model" onboarding pattern** — an explicitly-labeled platform-owned free model binding so first contact never blocks on credentials. Must be an *explicit* binding (provenance-tagged), never ambient inheritance — the R2-1 fail-open bug is the evil twin of this feature. LEARN: per-request cost rows (instance, provider, model, tokens, cost) is the receipt shape our provider receipts need. AVOID: scraping usage from an SSE tail ring buffer — parse the protocol. |
| **Credential vault** | Platform-DB AES-256-GCM (Rails encrypted credentials), decrypted server-side into instance config. No revocation doc, no per-user key ceremony, "we never read your token" as marketing. | 4-layer vault design (SecretCipher/SecretStore/Connection/connect-flows), HYBRID custody, fail-closed direction. | LEARN: their UX bar (paste token → verified test call → working) is what users accept; our vault must match that friction. AVOID: custody claims stronger than the architecture ("never accesses") — say precisely what we do. Their missing revocation story is a gap we should ship as a feature (revoke + rotate from chat). |
| **Conversation memory / channel ingress** | 4 channels + web, multi-channel per instance, dashboard-configured bot tokens. Channels ARE the product surface. No cross-channel memory. | Slack ingress (with known wedge/stale-image failure modes), MCP chatbot connectors, mobile app future. Durable cross-turn store. | LEARN: **Telegram + WhatsApp are the personal-agent market's front door** — every host in this class leads with them; our Slack+MCP-first posture skips where these users live. Their per-instance bot-token model (user creates their own Telegram bot) also neatly sidesteps platform-level rate limits and consent [I]. Defer, but put it on the channel roadmap explicitly. |
| **API & MCP Interface** | REST-ish dashboard + planned "Customer API"; no MCP surface at all. | MCP-native (canonical handles, connector surface, ui-test gate). | Keep. Their web "Mission Control" per instance is the analog of our get_status — but ours is conversational + self-auditing. No copy needed. |
| **Distribution & Discoverability** | Trustpilot + Reddit + SEO blog (their blog is an OpenClaw-ecosystem news site — a real acquisition channel: ~50 customers from Reddit alone, no ad budget). | MCP registries, ChatGPT app submission, packaging. | LEARN: ecosystem-news content marketing is cheap and worked for a solo founder. WATCH: consolidation (5 hosts for sale) means this class may be acquirable/partnerable rather than competitive. |
| **Uptime & Alarms / deploy & ops** | Pre-warmed pool; snapshot provisioning; in-place zero-downtime updates via `docker commit`; health→config-auto-repair→admin-page ladder; stuck-deploy watchdog (5 s poll, 20 min flag); pull-based config-migration registry; route reconciliation every 10 min. No user-facing alerts; no SLA. | 3 self-heal layers + host-independent alarm ladder + DR drill (strong), BUT: deploy-prod P0 — a failed deploy leaves ZERO containers; single droplet; forward-only deploys. | **COPY: never-empty deploys** — their model never has zero capacity: new state is proven (health-checked through the full routing stack) while the old committed image still exists; our stop-writer-then-deploy fence is the inverse and it's our open P0. COPY: config-migration pull registry (only set missing keys) for universe config evolution. LEARN: their stuck-in-deploying watchdog = our "merged is not deployed" lesson, productized. |
| **Observability** | Admin: Telegram/email at 5 fails, node_exporter metrics, container logs in dashboard. Customer: colored status dot, no alerts. | get_status receipts, canaries, Pushover ladder, release_state sha. | LEARN: their *customer-visible* container logs + metrics panel is more transparency than we expose per universe today; per-universe health belongs in `get_status`/chat ("your universe restarted twice today"). AVOID: alerting only the admin — universe owners are the ones who should hear their agent is down. |
| **Billing / paid-market / token architecture** | Infra fee + unbundled model cost; Claws prepaid credits (founder regrets leading with them); pause-snapshot-delete lifecycle; setup fees; trial with card-on-file. | Paid-market/escrow/Destiny(tiny) designs; no consumer billing shipped. | **COPY: the unbundling** — charge visibly for the universe (compute/orchestration), let model spend ride the user's own subscription/key; this is also the enforcement-survival posture (companion note §3). LEARN the founder's regret: launch with plain Stripe subscriptions; credits later — direct caution for leading with token/Claws-style economies. COPY: **hibernation lifecycle** (pause → snapshot → grace → delete, resume-on-payment) for dormant universes; 24/7 heartbeat for every universe forever doesn't scale economically [I]. Make our grace window ≫ 3 days. |
| **Identity / auth / access control** | Email+password (bcrypt), Google sign-in, **no MFA**; per-instance HTTP basic auth; device-pairing approval. | WorkOS auth live, founder-recognition fail-closed, tier model (with the known T2 write-ACL hole). | Keep ours. Their no-MFA at custody-of-Claude-tokens scale is the cautionary tale — we hold the same class of secret and must clear a higher bar. |

## 6. Top-5 actionable implications (classified)

1. **ADAPT — Per-universe hard isolation via snapshot + pre-warmed pool.** The P1 "no OS
   engine sandbox" concern and the R2-1 credential-bleed class both dissolve if a universe's
   engine turns run in a per-universe container/microVM provisioned ClawHosters-style
   (pre-baked image, pre-warmed pool, claim-don't-create, control-plane-only inbound,
   egress-filtered). Proven operable by ONE person at €19/mo retail. Smallest slice: one
   pre-baked image for the `converse` engine turn, one pooled sandbox claimed per universe,
   network policy = outbound-allowlist + inbound-from-daemon-only. Risks: cost floor per
   active universe; cold-start latency (mitigated by pool); Windows-dev/Linux-prod split.
   Verification: escape-attempt test suite + the existing sandbox P0 checklist.
   *This changes PLAN.md (Daemon Platform runtime allocation) if adopted — host + Codex
   review first.*
2. **ADOPT — Never-empty deploys (prove-new-before-stop-old).** ClawHosters updates by
   committing the running container, starting the new state, and health-checking through
   the full routing stack; there is no moment of zero capacity. Our deploy-prod P0 (failed
   fence → ZERO containers, 3 outages on 2026-08-07) is the exact anti-pattern. Smallest
   slice: reorder deploy-prod so the old container is stopped only after the new one passes
   the canary (or keep a `docker commit`/last-known-good tag to auto-restore on fence
   failure). Depends on: memory `deploy-pipeline-outage-window-and-level2` (Level 2
   rollback REVERSES forward-only policy → founder authorization required).
3. **ADOPT — Day-0 loaner model + explicit provider receipts.** Their free bundled models
   mean first chat never blocks on a credential; BYOK upgrades later. For us: an explicit,
   provenance-tagged platform-owned free binding (clearly labeled, rate-capped) as the
   universe's day-0 provider — the *legitimate* version of what R2-1's fail-open bug does
   accidentally. Pair with their per-request cost-receipt shape (universe, provider, model,
   in/out tokens, cost) which R2-1's "provider receipt" already gates on. Smallest slice:
   one free-tier model binding behind `allowed_providers`, labeled in `get_status`.
4. **ADOPT — Universe hibernation lifecycle.** Pause → snapshot → grace → delete /
   resume-on-signal, with scheduling. A 24/7 heartbeat per universe at fleet scale is an
   economic wall; ClawHosters ships hibernation as a *customer feature* (save Claws).
   Ours: idle universes drop to wake-on-ingress (Slack message, MCP call, scheduled
   automation) with state snapshotted; grace windows generous (their 3-day delete is the
   documented complaint to avoid). Smallest slice: define universe activity states in the
   universe-lifecycle spec + a wake-on-converse path; no deletion automation in v1.
5. **AVOID + WATCH — Their state model and the unvetted-commons failure.** Do not ship any
   surface where rebuild/migration loses conversation history (their backups *exclude*
   chat history — our durable brain is the counter-position; say it in marketing). And
   treat **ClawHub's 824 malicious skills / 7.7% infection rate** as the base rate for an
   unvetted agent-artifact commons: TinyAssets's public definition/node marketplace must
   launch evaluator-gated + provenance-gated (maps to existing Evolution & Evaluation
   safety principles; add an explicit "malicious-definition screening" requirement when the
   commons publication spec is next touched).

Secondary (no packet, noted for future builders): config-migration pull-registry pattern for
universe config evolution; per-universe health visible to the owner in `get_status`/chat;
Telegram/WhatsApp ingress on the channel roadmap; credential revocation-from-chat as a
custody feature; plain-Stripe-before-credits billing sequencing; ecosystem-news blog as
acquisition channel.

## 7. What ClawHosters validates about current TinyAssets bets

- BYO-subscription custody via setup-token paste + AES-GCM vault is live, marketed, and
  unenforced-against (reinforces companion precedents note §5) — and their missing
  revocation/MFA/key-ceremony shows where to beat them.
- Infra-fee-plus-user's-model billing is commercially real at the low end (€19/mo).
- "Boring stack, one operator" is sufficient for a ~40-instance fleet — our single-droplet
  present isn't embarrassing; our alarm ladder + DR drill already exceed their ops maturity.
- Durable memory, agent authority/safety, evaluation, and commons primitives are exactly
  the layers the hosting class lacks — the moat is real, keep building it.

## 8. Open questions

1. What are the free-bundled-model daily/monthly token limits, concretely? (Docs say limits
   exist; numbers not published.) Matters for calibrating our day-0 loaner caps.
2. What were the "ClawHosters' own restrictions" that broke a customer's agents
   (Trustpilot complaint)? Egress filtering? Gateway-only mode? Determines which
   restrictions users tolerate.
3. Does the platform ever proxy BYOK/subscription traffic through its own LLM proxy (where
   the IP-auth + metering lives), or do instances call providers directly in BYOK mode?
   [Docs imply direct; the proxy writeup implies managed-only metering — unresolved.]
4. Real churn: 1186 signups → 39 running. Is the hosted-personal-agent market retention
   actually terrible, and why (cost? novelty decay? memoryless agents?) — the answer shapes
   our heartbeat/hibernation economics.
5. Hetzner unit economics at fleet scale for us: per-universe microVM (Firecracker-class)
   vs full VPS vs shared-kernel containers — cost/isolation matrix needed before Implication
   1 goes to design.

## 9. Pickup packet (ready to land — not yet in STATUS.md per this session's one-deliverable constraint)

- **Concept:** per-universe hard isolation + never-empty deploys + day-0 loaner model +
  universe hibernation (implications 1–4; implication 5 is a standing constraint, not a
  lane).
- **Source artifact:** this note. Key URLs: clawhosters.com/{docs/architecture,
  docs/claude-setup-token, docs/security-overview, docs/claws-explained, docs/llm,
  docs/config-backups, roadmap}, clawhosters.com/blog/posts/how-i-built-60-second-vps-provisioning,
  clawhosters.com/blog/posts/building-managed-hosting-platform-tech-deep-dive,
  bestclawhosting.com/provider/clawhosters, betterclaw.io/compare/clawhosters,
  dev.to/yixn_io.
- **Initial provider:** claude. **Required reviewer:** Codex (verdict artifact under
  `docs/audits/`, verdict token approve/adapt/defer/reject). Build/push/live work on any
  implication is BLOCKED until that verdict.
- **Applies when touching:** `deploy/deploy-prod.yml` or the stop-writer fence (impl. 2);
  `tinyassets/providers/`, `credential_vault.py`, R2-1 (impl. 3); universe lifecycle spec
  `openspec/specs/universe-lifecycle-and-soul/` (impl. 4); sandbox/converse engine-turn
  code or #1485 (impl. 1); commons publication / definition marketplace specs (impl. 5).
- **Suggested STATUS.md row** (paste when landing):
  `| ClawHosters implications review — Codex re-check sources + verdict on impl. 1–4 (per-universe isolation, never-empty deploy, day-0 loaner, hibernation) | docs/design-notes/2026-08-10-arch-research-clawhosters.md, docs/audits/ | - | pending`
- **Worktree landing packet** (first buildable slice = implication 2, smallest + already-P0):
  branch `claude/deploy-never-empty`, worktree `../wf-deploy-never-empty`, base `main`;
  write-set `.github/workflows/deploy-prod.yml`, `deploy/`; PLAN modules: Uptime & Alarms,
  Distribution; memory refs: `deploy-pipeline-outage-window-and-level2`,
  `deploy-fence-takes-prod-down-on-failure`, `partial-compose-file-converges-the-project`;
  depends: Codex review verdict + founder authorization if it touches forward-only policy;
  verification: staged deploy on the box with induced fence failure → prod must still serve
  (`get_status` green throughout); fold-back: PR to main, delete row on land.

---

## Codex opposite-provider review — CLAWHOSTERS_VERDICT: ADAPT (2026-08-10)

Adopt over the body where they conflict:
- **Never-empty deploys:** approve the OUTCOME, reject `docker commit` as the mechanism
  (mutable snowflake images, secret capture, no SBOM/reproducibility). Correct target:
  always-live ingress + an EPOCH-FENCED SINGLE-WRITER CUTOVER. Note current main already
  candidate-load-tests pre-quiesce and records a rollback target — the P0 narrative in the body
  is partly historical.
- **Per-universe volumes:** reduce blast radius + allow serial rollout, but do NOT remove
  fencing — exclusive writer authority + consistent checkpoint/delta handoff still required.
- **Day-0 loaner:** if ever wanted (FOUNDER DIRECTIVE currently forbids platform-provided LLMs),
  it must be an explicit temporary binding (provider, budget, expiry, receipts) — never ambient.
- **Hibernation:** hibernate the runtime ACTIVATION, not the universe — identity/schedules/
  checkpoints stay continuously available; control plane wakes execution on admitted ingress.
- **Module table: REJECTED** as a current-state comparison (blends target PLAN with shipped
  state; vault/providers/deploy rows inaccurate) — treat the table as directional only.
- **Material misses to carry:** tenant/untrusted-workload/credential isolation are THREE separate
  boundaries; dedicated VPSs keep a shared control-plane compromise domain; warm-pool hygiene
  (atomic claim, reimage-on-release, secret scrubbing) unproven; shared-SQLite → per-universe
  machines requires partitioning platform vs universe state first; marketplace malware needs
  immutable hashes + publisher identity + capability manifests + scanning + revocation, not just
  provenance/evaluator gates.
