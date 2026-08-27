# Architectural research: DevBoxer + terragon-oss — the Terragon-successor "your subscription, our sandboxes" platform

**Date:** 2026-08-10 · **Initial provider:** claude (Claude Code session) · **Required reviewer:** codex
**Method:** `external-research-implications` skill; read-only + web; sources cited inline.
**Evidence discipline:** `[EV]` = direct evidence (source file at pinned commit, or fetched page dated 2026-08-10). `[INTERP]` = inference.

---

## 1. Canonical summary

**DevBoxer** (https://www.devboxer.com) is a hosted background-coding-agent platform: describe a task, an agent
(Claude Code / OpenAI Codex / Amp) works in an isolated cloud sandbox on a clone of your GitHub repo, and you review
the resulting PR. Pricing: **Core $30/seat/mo (100 sandbox hours, 3 concurrent tasks), Pro $60/seat/mo (225 hours,
30 concurrent), Enterprise custom** — while the model spend rides the user's own ChatGPT or Claude subscription
`[EV: devboxer.com homepage, fetched 2026-08-10]`.

**DevBoxer is Terragon with a new owner.** Terragon Labs (founder: Sawyer Hood `[EV: x.com/sawyerhood/status/1938263088836579536]`)
shut down 2026-02-09 for lack of traction ("weren't able to reach the level of traction needed to turn it into a
sustainable, long-term business" `[EV: docs.terragonlabs.com/docs/resources/shutdown via search]`), open-sourced the
entire platform as **terragon-labs/terragon-oss** (Apache-2.0, snapshot 2026-01-16, last commit `83142a17` 2026-02-10,
255★/44 forks), and DevBoxer states it is "built on the literally the same foundations"
`[EV: devboxer.com/docs/resources/terragon-shutdown]`. DevBoxer is a separate company (team undisclosed), a fresh
platform (no data migration), and added burst CPU/memory, a planned "Orchestrate mode," and the 30-task Pro
concurrency `[EV: same page]`.

**Consequence for this study:** terragon-oss is not just the corpse — it is, with high confidence, DevBoxer's live
architecture modulo those deltas. Every code citation below is from the pinned clone
(`terragon-labs/terragon-oss @ 83142a17`, read in scratchpad; paths relative to repo root).

**Relationship to existing note:** `docs/design-notes/2026-08-10-subscription-platform-precedents.md` ranks Terragon #2
and DevBoxer #4 at the market/policy level. This note adds the architecture level, and files one correction to that
note (§8, correction C1).

---

## 2. Source freshness stamp

| Source | Identity | Date | License |
|---|---|---|---|
| terragon-labs/terragon-oss | github.com/terragon-labs/terragon-oss, default branch, commit `83142a17f3970df3e14d1879234a603db6e4f615` (2026-02-10) | cloned 2026-08-10 | Apache-2.0 (TRADEMARKS.md restricts marks) |
| devboxer.com homepage + /docs + /docs/resources/terragon-shutdown | live fetches | 2026-08-10 | n/a |
| terragonlabs.com + docs.terragonlabs.com | shutdown page (docs TLS cert expired — site decaying) | 2026-08-10 | n/a |
| Founder threads | x.com/sawyerhood (Terragon launch, Max-plan usage tracker, leaderboard) | posts Jun–Jul 2025, fetched 2026-08-10 | n/a |
| HN thread "Alternatives to Terragon Labs" (id=46589735) | located; fetch rate-limited (429) twice — content not read | 2026-08-10 | n/a |

---

## 3. Architecture findings (the ten questions)

### 3.1 Product shape

One primitive: the **task** (DB entity: `thread`). User picks repo + branch + agent + prompt; platform clones repo
into a fresh sandbox, runs the coding agent, checkpoints work to a per-task git branch, opens a PR. Target user:
individual devs/teams delegating coding work `[EV: README.md; apps/www]`. Secondary surfaces: follow-up chats on a
task (`threadChat`, "thread version 1" = N chats per task `[EV: schema.ts:312-315]`), sub-tasks
(`parentThreadId`/`parentToolId` `[EV: schema.ts:300-304]`), drafts, scheduled tasks, and **automations** (§3.3).
No persistent agent identity, no memory, no community layer — it is a stateless task-runner with excellent ergonomics.

### 3.2 The subscription-connect UX — mechanically, per family (focus area a)

This is the closest live implementation of our `byo-llm-connect-flow` Slice 2 (which our design defers:
"Provider OAuth/device-flow or API-key ingress ... (Slice 2)" `[EV: openspec/changes/byo-llm-connect-flow/design.md]`).

**Claude — hosted OAuth 2.0 + PKCE popup, with Anthropic-hosted code display and manual paste-back**
`[EV: apps/www/src/lib/claude-oauth.ts; server-actions/claude-oauth.ts; components/credentials/add-credential-dialog.tsx]`:

- Client: Anthropic's own **Claude Code public client**, `CLIENT_ID 9d1c250a-e61b-44d9-88ed-5944d1962f5e`, no
  client secret, PKCE S256 (via `arctic`). Scopes: `org:create_api_key user:inference user:profile`.
- **Two modes behind one flow** (`AuthType = "subscription" | "api-key"`):
  - *subscription*: authorize at `https://claude.ai/oauth/authorize` — "gets you a token that can be used directly
    with claude code" (code comment). This is the Pro/Max plan path.
  - *api-key*: authorize at `https://console.anthropic.com/oauth/authorize`, then POST
    `https://api.anthropic.com/api/oauth/claude_cli/create_api_key` with the access token to **mint a real Anthropic
    API key** server-side.
- Redirect URI is **Anthropic's own code-display page** `https://console.anthropic.com/oauth/code/callback` — so no
  DevBoxer-registered redirect exists; the UI opens a popup, and the user **pastes the code** back:
  "Authorize Claude in the new window, then paste code below" `[EV: add-credential-dialog.tsx:397,401]`. Token
  exchange (`console.anthropic.com/v1/oauth/token`) and refresh happen server-side.
- After connect, the server calls `api.anthropic.com/api/oauth/profile` and stores account email, org, and
  `isMax = organization_type === "claude_max"` `[EV: apps/www/src/agent/msg/claudeCredentials.ts]` — used for plan-aware
  UX (Terragon even shipped "track your claude code usage ... see if you are maxing your max plan"
  `[EV: x.com/sawyerhood/status/1944908622280188252]`).

**ChatGPT/Codex — no hosted flow at all; local `codex login` + paste `auth.json`**
`[EV: apps/www/src/server-actions/codex-auth.ts; lib/openai-oauth.ts; add-credential-dialog.tsx:570]`:

- UI instruction: "Log in to ChatGPT in a terminal, then paste your [auth.json]". User pastes the whole
  `~/.codex/auth.json`; server extracts `tokens.{id_token,access_token,refresh_token,account_id}`, discards any
  `OPENAI_API_KEY`, and **immediately refresh-validates** against `https://auth.openai.com/oauth/token` with OpenAI's
  Codex public client `app_EMoamEEZ73f0CkXaXp7hrann` — invalid paste fails loudly ("run 'codex login' to refresh").
- The `id_token` JWT is parsed for `email`, `https://api.openai.com/auth.chatgpt_plan_type`, and
  `chatgpt_account_id` for display `[EV: server-lib/credentials.ts:26-50]`. Typed error `chatgpt-sub-required`
  exists in the task-error taxonomy `[EV: packages/shared/src/db/types.ts]`.

**Storage:** one unified `agent_provider_credentials` table — per `(user, agent)`, `type: "api-key" | "oauth"`,
separately encrypted columns (`apiKeyEncrypted`, `accessTokenEncrypted`, `refreshTokenEncrypted`, `idTokenEncrypted`)
under a single `ENCRYPTION_MASTER_KEY`, `isActive`, `expiresAt`/`lastRefreshedAt`, JSON metadata
`[EV: schema.ts:1133-1165]`. Four older per-provider tables are `_DEPRECATED` — they converged on the unified shape.

**Delivery to the sandbox:** credentials are materialized as the **CLI's own native credential file** inside the
sandbox — `~/.claude/.credentials.json` (`agentCredentialsFilename: ".credentials.json"`
`[EV: packages/sandbox/src/setup.ts:333]`); the in-sandbox daemon checks for that file and only exports a platform
`ANTHROPIC_API_KEY` fallback when the user file is absent `[EV: packages/daemon/src/claude.ts:5-32]`. The genuine
`claude`/`codex` CLIs then authenticate exactly as they would on a laptop.

### 3.3 Task/agent orchestration

**Postgres is the queue.** No BullMQ/Inngest/Trigger.dev anywhere; Redis exists only for rate-limiting/locks
`[EV: apps/www/src/lib/rate-limit.ts, redis.ts]`. Tasks carry `scheduleAt`/`reattemptQueueAt` with composite
`(scheduleAt,status)` / `(reattemptQueueAt,status)` indexes `[EV: schema.ts:330-334]`, and **four Vercel crons** sweep
them: `scheduled-tasks` every 1 min, `queued-tasks` every 10 min, `stalled-tasks` hourly (reaper), `automations`
every 30 min `[EV: apps/www/vercel.json]`. The control plane is entirely serverless (Next.js on Vercel,
`maxDuration: 800`).

**Lifecycle is an explicit XState machine** over `ThreadStatus` `[EV: apps/www/src/agent/machine.ts;
packages/shared/src/db/types.ts:121-152]`:
`draft → scheduled → queued → {queued-tasks-concurrency | queued-sandbox-creation-rate-limit | queued-agent-rate-limit}
→ booting → working → {working-done | working-error} → checkpointing → complete`.
Note the three **named backpressure states** — the user sees *why* a task is waiting, including "waiting due to agent
(Claude) rate limit". Concurrency gate at claim time: `activeThreadCount >= maxConcurrentTasks` (3 default, 10 pro in
code; DevBoxer sells 30) `[EV: server-lib/process-queued-thread.ts; lib/subscription-tiers.ts]`.

**In-sandbox daemon → server events.** A Node daemon (`packages/daemon`) runs inside every sandbox, drives the coding
CLI, and POSTs message batches to `/api/daemon-event` authenticated by a per-daemon token; the server computes context
usage from the last message's token usage and broadcasts to browsers `[EV: apps/www/src/app/api/daemon-event/route.ts;
api/internal/daemon-token]`. Follow-up messages are queued on the thread (`queuedMessages`) and fed to the running agent.

**Automations** = stored triggers that mint tasks: `manual | schedule (cron+timezone) | pull_request | issue |
github_mention`, each with author/draft/bot filters and auto-archive-on-complete; capped at 20 (unlimited on Pro)
`[EV: packages/shared/src/automations/index.ts; schema.ts:963-1005; subscription-tiers.ts]`.

### 3.4 Sandbox architecture + isolation

A clean **vendor-abstraction seam**: `ISandboxProvider` with four implementations — **E2B (production default)**,
**Daytona**, Docker (dev/test only), Mock `[EV: packages/sandbox/src/provider.ts, providers/]`. One sandbox per task,
holding a repo clone; template image built from `Dockerfile.hbs` + supervisord (`packages/sandbox-image`); E2B
template = 2 vCPU / 4 GB ("small"; "large" is Pro-gated) `[EV: packages/e2b/e2b.toml; subscription-tiers.ts]`.
Sandboxes pause/resume (`sandbox-resume-failed` is a typed error); per-environment setup scripts and encrypted env
vars (`environment` table, `run-setup-script` streaming route). Isolation is thus **rented microVMs from a sandbox
vendor**, not home-built. DevBoxer's stated delta: burst CPU/memory scaling `[EV: devboxer terragon-shutdown page]`.

### 3.5 GitHub integration

GitHub App is both the auth provider and the delivery rail. Per-task unique branch; **work is checkpointed and pushed
continuously with AI-generated commit messages**; PR opened automatically; `githubPR` + `githubCheckRun` tables track
PR state and CI conclusions; dedicated actions for `mark-pr-ready`, `fix-github-checks` (spawn a follow-up task from
failing checks), `retry-git-checkpoint`; the whole git workflow is optional per task (`disableGitCheckpointing`)
`[EV: README.md; schema.ts:393-453; server-actions/]`. GitHub webhooks feed PR/issue/mention automations, including
@-mentioning the bot in a PR comment to kick off a task.

### 3.6 Steering and observability

- **Web**: real-time streaming dashboard — daemon events → Postgres → PartyKit broadcast service (`apps/broadcast`) →
  browser; browser notifications on completion `[EV: AGENTS.md; apps/broadcast]`.
- **Permission model per task**: `permissionMode: "allowAll" | "plan"` + an `approve-plan` server action — plan mode is
  the consent gate, persisted on the thread `[EV: schema.ts:260-262; server-actions/approve-plan.ts]`.
- **Slack**: full ingress — app-mention handler harvests the mention's **thread replies, channel name, and resolves
  @-mention display names**, builds a context-rich prompt, and creates a task via `newThreadInternal`
  `[EV: apps/www/src/app/api/webhooks/slack/handlers.ts]`.
- **CLI (`terry`)**: `auth / create / list / pull` — pull a cloud task's branch + session down for **local handoff**
  `[EV: apps/cli/src/commands]`.
- **MCP server**: minimal — `SuggestFollowupTask` and `PermissionPrompt` tools, so MCP clients (Cursor, Claude Code)
  can create/manage tasks `[EV: packages/mcp-server/src/index.ts]`.
- Mobile: responsive web only; no native app found `[INTERP: no mobile app dir in repo; marketing mentions "mobile devices"]`.

### 3.7 Memory/state between tasks

**Essentially none — and this is the sharpest contrast with TinyAssets.** The only persistence is *session
continuity per task*: `claude_session_checkpoints (threadId, sessionId, r2Key)` uploads the Claude Code session
state (the `~/.claude/projects/**/<sessionId>.jsonl`) to Cloudflare R2 so a follow-up can resume the same agent
session after the sandbox died `[EV: schema.ts:1115-1131; packages/daemon/src/claude.ts isValidSessionId]`. No
cross-task memory, no user-level knowledge, no repo-level learned context. Each task starts cold.

### 3.8 Billing mechanics (focus area b)

Three unbundled meters `[EV: schema.ts subscription/userCredits/usageEvents; devboxer.com homepage]`:

1. **Seat subscription** (Stripe; `subscription.plan/seats`) — the platform fee: $30/$60 per seat per month.
2. **Sandbox hours** — the infra quota (100/225 h per tier); sandbox time is the metered unit, not tokens.
3. **Model spend** — *rides the user's subscription* (BYO OAuth, unmetered by the platform) **or**, when the user has
   no subscription, runs on platform keys through a **metered LLM proxy** with credit billing:
   `/api/proxy/{anthropic,google,openai,openrouter}` forwards requests, **parses streamed usage events**
   (input/cached/cache-creation/output tokens), checks credit balance, logs `usageEvents` rows per SKU, and
   auto-reloads credits `[EV: apps/www/src/app/api/proxy/anthropic/[[...path]]/route.ts]`.
   SKU pricing is straight provider list price (e.g. `openai_responses_gpt_5` $1.25/M in, $10/M out; Sonnet $3/$15;
   Opus $15/...) — passthrough, margin lives in the seat fee `[EV: packages/shared/src/model/usage-pricing.ts]`.
   Aggregation: `usage_events_agg_cache_sku` keeps running totals per (user, sku, eventType) with a
   `(created_at, id)` watermark for incremental catch-up `[EV: schema.ts:1068-1113]`.

### 3.9 What terragon-oss reveals structurally

Monorepo (pnpm + Turbo): `apps/{www, broadcast, cli, docs}`, `packages/{agent, daemon, sandbox, sandbox-image, e2b,
shared, mcp-server, transactional, r2, env, types, utils, ...}`. Stack: Next.js 15/React 19, Drizzle + Postgres,
better-auth, Redis (rate-limit only), PartyKit, Stripe, R2, PostHog, Vercel crons. Notable: **no dedicated queue
infrastructure** (Postgres rows + status machine + cron sweepers carried real production load); a full
growth-ops surface in-schema (waitlist, allowedSignups, access codes, feature flags per-user, reengagement +
onboarding-completion email tables); admin panel; `apps/isanthropicdown` — an Anthropic-uptime microsite (they were
dependent enough on Anthropic health to build a status page for it) `[EV: AGENTS.md; repo tree]`.

### 3.10 Why Terragon failed, and what DevBoxer changed

- Official: **traction, not policy and not unit economics** `[EV: shutdown pages]`. The precedents note's [INTERP]
  stands: the 2026-01-09 Anthropic OAuth crackdown hit protocol reimplementers, not real-CLI orchestrators; the
  shutdown one week later reads as coincidence.
- Structural reading `[INTERP]`: Terragon built the best-executed version of a product with no moat — stateless task
  running is a commodity being absorbed first-party (Anthropic's Claude Code cloud/Routines-class offerings; OpenAI's
  Codex cloud). A task-runner with **no memory, no persistent agent identity, no community/network layer** competes
  on ergonomics alone, against the model vendors themselves, while its COGS (sandbox vendor margin) and its demand
  (subscription holders) are both controlled by others. Sawyer Hood's own pitch — "you have to keep your terminal
  open. This is why we built Terragon" — was a feature-gap pitch, and the vendors closed the gap.
- DevBoxer's bet `[EV: terragon-shutdown page; homepage]`: same architecture, thinner team, higher concurrency (30),
  burst compute, "Orchestrate mode" (Claude Code advanced features for all agents), same unbundled pricing. It is a
  cost-structure/persistence bet, not a differentiation bet `[INTERP]`.

---

## 4. Module-by-module comparison vs TinyAssets

TinyAssets modules from `PLAN.md` Module Map + `openspec/specs/`. Verdict vocabulary: **COPY** (adopt mechanism
nearly as-is, TinyAssets-shaped), **LEARN** (adapt the idea), **AVOID** (explicitly do not import).

| # | TinyAssets module | They do (terragon-oss/DevBoxer) | We do | Verdict |
|---|---|---|---|---|
| 1 | **Onboarding / connect flow** (`byo-llm-connect-flow` slice 2, minimal-onboarding app) | Claude: PKCE popup on Anthropic's Claude Code client + Anthropic-hosted code page + paste-back; dual mode (subscription token vs minted API key); plan detection (`isMax`). Codex: paste `auth.json`, server refresh-validates immediately | Slice 1 = serving-binding authority only; Slice 2 (ingress) unbuilt; vault custody model designed, fail-closed | **COPY** the per-family UX shape (§5, I-1). AVOID their single-master-key custody (our per-universe vault + opaque custody refs is stronger) |
| 2 | **Providers / serving** (`provider-routing`, `credential-vault`, R2-1) | Credentials materialize as the CLI's native credential file in the sandbox; **platform `ANTHROPIC_API_KEY` fallback when user file absent** | R2-1 is *removing* exactly this fail-open ambient-fallback class; typed `ProviderAuthorityHeldError` | **AVOID** their fallback (it is the identity-leak pattern we already classified). **LEARN** their typed credential-error taxonomy (`invalid-claude-credentials`, `chatgpt-sub-required`) and always-fresh refresh-before-use |
| 3 | **Task queue / dispatch** (`daemon-runtime-and-dispatch`, `graph-execution-substrate`) | Postgres-as-queue + 4 cron sweepers + hourly stalled-task reaper; XState lifecycle with named backpressure states (`queued-agent-rate-limit`...); `reattemptQueueAt` | Dispatcher + auto-change loop; queue states largely internal; live incident class "writer hit its rate limit" surfaced as raw failure (memory: universe-writer-rate-limit) | **LEARN**: user-visible named wait-states + reaper cron + scheduled-vs-queued split. Validates our no-heavy-queue-infra instinct at real scale |
| 4 | **Sandbox / engine isolation** (P1 Concern "No OS engine sandbox"; `universe-engine-sandbox-p0` memory) | `ISandboxProvider` seam → E2B (2cpu/4GB microVM, default) / Daytona / Docker-dev / Mock; template image; pause/resume; per-task ephemeral | In-process confinement only (WebFetch-only, cwd-pin, rot-prone denylist); OS sandbox deferred | **COPY** the vendor-seam approach (§5, I-2). This is the fastest credible closure of our P1 |
| 5 | **GitHub delivery** (`community-patch-loop`, github PR effector; repo-delivery memory) | Continuous checkpoint-push with AI commits; auto-PR; `fix-github-checks` follow-up tasks; PR/issue/mention automations; check-run tracking | Patch loop generates content but the `github_pull_request` effect fails to emit (memory: repo-delivery-effect-not-emitted); delivery is end-of-run | **LEARN**: checkpoint-as-you-go (partial work always visible on the branch) + checks-feedback loop as an automation |
| 6 | **Channels / steering** (`universe-personification-and-relay`, `boundary-layer`, Slack ingress, minimal-onboarding app) | Slack mention → context harvest (thread replies + resolved names) → task; PartyKit live streaming; browser notifications; `plan` permission mode + persisted `approve-plan` | Slack Socket-Mode ingress to converse; MCP relay; no plan-approval primitive; consent context is lost across turns (memory: stateless-turn-loses-consent) | **LEARN**: (a) Slack thread-context harvesting for our ingress; (b) plan-approval persisted **on the work item** as the consent record |
| 7 | **Memory / brain** (`knowledge-retrieval-and-memory`, conversation_store) | None across tasks; only per-task session checkpoint (session jsonl → R2) for resume | Durable universe memory, wiki, session-anchored conversation store (PR #2394), 24/7 heartbeat | We are structurally ahead — **this is the moat their failure validates**. LEARN their session-checkpoint-to-object-storage for provider-session resumability across engine restarts |
| 8 | **Billing / paid market** (`paid-market-economy`, `token-architecture`, Track E) | Seat fee + metered sandbox-hours + model-on-user's-plan; passthrough SKU pricing via metered streaming LLM proxy; credits ledger + auto-reload; token-granular `usageEvents` + watermarked agg cache | Paid-market design in flight; Track E "cheapest adequate executable Internet route" reference pricing; no landed metering schema | **COPY** the unbundling + metering schema as Track E input (§5, I-3) |
| 9 | **Deploy / ops** (`uptime` module; P0 deploy-fence concern) | Serverless control plane (Vercel) + managed Postgres/Redis/R2 + vendor sandboxes: zero-container ops, control/execution planes fully split | Single-box docker compose; deploy failure = zero containers (P0 2026-08-07); Slack agent wedges | **LEARN**: control-plane/execution-plane separation — the daemon POSTing authenticated events to a stateless ingest API is the shape our slack-agent/daemon split should converge to |
| 10 | **Distribution / commons** (`wiki-commons`, `data-commons`, attribution, remix) | Waitlist/access-codes/reengagement growth ops; zero community, zero remix, zero provenance | Commons + lineage + attribution + remix is the platform thesis | Keep. Their zero-moat death is the counterfactual `[INTERP]` |
| 11 | **API & MCP interface** (`live-mcp-connector-surface`, 6-handle discipline) | MCP surface is 2 purpose-built tools (SuggestFollowupTask, PermissionPrompt) | 6 canonical handles, drift-guarded | Convergent: both keep MCP surfaces tiny and purpose-shaped. No action |
| 12 | **Local handoff** (no current TinyAssets equivalent) | `terry pull`: take a cloud task over locally with branch + session | Nothing — universes are cloud-only | **Watch/Defer**: a "pull my universe's work locally" verb is a credible future power-user feature |

---

## 5. Top-5 actionable implications

**I-1. Slice-2 connect UX: copy Terragon's per-family mechanics (Adopt — gated on Codex review).**
The exact production-proven recipe for our unbuilt `byo-llm-connect-flow` Slice 2 exists under Apache-2.0:
Claude = PKCE popup on Anthropic's own public client with the Anthropic-hosted code page and paste-back (no
platform-registered redirect URI needed — significant: the platform never appears in Anthropic's OAuth config), dual
subscription/api-key mode, post-connect profile call for plan-aware UX; Codex = `auth.json` paste with immediate
server-side refresh-validation and JWT plan parsing. Slot the tokens into **our** vault/custody model (their
single-master-key table is the part we do not copy). Smallest slice: Claude subscription mode only, one universe,
vault-stored, behind the Slice-1 serving-binding gate. *Policy caveat carried from the precedents note: the paste-back
variant is materially closer to the sanctioned `setup-token` pattern than a redirect-based login; still route through
the ask-first channel before marketing it.*

**I-2. Close the P1 engine-sandbox gap with a sandbox-vendor seam, not a bespoke sandbox (Adapt).**
Terragon's `ISandboxProvider` (E2B default / Daytona / Docker-dev / Mock) is the industry answer to exactly our open
P1 "No OS engine sandbox": rent microVM isolation, abstract the vendor, keep a Docker provider for dev. Our
`converse`/engine `claude -p` turn is a smaller workload than their full dev environment — a 2cpu/4GB E2B-class
sandbox with our existing cwd-pin/denylist *inside* it is defense-in-depth rather than the sole barrier.

**I-3. Unbundled billing blueprint for the paid market (Adapt).**
Charge for the universe (seat/subscription + metered infra-hours), let model spend ride the user's plan, and meter
platform-key usage at provider list price via a streaming usage-parsing proxy with a credits ledger + auto-reload +
watermarked aggregation cache. This is both the survival-trait billing hygiene the precedents note demands and a
concrete schema (`usageEvents`/`usage_events_agg_cache_sku`/`userCredits`) for Track E's "top-line reference price"
accounting. Their $30–60 seat + ~100–225 sandbox-hours is a live market anchor for universe pricing.

**I-4. Queue-state honesty + reaper (Adapt, applies when touching run/turn lifecycle or dispatcher).**
Named, user-visible backpressure states — especially `queued-agent-rate-limit` — plus `reattemptQueueAt` and an
hourly stalled-work reaper. This directly addresses the live "my writer hit its rate limit" failure class: the state
the user saw as a dead turn is, in Terragon's model, a first-class queue position with an explanation.

**I-5. The strategic lesson: do not drift into being a task-runner (Watch/steering input).**
Terragon executed the "cloud agents on your subscription" category best-in-class and still died of traction while
model vendors absorbed the feature. What they lacked is precisely what TinyAssets is: persistent identity, durable
memory, 24/7 heartbeat, user-built automations *as owned artifacts*, and a commons with lineage. Every future
prioritization fight between "better task ergonomics" and "deeper universe persistence/community" should cite this
`[INTERP, grounded in §3.10]`.

---

## 6. Adjacent findings worth keeping

- **Session-checkpoint-to-R2** (thread × sessionId × r2Key) is a clean pattern for resumable provider sessions across
  engine restarts — compare against our conversation_store (PR #2394) when engine-restart resume comes up.
- **Slack context harvesting** (thread replies + resolved display names folded into the task prompt) is directly
  liftable into our Slack ingress.
- **Plan-mode + persisted approve-plan** is a minimal consent primitive that survives statelessness — the pending
  record lives on the work item (cf. memory: stateless-turn-loses-consent-context).
- **`apps/isanthropicdown`**: they were so exposed to Anthropic availability they built a public status microsite.
  Our provider-outage posture (park-and-retry, chain exhaustion) should assume the same exposure.
- **Growth ops in-schema** (waitlist, access codes, reengagement emails, per-user feature flags) — a checklist of the
  boring launch machinery TinyAssets has not built.

---

## 7. Cross-provider review gate

- `initial_provider: claude` (this study). **Required reviewer: Codex** — re-check terragon-oss at `83142a17`
  (especially `claude-oauth.ts`, `codex-auth.ts`, `setup.ts`, `subscription-tiers.ts`, the proxy routes) and the
  DevBoxer pages, then verdict `approve/adapt/defer/reject` per implication I-1..I-4 in a durable artifact.
- Build/push/live work derived from I-1..I-4 is **blocked** until that review lands. I-5 is steering input, not build.
- Live Codex dispatch was deliberately not performed inside this session: the parent task constrained the run to
  read-only + one deliverable, and this artifact *is* the input the review gate consumes.

## 8. Corrections and pickup packets

**C1 — correction to `2026-08-10-subscription-platform-precedents.md` §5.** That note states "No surviving product
presents an in-product Claude OAuth login." terragon-oss shows Terragon shipped, and DevBoxer inherited, an
**in-product Claude OAuth flow** (Anthropic's Claude Code public client, PKCE, popup + Anthropic-hosted code
paste-back) `[EV: claude-oauth.ts]`. The claim should be narrowed to "no platform-registered redirect-URI login;
the surviving pattern is Anthropic-client + code-paste-back." Apply on next edit of that note.

**Pickup packet (I-1, primary):**
- Concept: per-family subscription-connect ingress (Slice 2 of `byo-llm-connect-flow`).
- Source: this note + terragon-oss `@83142a17` files cited in §3.2. Reviewer: Codex (gate above).
- Next home: `openspec/changes/byo-llm-connect-flow/` (extend tasks with Slice-2 detail) after review verdict.
- Next action: Codex review of I-1..I-4; then Slice-2 task breakdown referencing §3.2 mechanics.
- Write boundary when built: `tinyassets/credential_vault.py`, `tinyassets/api/cloud_connections.py`, new connect
  ingress module, WebSite connect page; branch `claude/byo-connect-slice2`, worktree `../wf-byo-connect-slice2`.
- Verification: focused tests + dual-family review + rendered chatbot `ui-test` + `--assert-handles` canary (no MCP
  surface change expected).
- Blockers: Slice-1 keystone (serving binding/custody) per design.md; ask-first policy caveat in I-1.
- **Why no STATUS.md row from this session:** parent task was scoped read-only + one deliverable. The packet above is
  lift-ready; the next session that touches STATUS.md should add a Codex-review row for this artifact.
- "Applies when touching" cues: provider connect/ingress, credential vault custody, engine sandbox isolation,
  paid-market pricing/metering, dispatcher/turn lifecycle states, Slack ingress.

## 9. Open questions / verification gaps

1. DevBoxer's actual deltas beyond the migration page (burst compute, Orchestrate mode, 30-concurrency) — is the
   connect flow unchanged from terragon-oss? (Docs site returns 404s on deep paths; needs a signup-path probe.)
2. Who operates DevBoxer (team undisclosed everywhere fetched) — relevant to how much weight its survival carries as
   a policy precedent.
3. HN thread id=46589735 (Terragon alternatives) — fetch 429'd twice; would add failure-analysis color and the
   competitive set users migrated to.
4. Whether Anthropic's current ToS posture treats the Anthropic-client + code-paste hosted flow differently from
   `setup-token` paste — the precedents note's ask-first channel is the resolution path, not more research.
5. Terragon's sandbox-hours→Stripe metering join (hours quota enforcement code) was not located in this pass; the
   quota may have been soft/marketing-only in the OSS snapshot `[unknown]`.

---

## Codex opposite-provider review — DEVBOXER_VERDICT: ADAPT (2026-08-10)

Adopt over the body where they conflict:
- **Slice-2 connect UX:** KEEP the family-specific wizard, immediate server-side validation,
  typed credential health, genuine-CLI handoff. For Claude, DEFAULT to the setup-token paste
  (+ API-key entry) — NOT the Terragon in-product PKCE flow: Anthropic's explicit developer
  prohibition is the most consequential evidence, and Terragon's own PKCE `state` is not
  verified app-side (CSRF/session-binding weakness). ChatGPT keeps real OAuth (green). PKCE
  upgrade only if/when sanctioned.
- **Sandbox rental:** viable as an IMPLEMENTATION of the existing engine-os-sandbox/execution-
  authority contract (never a replacement): explicit isolation class (Daytona default is a
  CONTAINER — request VM class), deny-if-unavailable, egress policy, credential confinement,
  immutable image digest, kill/revoke, budgets, receipts, §14 concurrency proof. Renting adds an
  uptime dependency — the 24/7 rule demands vendor-outage/failover evidence.
- **Stronger custody pattern than copying credential files into sandboxes:** Daytona-style
  proxy-injected, destination-scoped secrets that never enter the sandbox — prefer where CLI
  compatibility permits. Terragon's daemon DISABLES the CLIs' inner protections, making vendor
  isolation load-bearing; single master key = custody blast radius.
- **Billing:** copy the 3-meter separation + append-only events + watermarked aggregates as
  TELEMETRY feeding our integer conservation-checked market ledger — the Terragon schema lacks
  lineage/receipts/idempotency/fee-split and is not a ledger.
- **Module-table corrections recorded** (several rows understated OUR landed state: github PR
  adapter is shipped w/ consent+receipts; paid-market code substantially landed; local/host-tray
  execution is first-class; Slack thread-context + durable consent exist). "Their zero-moat death
  validates our moat" is interpretation, not causal evidence.
- Also: PartyKit = fan-out only (no durable ordering/replay); per-THREAD resumable sandboxes
  change credential-remanence + billing assumptions; mid-turn sandbox loss can lose
  uncheckpointed work (checkpoint cadence matters); the Postgres queue recipe needs atomic
  claim/idempotency/reaper-fencing before reuse.
