# Anthropic subscription structures — can a user's own cloud universe run on their Claude subscription?

Date: 2026-08-10 (research same-day; all web citations accessed 2026-08-10). Status:
**research note / evidence audit only** — no code touched. Companion to
`2026-08-10-cloud-brain-client-inference-options.md` (esp. its ADAPT addendum and
same-day freshness check, which this note extends and partially refines).

**Question:** each user has their OWN isolated universe (a cloud environment we host),
their own agent/memory/automations that they created and enabled, and brings their own
Claude subscription into it. TinyAssets never resells access, never pools credentials,
never routes one user's requests through another's credential. Is there a structure
under which this is the USER's use (like their laptop / VPS / CI) rather than the
developer "routing on behalf of users"?

**Method note (founder directive):** "don't assume they don't allow something — be sure
there is no way to do what we want and be allowed to." This note therefore audits the
sanction side as hard as the prohibition side.

**AGENTS.md gate:** research-derived finding; needs opposite-provider (Codex) review
before any build/push/live rollout based on it.

Evidence-type labels used throughout:
- **[POLICY]** explicit Anthropic policy/terms text
- **[DOCS]** official Anthropic documentation describing a supported practice
- **[ENFORCE]** observed enforcement history
- **[PRACTICE]** third-party practice, incl. informal Anthropic statements relayed by third parties
- **[INTERP]** third-party interpretation (someone else's reading, not Anthropic's words)

---

## 1. Evidence table

