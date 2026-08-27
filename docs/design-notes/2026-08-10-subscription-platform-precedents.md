# Subscription-platform precedents — who lets users bring their Anthropic account, and how

Date: 2026-08-10 (web research same-day; all citations accessed 2026-08-10). Status:
**research note / market-precedent survey only** — no code touched. Companion to
`2026-08-10-anthropic-subscription-structures.md` (the policy/evidence audit; this note is
the MARKET side of the same question). Founder directive: "research online other platforms
that do similar things… plenty of other platforms let you use your Anthropic account to do
a lot of things."

**Our shape, for comparison:** developer-hosted cloud, one isolated "universe" per user
(their agent + memory + automations they created), running 24/7 on the USER's own
Claude/ChatGPT subscription.

**AGENTS.md gate:** research-derived finding; needs opposite-provider (Codex) review before
any build/push/live rollout based on it.

Evidence labels as in the sibling note: [POLICY] [DOCS] [ENFORCE] [PRACTICE] [INTERP].

---

## 1. The landscape in one paragraph

The market splits cleanly into four classes. (A) **Developer-hosted cloud platforms running
the genuine Claude Code CLI on the user's pasted subscription token** — Terragon (dead, for
business reasons), Depot, DevBoxer, ClawHosters — none of which has any observed Anthropic
enforcement against it, ever. (B) **Local/relay products** running genuine Claude Code on
the user's machine under the user's own login — Conductor, Zed, Happy, Omnara,
self-hosted OpenClaw — the class Anthropic has explicitly acknowledged and (in Conductor's
and OpenClaw's cases) named or informally sanctioned. (C) **Protocol reimplementations**
that called Anthropic's API directly with subscription OAuth tokens and spoofed Claude Code
client headers — OpenCode, Cline, Roo, Kilo, the OAuth→API proxy bridges — the ONLY class
ever enforced against, first technically (2026-01-09 fingerprint block), then legally
(2026-03-19 lawyers to OpenCode), then by usage-class cutoff (2026-04-04, reversed
2026-05-13, repricing paused 2026-06-15). (D) **Anthropic's own first-party rails** —
GitHub Action, Claude Code on the web, **Routines** (scheduled autonomous cloud agents on
subscription limits), Managed Agents (hosted agents, API-billed), self-hosted environments
(session-scoped tokens) — which show exactly where Anthropic is steering this demand.

---

## 2. Precedent table

Column key: **Exec** = where model-consuming execution happens. **Auth** = how the user's
Anthropic credential gets there. **Response** = observed Anthropic reaction.

### A. Developer-hosted cloud + user's subscription (our shape)

| Platform | What it does | Exec | Auth | Anthropic response | Marketing posture | Sources (accessed 2026-08-10) |
|---|---|---|---|---|---|---|
| **Terragon** (Terragon Labs) | Pioneer of cloud background coding agents: task → fresh sandbox → genuine Claude Code/Codex runs → PR. | Terragon-hosted cloud sandboxes | "Sign in… with GitHub and connect your Claude Code subscription or Anthropic API key"; repo README: "BYO Subscription & API Keys — use your existing Claude or ChatGPT subscriptions to power coding agents." Exact connect mechanism not publicly documented. | **None observed.** Operated openly ~mid-2025→Feb 2026. Shut down 2026-01-16 (service to 2026-02-09) explicitly for traction: "wasn't able to reach the level of traction needed to turn Terragon into a sustainable, long-term business." [ENFORCE-absence] | Open — subscription connect was a headline feature. | github.com/terragon-labs/terragon-oss; thetoolnerd.com "Era of Virtual Employees"; docs.terragonlabs.com/docs/resources/shutdown |
| **Depot** (depot.dev) | Remote agent sandboxes; `depot claude` creates/resumes/shares Claude Code sessions org-wide. | Depot-hosted cloud sandboxes | **User runs `claude setup-token`, pastes into Depot's secret store**: `depot claude secrets add CLAUDE_CODE_OAUTH_TOKEN` — docs recommend this "for Max plan subscribers"; API key is the alternative. Genuine Claude Code CLI. | **No public signal either way.** Live and documented as of 2026-08-10. [PRACTICE] | Quiet-open: in docs/blog, not a "use your Max sub" banner. No policy caveats in their docs. | depot.dev/docs/agents/claude-code/quickstart; depot.dev/blog/now-available-remote-agent-sandboxes |
| **DevBoxer** (devboxer.com) | Terragon's self-declared successor (hosts the "Terragon Shutdown" migration page): parallel coding agents in remote sandboxes (Claude Code, Codex/GPT-5.5, Gemini, OpenCode, Amp). | DevBoxer-hosted cloud sandboxes | Homepage: "**Connect ChatGPT or Claude subscription**." Mechanism not confirmed from public docs (likely setup-token class). | **No public signal.** Live as of 2026-08-10. [PRACTICE] | Open — subscription connect on the homepage. Notably charges for **infra separately** ($30–60/seat incl. sandbox hours) while the model runs on the user's subscription. | devboxer.com; devboxer.com/docs/resources/terragon-shutdown |
| **ClawHosters** (clawhosters.com) | Hosted OpenClaw personal-assistant instances (24/7 agent + channels + skills) — the closest thing to "hosted universe" in the wild. | ClawHosters-hosted servers (Germany) | **User pastes `claude setup-token`** "to use your existing Claude subscription (Pro or Max) to power instances, instead of paying for separate API access"; token "encrypted with AES-256 and stored on German servers." | **No public signal.** Live as of 2026-08-10. Rides on OpenClaw's post-pause informal sanction (sibling note E14). [PRACTICE] | Open in docs; framed as "personal use with existing subscription," no ToS warnings beyond "treat this token like a password." | clawhosters.com/docs/claude-setup-token |
| **Omnara** (omnara.com, YC S25) | Agent control plane: mobile/web mission control; machines = your own laptop/VM **or cloud pools** (Blaxel, Daytona, Unikraft). | Hybrid: relay to user machines, or provider-allocated cloud machines | Cloud mode: "bring your own API keys" via console model-provider credentials; relay mode inherits your local `claude` login. Subscription-in-cloud not advertised. | None observed. | Neutral — leads with control-plane value, not subscription arbitrage. | omnara.com; docs.omnara.com (machines/pools, model-providers) |
| **Hosted refusers: Hermes; OpenClaw Launch** | Managed OpenClaw hosting vendors that **decline** subscription auth: "we won't take custody of your subscription credential and route your bot's traffic through it"; cite the developer clause + "since January 2026 Anthropic has also enforced it at the API layer — subscription tokens used outside Claude Code are rejected." API-key only; self-hosting called fine. | Vendor cloud | API key only (by choice) | n/a — self-imposed | Conservative; publish their reasoning as guides. | openclawlaunch.com/guides/openclaw-claude-subscription; openclawlaunch.com/guides/hermes-claude-subscription (sibling note E16) |

### B. Local / relay / user-controlled compute (surviving, some named by Anthropic)

| Platform | What it does | Exec | Auth | Anthropic response | Posture | Sources |
|---|---|---|---|---|---|---|
| **Conductor** (conductor.build, Melty Labs) | Mac app orchestrating parallel Claude Code/Codex/Cursor agents in local git worktrees. | User's Mac | Genuine Claude Code via Agent SDK; "use an Anthropic API key or existing subscription"; app is free — "bring your own Claude or Codex subscription." | **Named in Anthropic's 2026-05-13 announcement**; coverage calls it "legitimized." Post-2026-06-15 pause: "keep using your Claude subscription in Conductor the same way you do today." [ENFORCE→sanction] | Open. | conductor.build; conductor.build/blog/claude-subscription-update |
| **Zed** | Editor with Claude Code in the agent panel via ACP (`claude-agent-acp` wraps the Agent SDK). | User's machine | `/login` in-thread → API key or Claude subscription "where supported." | Covered by the same May-13 billing announcement (Zed wrote the canonical explainer); operating normally under the pause. | Open. | zed.dev/blog/claude-code-via-acp; zed.dev/blog/anthropic-subscription-changes |
| **Happy** (happy.engineering, slopus/happy) | Open-source mobile/web client for Claude Code: CLI wrapper spawns the **real** `claude` process locally; E2E-encrypted relay server; phone renders. | User's machine (relay carries only encrypted blobs) | User's existing local Claude login; Happy never holds a usable credential. | None needed — architecture avoids the question entirely. | Open; leads with encryption/"your code never leaves your devices." | github.com/slopus/happy; happy.engineering/docs/features |
| **OpenClaw (self-hosted)** | 24/7 autonomous personal agent on user hardware/VPS. | User's own box/VPS | Post-pause: "Claude CLI reuse" (same host as `claude` login) or user-pasted setup-token; "**Anthropic staff told us this usage is allowed again**" — while their docs still call API keys "the safer recommended path" for production. | Blocked 2026-04-04 as a harness (on user hardware — location didn't protect it); reinstated ~2026-05-13; informally sanctioned post-pause. [ENFORCE both directions] | Open. | docs.openclaw.ai/concepts/oauth, /providers/anthropic (sibling note E14) |
| **Coder / Codespaces / devcontainers** | Cloud dev workspaces (org- or user-procured). | Org/user cloud workspaces | Interactive `claude` subscription login inside the workspace; Anthropic's own docs bless Codespaces + storing `CLAUDE_CODE_OAUTH_TOKEN` as a Codespaces secret. | Documented-supported (sibling note E8). [DOCS] | Neutral infra. | coder.com/blog/using-claude-code-with-coder-workspaces; github.com/coder/coder/discussions/23706; code.claude.com/docs/en/devcontainer |

