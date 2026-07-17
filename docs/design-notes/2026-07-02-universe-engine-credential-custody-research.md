# Universe Engine Credential Custody — Research + Options

- **Status:** Design note — the patch-loop-s5 branch builds the engine-onboarding
  + non-ambient-gate core to this design. It is **STILL UNDER the Codex
  opposite-provider CODE-review gate** (iterating — round-17 verdict = adapt); do
  **not** read this note as having cleared that gate. (Round-17 #6 correction: an
  earlier draft circularly claimed the S5 build had already "passed the Codex
  opposite-provider review gate" — it has not; the gate is the ongoing r1–r17
  review of this very branch.) This is DISTINCT from the 2026-07-02 review of the
  research *finding* (the ToS conclusion) at the end of this note, which is a
  separate, completed artifact. Resolves the open research lane in
  `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md`
  §11 item #2 (host: "research and think about it"). The source conclusions stand:
  OpenAI prohibits API-key transfer (raw-key custody NOT-offered pending a
  provider-approved delegated path); both providers document sanctioned
  private-automation paths.
- **Author:** Navigator (Claude), 2026-07-02, from host directive same day.
- **Reads (context, not restated):** the relay-architecture note §11; PLAN
  *Daemon Platform* + *Providers* modules; `AGENTS.md` Hard Rule #3 +
  Configuration section.
- **Load-bearing finding up front (§0):** the "founder brings their **personal
  subscription** and we host it 24/7 server-side" assumption is **ToS-blocked** on
  both Anthropic and OpenAI *as a general server-side custody model*. The clean
  device-independent paths are **API key** and **self-hosted endpoint**.
  This reshapes the recommendation — read §0 first.
- **Emerging lane (2026 update — NOT built here, flag prominently):** Anthropic
  now documents **subscription-backed unattended "routines"** driven by
  **scoped trigger tokens** (a Claude Code routines/automation API) — a
  provider-sanctioned automation path that is *narrower and different* from
  "custody the founder's OAuth login." If it matures, it **may reopen a
  founder-subscription model** under scoped tokens (not raw login custody). Treat
  it as **future research**, gated by its own ToS review; do not assume "only two
  lawful 24/7 lanes" is permanent. See §0.1 for the durable link.

---

## 0. The ToS reality check (decisive — read first)

The host floated three engine sources with "none privileged." Provider terms do
privilege them, and the split is sharp:

**Anthropic (Claude Pro/Max/Team subscription) — server-side custody is prohibited.**
Anthropic's current Consumer Terms + Usage Policy (re-verify at the §0.1 links):
- Bar accessing the service through automated / non-human means EXCEPT via an
  Anthropic **API Key** (the terms carve out the API key as the sanctioned
  automated-access path).
- Bar **sharing** account login information / credentials with anyone else — so
  the platform holding + driving a founder's *personal* login is prohibited.
- Net: **an API key is the appropriate path for server-side / automated access.**
  (C7 correction: an earlier draft quoted a specific "OAuth-tokens-are-for-
  Claude-Code/Claude.ai-only" sentence verbatim; that exact wording could not be
  re-verified on the current Consumer Terms page, so it is paraphrased here — the
  API-key-exception + no-credential-sharing conclusion still holds. Freshness:
  re-check before acting.)

