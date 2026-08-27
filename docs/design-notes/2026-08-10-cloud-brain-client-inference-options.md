# Cloud brain + client inference — architecture options

Date: 2026-08-10 (research completed 2026-08-10/11). Status: **research note / options
analysis only** — no code touched. Problem statement: memory
`cloud-brain-client-inference-split`. Adjacent goals: `minimal-onboarding-android-app`,
`no-host-writer-ever-prune-all-fleets`.

Code citations are from `origin/main` @ `7b451b2c` (the local checkout is 689 commits
behind — see the grounding caveat in
`docs/design-notes/2026-08-10-minimal-onboarding-android-app.md`). Web citations carry
their access date (2026-08-10/11). **AGENTS.md gate:** this is a research-derived
finding; it needs the opposite-provider (Codex) review before any build, push, or live
rollout based on it.

---

## 0. Founder correction — the load model this note is built on

Founder, 2026-08-10 (verbatim, relayed by the lead):

> "the heartbeat is a persistent cloud agent working 24/7 on the founder's vision and
> is always building automations to run other things that would happen in the cloud so
> no I would not say the majority happens on device. just that we should utilize a
> device when one is involved in the ways that make sense."

So the architecture is **not** "client executes, server is fallback." It is:

- **Backbone (majority of LLM work, permanent): cloud-side execution on the user's own
  connected provider** — the 24/7 heartbeat agent, the automations it builds, cadence
  work, inbound Slack. This is exactly the in-flight `byo-llm-connect-flow` slice 1
  serving-binding path (`openspec/changes/byo-llm-connect-flow/design.md`). The
  platform still never pays tokens (Hard directive: no host writer ever); what the
  platform pays for the backbone is **orchestration compute** (each server-side turn is
  a `claude -p` / `codex exec` subprocess with vault-materialized credentials —
  `tinyassets/providers/base.py:373-396` materialization seam) plus **credential
  custody risk** (the slice-1 adversarial review's 5 criticals all live in this area).
- **Client offload (edge optimization, additive): when a device is actively involved**
  — the user is mid-conversation in the phone/desktop app — that interactive turn can
  execute on the device, on the user's locally-authenticated subscription. Wins: no
  server CPU/RAM for that turn, and for desktop-CLI users the credential never has to
  be deposited server-side at all *unless* they also opt into server-initiated
  surfaces (Slack/heartbeat) — which shrinks the custody surface to an explicit
  opt-in.

The question this note answers: **which client-offload shape composes best on top of
the backbone, and is it even feasible per provider family?** The feasibility crux is
provider auth policy — and it turns out to be the decisive input.

---

## 1. Provider-auth reality (the crux findings, cited)

### 1.1 Summary table

| Question | Anthropic (Claude Pro/Max) | OpenAI (ChatGPT Plus/Pro) |
|---|---|---|
| How does the CLI authenticate a subscription? | Browser OAuth via `/login`; creds in macOS Keychain / `~/.claude/.credentials.json`; long-lived token via `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` ([code.claude.com/docs/en/authentication.md](https://code.claude.com/docs/en/authentication.md), 2026-08-10) | Browser OAuth "Sign in with ChatGPT" via `codex login` (PKCE to `auth.openai.com`); tokens in `~/.codex/auth.json` or OS keyring; auto-refresh; device-code flow (beta) for headless ([learn.chatgpt.com/docs/auth](https://learn.chatgpt.com/docs/auth), 2026-08-10) |
| Agent SDK on a subscription? | **No.** Agent SDK is API-key only; docs: "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK" ([code.claude.com/docs/en/agent-sdk/quickstart.md](https://code.claude.com/docs/en/agent-sdk/quickstart.md), 2026-08-10) | Codex SDK/CLI headless (`codex exec`) runs under the same ChatGPT login; API-key mode also exists (standard API pricing) |
| Third-party app using the user's subscription? | **Prohibited and enforced.** Terms updated 2026-02-20: "The use of OAuth tokens obtained via Claude Free, Pro, or Max accounts in any other product, tool, or service is not permitted"; server-side blocking from 2026-04-04; Anthropic "does not permit third party developers to offer Claude.ai login or to route requests through Free, Pro, or Max plan credentials on behalf of their users" ([alternativeto.net](https://alternativeto.net/news/2026/2/anthropic-officially-bans-using-subscription-authentication-for-third-party-tools), [apiyi analysis](https://help.apiyi.com/en/anthropic-claude-subscription-third-party-tools-openclaw-policy-en.html), [openclawlaunch guide](https://openclawlaunch.com/guides/openclaw-claude-subscription), The Register 2026-04-06 spokesperson quote; all accessed 2026-08-10) | **Publicly endorsed, not contractual.** Sam Altman (X, April 2026) said ChatGPT Plus/Pro users can authenticate third-party harnesses (e.g. OpenClaw) with their ChatGPT account; OpenClaw ships `openclaw models auth login --provider openai-codex`; OpenAI's "Codex for Open Source" program explicitly supports OpenCode/Cline/OpenClaw-style tools. OpenAI's formal terms neither permit nor prohibit — tolerated + endorsed, not committed ([explainx.ai](https://explainx.ai/blog/openclaw-chatgpt-plus-pro-openai-anthropic-subscription-2026), [manifest.build](https://manifest.build/blog/chatgpt-plus-tokens-third-party-harnesses/), accessed 2026-08-10) |
| Mobile: third-party app executes turns on the user's subscription? | **No supported path.** Subscription access on mobile is exclusively Anthropic's own Claude apps (Code tab cloud sessions, Remote Control of a local CLI, Dispatch to Desktop). "Cloud sessions and Remote Control require a claude.ai account, so they aren't reachable with an Anthropic Console API key or from a third-party provider" ([code.claude.com/docs/en/mobile.md](https://code.claude.com/docs/en/mobile.md), 2026-08-10). No Agent SDK for Android/iOS. | **No packaged mobile path.** There is no Codex CLI/SDK for Android/iOS. The PKCE OAuth flow is technically completable from a mobile app, and OpenAI's posture suggests tolerance, but nothing is documented/supported for on-device third-party execution. Unverified gray zone — treat as "not yet." |
| What remains allowed under subscription | Claude.ai, Claude Code, Claude Desktop, Claude Cowork, used directly by the human ("ordinary use"); a user personally running the `claude` CLI on hardware they control | Codex surfaces + third-party harnesses per the public endorsement |
| Compliant third-party route | **API key** (Console, pay-as-you-go) — or a "previously approved" partnership with Anthropic | Subscription OAuth (tolerated) or API key |

### 1.2 The finding that matters most: the asymmetry cuts BOTH ways of our design

Anthropic's prohibition is written against **products**, not against locations. "Route
requests through Free, Pro, or Max plan credentials on behalf of their users" describes:

1. **Our client-offload idea on Anthropic**: a TinyAssets desktop app that invokes the
   user's locally-installed `claude` CLI is a third-party product offering claude.ai
   rate limits to its users. The openclawlaunch guide's carve-out ("running Anthropic's
   own `claude` CLI on your personal hardware is permitted as ordinary use... the
   restriction applies to third-party services taking custody of credentials and
   routing traffic") protects a *user's personal setup*, not a shipped product whose
   feature is "connect your Claude subscription." Risk level: prohibited-by-default;
   the only sanctioned door is the docs' "unless previously approved" — i.e. ask
   Anthropic.
2. **Our existing cloud backbone on Anthropic**: the byo-llm design deposits the
   user's subscription credential into the universe vault and the *server* runs
   `claude -p` with it. That is literally "routing requests through plan credentials on
   behalf of users." The technical block (tokens rejected outside Claude Code) may not
   fire — the traffic comes from a real Claude Code binary — but the ToS violation is
   the same class Anthropic enforced against OpenClaw's managed instances. **The
   compliant Anthropic BYO route for a multi-user product is an API key**, which
   collides with our current subscription-only default
   (`TINYASSETS_ALLOW_API_KEY_PROVIDERS` off — AGENTS.md § Configuration).
3. **The founder's own u-tiny** is the least-risky case (the founder is user and
   operator, personal hardware/credentials, closer to "ordinary use") — but it does not
   generalize to customers.

**OpenAI is the opposite:** subscription-backed third-party use is publicly endorsed by
leadership and operationalized by the ecosystem (Codex OAuth in OpenClaw), for both
server-held and client-local shapes — though it rests on public statements, not
contract, so it can change.

Consequence: **execution location is not the primary compliance variable — provider
family is.** Codex/ChatGPT subscriptions can back both the backbone and the offload
today; Claude subscriptions can back neither for third-party users without an Anthropic
partnership — Claude support for customers should route via API keys (and the "Other"
bucket of the onboarding flow) until/unless a partnership exists.

---

## 2. Prior art — cloud brain vs client executor

| System | Split | What we take from it |
|---|---|---|
| **OpenClaw** ([openclaw.ai](https://openclaw.ai/), [architecture writeups](https://ppaolo.substack.com/p/openclaw-system-architecture-overview), mobile-node launch 2026-06-29 [MarkTechPost](https://www.marktechpost.com/2026/06/29/openclaw-releases-ios-and-android-companion-node-apps-that-connect-a-phone-to-a-self-hosted-ai-agent-gateway/)) | Single **Gateway** process (sessions, routing, channels, tools, events) on the user's machine/server = the brain; the iOS/Android apps are **nodes/peripherals** — "not standalone AI assistants" — that give the agent eyes/ears. Inference runs where the gateway runs. Subscriptions: Codex OAuth login for ChatGPT plans; Claude subscription path killed 2026-04-04 → API keys. | The founder's "OpenClaw-like agent" reference implemented: **one brain, thin device nodes, channel-agnostic sessions.** Crucially, OpenClaw solves subscription auth by putting the brain ON the user's hardware — self-hosted, so credential use is "ordinary." TinyAssets inverts this (brain in our cloud), which is exactly what makes Anthropic-subscription compliance hard. The mobile apps also prove the phone-as-node UX: notifications, camera/mic in, agent out. |
| **Claude Code itself** ([code.claude.com/docs/en/mobile.md](https://code.claude.com/docs/en/mobile.md)) | Anthropic's own three shapes: **cloud sessions** (phone thin client → Anthropic-hosted execution), **Remote Control** (phone steers the user's local CLI session — the phone is UI, the laptop is the executor), **Dispatch** (phone hands a task to the Desktop app). | Anthropic's own product treats "phone present, execution elsewhere" as normal — the phone never executes. Remote Control is the closest sanctioned analog to our Option A (device as registered executor for its user), except the executor is the user's own logged-in desktop, not a server. |
| **Temporal-style pull workers** (general pattern; also OpenClaw's node model, and CMA self-hosted sandboxes' outbound-polling `EnvironmentWorker`) | Cloud owns durable state + a task queue; workers **register and long-poll outbound**; work is leased with heartbeats/timeouts; results post back; queue falls over to other workers when a worker vanishes. Anthropic's Managed Agents "self-hosted sandbox" is this exact shape productized: agent loop in the cloud, tool execution in a customer-run worker that polls an outbound work queue with a scoped environment key. | The proven mechanics for Option A: outbound-only connectivity (no inbound hole into the device), lease + reclaim (`reclaim_older_than_ms`), per-boundary keys, idempotent result posting. Our `conversation_store` ext_id idempotency is the matching write-side primitive. |
| **continue.dev / editor agents** | Config + identity sync in cloud; inference client-side on the developer's own keys/local models. | Evidence that "client-direct + cloud state sync" (Option B) is a normal shape for desktop dev tools; less applicable to a phone. |

Pattern library: **(i)** brain-on-user-hardware (OpenClaw) — sidesteps subscription ToS
entirely but abandons our zero-hosts-online Forever Rule; **(ii)** device-as-thin-client
+ cloud executes (Claude cloud sessions; our backbone); **(iii)**
device-registers-as-executor, cloud queues the turn (Temporal/CMA-worker; Remote
Control) — the shape Option A borrows.

---

## 3. Options

Terminology: "backbone" = server-side execution of a turn by spawning the provider CLI
with vault-materialized creds under the slice-1 serving binding
(`ProviderWorkBinding`, `allowed_operations=("converse",)`,
`engine_source=requester_local` — design.md Decisions 1–4).

### Backbone (was "Option C") — server-side on the user's connected credential

Not an option among peers; **the permanent spine.** Every surface with no device
present (heartbeat, automations, inbound Slack) requires it, and per the founder's
correction that is the majority of turns. In-flight as `byo-llm-connect-flow` slice 1
(Codex building). What this note changes about it: **(a)** the credential type per
provider family must follow §1.2 — Codex subscription OAuth is fine; Claude for
customers should be API-key (`llm_subscription` vs `llm_api_key` custody classes both
already fit the vault + serving-binding design; the API-key path additionally needs the
per-universe user-supplied-key route kept distinct from the banned host-global flag,
per the slice-3 kill-list item G); **(b)** every serving binding should carry an
**execution-location dimension** (`server` today) so the offload layer is additive,
not a rework.

- **Cost at scale:** platform pays orchestration compute per concurrent turn (a CLI
  subprocess: ~100s of MB RSS + CPU while streaming; the prod box is 1.9Gi today —
  memory `deploy-pipeline-outage-window-and-level2`), never tokens. Scales linearly
  with concurrent turns; heartbeat/automation load dominates and is schedulable
  (cadence smoothing, per-universe concurrency caps).
- **Custody:** full server-side custody for every connected user (the slice-1
  criticals' home turf). Fail-closed gate #2399 + assignment admission are the
  mitigations.
- **Latency/offline:** best availability (24/7, no device needed); latency = queue +
  subprocess spawn.
- **ToS:** OpenAI OK; Anthropic-subscription NOT OK for third-party users (§1.2) — use
  API keys or partnership.
- **Codebase:** slice 1 + slice 2 (connect UX) + slice 3 (prune), as specced.

### Option A — client-executor pull model (device registers as a worker)

The app (desktop first) registers as the **executor for its user's universe**. Cloud
brain resolves a turn exactly as today up to the sink (design.md Decision 4), but
instead of spawning a subprocess it **enqueues a turn-lease** for the universe's
registered executor; the device long-polls (outbound-only), executes via the local
CLI/SDK under the user's locally-held login, posts the result back; the brain records
it in `conversation_store` and continues (egress, memory, learning). No device online
or lease expired → fall back to the backbone if a server-usable credential exists,
else queue/nudge.

- **Cost:** removes server compute for interactive turns only — the minority (§0). Real
  win is **custody**: a desktop-only user who declines Slack/heartbeat needs *no*
  server-held credential at all; their credential never leaves the device.
- **Custody surface:** replaces credential custody with **device-executor authority**:
  a device-scoped binding (reuse `ProviderWorkBinding` shape: owner, universe,
  provider, operations `("converse",)`, budgets, expiry; `credential_reference_digest`
  becomes a device-registration/attestation reference instead of a vault record).
  New attack surface: a malicious "executor" returning forged results for someone
  else's universe → the lease must bind (universe, interlocutor, binding revision,
  lease id) and results must be accepted only from the leased device identity.
  Prompt/context flows *out* to the device — fine, it is the user's own conversation.
- **Latency/offline:** adds a hop (queue → poll → execute → post); interactive turns
  tolerate it. Device asleep = fallback.
- **Complexity:** highest — worker registry, lease/heartbeat/reclaim, result
  idempotency (ext_id = lease id slots into the existing
  `conversation_store` partial-unique `(session_id, ext_id)` index,
  `conversation_store.py:131-138`), plus a desktop app shipping a CLI-driving runtime.
- **ToS:** OpenAI: endorsed shape (this is OpenClaw-with-cloud-brain; Codex OAuth
  lives on the device). Anthropic: prohibited-by-default for a shipped product (§1.2
  item 1) — desktop offload on Claude requires Anthropic approval; otherwise
  Claude-side offload is API-key-on-device (allowed, but then custody is trivial
  anyway and the offload win is just compute).
- **Codebase mapping:** additive on slice 1 — a second executor behind the same sink:
  `execution_location=client_device` on the serving binding; a turn-lease store; an
  authenticated device-executor endpoint (WorkOS-bound device registration); no change
  to the request-capability chain up to the sink.

### Option B — client-direct model (app calls the provider itself, syncs state)

The app holds its own provider auth (its own Codex OAuth PKCE session, or an on-device
API key) and calls the provider **directly**; the cloud brain is consulted for
context (persona, memory window) before the call and receives the transcript after,
via MCP/API.

- **Cost:** same interactive-compute win as A, minus the queue infrastructure.
- **Custody/coherence:** the serious problem is not custody (credential stays
  on-device) but **brain integrity**: the turn runs *outside* the universe's
  orchestration — no server-side sink validation, no tool governance, no OS-sandbox
  seam, and the persona/tool surface must be replicated client-side and drifts. The
  agent's actions (automations, effects, wiki writes) can't be trusted from a
  client-composed turn without re-deriving authority server-side anyway. Two-channel
  coherence degrades to "sync when the app feels like it."
- **ToS:** on OpenAI, a third-party app driving Codex OAuth is the endorsed shape; on
  Anthropic, same prohibition as A. Mobile: this is the only shape a phone could even
  attempt (no CLI on Android), and it is exactly the unsupported gray zone (§1.1
  mobile row).
- **Verdict:** poor fit for a platform whose product *is* the governed universe turn.
  Acceptable only as a degraded "draft locally, commit through the brain" mode.

### Option D — hybrid: desktop = client-executor, phone = backbone

Desktop app (CLI exists on the machine) does Option A; the Android app always routes
turns through the backbone on the user's connected credential (server-side), because
no supported mobile client-execution path exists on either provider today (§1.1).
Re-evaluate the phone half if OpenAI ships a supported mobile auth surface for
third-party harnesses.

- This is Option A with an honest mobile story, and it matches the Android-app scope
  note's smallest-shippable v1 (app speaks MCP `converse`; backbone answers).

### Comparison

| | Backbone (spine) | A: pull-executor | B: client-direct | D: hybrid |
|---|---|---|---|---|
| Platform cost at scale | compute for ALL turns (dominant term regardless — heartbeat/automations) | backbone minus interactive-turn compute | same as A | same as A (desktop share only) |
| Custody surface | full server custody | opt-in custody only (Slack/heartbeat users); device-binding surface added | credential on device; brain-integrity risk instead | as A for desktop; full custody for phone users |
| Offline/latency | best availability; queue+spawn latency | +1 hop; device-presence dependent, clean fallback | lowest latency; worst coherence | as A / as backbone |
| Complexity | in flight (slice 1) | high (lease infra + desktop runtime) | medium infra, high drift cost | A + nothing new for phone |
| ToS: OpenAI sub | endorsed-tolerated | endorsed-tolerated | endorsed-tolerated | endorsed-tolerated |
| ToS: Claude sub | **prohibited for 3P users** → API-key or partnership | **prohibited-by-default** → approval or API-key | same as A | same as A |
| Needs from codebase | slices 1–3 as specced + execution-location field | turn-lease store, device registry, executor endpoint | client persona/tool replication, sync protocol | = A |

---

## 4. Recommendation

**Sequence (backbone first, offload later, per the founder's load model):**

1. **Land `byo-llm-connect-flow` slice 1 unchanged as the spine** (in flight, Codex).
   Add only one cheap future-proofing ask to the slice-1/2 review: the serving
   binding / engine assignment records an `execution_location` (fixed `server` for
   now) so the offload layer is later additive. Do not block slice 1 on anything in
   this note.
2. **Fix the provider-family compliance posture in slice 2 (connect UX):** "Connect
   ChatGPT" = Codex OAuth (subscription, endorsed). "Connect Claude" for customers =
   **API-key paste** (Console) unless/until an Anthropic partnership or "previous
   approval" exists — do not ship a customer-facing "connect your Claude Pro/Max"
   button; that is the exact thing Anthropic enforced against on 2026-04-04. The
   founder's own u-tiny on the founder's own creds is a tolerable personal-use bridge
   but not the template. This also means revisiting subscription-only-by-default
   (`TINYASSETS_ALLOW_API_KEY_PROVIDERS`) so a *user-supplied per-universe* API key is
   a first-class connect path (distinct from the banned host-global flag — slice-3
   kill-list item G already flags the separation).
3. **Then Option D (= A on desktop only), as an additive layer:** turn-lease queue +
   device-executor registration behind the existing sink, desktop app first, OpenAI
   family first (zero ToS risk). Claude-family desktop offload only behind an
   Anthropic conversation ("unless previously approved" is an explicit invitation to
   ask). Phone stays on the backbone indefinitely; the Android app ships against
   `converse` over MCP exactly as scoped in the Android note.
4. **Option B is rejected** as a primary shape (ungoverned turns break the universe
   authority model); keep it in the back pocket as a degraded offline-draft mode only.

**Why this ordering:** the founder's correction makes the backbone the dominant cost
term either way — offload never removes heartbeat/automation load — so offload is
justified by *custody reduction and interactive snappiness*, not by cost rescue. Both
of those are real but neither outranks "an agent that can reply at all" (slice 1) or
"a connect flow users can actually complete" (slice 2).

**Biggest risk:** Anthropic-side compliance of the *backbone itself* (§1.2 item 2). If
we ship customer Claude-subscription server-side serving, we are in the enforced-ban
class; if we ship Claude API-key only, Claude users get pay-per-token instead of their
subscription — a real UX/cost regression vs. the Codex path that the onboarding copy
must be honest about. Escalate to a host decision: pursue Anthropic approval, or
launch Claude support as API-key-only.

---

## 5. Unified cross-channel memory — identity sketch (design, not code)

**Today (partitioned by channel):** `session_id = f"slack:{channel_id}"`
(`tinyassets/app_ingress.py:175` on origin/main) and `converse:<universe_id>:<actor>`
(MCP path; documented contract in `tinyassets/conversation_store.py:26`). Slack and
app/chatbot conversations are separate stores; the agent cannot "remember the last
time it spoke to you no matter what the channel."

**Target identity:** one conversation per **(universe, interlocutor)**, channel demoted
to per-turn metadata.

- `session_id = conversation:<universe_id>:<principal_id>` where `principal_id` is the
  resolved platform identity (WorkOS user id / founder id), produced by the existing
  recognition seam (`app_principal_mapping.py` maps `slack:U…` → principal; MCP path
  already has the authenticated actor). **Identity resolution is the gate:** a turn
  whose sender does not resolve to a principal keeps today's channel-keyed session and
  the existing fail-closed multi-principal guard (`app_ingress.py:177-184` — memory
  only in founder-authorized 1:1 DMs). Never merge a shared-channel timeline into a
  personal conversation.
- **Channel as metadata:** add a `channel` column (e.g. `slack:D123`, `app:android`,
  `mcp:claude-ai`) to `conversation_turns`; the loader reads the unified timeline
  ordered by `turn_no` and may render channel tags into the fenced window so the agent
  can say "as you said on Slack earlier." Same additive-`ALTER TABLE` pattern the
  `ext_id` migration already uses (`conversation_store.py:120-125`).
- **Concurrent two-channel writes:** already solved by the store's primitives —
  `BEGIN IMMEDIATE` serialization + `UNIQUE(session_id, turn_no)` retry for
  interleaving (`conversation_store.py:169-210`), and the partial unique index
  `(session_id, ext_id) WHERE ext_id != ''` for stable-identity dedup
  (`conversation_store.py:131-138`). One requirement becomes load-bearing once
  channels share a session: **ext_ids must be namespaced per channel** (`slack:<ts>`,
  `app:<client_msg_id>`, `mcp:<request_id>`, `lease:<lease_id>` for Option-A results)
  so cross-channel ids can never collide in the shared uniqueness scope. Two channels
  interleave as ordinary interleaved turns — no vector clocks needed; turn order is
  arrival order at the single per-universe store, which is the honest semantics.
- **Migration:** lazy rewrite — on first resolved-principal turn, if a legacy
  `slack:<D-channel>` or `converse:<uid>:<actor>` session exists for the same
  principal, backfill-copy (or re-key) its rows into the unified session with their
  original `ts` and namespaced ext_ids; idempotent by ext_id. Non-DM slack sessions
  are left untouched until per-message actor identity exists.
- **Relation to the offload options:** all options write through the same brain-side
  store — in Option A the device posts the turn result and the *brain* records both
  sides (device never writes the store directly); in Option B this is exactly the
  coherence that degrades, another reason B is rejected.

Cross-refs: [[agent-needs-cross-turn-memory]] (the durable store this evolves),
[[cloud-brain-client-inference-split]] (the gap finding), R2-4/wiki-onboarding rows in
STATUS.md are unaffected.

---

## 6. Open questions / required follow-ups

1. **Host decision:** Claude customer path = API-key-only launch, or pursue Anthropic
   "previous approval" for subscription use? (Blocks slice-2 connect-UX copy.)
2. **Codex opposite-provider review** of this note per AGENTS.md § Project Skills
   (research-derived finding gating build work) — not yet run; route before any
   implementation lane opens.
3. Verify at build time whether OpenAI has since formalized third-party
   subscription use in its service terms (today it is endorsement, not contract —
   re-check [openai.com/policies/service-terms](https://openai.com/policies/service-terms/)).
4. Mobile: re-check for a supported OpenAI mobile third-party auth path before
   committing any phone-side execution work; today none exists.

---

## Codex opposite-provider review — NOTE_VERDICT: ADAPT (2026-08-10)

Verified/corrected findings (full verdict in session artifacts; adopt these over
the body text where they conflict):

**Compliance (Claim 1) — the a/b/c distinction, verified with sources:**
- (a) Own subscription, own machine, first-party `claude` CLI: permitted.
- (b) Founder's subscription on the founder's own server for the founder's OWN
  universe (today's dogfood): reasonably within permitted personal automation
  (Anthropic documents subscription-backed `claude -p`, scripts, CI, setup
  tokens). Keep it isolated dogfood — it is NOT evidence customer routing is OK.
- (c) Multi-user platform holding CUSTOMERS' Pro/Max credentials and routing on
  their behalf: clearly prohibited without approval.
- A desktop product invoking users' locally-authenticated Claude is GRAY/high-risk
  — server custody absence does not override the developer-product restriction.
  Seek Anthropic approval before any "Connect Claude Pro/Max" button.
- Date corrections: Consumer Terms effective 2025-10-08; 2026-02-20 was a
  legal-docs clarification; 2026-04-04 was the reported OpenClaw cutoff, not a
  terms date. Anthropic's 2026-06-15 update explicitly allows personal Agent
  SDK/`claude -p`/third-party-app use on subscription limits.

**OpenAI (Claim 2) — HIGH confidence**, but integrate via the official Codex
SDK/app-server (Codex owns OAuth + refresh); never raw token extraction; a
generic "Sign in with ChatGPT" identity login is NOT model authorization. Remove
the unsupported claim that the Codex OSS program endorses specific harnesses.

**Architecture (Claim 3) — direction approved with changes:**
- Cloud brain stays authoritative over turn ledger, context, budgets, tools,
  effects, final commit. Devices are executor CAPABILITIES behind one durable
  turn/lease queue; a device returns model output / tool PROPOSALS; the cloud
  re-authorizes and commits effects.
- Device registration is a DISTINCT registration+lease object — do not repurpose
  `ProviderWorkBinding.credential_reference_digest`.
- **"Land slice 1 unchanged" is WRONG:** slice 1 as built mints `llm_subscription`
  bindings for Claude AND Codex — for customers that creates exactly the
  prohibited (c) pathway. REQUIRED: gate Claude-subscription minting to the
  founder/dogfood identity until an Anthropic path exists; Codex minting may be
  customer-facing.
- **API-key paste for Claude CONFLICTS with `retire-mcp-provider-secret-deposit`**
  (no MCP/cloud-vault API-key intake; keys live on requester-controlled
  executors) — and requester-executor keys cannot power zero-host-online 24/7
  heartbeats. Claude's 24/7 customer route therefore needs: an Anthropic
  partnership, a provider-native delegated commercial credential, or the
  market/cloud-executor route. HOST DECISION required.

**Memory (Claim 4) — namespace approved with changes:** keep per-channel
transcripts + PROMOTED cross-channel memory with provenance/disclosure scope (a
work Slack DM must not auto-leak raw content into a personal channel); structured
`(channel_namespace, external_id)` columns (not a prefixed string — `slack:123`
vs `123` would double-represent the same message); migration keyed by
`(legacy_session_id, legacy_row_id)`; server-assigned sequence for ordering
(event-time `ts` stays metadata); `UNIQUE(session_id, turn_no)` requires
renumbering on merge; excluding multi-principal channels is correct.

**Current-code corrections:** at `origin/main@7b451b2c` MCP `converse` does NOT
read/write `conversation_store` (only Slack does) — there aren't two partitioned
durable stores yet; `load_recent()` orders by `ts, turn_no` (event-time);
`app_principal_mapping.py`'s sealed mapping is the unified-principal seam, not
the runtime actor string; `TINYASSETS_ALLOW_API_KEY_PROVIDERS` gates
Gemini/Groq/Grok, not the Claude/Codex overlay; the `base.py:373-396` citation is
the universe-vs-ambient selection seam, the materialization begins after it.

---

## Freshness check 2026-08-10 (primary sources, same-day) — supersedes stale dates above

Founder recalled Anthropic "going back and forth but still allowing it" — verified correct.
Both of these are TRUE simultaneously; the variable is WHO routes the credential:

- **User side, ALLOWED today:** support.claude.com (article 15036540): "We're pausing the
  changes... For now, nothing has changed: Claude Agent SDK, `claude -p`, and third-party app
  usage still draw from your subscription's usage limits." The April cutoff was walked back; the
  planned Agent SDK credit system ($20 Pro / $100 Max-5x / $200 Max-20x monthly, explicitly
  covering "third-party apps that authenticate with your Claude subscription") is PAUSED, not
  cancelled.
- **Developer side, PROHIBITED (current, unreversed):** code.claude.com/docs/en/legal-and-compliance:
  "Anthropic does not permit third-party developers to offer Claude.ai login or to route requests
  through Free, Pro, or Max plan credentials on behalf of their users." Developers → API keys, or
  "contact sales" for permitted-auth questions.

CONSEQUENCES (refining the ADAPT addendum):
1. Cloud backbone holding CUSTOMERS' Claude subscription creds: still prohibited → slice-1 task
   1.7 gate stands (founder/dogfood only for Claude-subscription minting).
2. Desktop client-executor for Claude is UPGRADED from "gray/high-risk" to plausibly-allowed:
   the USER authenticates via Anthropic's own CLI on their own machine; our app invokes the local
   CLI and never offers Claude login nor touches the credential — inside today's explicit
   "third-party app usage draws from your subscription" allowance. Design the device-executor
   lane (distinct lease object, cloud commits effects) with Claude-via-local-CLI as a candidate
   FIRST-CLASS route alongside Codex.
3. The paused credit system signals Anthropic is building toward SANCTIONED third-party
   subscription auth with per-plan budgets — watch for un-pause; pursue the contact-sales /
   partnership ask for "Connect Claude" when customer-facing launch nears.
4. OpenAI/Codex path unchanged (green).