### C. The blocked class — protocol reimplementation on subscription OAuth

| Platform | What happened | Dates | Sources |
|---|---|---|---|
| **OpenCode** (sst/anomalyco; 112k+ stars) | Shipped a Claude Pro/Max OAuth plugin using Claude Code's own OAuth flow + spoofed client identity. **2026-01-09:** server-side fingerprint block ("This credential is only authorized for use with Claude Code"). **2026-03-19:** PR #18186 "anthropic legal requests" — plugin removed, deprecated on npm; maintainer Dax: "we did our best to convince anthropic to support developer choice **but they sent lawyers**… appreciate our partners at openai, github and gitlab who are going the other direction." Now partners with OpenAI; community forks of the plugin exist but even OpenCode's docs say "Anthropic explicitly prohibits this." | Jan 9 / Feb 18–19 (legal-docs update) / Mar 19, 2026 | ridakaddir.com/blog/post/did-anthropic-kill-opencode-claude-subscription-ban; x.com/thdxr/status/2034730036759339100; x-cmd.com/blog/260320; opencode.ai/docs/providers |
| **Cline, Roo Code, Kilo** | Same Jan-9 OAuth block; never restored; API-key only since. | 2026-01-09 | kersai.com timeline; RooCodeInc/Roo-Code#4799 |
| **OpenClaw (pre-block) + NanoClaw, Clawdbot** | 2026-04-04 usage-class cutoff of "third-party harnesses" on subscription quotas (incl. on user hardware), one-month credit as compensation; reversed 2026-05-13 with the credit-split plan; split paused 2026-06-15. | Apr 4 → May 13 → Jun 15, 2026 | TechCrunch 2026-04-04; VentureBeat 2026-05-13; support.claude.com/15036540 |
| **OAuth→API proxy bridges** (CLIProxyAPI, VibeProxy, claude-code-proxy class) | Local proxies that convert API-key requests from tools like Factory Droid into OAuth-authenticated "Claude Code" requests. Exactly what the fingerprinting targets; community guides persist; account-ban risk documented (automated bans within ~20 min in the Jan 9–15 window, some reversed). | ongoing cat-and-mouse | saybackend.com/blog/cliproxyapi-factory-droid-byok; kersai.com |