| # | Source (accessed 2026-08-10) | Type | Exact language | What it proves |
|---|---|---|---|---|
| E1 | code.claude.com/docs/en/legal-and-compliance | [POLICY] | "**OAuth authentication** is intended exclusively for purchasers of Claude Free, Pro, Max, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications." / "**Developers** building products or services that interact with Claude's capabilities, including those using the Agent SDK, should use API key authentication… Anthropic does not permit third-party developers to offer Claude.ai login or to route requests through Free, Pro, or Max plan credentials on behalf of their users." / "Anthropic reserves the right to take measures to enforce these restrictions and may do so without prior notice." / "For questions about permitted authentication methods for your use case, please contact sales." | The developer-side prohibition, verbatim, current. Note the two prohibited verbs are **offer** (login) and **route** (requests) — both are actions of the *developer*, not properties of the compute location. Also: contact-sales is the named exception channel. |
| E2 | Same page | [POLICY] | "Advertised usage limits for Pro and Max plans assume ordinary, individual usage of Claude Code and the Agent SDK." | Even where auth is allowed, plan limits are calibrated to individual usage — a 24/7 heartbeat is exposed on the *limits* axis regardless of the auth structure. |
| E3 | support.claude.com article 15036540 "Use the Claude Agent SDK with your Claude plan" (updated ~2026-06-16) | [POLICY] | "We're pausing the changes to Claude Agent SDK usage described below. For now, nothing has changed: Claude Agent SDK, `claude -p`, and third-party app usage still draw from your subscription's usage limits." Planned (paused) credits: Pro $20 / Max-5x $100 / Max-20x $200 / Team + Enterprise tiers. | **User-side third-party app use on subscription is currently allowed**, explicitly, including headless `claude -p`. The credit system (which would have covered third-party apps authenticating with the subscription) is paused, not cancelled. |
| E4 | code.claude.com/docs/en/authentication | [DOCS] | "For CI pipelines, scripts, or other environments where interactive browser login isn't available, generate a one-year OAuth token with `claude setup-token`… set it as the `CLAUDE_CODE_OAUTH_TOKEN` environment variable wherever you want to authenticate… This token authenticates with your Claude subscription and requires a Pro, Max, Team, or Enterprise plan." Precedence list: "`CLAUDE_CODE_OAUTH_TOKEN`… Use this for CI pipelines and scripts where browser login isn't available." | Anthropic builds and documents a **subscription credential designed to leave the login machine** and run unattended elsewhere ("wherever you want to authenticate"). CI/servers are the stated purpose. |
| E5 | Same page | [DOCS] | "If your browser shows a login code instead of redirecting back… paste it into the terminal… This happens when the browser can't reach Claude Code's local callback server, which is common in WSL2, SSH sessions, and containers." | Anthropic's own login flow is engineered for remote/containerized environments — logging in *inside* a container/SSH session is anticipated, supported behavior. |
| E6 | code.claude.com/docs/en/github-actions | [DOCS] | "`CLAUDE_CODE_OAUTH_TOKEN`: an OAuth token that authenticates with your Claude subscription, available on Pro, Max, Team, and Enterprise plans. Generate one by running `claude setup-token` locally." / quick setup: "choose between creating a long-lived token with your Claude subscription and pasting in an API key." / "If you authenticate with an OAuth token, runs use your Claude subscription instead of API billing." / "the Claude Code GitHub Action runs on GitHub-hosted runners." / cron example: "the Claude Code GitHub Action runs in automation mode on any GitHub event, including a cron schedule." | **The strongest cloud-compute precedent.** Anthropic's own product docs sanction subscription tokens executing on *third-party cloud compute* (GitHub's servers), *unattended*, on a *schedule*, deposited in a *third party's secret store*. Compute location and unattended operation are demonstrably not the line. |
| E7 | Same page | [DOCS] | "For a secret shared across repositories, authenticate with an API key… rather than an OAuth token, since an OAuth token is tied to the subscription of the person who ran `claude setup-token`." | The constraint Anthropic names is **per-person binding** — one person's token serves that person's usage. Exactly the isolation property our per-user universe has (and pooling lacks). |
| E8 | code.claude.com/docs/en/devcontainer | [DOCS] | "A dev container runs as a Docker container, either on your machine or **on a cloud host such as GitHub Codespaces**." / "Sign in to Claude Code: open a terminal in the rebuilt container and run `claude`, then follow the authentication prompt." / "To carry authentication across codespaces, store `ANTHROPIC_API_KEY` or a `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` as a Codespaces secret." | Anthropic explicitly instructs subscription sign-in **inside cloud containers hosted by a third party (Microsoft)**, including storing the subscription token in that third party's secret store. "User's cloud container" ≈ sanctioned. |
| E9 | code.claude.com/docs/en/claude-code-on-the-web | [DOCS] | "Claude Code on the web runs tasks on Anthropic-managed cloud infrastructure… in research preview for Pro, Max, and Team users." / "Claude Code on the web shares rate limits with all other Claude and Claude Code usage within your account… There is no separate compute charge for the cloud VM." | Anthropic's first-party framing of subscription-backed cloud execution: the subscription pays for *model usage wherever it runs*; the VM is incidental. |
| E10 | code.claude.com/docs/en/self-hosted-environments | [DOCS] | "A self-hosted environment executes Claude Code cloud sessions on infrastructure your organization operates." (Team/Enterprise public beta) / "Billing: sessions in a self-hosted environment consume your organization's Claude Code usage the same way sessions in Anthropic-hosted environments do." / "the session authenticates with an Anthropic-issued, session-scoped OAuth token." | Anthropic productized "subscription inference from customer-operated servers" — with a control plane, work queue, and runner fleet. The *architecture we want* exists first-party; the sanctioned custody model is notable: **Anthropic mints session-scoped tokens**, the operator never holds the user's long-lived credential. |
| E11 | anthropic.com/legal/consumer-terms (effective 2025-10-08) | [POLICY] | "You may not share your Account login information, Anthropic API key, or Account credentials with anyone else." / "You also may not make your Account available to anyone else." / prohibited: "to access the Services through automated or non-human means, whether through a bot, script, or otherwise" — "Except when you are accessing our Services via an Anthropic API Key **or where we otherwise explicitly permit it**." | The consumer-terms constraints: no credential *sharing with other persons*, no *account sharing*, and an automation ban **with an explicit-permission carve-out** — which E3/E4/E6 (documented Agent SDK / setup-token / Actions use) fill. Nothing here turns on compute location either. |
| E12 | TechCrunch 2026-04-04; VentureBeat coverage; apiyi/kersai summaries | [ENFORCE] | Anthropic (2026-04-04): subscribers will "no longer be able to use your Claude subscription limits for third-party harnesses including OpenClaw"; "applies to all third-party harnesses and will be rolled out to more shortly." Boris Cherny: "subscriptions weren't built for the usage patterns of these third-party tools"; "This is more about engineering constraints." | The April block: aimed at **third-party harnesses** (non-Claude-Code clients) and justified on **capacity/billing**, not security or location. It hit OpenClaw *running on users' own hardware* — i.e., being on the user's machine did **not** protect a third-party product. Location isn't the line in either direction. |
| E13 | VentureBeat 2026-05-13 ("reinstates… with a catch"); Zed blog; techtimes; digitalapplied | [ENFORCE] | ~2026-05-13/14: Anthropic reinstated third-party agent usage and announced the Agent SDK credit split effective June 15 — "one [pool] for using Claude through Anthropic's first-party tools… another for third-party agent and SDK usage" (Zed's description); the programmatic pool covered "the Agent SDK, the `claude -p` flag, GitHub Actions, or an external harness like OpenClaw." 2026-06-15/16: change paused (E3). | The resolution Anthropic *chose* was a **billing** mechanism that explicitly prices in third-party and unattended usage — including server-side shapes (GitHub Actions) and external harnesses. That is a sanctioning trajectory for the *usage class*, with the price as the catch. |
| E14 | docs.openclaw.ai/concepts/oauth + /providers/anthropic | [PRACTICE] | "**Anthropic staff told us this usage is allowed again**, so OpenClaw treats Claude CLI reuse and `claude -p` usage as sanctioned for this integration unless Anthropic publishes a new policy." Auth paths: "User runs `claude setup-token` on a machine with Claude Code, then pastes into OpenClaw"; "Claude CLI reuse expects the OpenClaw process to run on the same host as the Claude CLI login." Also: "For Anthropic in production, API key auth is still the safer recommended path." | Post-pause, Anthropic staff informally sanctioned a third-party product invoking the user's subscription via the real CLI / pasted setup-token — the very product they blocked in April. OpenClaw gateways commonly run on users' VPSes; no host-location caveat is made. (Informal; revocable; their own docs still hedge toward API keys for production.) |
| E15 | Search coverage of May-2026 reinstatement (dataworldbank repost of VentureBeat; groundy) | [PRACTICE] | "By explicitly allowing third-party apps like **Conductor** and OpenClaw to authenticate via the Agent SDK, Anthropic is legitimizing a workflow it had previously attempted to block." | At least two named third-party products currently operate subscription auth with Anthropic's awareness. Precedent that "previously approved"/tolerated third-party subscription integrations exist. |
| E16 | openclawlaunch.com/guides/hermes-claude-subscription | [INTERP] | "Running Claude Code yourself is fine: the policy restricts third-party services acting on your behalf, not where you run Anthropic's own CLI." / "The problem is handing the credential to someone else's harness." / enforcement detail: tokens rejected with "this credential is only authorized for use with Claude Code." | The best-articulated conservative reading: the line is **credential custody by a hosted service**, so a hosted agent vendor (Hermes) declines to offer subscription auth. NB: this is a vendor's interpretation, not Anthropic text — and its enforcement detail shows the technical block fingerprints the *client binary*, not the host. |
| E17 | code.claude.com/docs/en/agent-sdk/quickstart (per 2026-08-10 sibling-note fetch) | [POLICY] | "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK." | "Unless previously approved" is a standing, explicit invitation: approval is a defined state a product can be in. |
| E18 | August 2026 news sweep (TechCrunch 2026-08-09 auto-mode; changelogs) | [ENFORCE] | No July/August 2026 change to subscription/third-party auth policy found. The only August policy story is auto-mode-by-default (2026-08-14), unrelated. | The June-15 pause state (E3) is still the operative state as of 2026-08-10. |

---

## 2. Parsing the prohibition — what the words actually restrict

The developer-side sentence (E1) prohibits two developer actions:

1. **"offer Claude.ai login"** — the developer presenting Claude sign-in as a feature of
   *their product*. What it demonstrably does not cover: the user running Anthropic's own
   login flow in an environment the user controls (E5, E8 — Anthropic tells users to do
   exactly that inside containers/Codespaces). Unresolved: a developer *hosting* the
   environment and *initiating* Anthropic's own flow inside it (our 3a) — no text either
   way.
2. **"route requests through Free, Pro, or Max plan credentials on behalf of their
   users"** — the developer's service being the thing that carries requests on a user's
   plan credential. The words that do the work are "route… on behalf of": a service
   layer between the user and Anthropic. What it demonstrably does not cover:
   unattended execution of the user's own workload on the user's own token on rented
   compute (E6 — GitHub routes nothing; the workflow the *user configured* runs the
   *user's token* for the *user's repo*).

Three readings are textually available for our structure (isolated per-user universe,
user's own token, user-created automations):

- **Narrow (credential-brokering reading):** the clause targets pooled/brokered/resold
  access — a developer fronting many users with plan credentials as the product's fuel
  supply. Our per-user isolation escapes it. Supported by: E7 (per-person binding is the
  named constraint), E12-E13 (enforcement was billing-motivated and resolved by pricing,
  not by a custody rule), E14-E15 (products doing per-user subscription invocation are
  tolerated post-pause).
- **Custody reading (Hermes, E16):** any hosted service that takes the user's plan
  credential and executes with it is "routing on behalf of." Our cloud universe is
  inside it; only user-procured compute escapes.
- **Maximal reading:** all third-party products on subscription auth are prohibited.
  Contradicted by the current operative state (E3 "third-party app usage still draws
  from your subscription's usage limits", E14, E15) — this reading was briefly *true in
  enforcement* during April 4 – mid-May 2026 and could return, but it is not the
  current policy posture.

**Where the line has actually been drawn in practice:** every enforcement and sanction
event turned on (a) *which client* consumes the quota (the genuine `claude` binary vs. a
reverse-engineered harness — E12, E16's rejection string), (b) *who holds and applies
the credential* (the person vs. a product pooling it), and (c) *billing sustainability*
(E12 rationale, E13 remedy). **No event, in either direction, turned on compute
location.** The claim "cloud execution is prohibited per se" has no evidentiary support;
the claim "hosted third-party custody is prohibited per se" has interpretive support
(E16) but no direct Anthropic text and no enforcement instance distinguishable from the
harness/pooling cases.

---

## 3. Enforcement history — what actually got blocked, restored, and left alone

| Date | Event | What it hit / spared |
|---|---|---|
| 2025-10-08 | Consumer Terms effective (E11) | Baseline: no credential sharing, automation carve-out "where we otherwise explicitly permit it." |
| 2026-02-20 | Legal-docs clarification | Terms language made explicit that subscription OAuth tokens are for Anthropic products. No enforcement yet. |
| 2026-04-04 | Technical block (E12) | Third-party **harnesses** (OpenClaw first, "all third-party harnesses" intended) cut off from subscription quotas — including on users' own hardware. Tokens used by non-Claude-Code clients rejected ("only authorized for use with Claude Code", E16). The genuine `claude` CLI kept working everywhere: laptops, VPSes, CI, containers. **Location never appeared in the enforcement logic.** |
| ~2026-05-13 | Reinstatement + credit announcement (E13) | Third-party usage restored; June-15 credit split announced pricing third-party/programmatic usage (incl. GitHub Actions and external harnesses) into a per-plan monthly credit. |
| 2026-06-15/16 | Pause (E3) | Credit split paused. Operative state: Agent SDK, `claude -p`, third-party app usage draw from subscription limits. Anthropic staff → OpenClaw: "allowed again" (E14). |
| 2026-07/08 | No change found (E18) | Pause state persists as of 2026-08-10. |

**Answer to the risk question (task §4):** there is **no observed enforcement against
user-controlled cloud environments as such**. Enforcement hit (i) non-Claude-Code
client binaries on subscription tokens and (ii) the third-party-harness usage class as
a billing matter — the latter now reinstated pending a repriced credit system. The
OpenClaw block was client-fingerprint + usage-class, not location; the reinstatement
restored the usage class on subscription pools, with the credit system as the signaled
future rail.

---

## 4. Verdicts per structure

### 3a. User authenticates directly with Anthropic inside their own universe (we surface Anthropic's own login/device-code flow in the user's container; credential is minted between user and Anthropic and lives only in that user's isolated environment)

**Verdict: GRAY (favorable-leaning), untested.**

- For: E5 (login-in-container is anticipated, supported), E8 (Anthropic instructs
  exactly this inside Microsoft-hosted cloud containers), E6/E9 (location isn't the
  line), the credential is created by the user with Anthropic — nothing is "handed to"
  us in the E16 sense; revocation stays with the user.
- Against: "offer Claude.ai login" (E1) is the closest textual hook — a TinyAssets
  onboarding step that presents Claude sign-in is *facially* the prohibited verb, even
  if the flow is Anthropic's own. The Codespaces analogy breaks at one point: Microsoft
  hosts the container but is not the developer of the product the credential powers;
  we are both host and developer. No text resolves that difference.
- Custody-in-fact: we operate the container host, so we *could* read the credential
  even if we never do. E10 shows Anthropic's own answer to this problem in their
  first-party product: **session-scoped tokens minted by Anthropic** so the operator
  never holds long-lived credentials. No third-party equivalent exists today.
- Sibling note's freshness-check §2 called desktop client-executor "plausibly-allowed";
  3a is that argument moved into our cloud — one step further from "user's personal
  setup," one step closer to the prohibited verb. Ask-first territory.

### 3b. User runs `claude setup-token` themselves and pastes it into their universe (CI-style, user-initiated)

**Verdict: GRAY (the strongest evidenced structure today), durable only until the pause lifts.**

- For: this is the *exact mechanical shape* Anthropic documents and blesses elsewhere:
  setup-token exists for non-interactive environments "wherever you want to
  authenticate" (E4); Anthropic tells users to deposit that token in GitHub's and
  Microsoft's secret stores for unattended cloud execution, including cron (E6, E8);
  the operative policy state says third-party app usage draws from subscription limits
  (E3); OpenClaw's staff-sanctioned integration includes this precise paste flow (E14);
  the consumer-terms automation ban has the explicit-permission carve-out these docs
  fill (E11); per-person token binding — our isolation invariant — is the constraint
  Anthropic itself names (E7).
- Against: the token sits in *our* vault, which is the E16 custody reading's target and
  arguably "shar[ing] your Account credentials" (E11) — the GitHub-secret precedent
  softens but does not erase this (GitHub is neutral infrastructure; we are the
  product). And our workload (24/7 heartbeat) meets E2's "ordinary, individual usage"
  calibration head-on: this is the OpenClaw-class usage pattern the April block was
  aimed at. If the credit system un-pauses, this usage moves to a paid credit pool —
  a UX/pricing change we must be ready to absorb, not a compliance surprise.
- Note this is precisely the slice-1 `llm_subscription` binding path the sibling note's
  Codex ADAPT gated to founder/dogfood. The gate's *prohibition rationale*
  ("clearly prohibited") overstates what the evidence shows for the isolated,
  user-initiated shape; but the gate's *conclusion* (don't ship customer-facing Claude
  subscription minting without an Anthropic conversation) survives on risk grounds:
  Anthropic "may [enforce] without prior notice" (E1), the pause is explicitly
  temporary, and we'd be betting customers' accounts.

### 3c. Universe as "user's rented computer" (VPS analogy)

**Verdict: SPLITS IN TWO.**

- **User-procured compute (their VPS, their box, our Tier-2 tray / Tier-3 clone):
  ALLOWED on current evidence.** "Running Claude Code yourself is fine: the policy
  restricts third-party services acting on your behalf, not where you run Anthropic's
  own CLI" (E16 — and here the conservative reading *agrees*); OpenClaw-on-VPS is
  widespread practice under E14's sanction; E5/E8 support remote login flows. No
  Anthropic statement addresses VPS use *by name*, but every element (remote host,
  container, unattended, user-owned) is separately documented. This is
  practice-plus-composition, not an explicit sentence — labeled accordingly.
- **TinyAssets-procured compute (our hosted universe): the analogy does not carry by
  itself.** Renting the computer *from the developer whose product runs on it* is what
  every managed-service does; if the analogy alone sufficed, the "on behalf of" clause
  would be empty. The favorable distinguishing facts (per-user isolation, user-created
  automations, no pooling) are real but their sufficiency is exactly the open
  question — see §7. GRAY.

### 3d. Agent SDK credit system (paused)

**Verdict: NOT AVAILABLE (paused) — but if un-paused, it is the sanctioned rail for exactly our shape's billing.**

The announced pool covered "third-party agent and SDK usage" including GitHub Actions
and external harnesses (E13) — i.e., server-side and unattended shapes were inside the
priced-in class, not excluded. Nothing in the announcement limited it to client apps.
What it would *not* automatically resolve: the developer-side "offer login / route"
clause, which co-existed with the credit announcement. Practical meaning for us: the
credit system un-pausing converts the *billing* risk of 3b into a defined product
("your automations spend your plan's agent credit"), and its terms will likely state
the custody rules we currently have to infer. **Watch item — check 15036540 at every
build checkpoint.**

### 3e. Partnership / contact-sales ("previously approved")

**Verdict: ALLOWED by definition — the only durable, explicit sanction available; requires Anthropic's yes.**

"Unless previously approved" (E17) and "for questions about permitted authentication
methods for your use case, please contact sales" (E1) define an approval state.
Conductor and OpenClaw are named in coverage as legitimized third-party subscription
integrations (E15, E14) — informal precedent that approval-in-practice is attainable
for per-user, non-pooled shapes. No public example yet of an approved *hosted*
service — we would be asking for the unproven case, with E10 (session-scoped tokens,
operator never holds the credential) as the architecture to propose.

---

## 5. The best compliant structure for our shape

**Layered, in this order:**

1. **Compliance-max tier that needs nobody's permission (ship regardless):** the
   universe on **user-procured compute** — Tier-2 tray install or the user's own
   VPS/box — with the user's own `claude` login. This is 3c's allowed half
   (OpenClaw-equivalent), it already matches the project's Tier-2/Tier-3 surfaces, and
   it is immune to every reading of the developer clause because we never touch compute
   or credential. Cloud brain keeps state/orchestration; the user's machine registers
   as the executor (the sibling note's Option A/D device-executor lane, generalized
   from "desktop app" to "any user-controlled host"). For users who accept
   self-hosting, the Forever-Rule cost is availability-when-their-box-sleeps — the
   backbone can queue rather than execute.
2. **For the hosted cloud universe on Claude subscription: 3b now, engineered for the
   narrow reading, gated by an Anthropic ask (3e) before customer-facing launch.**
   Concretely: user-initiated `claude setup-token` paste (never a "Connect Claude"
   OAuth button we operate — that's 3a's unresolved verb); one credential per universe,
   sealed to that universe, consumed only by that user's own turns and automations
   (E7's binding invariant, enforced by the existing serving-binding admission);
   genuine `claude` CLI only (Hard Rule 3 already guarantees this — the technical
   enforcement layer fingerprints the binary, E16); cadence/concurrency caps that keep
   each universe's draw inside plausible individual usage (E2); revocation
   instructions + honest copy that this runs on the user's plan and Anthropic's policy
   controls it; kill-switch to API-key/credit-system fallback for the day the pause
   lifts. **Founder/dogfood can run this today** (Codex review's category (b), already
   the live state). **Customer-facing default remains gated** — not because the
   evidence shows prohibition (it shows GRAY), but because Anthropic enforces without
   notice against *users'* accounts, and the contact-sales channel is explicitly
   offered and cheap.
3. **Send the contact-sales inquiry now (3e)**, proposing the E10 architecture
   (session-scoped or delegated tokens; we never custody long-lived plan credentials)
   as the preferred end state, with 3b's isolation invariants as the interim. The
   paused credit system (3d) tells us Anthropic is building a sanctioned rail for
   precisely this usage class; being a known, well-shaped integration when it lands is
   the durable win.

**What the evidence does NOT force:** the conclusion that only partnership/API paths
exist. That conclusion held under the April enforcement state; it does not hold under
the current operative state (E3/E14/E15). The honest current answer is: user-side
subscription use in user-controlled environments (incl. cloud) is sanctioned; the
hosted-developer variant is GRAY with a defined ask-first channel; nothing supports
"prohibited per se."

---

## 6. OpenAI parity (brief)

- Subscription-backed third-party use: publicly endorsed (Altman, April 2026) and
  operationalized (OpenClaw Codex OAuth PKCE with manual-paste for "remote/headless
  setups" — E14 source; OpenAI help center "Using Codex with your ChatGPT plan").
  Still endorsement + practice, not contract; one analyst notes none of OpenAI's OAuth
  surfaces *formally* let a subscription pay for a third-party app's calls.
- Server-side: the official **Codex app-server** is documented for embedding —
  "Embed Codex into your product with the app-server protocol… authentication,
  conversation history, approvals, and streamed agent events," with remote/WebSocket
  deployment (experimental). Per the sibling note's Codex review: integrate via the
  official SDK/app-server (Codex owns OAuth+refresh), never raw token extraction.
- Net: OpenAI remains the green-path family for both backbone and hosted execution;
  no July/August 2026 change found. Re-verify service terms at build time (sibling
  note follow-up 3 stands).

---

## 7. What is genuinely unknown (cannot be resolved by more reading)

1. **The classification of a developer-hosted, per-user-isolated environment.** No
   Anthropic text, statement, or enforcement instance decides whether it is the user's
   use (like their CI/Codespace) or the developer's routing (like a pooled harness
   service). Every verdict above that says GRAY is gray *because of this one gap*.
   Only Anthropic can answer it — and the contact-sales sentence exists to ask.
2. **Whether "offer Claude.ai login" covers presenting Anthropic's own flow** from
   inside a product surface (3a). Untested textually and in practice.
3. **The un-paused credit system's conditions** — whether it will carry
   client/custody/location restrictions alongside pricing. Its announced scope (E13)
   suggests usage-class pricing, not structural bans, but that is inference.
4. **Durability of the informal sanctions** (E14 staff statement, E15 tolerance).
   Explicitly revocable: "unless Anthropic publishes a new policy." The Feb→Apr→May→Jun
   sequence shows both directions of movement within four months.
5. **Whether "ordinary, individual usage" (E2) will be enforced against 24/7
   per-user agents** on subscription plans even where the auth structure is accepted.
   The April rationale says capacity is the real driver; a compliant-auth heavy user
   can still be throttled or repriced.

---

## 8. Draft contact-sales inquiry (one paragraph)

> We're building TinyAssets, a platform where each user gets an isolated cloud
> environment ("universe") containing their own persistent agent, memory, and
> automations they create and enable themselves. We want each user to power their own
> universe with their own Claude subscription: the user personally generates a
> credential with Anthropic (e.g. `claude setup-token`, or signing in to Claude Code
> inside their environment), it is sealed to their single universe, and only that
> user's own turns and automations ever consume it — we never pool, resell, broker, or
> route one user's requests through another's credential, and all model calls go
> through the genuine Claude Code CLI. This looks to us like the per-user pattern your
> docs support for CI, GitHub Actions, and Codespaces, but we host the environment, so
> we want to confirm how your third-party developer authentication policy applies:
> is this structure permissible today, is there a "previously approved" path for it,
> and would you prefer an architecture where Anthropic mints session-scoped tokens
> (as in Claude Code self-hosted environments) so we never hold long-lived plan
> credentials? We're also interested in the paused Agent SDK credit system as the
> billing rail for this usage, and happy to shape our integration to whatever
> structure you'd sanction.

---

## Cross-refs

- `docs/design-notes/2026-08-10-cloud-brain-client-inference-options.md` — options
  architecture; its ADAPT addendum's "clearly prohibited (c)" applies to *pooled/
  customer-credential routing generally*; this note refines the isolated-per-user
  subcase to GRAY-with-ask-channel and does not lift the slice-1 task-1.7 gate.
- Memory: `founder-mapping-proven-live-slack`, `universe-writer-rate-limit` (writer
  capacity is the practical ceiling regardless of policy), `user-subscription-runs-the-universe`
  (product principle this note serves).
- STATUS.md: R2-1 credential fail-closed lane (custody engineering these verdicts assume).
- Watch items: support.claude.com/15036540 (credit-system un-pause);
  code.claude.com/docs/en/legal-and-compliance (developer clause wording);
  OpenAI service terms formalization.

---

## Codex opposite-provider review — STRUCTURES_VERDICT: ADAPT (2026-08-10)

Adopt these over the body where they conflict:

- **Evidence APPROVED:** the GitHub Actions / devcontainer subscription-token evidence is
  accurate (setup-tokens in GitHub Secrets, OAuth in every example incl. cron, Codespaces
  secrets). Compute location is genuinely not the boundary.
- **But the "irresolvable gap" framing is REJECTED:** Anthropic's operative DEFAULT decides the
  product case — third-party developers may not offer Claude.ai login/rate limits or route
  Pro/Max credentials for users **"unless previously approved."** Per-user isolation does not
  negate "on behalf of." So customer-facing hosted Claude custody = **approval-required by
  default**, not gray-proceed. The Agent SDK docs (stronger than the OpenClaw hearsay) expressly
  direct third-party products to API keys and say they cannot offer Claude rate limits unless
  approved.
- **Sharpened plan:** (1) build the provider-neutral user-executor tier (genuinely personal
  self-use); (2) hosted setup-token = founder-internal ONLY, no customer token intake; (3)
  obtain WRITTEN Anthropic approval before any private beta / customer connect UI; contact-sales
  inquiry is safe to send; session-scoped delegation is a proposal to pitch, not an existing
  mechanism (self-hosted environments are Team/Enterprise + Anthropic-control-plane only).
- **Codebase corrections (route to slice-1 follow-ups):** the active slice branch does not yet
  implement task 1.7 (its Claude rejection is technical role-coverage, not a compliance gate,
  provider_serving_binding.py:196); the credential vault persists recoverable CLEARTEXT with
  best-effort file modes (credential-vault spec :47) — custody sealing needed before any
  customer token could ever be taken. E18's freshness citation is invalid (dated after the note).