**OpenAI (ChatGPT Plus/Pro subscription) — same conclusion.** The
"individual use only / no credential sharing / no **using ChatGPT to power
third-party services**" restriction is stated in OpenAI's **ChatGPT Pro Help Center
article** (<https://help.openai.com/en/articles/9793128/>), **not** in the Terms of
Use / Business Terms (round-22 #5 provenance correction: an earlier draft attributed
"power third-party services" to the Terms/Business Terms; it is a Help-Center
statement — cite the exact article above). Separately, OpenAI's own **Codex CI/CD
auth guide** (<https://learn.chatgpt.com/docs/auth/ci-cd-auth>) says plainly: **"The
right way to authenticate automation is with an API key,"** and discusses
ChatGPT-subscription-auth-in-CI as an advanced workflow for **trusted private
automation**. (Round-22 #5 correction: the guide DOES explicitly require **one
machine — or a serialized job stream — per ``auth.json`` copy** (concurrent runners
sharing one ``auth.json`` race the single-use refresh-token rotation and trip
``refresh_token_reused``); an earlier draft obscured this because its quotation was
not word-for-word. Paraphrase accurately: the guide's framing is
private/trusted-automation-oriented, one-machine/serialized-per-auth.json, and it
discourages public/OSS use.)
**(round-14 #6 INFERENCE, not a verbatim quote):** from "personal/private only" +
"no public/OSS" we *infer* it is also not sanctioned for **a platform running
automation on behalf of other users** — the guide does not say that phrase
literally. Either way, Codex sanctions trusted *private* account-auth, so
the blanket "no ChatGPT automation" reading is too strong (see the Enterprise
access-token narrowing below).

> **Narrowing (Codex review 2026-07-02):** the blanket "no ChatGPT automation" is
> too broad — OpenAI *does* document **Business/Enterprise Codex access tokens for
> trusted non-interactive workflows**. That is an **org-level** path, distinct from
> a *personal* ChatGPT Plus/Pro subscription, and does not change the reshape
> conclusion (the platform still must not custody a founder's *personal consumer*
> subscription). It is, however, relevant to enterprise founders + market hosts,
> who may legitimately bring an org access token as their engine. Add durable links
> (OpenAI Codex access tokens / CI auth / terms; Anthropic legal + consumer terms).

**What this means for the reshape.** A founder's **subscription** cannot lawfully be
custodied by the platform and driven 24/7 server-side on their behalf — it is
simultaneously (a) account-credential sharing, (b) OAuth-token-in-a-third-party-
service, and (c) using a personal subscription to power a third-party service. This
holds for both providers. Among the original three host-floated sources, the
device-independent 24/7 engines are the API-key lane and the self-hosted OSS
endpoint. Anthropic Routines now adds a separate **provider-hosted,
subscription-backed cloud lane**: it can run while the founder's device is off,
is currently a research preview subject to subscription usage caps, and exposes
an API trigger protected by a per-routine scoped bearer token. That token invokes
Anthropic's routine; it does **not** authorize TinyAssets to custody the founder's
Claude login or subscription credential. The **API-key lane's lawfulness remains
PROVIDER-SPECIFIC** (round-15
#1): OpenAI's Services Agreement bars transferring a key to a third party, so
raw-OpenAI-key custody is NOT offered pending a provider-approved delegated path;
Anthropic is conditional. See the per-provider verdict in §4.2b — do not read "API
key" as a blanket sanctioned lane. The subscription-CLI path survives **only** as
the *platform's own* first-party engine
(host Jonathan's own account, on the host's own trusted infra, serialized — the
current droplet model), never resold/shared per founder.

This does not kill the reshape; it renames the sources the founder may "bring":
**bring an API key, bring an endpoint, or rent a daemon from the market.** There is
**NO platform-provided default engine for founders, and NO privileged "platform
universe"** (host correction 2026-07-02: clean slate — zero universes until users
create them): the host's own droplet subscription is *his own* account self-hosted
on his own infra (the one ToS-clean subscription case — your own sub on your own
infra), serving whatever universe(s) he creates, never a per-founder default. The
**zero-engine path is the chatbot's own LLM in-session** (interactive-only via
subagents), not a platform engine.

### 0.1 Durable first-party sources (re-verify before acting; providers revise terms)

The §0 conclusion is a **policy/legal INFERENCE** from the providers' own terms +
auth docs — NOT a verbatim provider quote. (C7: an earlier draft quoted specific
sentences that could not be re-verified on the current pages; the API-key-
exception + no-credential-sharing conclusion still follows from the terms as a
whole, but treat it as an inference and get counsel before productionizing any
subscription-adjacent lane.) Exact current sources:

- **OpenAI — Codex CI/CD auth guide** (the `CODEX_API_KEY` per-run path for headless
  `codex exec`; "API key is the right way to authenticate automation"; and the
  requirement of **one machine / a serialized job stream per `auth.json` copy** —
  round-22 #5): <https://learn.chatgpt.com/docs/auth/ci-cd-auth>.
- **OpenAI — Codex Enterprise access tokens** (`CODEX_ACCESS_TOKEN`, org-level,
  DISTINCT from a personal ChatGPT subscription AND from an API key):
  <https://learn.chatgpt.com/docs/enterprise/access-tokens>.
- **OpenAI — ChatGPT Pro Help Center article** (the "individual use only / no
  credential sharing / no powering third-party services" restriction — a Help-Center
  statement, NOT a Terms/Business-Terms clause; round-22 #5, exact article):
  <https://help.openai.com/en/articles/9793128/>.
- **OpenAI — Terms of Use / Business terms** (individual-use + no-credential-sharing
  framing; note the specific "power third-party services" phrase is a Help-Center
  statement above, not a Terms/Business-Terms clause — round-21 #5):
  <https://openai.com/policies/terms-of-use/> and
  <https://openai.com/policies/business-terms/>.
- **Anthropic — Claude routines** (the emerging subscription-backed unattended-
  automation / scoped-trigger-token lane; re-verify current shape + ToS):
  <https://code.claude.com/docs/en/routines>.
- **Anthropic — Consumer Terms of Service** (governs the SUBSCRIPTION / login lane —
  the automated-access / credential-sharing terms §0 infers the no-subscription-
  custody conclusion from): <https://www.anthropic.com/legal/consumer-terms>.
- **Anthropic — Commercial Terms of Service** (governs the **API-key** lane, per
  Anthropic — NOT the Consumer Terms; permits customers to build products/services
  on the API for their own users. The instrument for the §2b Anthropic verdict):
  <https://www.anthropic.com/legal/commercial-terms>.
  API keys are issued/managed at <https://console.anthropic.com/>.

**Two DISTINCT credential classes — do not conflate (F5b correction):**
1. A **BYO API key** (Anthropic `ANTHROPIC_API_KEY`, OpenAI `OPENAI_API_KEY` /
   headless-codex `CODEX_API_KEY`) — a per-founder key that flows through the
   **BYO-API-key vault lane**.
2. An **org-level OpenAI Codex ACCESS TOKEN** — a *different* credential
   (`CODEX_ACCESS_TOKEN`, NOT `CODEX_API_KEY`) minted for a Business/Enterprise
   org for non-interactive Codex. It is **not** the same as a personal ChatGPT
   subscription (that stays blocked) **and it does NOT flow through the API-key
   lane** — it would need its own access-token credential type + auth plumbing.
   Enterprise founders / market hosts may legitimately bring one, but it is
   separate future work, not the BYO-API-key path implemented in S5.

**Resolved self-contradiction (F5c):** there is **NO founder-facing platform
default engine** — a founder brings their own (BYO key / endpoint / market /
own-device daemon). The *only* platform-held subscription is the **host's own
droplet subscription**, which serves **only the host's own universe(s)** on the
host's own infra (Option E, process-global) — it is never a per-founder default
and never flows through the founder vault.

### 0.2 Phase-1 vs Phase-2, and the enforcement scope

**Phase split (host: "build execution first").** Phase-1 S5 ships only the
**non-ambient GATE + honest declaration + no-fake-capability + no-plaintext-
through-chat**. The REAL executable onboarding lane — an out-of-chat,
founder-authenticated secret deposit returning an opaque credential *reference*,
a real KMS-encrypted per-tenant vault, and a real executor — is **Phase 2**. In
Phase 1 the executable BYO path is DARK end-to-end: `set_engine` refuses a raw
key through the chatbot, `resolve_engine_binding` never binds a BYO key, and the
env overlay injects nothing. The `TINYASSETS_BYO_VAULT_ENCRYPTED` flag is gated
behind a **code-backed encryption-capability attestation** that returns False
until Phase-2 lands, so no flag flip can unlock plaintext-key deposit+execution.

**⚠ The non-ambient gate is Phase-1 SCAFFOLDING — it does NOT yet fully prevent
ambient execution at every boundary. `TINYASSETS_NON_AMBIENT_WORK` MUST stay OFF;
flipping it ON is unsafe until Phase 2 closes the execution-boundary gate.** The
gate today lives only in the cloud-worker supervisor (`cloud_worker.py`), and the
provider router still permits ambient execution whenever BYO is dark / no
universe context is threaded / the universe is unbound / the role is non-writer.
The COMPLETE guarantee requires (a) **S3's universe-context threading** so
`run_branch` / `converse` / version / resume carry authoritative universe
identity to the router, plus (b) an **all-roles router gate that fails closed
when a FOUNDER universe is unbound** (the host's OWN universes legitimately use
the droplet subscription, so the gate must distinguish founder-vs-host). Both are
**Phase 2**; S3's context threading is not on this branch, so the full
router-execution gate is deliberately NOT built here.

**Enforcement scope — writer-role only (Phase-1 tightening applied).** What IS
enforced today: a BYO-bound universe's **writer** never borrows platform provider
auth (the writer-binding constraint, centralized + fail-closed). A "writer route"
is `role == "writer"` OR any role NOT in `FALLBACK_CHAINS` (an unknown role aliases
to the writer chain — `model_hint` is user free-form — so it must be enforced too.
**(round-14 #6 correction:** an earlier draft said `model_hint` is *whitelisted* at
the write surface; it is NOT — r11 #5 deliberately RESTORED free-form stored
`model_hint`, and the security invariant lives at the shared ROUTER boundary, which
classifies any unknown role as a writer route.) Judge/extract calls may
still use platform capacity — the judge/extract fallback chains have no claude-code
entry, so a claude-only BYO universe would have an EMPTY judge chain and could not
evaluate at all. Per-universe judge/extract routing is Phase-2 work.

---

## 1. Part A — the existing substrate (what's already built)

The custody machinery is **~70% present** — this is recomposition, not greenfield.

### 1.1 Local-operator secrets (platform-global, not per-tenant)
`scripts/load_secrets.sh` + `scripts/secrets_keys.txt` pull a **fixed set of
operator secrets** (Cloudflare, DigitalOcean, one `OPENAI_API_KEY`, `GH_TOKEN`)
from a vault (`TINYASSETS_SECRETS_VENDOR` = `1password` default / `bitwarden` /
`plaintext`), keyed by a single vault collection `"tinyassets"`
(`load_secrets.sh:44-45`, `secrets_keys.txt:6-9`). This is **one global identity for
the operator**, not a per-founder store. `secrets_keys.txt:11-13` explicitly excludes
CI secrets and is "only the keys a human operator needs on their own machine." **Not
the substrate for per-tenant engine creds** — it is the ops toolbox.

### 1.2 The droplet's shared subscription home (single-tenant by construction)
`deploy/compose.yml:47-52,166-167` sets **one** `CODEX_HOME=/data/.codex` and **one**
`CLAUDE_CONFIG_DIR=/data/.claude`, shared by the daemon and all four workers on the
`tinyassets-data` volume. `deploy/docker-entrypoint.sh:105-171` seeds them first-boot
from `TINYASSETS_CODEX_AUTH_JSON_B64` / `CLAUDE_CODE_OAUTH_TOKEN` /
`TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64`, never clobbering a rotated in-place token.
`deploy/codex-flock-wrapper.sh:26-51` serializes Codex's single-use refresh-token
chain across containers with an exclusive `flock` (OpenAI issue #10332 class).

This is **the platform's ONE subscription**, single-tenant. PLAN *Daemon Platform*
confirms the intent: *"Host subscription auth can fan out to multiple same-provider
workers … two Codex workers sharing `CODEX_HOME=/data/.codex` and two Claude workers
sharing `CLAUDE_CONFIG_DIR=/data/.claude`; no second subscription or per-worker auth
home is required."* **What breaks at N founders:** the whole model assumes one auth
home per provider. N founders' separate subscriptions on one droplet would need N
isolated `CODEX_HOME`/`CLAUDE_CONFIG_DIR` dirs, N flock domains, and per-request
selection of which one to use — and per §0 it is ToS-blocked anyway. So the droplet
subscription home stays the host's *own* self-hosted engine for whatever universe(s)
the host creates, not a per-founder container and not a founder default (there is no
privileged "platform universe" — clean slate until users create universes).

### 1.3 The per-universe credential vault (already exists, READ-wired)
`tinyassets/credential_vault.py` is a **per-universe** secret store — this is the real
seam for BYO engine creds:
- One `.credential-vault.json` per universe dir (`credential_vault.py:16,21-23`),
  written atomically at `0o600`, dir at `0o700` (`:119-127,54-56`).
- Typed records: `social` / `llm_subscription` / `vcs` (`:18`).
- Resolvers materialize per-universe `CODEX_HOME` from `auth_json_b64`
  (`ensure_codex_home_from_vault`, `:236-261`), a per-universe `CLAUDE_CONFIG_DIR`
  and `CLAUDE_CODE_OAUTH_TOKEN` (`:297-328`), and per-destination GitHub tokens
  (`resolve_github_token`, `:173-195`).
- **READ path is wired into the providers:** `providers/base.py:100-114`
  `subprocess_env_for_provider` → `credential_vault.apply_provider_auth_env`
  (`:367-381`) overlays per-universe auth onto the subprocess env, and
  `codex_provider.py:129` / `claude_provider.py:71,156` call it on every CLI
  invocation. So a per-universe engine credential **already flows to the CLI
  subprocess today**, if a vault exists and the universe is resolved.

**Two gaps in the existing vault (both material to this research):**
- **(a) At-rest = encoding, not encryption.** Secrets are stored **base64** in
  plaintext JSON (`_secret_value` decodes `token_b64`/`secret_b64`, `:159-170`;
  `auth_json_b64` materialized verbatim, `:247-252`). `0o600` + `0o700` is the only
  barrier. **No envelope encryption, no KMS, no per-tenant key.** Droplet root or a
  path-traversal read = every universe's creds in cleartext. Base64 is obfuscation,
  not protection (cf. the JADEPUFFER agentic-ransomware class that harvests exactly
  base64'd creds).
- **(b) No WRITE surface.** `write_credential_vault` (`:107-141`) exists as a library
  primitive but **nothing calls it** from universe creation or any MCP action (grep:
  zero call sites in `tinyassets/api/`). There is no user-facing way for a founder to
  *deposit* an engine credential yet. The vault is a wired reader with no filler.

### 1.4 Per-universe engine binding (the attach points)
- **Config side:** `tinyassets/config.py` `UniverseConfig.{preferred_writer,
  preferred_judge,allowed_providers}` (`config.py:29-53`) loaded from
  `{universe}/config.yaml`, consumed by `providers/router.py:263-297` (preference)
  and `:277-302` (allowlist). **But** `_action_create_universe` writes **no**
  config.yaml today (relay note §4), and the router reads it from a **process-global
  singleton** `runtime.universe_config` (`router.py:183-187,265`).
- **Runtime side:** `_action_daemon_summon` (`api/universe.py:1783-1822`) carries
  `provider_name`/`model_name` into `summon_daemon` → a `runtime_instance` row. **This
  is where a per-founder credential *reference* attaches** — the runtime_instance
  metadata is the natural home for a `credential_ref` (vault entry id / KMS key alias),
  keeping the secret out of the row and out of public state.

### 1.5 The multi-tenant resolution gap (Gap A — directly blocks custody)
Both the engine selection (`runtime.universe_config` singleton, `router.py:265`) and
the credential resolution (`apply_provider_auth_env` reads the **process-global**
`TINYASSETS_UNIVERSE` env, `credential_vault.py:360-364`) are **process-global**.
Correct for a single-universe daemon; **wrong for the shared MCP server** where one
process serves many universes. Until per-request universe context is threaded to
*both* the router and the vault resolver, the server literally cannot pick the right
founder's engine or the right founder's creds per call. **Credential custody is
downstream of fixing Gap A** — no isolation design works while the selector is a
global env var.

### 1.6 Auth principals already exist
`tinyassets/auth/provider.py` has the WorkOS resource-server path
(`:1112-1119`, `WorkOSAuthProvider`) — the founder principal (§11 rule #3 "principal
b"). The relay note's Gap B (Codex CRITICAL) is that the **universe intelligence** is
a *daemon-class* actor with no user-OAuth token; it needs a non-user auth path
evaluated before user-OAuth scope gating. Credential custody and daemon-actor auth
are the same knot: the intelligence must (i) authenticate as a non-user principal to
*act*, and (ii) hold the founder's engine creds to *think*.

---

## 2. Part B — external best practice (cited, freshness 2026-07-02)

- **BYO-API-key custody is the industry-standard 24/7 pattern.** Braintrust encrypts
  provider API keys with **AES-GCM**; the consensus best practice is **AES-256-GCM +
  a KMS (AWS KMS / HashiCorp Vault)**. Warp keeps BYO keys **on-device only** (OS
  keychain) — viable for a *local-app* engine, but incompatible with the hard "runs
  without the founder's device on" requirement, so it is out for the hosted path.
- **Per-tenant envelope encryption is the multi-tenant isolation standard.** DEK per
  tenant, wrapped by a per-tenant KEK/CMK in KMS; **encryption context** binds
  ciphertext to a tenant so tenant A's context can't decrypt tenant B's data even on a
  shared key. One CMK per tenant is the cost-conscious default and keeps blast radius
  per-tenant.
- **Static keys are becoming optional.** Anthropic now supports **Workload Identity
  Federation** for the Claude API (OIDC IdP → Claude API, no stored `sk-ant-…`). This
  is the *strongest* option for the platform's own engine and for a founder on
  BYO-cloud (their IdP federates to their Claude API) — no long-lived secret to
  custody at all.
- **"Maybe GitHub secrets handles this" — wrong tool.** GitHub Actions secrets are
  **CI-scoped**: injected into workflow runs, not a runtime API for a 24/7 daemon to
  fetch a specific founder's key per request. `secrets_keys.txt:11-13` already draws
  this line ("GitHub Actions secrets are out of scope … they stay in repo settings").
  The correct runtime analog is a **secret manager / KMS with per-tenant scoping**
  (Vault, AWS Secrets Manager + KMS, Infisical/OpenBao for the OSS-cloner story). The
  project already ships a vendor-abstracted secret loader (`load_secrets.sh`, 1Password/
  Bitwarden/plaintext) — the runtime store should mirror that vendor-agnostic shape,
  not bolt onto CI.

---

## 3. Options matrix — per engine source

Legend: 24/7-no-device = runs with the founder's computer/phone off. Blast radius =
what a droplet compromise exposes.

| Engine source | Where creds live | 24/7 no-device | Multi-tenant isolation | Blast radius (droplet pwned) | ToS / legal | Impl cost |
|---|---|---|---|---|---|---|
| **A. Founder subscription (Claude/ChatGPT CLI)** | would need per-universe `CODEX_HOME`/`CLAUDE_CONFIG_DIR` + OAuth tokens | **Yes technically** | per-universe auth home (exists) | one auth home per founder, cleartext OAuth | **BLOCKED** — §0 (account-sharing + OAuth-in-3rd-party + power-3rd-party-service, both providers) | n/a — don't build |
| **B. Founder API key** — verdict is PROVIDER-SPECIFIC (round-15 #1), not one blanket "sanctioned" claim | per-universe vault, **KMS-wrapped** | **Yes** | per-tenant DEK + encryption context | one founder's key **iff** per-tenant key; all keys iff shared/base64 (today) | **OpenAI: NOT-OFFERED.** The OpenAI **Services Agreement prohibits transferring API keys to/from third parties**; the project-key article (5008148) covers *intra-org* collaboration, NOT handing a key to TinyAssets. Consent+encryption+spend-limits do NOT cure this — it needs a **provider-approved delegated/service path** (an OpenAI-sanctioned OAuth/service-account flow) or explicit legal approval first. **Anthropic: CONDITIONAL** — a raw key grants account access (support 9767949); requires dedicated key + consent + spend limits + legal review (see §4.2b). Template = the GitHub App path (delegated, provider-sanctioned). | Med — Anthropic conditional lane; OpenAI raw-key deferred pending a delegated path |
| **C. Self-hosted OSS endpoint (Ollama/vLLM/`ANTHROPIC_BASE_URL`)** | vault holds **endpoint URL + bearer token**, not model creds | **Depends on founder's host** being up | endpoint+token per universe | one endpoint token (low-value; founder's infra) | **CLEAN** — no provider account shared; provider-agnostic base-url already in PLAN | Low — endpoint+token is a thin vault record; router needs base-url binding per universe |
| **D. BYO-cloud / Workload Identity Federation** | **no stored secret** — OIDC federation to founder's cloud LLM | **Yes** | per-founder OIDC trust | **nothing** — no long-lived secret at rest | **CLEANEST** — no key custody at all | High — federation plumbing; forward-looking, not MVP |
| **E. Host's-own subscription (NOT a founder default)** | droplet `/data/.codex` + `/data/.claude` (exists) | **Yes** | host's own account, serving ONLY the host's own universe(s) — never a per-founder default | host's own account only | **OK** — first-party, host's own account/infra (§0) | Zero — already live |

---

## 4. Recommendation

**Adopt a BYO-engine custody model; the "founder brings an engine" lanes are
API-key, self-hosted-endpoint, and market-rented daemon. There is NO platform-
provided default engine for founders (host correction 2026-07-02).**

1. **Zero-engine path (bring nothing) = the chatbot's own LLM in-session, NOT a
   platform engine.** A founder who assigns no engine has no persistent universe
   intelligence; they interact via the **chatbot**, whose own LLM (host client's)
   runs the work via subagents — interactive only, no 24/7, no app-route. The
   host's droplet subscription is the host's *own* self-hosted account, serving
   whatever universe(s) *he* creates, never a founder default (no privileged
   "platform universe"; clean slate). (Corrects the earlier "platform subscription is the default engine"
   framing; "assign an LLM at creation" has no free default — it upgrades you from
   chatbot-in-session to always-on.)

1b. **Market-rented lane (host enrichment, relay note §12).** A founder who wants
   24/7 without BYO-engine or self-hosting sets their universe to run at the current
   market rate (e.g. "GLM 5.2") with a spending cap; a market host runs *their own*
   engine legally and gets paid. The platform never custodies the founder's creds —
   the clean sidestep to the whole ToS problem.

2. **BYO-hosted lane — Option B (API key). The verdict is PROVIDER-SPECIFIC — there is
   NO blanket "sanctioned" claim (round-15 #1 critical correction).** A founder-supplied
   key would be stored in the per-universe vault **under envelope encryption** (§5),
   resolved per-request off the universe's `credential_ref`, and **requires relaxing
   `TINYASSETS_ALLOW_API_KEY_PROVIDERS` per-universe** (§6). But whether it is LAWFUL to
   custody at all depends on the provider's own transfer terms — decide per provider,
   below.

2b. **Per-provider custody verdict (round-15 #1 rewrite — provider-by-provider, not one
   blanket claim). The clean, provider-sanctioned template is the DELEGATED path
   (GitHub App: the provider issues a scoped, revocable token to the platform — the
   founder never hands over a raw key). Measure each provider against that.**
   - **OpenAI — raw API-key custody is NOT OFFERED (pending a delegated/service path).**
     The [OpenAI Services Agreement](https://openai.com/policies/services-agreement/)
     **prohibits transferring API keys to or from third parties**. The project-key
     article (help.openai.com/en/articles/5008148) covers **intra-organization**
     collaboration — sharing a key *within* your own org — NOT handing a key to
     TinyAssets, a third party. So consent + encryption + spend-limits do **not** cure
     it: raw-OpenAI-key custody needs a **provider-approved delegated/service path**
     (an OpenAI-sanctioned OAuth / service-account flow, the GitHub-App analogue) OR
     explicit legal approval. **Mark it NOT-OFFERED until such a path exists; do not
     build the raw-key lane for OpenAI.** (The personal-*subscription* prohibition in
     §0 is unchanged; the Business/Enterprise **Codex access-token** path in §0.1 is a
     separate, provider-sanctioned org flow — that IS a delegated-style path.)
   - **Anthropic — CONDITIONAL (re-evaluated via COMMERCIAL Terms, round-17 #6).**
     Anthropic states that **API keys are governed by its Commercial Terms of
     Service** ([Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)),
     **not** the Consumer Terms that govern the subscription/login lane (§0). This
     matters: the Consumer-Terms framing an earlier draft leaned on is the WRONG
     instrument for the API-key lane. The Commercial Terms permit a **customer to
     build products and services that use the API to serve THEIR OWN users** — so a
     platform custodying a founder's API key to power that founder's universe may be
     **MORE viable** under Commercial Terms than the Consumer-Terms framing implied.
     This is **not** a green light. Anthropic still warns an uploaded API key
     **grants account access** ([API-key best practices](https://support.anthropic.com/en/articles/9767949-api-key-best-practices-keeping-your-keys-safe-and-secure)),
     and the load-bearing open question is the **contracting-party / agent
     relationship**: is TinyAssets the Anthropic *customer* (contracting in its own
     name, serving founders as its users) or the founder's *agent* (the founder is
     the customer)? That must be **resolved by legal counsel before this becomes
     implementation authority** — it is not settled by this note. Before
     productionizing it still requires: **(a)** a dedicated key (never a personal
     all-scopes key), **(b)** explicit founder **consent** at deposit, **(c)** per-key
     **spend limits**, and **(d) legal review** of the contracting-party
     question above. Label any "sanctioned" reading an INFERENCE, not a provider
     endorsement. (Custody remains DEFAULT-DENY in code — `credential_vault.
     sanctioned_custody_services()` is empty until this legal question resolves.)
   - **Others (Gemini / Groq / xAI)** — state each per its own current terms before
     offering; do not assume the Anthropic verdict transfers. (Not researched here.)
   This converges with the credential vault's provider-generic model: the vault offers
   only credential KINDS that are legal per provider, and each provider's registry entry
   declares its own sanctioned custody path — raw-key where the provider permits it,
   delegated-token where it doesn't.

3. **BYO-endpoint lane — Option C, for OSS / privacy / cost.** Founder points the
   universe at their own `OLLAMA_HOST` / `ANTHROPIC_BASE_URL` + a bearer token. The
   platform custodies **an endpoint + token, not a model account** — low blast radius,
   ToS-trivial, and it satisfies the OSS-cloner and privacy stories. Availability is
   explicitly the founder's responsibility (their host up = engine up); the platform
   surfaces "engine unreachable" honestly (Hard Rule #8, never fake success).

4. **Do NOT build Option A (founder subscription custody).** It remains ToS-blocked on
   both providers. A founder may use a **local-app / on-device relay**, or—where
   Anthropic Routines is available—configure a provider-hosted routine and delegate
   only its per-routine scoped bearer trigger token. Routines are a research preview,
   consume the founder's subscription allowance and are subject to plan caps; they are
   device-independent because Anthropic executes them in its cloud. This is a distinct
   delegated execution lane, **not permission for TinyAssets to store or drive the
   founder's Claude login/OAuth credential**. Say that boundary plainly at engine-
   assignment time rather than silently degrading.

5. **Put Option D (Workload Identity Federation) on the roadmap, not the MVP.** It is
   the strongest end-state (zero secret at rest) but needs OIDC federation plumbing.
   Track it as the eventual replacement for stored API keys, especially for the
   platform's own engine.

**One-line version (F5 corrected):** *founders bring an **API key** or an
**endpoint** (or run the daemon on their own device); there is **NO founder-facing
platform default engine** — the host's own droplet subscription serves **only the
host's own universe(s)**, never a per-founder default; and nobody's personal
subscription gets custodied server-side.*

---

## 5. Multi-tenant credential isolation design (for the B/C lanes)

Target the failure the current vault has (§1.3a): today a droplet compromise yields
every universe's creds in base64. The isolation design:

1. **Fix Gap A first (hard prerequisite).** Thread the resolved `universe_id` from the
   request/actor context to *both* the router's engine selection and the vault's
   credential resolver. Retire the process-global `TINYASSETS_UNIVERSE` +
   `runtime.universe_config` singleton for the shared MCP server (keep it only for the
   single-universe daemon process). Without this, isolation is theatre.

2. **Per-tenant envelope encryption at the vault boundary.** Replace base64 with:
   DEK per universe → encrypt secret with AES-256-GCM → wrap DEK with a per-tenant KEK
   in the secret manager/KMS → store only the wrapped DEK + ciphertext + **encryption
   context = {universe_id, founder_id}** in `.credential-vault.json`. Decrypt only
   inside `subprocess_env_for_provider`, only for the resolved universe, only long
   enough to build the subprocess env. Encryption context makes a stolen ciphertext
   useless without the matching tenant context even on a shared KEK.

3. **Vendor-agnostic secret backend, mirroring `load_secrets.sh`.** Support a KMS/
   Vault vendor for the hosted droplet **and** a local/OSS backend (OpenBao/Infisical,
   or age/sops with a host key) so the Tier-3 OSS cloner isn't forced onto AWS. The
   `credential_vault.py` resolver API stays the seam; the backend is swappable behind
   it. Never a committed plaintext file (mirrors the existing vault-first posture).

4. **`credential_ref`, never the secret, on the runtime_instance row.** `summon_daemon`
   records a `credential_ref` (vault entry id + KMS key alias) in runtime_instance
   metadata (`api/universe.py:1808-1817`). Public state, run receipts, and
   `get_status` reference only the **non-secret summary** already returned by
   `write_credential_vault` (`credential_vault.py:136-141`) — count/types/services,
   never values.

5. **Blast-radius containment.** Per-tenant KEK ⇒ compromising one founder's context
   exposes one founder, not the fleet. Decrypt-just-in-time + never-persist-decrypted
   ⇒ memory-scraping window is one subprocess spawn. Keep the `0o700`/`0o600` posture
   as defense-in-depth under the encryption, not instead of it.

6. **Write surface = a consent-gated MCP action, founder-WorkOS-authenticated.** Wire
   `write_credential_vault` behind a new deposit action authorized by the **founder's
   WorkOS principal** (§11 rule #3 "principal b"), never by the relay/chatbot. Deposit
   is a founder-only, first-party act (consistent with the 2026-07-02 personification
   finding that behavioral/credential trust can't ride on a connector tool result).

---

## 6. Reconciliation with Hard Rule #3 + subscription-only posture (flagged)

- **Hard Rule #3 ("No API SDKs for the *primary writer*").** The rule scopes the
  **primary writer** to CLI subprocesses (`claude -p` / `codex exec`) — it is about not
  routing the *writer* through provider SDKs, not a blanket ban on API keys. The B lane
  keeps CLIs where the platform's own engine writes, and uses **API keys as the
  engine-auth for a founder's BYO engine** (many CLIs, incl. Codex, accept an API key;
  `ANTHROPIC_BASE_URL` + key drives the OpenAI-compatible path). **Recommendation: keep
  Hard Rule #3 as-is for the *host's own self-hosted writer*; explicitly document that a
  *founder's BYO engine* may be API-key-authenticated.** If a founder's API-key engine
  must be reached via SDK rather than CLI, that is a genuine amendment to Rule #3 and
  needs host sign-off — flag, don't assume.

- **Subscription-only-by-default (`TINYASSETS_ALLOW_API_KEY_PROVIDERS`).** Today this is
  a **process-global** gate (`providers/base.py:72-74`; stripped in
  `docker-entrypoint.sh:72-81`; `compose.yml:54` sets it `"0"`). The B lane needs it
  **per-universe**: the host's own self-hosted engine stays subscription-only, but a founder who
  deposits an API key opts *their* universe into API-key providers. **This is a real
  policy change** — the global boolean becomes a per-universe capability, gated by the
  founder having deposited a key. Recommend: keep the global default `0`; add a
  per-universe override that is *only* truthy when a vault holds a validated key for
  that universe (never a free-floating env flip). **Host decision required.**

---

## 7. Open risks + host decisions needed

1. **[Host decision] Confirm the ToS reading (§0) and the "no founder-subscription
   custody" stance.** If accepted, the engine-assignment UX must offer "API key /
   self-hosted endpoint / rent a market daemon," **not** "connect your Claude/ChatGPT
   subscription" (and "no engine" = interactive-via-chatbot, not a platform-run
   default). The biggest risk is shipping a subscription-connect affordance that gets
   founders (or the platform) account-banned.
2. **[Host decision] Per-universe `TINYASSETS_ALLOW_API_KEY_PROVIDERS` relaxation
   (§6).** Approve turning the global subscription-only gate into a per-universe
   capability gated on a deposited key.
3. **[Host decision] Secret-backend vendor(s)** for hosted droplet vs OSS cloner
   (KMS/Vault vs OpenBao/age-sops). Affects blast radius and the Tier-3 clone story.
4. **[Depends] Gap A must land before any isolation work** — per-request universe
   resolution in the shared MCP server (relay note Gap A). Custody sits on top of it.
5. **[Verify at build] Codex-CLI-with-API-key** actually honors a per-universe key via
   env without touching the shared `/data/.codex` subscription home (auth precedence).
6. **[Legal watch] Provider terms drift.** The Anthropic crackdown was 2026-04-04 and
   is <90 days old; re-verify §0 before any public engine-assignment copy ships.

---

## 8. The single biggest risk

**Shipping any "bring your subscription" path.** The reshape's §11 wording ("none
privileged … we don't care how they bring an LLM") reads as if a founder subscription
is a first-class engine source. It is not — custodying and driving a founder's Claude
Pro/Max or ChatGPT Plus subscription server-side violates both providers' terms three
ways over and risks account bans for the founder *and* platform. Every downstream
decision (UX copy, vault schema, engine-assignment flow) must encode: **subscription =
host's-own-self-hosted-only or on-device-only (never a per-founder default); the
founder's 24/7 BYO engine is an API key
or an endpoint.**

---

## Codex opposite-provider review (2026-07-02) — ADAPT

Dispatched per the AGENTS.md research-finding gate (Claude-made finding →
Codex review before it gates build). Verdict **ADAPT** — the load-bearing ToS
conclusion is **confirmed**, with one narrowing.

- **CONFIRMED (Anthropic, SUBSCRIPTION lane):** don't route third-party requests
  through Free/Pro/Max credentials; **Consumer Terms** bar credential sharing + most
  non-API automation. NOTE (round-17 #6): this Consumer-Terms conclusion is about the
  *subscription/login* lane only. The separate **API-key** lane is governed by
  Anthropic's **Commercial Terms** (§2b) — do not extend the Consumer-Terms bar to
  the API-key custody question, which is CONDITIONAL pending the contracting-party
  legal review, not barred.
- **ADAPT (OpenAI):** the note overstated the OpenAI side. OpenAI recommends API
  keys for programmatic Codex and forbids account sharing / programmatic
  extraction, **but also documents Business/Enterprise Codex access tokens for
  trusted non-interactive workflows** — an org-level path distinct from a personal
  ChatGPT subscription. Narrowed inline above. Does not change the conclusion for
  *personal* subscriptions.
- **Net:** "do not custody a founder's personal consumer subscription server-side"
  stands and is now opposite-provider-confirmed → may gate build. The host's
  **market-rented-daemon lane** (relay-architecture note §12) is the clean
  sidestep: market hosts run their own engines legally + get paid.
- Codex also re-confirmed the foundation merge-blockers (fail-open optional-mode
  fallback; daemon-scope-gate = Gap B; rename-orphan test debt; branch behind
  origin/main). Logged in `2026-07-02-universe-intelligence-relay-codex-review.md`.

Raw: `$CLAUDE_JOB_DIR/tmp/codex_custody_review.md`.