Adjacent non-precedents: **Factory droid** (API-key BYOK only; subscription reachable only
via the proxy-bridge gray market), **Cursor/Devin/Copilot/Jules** (own billing, own models
— they answer hosted-agent demand with API/first-party economics, not BYO-subscription).

### D. Anthropic's first-party rails (what they built for exactly this demand)

| Product | Shape | Billing | Why it matters to us | Sources |
|---|---|---|---|---|
| **Claude Code GitHub Action** | Subscription token on third-party cloud (GitHub runners), unattended, cron-capable | Subscription | The sanctioned template our 3b mirrors (sibling note E6) | code.claude.com/docs/en/github-actions |
| **Claude Code on the web** | Anthropic-hosted VMs | Subscription ("no separate compute charge") | First-party proof the subscription pays for model usage wherever it runs | code.claude.com/docs/en/claude-code-on-the-web |
| **Claude Code Routines** (research preview 2026-04-14) | **Scheduled / API-triggered / event-driven autonomous agent runs on Anthropic-managed cloud** — configure prompt + repo + connectors once, it "keeps working whether or not anyone is sitting at a keyboard" | **Subscription limits**, plus daily run caps: Pro 5 / Max 15 / Team-Ent 25 runs/day; metered overage for orgs | **Anthropic's own version of our product shape** — persistent cloud automations on the user's subscription. Proves the shape is legitimate *and* shows their answer to the 24/7-limits problem: per-day run caps + overage, not a ban | claude.com/blog/introducing-routines-in-claude-code; code.claude.com/docs/en/routines; infoq.com/news/2026/05/anthropic-routines-claude |
| **Claude Managed Agents** (public beta 2026-04-08) | Composable APIs for developer-built hosted agents: sandboxes, state, memory, permissions, scheduled execution | API token pricing + session runtime fee | The rail Anthropic offers *developers* for hosted agents — i.e., their preferred answer to "TinyAssets wants to host agents" is API-billed, not subscription | claude.com/blog/claude-managed-agents; platform.claude.com/docs/en/managed-agents/overview |
| **Claude Code self-hosted environments** | Cloud sessions on customer-operated infra; **Anthropic mints session-scoped OAuth tokens** — operator never holds the long-lived credential | Subscription (org) | The custody architecture to *ask for* (sibling note E10, §3e proposal) | code.claude.com/docs/en/self-hosted-environments |
| **Cowork** (2026-01, Pro+) | Background multi-step autonomous task execution inside Claude | Subscription | First-party normalization of "my subscription runs background automations" | coverage via vellum.ai / coworkerai.io |

---

## 3. What actually distinguishes blocked from surviving

Every enforcement event since January 2026 discriminates on the same three axes — and
never on compute location:

1. **Client identity.** Blocked: reimplementations of the Anthropic API using subscription
   OAuth + spoofed Claude Code headers (OpenCode plugin, Cline, Roo, Kilo, proxy bridges).
   Surviving: everything that runs the **genuine `claude` binary or Agent SDK** under
   Anthropic's own auth flows — locally (Conductor, Zed, Happy) *and hosted*
   (Terragon, Depot, DevBoxer, ClawHosters). The Jan-9 rejection string ("only authorized
   for use with Claude Code") is a client fingerprint, not a location check.
2. **Enforcement instruments.** Server-side fingerprinting; ToS/legal-docs updates
   (Feb 18–19); **lawyers to open-source projects distributing an auth plugin** (Mar 19);
   one usage-class cutoff on capacity grounds (Apr 4) that was reversed into a pricing
   plan (May 13) and then paused (Jun 15). No instrument has targeted a hosted platform
   as such.
3. **Marketing framing correlates with enforcement.** The blocked class marketed
   subscription auth explicitly as **API-cost avoidance** ("route heavy workloads through
   your Max plan"). Survivors frame it as *account continuity* ("bring your own
   subscription", "use your existing login") and — in the strongest pattern (DevBoxer) —
   **charge separately for the infrastructure while the model runs on the user's plan**,
   so the vendor visibly isn't reselling Anthropic inference.

**Since the 2026-06-15 pause: zero observed enforcement against any
hosted-cloud + user-subscription product running the genuine CLI** (Depot, DevBoxer,
ClawHosters all live as of 2026-08-10). Also zero *explicit approval* of one — no hosted
platform appears in Anthropic's named/acknowledged set (Conductor, OpenClaw, Zed-class are
all user-machine). The hosted vendors themselves split: Depot/DevBoxer/ClawHosters do it;
Hermes/OpenClaw Launch refuse on the custody reading. That split is the market pricing the
same ambiguity our sibling note's §7 identifies.

---

## 4. Closest precedents to OUR shape, ranked

1. **ClawHosters** — hosted, developer-operated servers; persistent 24/7 personal agent
   per user; user-pasted setup-token; user's Pro/Max pays for the model. This is our
   universe shape minus the multi-automation platform layer. Alive, open about it, no
   observed enforcement. Caveats: small operator, rides OpenClaw's informal
   staff-sanction, and its custody model (vendor-encrypted token vault) is exactly what
   the conservative vendors refuse — survival ≠ sanction.
2. **Terragon (historical)** — the fullest-featured version of "developer cloud + your
   subscription," operated openly for ~9 months including through the January crackdown,
   and died of *traction*, not policy. Its Jan-16 shutdown one week after the Jan-9 OAuth
   block is, on all available evidence, coincidence (the block hit non-Claude-Code
   clients; Terragon ran the real CLI) — but treat that as [INTERP], not established.
3. **Depot** — the live, quiet, engineering-respectable version: hosted sandboxes,
   setup-token in a secrets store, API-key alternative always offered, no
   subscription-arbitrage marketing. The de-risked posture to copy.
4. **DevBoxer** — proves the Terragon shape remains commercially viable *today* with
   "Connect ChatGPT or Claude subscription" on the homepage, and models the
   infra-fee/model-on-your-plan unbundling.
5. **Claude Code Routines (first-party)** — not a third-party precedent but the strongest
   signal of all: Anthropic itself now sells "your subscription runs scheduled autonomous
   cloud agents," rate-shaped by daily run caps. Our 24/7 universe is this product's
   generalization; the caps are the calibration Anthropic considers subscription-fair.

Nobody is doing **exactly** our shape (hosted + user subscription + open-ended 24/7
automations, at platform scale) both openly and with explicit Anthropic blessing. The
class exists and survives; the blessing doesn't — for anyone.

---

## 5. Bottom line

**The market evidence converges with the sibling note's §5 and sharpens it:**

- **Safest mechanism, as practiced by every surviving hosted platform:** user-initiated
  **`claude setup-token` paste** into a per-user secret store, consumed only by the
  **genuine `claude` CLI**, one credential per user/universe, never pooled. No surviving
  product presents an in-product Claude OAuth login ("offer Claude.ai login" is the
  prohibited verb; nobody hosted tests it). Offer the API-key alternative alongside, as
  Depot/Terragon did.
- **Billing hygiene is a survival trait:** charge for the universe (compute/orchestration)
  explicitly; let the model spend visibly ride the user's plan. Never market as
  API-cost avoidance.
- **Rate-shape to first-party norms:** Routines' Pro-5/Max-15 daily-run caps are
  Anthropic's own definition of subscription-fair autonomous cloud usage. Cadence caps per
  universe in that envelope convert the E2 "ordinary, individual usage" risk from
  qualitative to benchmarked.
- **Enforcement answer:** no one has been enforced against for the
  hosted + user-subscription combination — not before the June-15 pause and not since.
  Enforcement has exclusively hit protocol reimplementation, header spoofing, and (once,
  reversed) the harness usage class on capacity grounds. But absence of enforcement ≠
  permission: the conservative hosted vendors' refusals and the sibling note's E1/E16
  reading still stand, Anthropic "may [enforce] without prior notice," and the paused
  credit split remains the signaled future rail. The ask-first channel (§3e + the E10
  session-scoped-token architecture) remains the only durable sanction — now with a
  stronger pitch: "we are the platform-shaped version of Routines; price us like it."

**Refinement fed back to the sibling note's timeline (§3):** two events precede its
2026-02-20 start — **2026-01-09** server-side client-fingerprint blocks (the origin of the
E16 rejection string, hitting OpenCode/Cline/Roo/Kilo) and **2026-03-19** legal demands
forcing OpenCode to delete its subscription-auth plugin. Both reinforce the note's core
finding (the line is client identity + custody + billing, never location) and add one hard
datum: Anthropic will use **lawyers**, not just fingerprints, against distribution of
non-Claude-Code subscription auth.

## Watch items

- support.claude.com/15036540 — credit-system un-pause (moves this whole class to a priced rail).
- Routines caps/GA terms — first-party calibration of subscription-fair autonomous usage.
- Depot / DevBoxer / ClawHosters — canaries for the hosted class; if any loses Claude
  subscription support, re-run this analysis before the next build gate.
- OpenClaw docs.openclaw.ai/providers/anthropic — the informal sanction's continued wording.

---

## Codex opposite-provider review — PRECEDENTS_VERDICT: ADAPT (2026-08-10)

Chronology CONFIRMED (Jan-9 backend OAuth rejection, Mar-19 OpenCode legal removal, Apr-4
harness-class cutoff incl. OpenClaw — NOT merely header-spoofing — May-13 reversal, Jun-15 pause;
no compute-location or hosted-genuine-CLI enforcement counterexample found). Corrections:
manual paste + genuine CLI do NOT erase "on behalf of" under the written rule; Routines' 5/15/25
is a conservative scheduled-start benchmark, not a universal permission (orgs continue via
metered extra usage; one-off runs don't count).

**FINAL RISK-GRADED LADDER (adopt):**
- **BUILD now (low risk):** provider-neutral executor+queue; customer-owned laptop/VPS execution
  (we never receive the Claude credential); API-key / Workload Identity Federation / Anthropic
  **Managed Agents** as TinyAssets-hosted customer paths; KMS/envelope-encrypted custody with
  audit + rotation/revocation + emergency disable; ONE AGGREGATE identity/concurrency/run/token
  budget PER ANTHROPIC ACCOUNT across all a user's universes (not per-credential);
  Routines-inspired scheduled-start caps + concurrency/wall-clock/token/rolling budgets;
  founder-only hosted-subscription adapter behind a fail-closed flag; SEND the contact-sales
  inquiry now (ask specifically: hosted custody, claude -p, customer-created schedules, plan
  types, volume, delegated/session-scoped tokens — request a WRITTEN answer).
- **DOGFOOD now (medium risk):** founder's sub, founder's work, founder-only env; founder
  personally generates+pastes the token; genuine `claude -p` only; tight caps, full audit,
  immediate revocation, tested API-key/disable fallback. Success ≠ approval.
- **SHIP to customers (high risk until approved):** any TinyAssets-hosted storage/use of a
  customer Claude subscription credential — including setup-token paste through genuine CLI —
  requires PRIOR WRITTEN Anthropic approval; if approved, prefer Anthropic-minted short-lived
  delegated credentials over 1-year setup-tokens. Customer defaults meanwhile: API-key/WIF/
  Managed Agents + user-controlled executors. Infra-billing separation + restrained marketing
  stay good hygiene; the written approval is the launch gate.
