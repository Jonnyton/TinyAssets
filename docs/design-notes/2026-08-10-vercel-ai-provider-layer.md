# vercel/ai (AI SDK) as a solution to user-subscription-powered universes — evaluation

Date: 2026-08-10 (all web citations accessed 2026-08-10). Status: **research note /
external evaluation only** — no code touched. Founder prompt: "perhaps this project has
a solution" → evaluate whether vercel/ai or its ecosystem provides the missing
mechanism for running each user's hosted cloud universe on the user's own LLM
subscription (Claude Pro/Max, ChatGPT) or key, compliantly.

Companions: `2026-08-10-anthropic-subscription-structures.md` (policy verdicts E1–E18,
cited below as "structures note") and `2026-08-10-cloud-brain-client-inference-options.md`
(architecture + Codex ADAPT). Scope guard: a prior pass already mined vercel/ai for
memory patterns (memory `ai-dev-process-research-2026-08`); this note is ONLY the
provider/auth/execution layer.

**AGENTS.md gate:** research-derived finding; needs opposite-provider (Codex) review
before any build/push/live rollout based on it.

**Verdict up front: ADOPT-THE-PATTERN, not the library. Nothing here changes the
Anthropic compliance picture.** The single most useful find is the ben-vargas CLI-wrapper
provider family — an actively maintained, Vercel-directory-listed existence proof of
exactly our target abstraction ("one uniform model interface over subscription-CLI +
API-key + self-hosted engines") — plus one cautionary tale (Gemini CLI's individual-
account path killed by the vendor), Vercel's own documented Claude-subscription
pass-through proxy (mechanism precedent only — see §4), and Vercel's new first-party
sandbox harness layer (§2b, added per Codex review).

**Codex opposite-provider review: NOTE_VERDICT: ADAPT (2026-08-10)** — corrections
folded into the body below; verdict block at the end of the note.

---

## 1. What vercel/ai actually is at the provider layer

The AI SDK (github.com/vercel/ai, TypeScript) defines a **Language Model Specification**
(currently V4, in `@ai-sdk/provider`): a provider implements `LanguageModelV4` with
`specificationVersion`, `provider`/`modelId`, `supportedUrls`, and two methods —
`doGenerate()` and `doStream()` (typed stream events). App code calls `generateText`/
`streamText` against any conforming model. Two composition layers sit on top
([ai-sdk.dev custom-providers guide](https://ai-sdk.dev/providers/community-providers/custom-providers),
accessed 2026-08-10):

- **Middleware** — `wrapLanguageModel({ model, middleware })` with three hooks:
  `transformParams` (mutate params pre-call), `wrapGenerate`, `wrapStream` (wrap the
  call itself). Chainable. Built-ins: default settings/instructions, reasoning
  extraction, JSON-fence stripping, simulated streaming. Canonical use cases:
  guardrails, caching, logging, RAG injection
  ([ai-sdk.dev middleware docs](https://ai-sdk.dev/docs/ai-sdk-core/middleware)).
- **Registry / model strings** — `createProviderRegistry` and `provider/model` string
  slugs (`'anthropic/claude-opus-5'`) resolve to concrete provider instances; the AI
  Gateway uses the same slug namespace.

Providers are ordinary npm packages; Vercel's directory lists ~24 official + 35+
community providers and explicitly does not endorse the community ones.

## 2. The CLI-wrapping provider ecosystem (precedent AND mechanism)

This is the part that matches our problem. One maintainer, **Ben Vargas** (independent;
every package carries "unofficial community provider… not affiliated with or endorsed
by Anthropic/OpenAI or Vercel"), maintains a family of providers that put the AI SDK
interface **on top of subscription-authenticated agent CLIs** — all listed on Vercel's
own docs site under Community Providers:

| Package | Wraps | Auth | Currency (checked 2026-08-10) |
|---|---|---|---|
| `ai-sdk-provider-claude-code` | `@anthropic-ai/claude-agent-sdk` (pinned exactly; **0.3.226** at v4.1.0 per current `package.json` — Codex-verified), which spawns the **genuine Claude Code runtime** (per-platform native binaries via optionalDependencies) as a subprocess | Whatever the CLI env holds: `claude auth login` (Pro/Max subscription OAuth), `CLAUDE_CODE_OAUTH_TOKEN` setup-token, `ANTHROPIC_API_KEY`, Bedrock/Vertex creds — the subprocess env is built from a **sanitizing allowlist** (prefix-matched `ANTHROPIC_`/`CLAUDE_`/`AWS_`/`GOOGLE_`) | v4.1.0 published **2026-08-10 (today)**; repo pushed today; 359 stars; AI SDK v7/v6/v5/v4 tags ([github.com/ben-vargas/ai-sdk-provider-claude-code](https://github.com/ben-vargas/ai-sdk-provider-claude-code)) |
| `ai-sdk-provider-codex-cli` | Codex CLI subprocess — two modes: `codexExec` (spawn `codex exec` per call, `--experimental-json`) and `codexAppServer` (persistent `codex app-server` JSON-RPC client, true delta streaming) | ChatGPT OAuth from `codex login` (`~/.codex/auth.json`) **or** `OPENAI_API_KEY` env | v2.1.2 published 2026-07-23; requires Codex CLI 0.144.x; separate `codex-app-server` provider page on ai-sdk.dev ([github.com/ben-vargas/ai-sdk-provider-codex-cli](https://github.com/ben-vargas/ai-sdk-provider-codex-cli)) |
| `ai-sdk-provider-chatgpt-oauth` | **No CLI** — calls `chatgpt.com/backend-api/codex/responses` directly with OAuth tokens (reads `~/.codex/auth.json`, or PKCE flow, or env vars); auto token refresh | ChatGPT Plus/Pro OAuth | last publish 2025-09-16 — **stale**; the reverse-engineered-harness shape, superseded by the CLI wrapper |
| `ai-sdk-provider-gemini-cli` | `@google/gemini-cli-core` | Personal Google OAuth (free tier / AI Pro / Ultra) or API key | **ARCHIVED + all versions npm-deprecated.** README: Google transitioned Gemini CLI to Antigravity CLI and on **2026-06-18 stopped serving Gemini CLI requests from individual accounts**, "remov[ing] this package's core use case — accessing Gemini models via personal Google OAuth without per-token API billing." Scope note (Codex correction): Google ended the *individual consumer-account OAuth/subscription path* only — the official `google-gemini/gemini-cli` repo stays active and enterprise/API-key access survived |

(Also-rans confirming ecosystem breadth: `SylphxAI/ai-sdk-provider-claude-code` fork,
`coji/claude-code-ai-provider`, `ai-sdk-cc-provider`.)

**What this proves for us:**

1. **The abstraction we want exists and works in public.** The twin claude-code /
   codex-cli providers are literally "one `LanguageModel` interface whose backing
   engine is a subscription-authenticated CLI subprocess *or* an API key, selected by
   ambient credential" — our universe-writer target shape, shipped, documented on
   Vercel's site, and current (claude-code updated same-day).
2. **The mechanics are the same ones we already use.** Subprocess spawn of the genuine
   binary, JSON output mode, env-allowlist construction, stderr-based auth/timeout
   error classification, session management, warm-start. Nothing novel — but a working
   reference implementation for details we're still hardening (see §5).
3. **Auth never gets nicer than the CLI's own auth.** Every current provider defers to
   `claude auth login` / `codex login` / env tokens. There is **no OAuth-brokering
   provider for Anthropic** (the one that tried for OpenAI, `chatgpt-oauth`, went
   stale in favor of the CLI wrapper). The interface is nicer; the credential
   mechanics are identical to ours.
4. **The whole class lives at the model vendor's pleasure.** Google ended the
   individual-account Gemini CLI subscription path with one product decision
   (2026-06-18) and the provider archived itself the next month. Same tail risk the
   structures note documents for Anthropic (Feb→Apr→May→Jun 2026 whiplash). Any
   design of ours must keep the engine-source swappable — which the serving-binding
   model already does.

## 2b. Vercel's first-party harness layer (missed in the first pass; added per Codex review)

vercel/ai now ships an experimental **first-party** harness tier alongside community
providers ([`@ai-sdk/harness-claude-code`](https://github.com/vercel/ai/blob/main/content/providers/02-ai-sdk-harnesses/01-claude-code.mdx),
[`@ai-sdk/harness-codex`](https://github.com/vercel/ai/blob/main/content/providers/02-ai-sdk-harnesses/02-codex.mdx),
accessed via Codex review 2026-08-10):

- `harness-claude-code` runs the **official Anthropic Agent SDK inside a Vercel
  Sandbox** and bridges agent events over WebSocket; `harness-codex` wraps the
  official Codex SDK the same way. This is Vercel productizing "hosted, isolated,
  per-tenant agent execution" — architecturally the closest first-party analog to our
  hosted universe writer.
- Auth: both document Gateway/API-key-style env vars. `harness-claude-code` accepts
  arbitrary process `env`, so an isolated tenant credential (e.g.
  `CLAUDE_CODE_OAUTH_TOKEN`) is *technically* injectable — but Vercel documents no
  subscription auth, brokers no OAuth, and establishes no entitlement. It helps
  hosted execution/isolation mechanics, not the subscription-compliance question.
- Relevance to us: a design comparable for the sandbox/isolation seam (STATUS P1 "No
  OS engine sandbox") and confirmation that "official agent SDK in an isolated
  per-tenant sandbox, events bridged out" is where the ecosystem is converging. Not a
  reason to adopt the library: it presumes Vercel Sandbox infrastructure and a TS
  control plane.

## 3. Vercel AI Gateway — BYOK reality

Sources: [BYOK docs](https://vercel.com/docs/ai-gateway/authentication-and-byok/byok)
(last_updated 2026-07-31), [coding-agents/claude-code](https://vercel.com/docs/ai-gateway/coding-agents/claude-code)
(last_updated 2026-07-28), [changelog 2026-01-26](https://vercel.com/changelog/claude-code-max-via-ai-gateway-available-now-for-claude-code).

- **BYOK takes provider API / service-account credentials only** (Codex-corrected
  phrasing): Anthropic `{ apiKey }`, OpenAI `{ apiKey }`, Azure
  `{ apiKey, resourceName }`, Vertex service account, Bedrock SigV4. **No consumer
  subscription/OAuth credential type exists in BYOK.** (Vercel OIDC authenticates the
  caller to the Gateway, not the end user to Anthropic/OpenAI.) No markup on BYOK
  traffic; requires paid tier + purchased Gateway credits.
- **Per-user credentials: yes, per-request.** `providerOptions.gateway.byok` accepts
  credentials per request (overriding dashboard creds), with multiple credentials per
  provider tried in order — the documented pattern for per-tenant isolation in a
  multi-customer app. This is real prior art for "each end-user brings their own
  key" in a hosted product — but only for **API keys**.
- **Fail-open by design:** "If a query using your credentials fails, AI Gateway will
  retry the query with its system credentials," billed to your credits. Community
  threads show exactly the failure our R2-1 lane exists to prevent — subscription
  traffic silently landing on Gateway credits
  ([community thread 40449](https://community.vercel.com/t/claude-max-subscription-did-not-route-through-ai-gateway-and-ended-up-using-my-ai-credits/40449)).
  For us this fallback is an **anti-pattern** (memory
  `ambient-credential-fallback-is-an-identity-leak`; a missing/failed user credential
  must fail closed, never fall through to a platform-side credential).
- **The subscription mode is a proxy, not BYOK.** "With Claude Code Max" (shipped
  2026-01-26): the user's own Claude Code client sets
  `ANTHROPIC_BASE_URL=https://ai-gateway.vercel.sh` plus
  `ANTHROPIC_CUSTOM_HEADERS="x-ai-gateway-api-key: Bearer …"`, then logs in normally
  with "Claude account with subscription." Claude Code keeps authenticating with
  Anthropic via its own `Authorization` header (the plan OAuth token **transits
  Vercel's proxy**); the gateway authenticates itself with the separate header and
  provides observability/routing. Codex-CLI-via-Gateway, by contrast, is *not*
  subscription pass-through — it repoints `model_provider` at the gateway and pays
  with a Gateway API key.

## 4. Compliance: does any of this change the Anthropic picture?

**No.** Mapping onto the structures note:

- `ai-sdk-provider-claude-code` operates under exactly the current pause-state
  allowance (structures note E3: "Claude Agent SDK, `claude -p`, and third-party app
  usage still draw from your subscription's usage limits") and the genuine-binary
  fingerprint line (E12/E16) — it spawns the real Claude Code runtime. It is the same
  setup-token/CLI-login mechanics under a nicer TypeScript interface. It carries its
  own disclaimer ("comply with Anthropic's Terms of Service") and is **not**
  Anthropic-sanctioned. A hosted multi-user product built on it inherits our identical
  GRAY verdict (structures note §4/3b) — the interface layer changes nothing about
  who holds the credential or whose plan the traffic draws from.
- **Separate three things the first draft blurred** (Codex correction). (1) *Official
  runtime/library status*: the Anthropic Agent SDK itself IS official and explicitly
  contemplates commercial products under Anthropic's Commercial Terms — with API-key
  auth. So "nothing in the ecosystem is Anthropic-sanctioned" is too blunt: the
  runtime is sanctioned. (2) *Technical credential transport*: CLIs, env tokens,
  proxies all move the credential fine. (3) *Legal entitlement to consume a user's
  consumer Pro/Max subscription from a hosted third-party product*: this is the only
  unresolved item, no ecosystem artifact resolves it, and no Anthropic-sanctioned
  OAuth-token provider exists. The only direct-OAuth package (`chatgpt-oauth`,
  OpenAI side) is the reverse-engineered shape and has gone stale.
- **One [PRACTICE] datum, mechanism only:** Vercel — a major vendor — has publicly
  documented and shipped, since 2026-01-26, a proxy through which Claude *plan
  credentials* transit third-party infrastructure (the traffic still originates from
  the genuine `claude` client; Vercel never holds the credential at rest — the user's
  own client sends it per-request). Per Codex review, do NOT read more into it:
  "survived enforcement" is an absence-of-evidence claim, establishes no Anthropic
  approval and no precedent for hosted credential custody, and cannot support a
  GRAY-not-prohibited inference. The operative rule stays the companion notes' ADAPT:
  hosted customer-subscription custody is **approval-required by default**. Our
  hosted-universe shape (credential at rest in our vault, we initiate turns) remains
  the harder case; the contact-sales/3e ask from the structures note stands unchanged.
- OpenAI side: the codex-cli provider is one more instance of the already-endorsed
  pattern (structures note §6) — confirming, not changing, that Codex subscription
  auth is the green-path family.

## 5. Architecture fit — mapped onto engine_source + serving bindings

Our layer today (origin/main; local citations indicative): `BaseProvider` ABC +
`ProviderRouter` (`tinyassets/providers/base.py`, `router.py`), per-family subprocess
providers (`claude_provider.py` spawns `claude -p [--output-format json]`,
`codex_provider.py`, plus gemini/grok/groq/ollama), env materialization via
`subprocess_env_for_provider` with API-key opt-in gating, subscription auth-health
probes, and `engine_source ∈ {byo_api_key, self_hosted_endpoint, market_rented,
host_daemon}` on the set-engine surface (`tinyassets/api/universe.py:4864`), with
slice-1 `ProviderWorkBinding` minting per-universe serving bindings.

**Adopt the library? No.**

- The AI SDK's value is a uniform interface *for TypeScript app code doing inference*.
  We have no such consumer: our writer is Python, subprocess-first, and Hard Rule 3
  (no API SDKs for the primary writer) exists precisely to stay on the genuine CLIs.
- Adding a Node sidecar to reach `ai-sdk-provider-claude-code` would wrap our
  subprocess in their subprocess — a new runtime, a new supply chain, zero new
  capability (they end up spawning the same binary we already spawn), and new
  latency/RSS on a 1.9Gi prod box.
- (Narrow future exception: if a TS surface of ours ever needs client-side inference —
  website playground, desktop app — the AI SDK is the obvious client library there.
  Out of scope now.)

**Adopt the pattern? Yes — three concrete transfers, one validation, one anti-pattern:**

1. **Formalize the writer interface = LanguageModel-spec analog — by EXTENDING the
   existing abstraction, not creating a new one** (Codex-sharpened). We already have
   the shape (`BaseProvider` ≈ `LanguageModelV4`, `ProviderRouter` ≈ registry). The
   transfer is making **engine-source a first-class constructor dimension of the
   provider instance** rather than ambient env: a universe turn should resolve to a
   provider instance bound to `{engine_source, credential_ref, model}` at admission
   (the serving binding IS this object — validation that slice 1 is the right shape).
   Concretely: add explicit engine-binding + credential-identity + fail-closed
   middleware seams around `BaseProvider`/`ProviderRouter`; do not introduce a
   parallel provider interface.
   Target taxonomy maps 1:1: `claude-cli-subscription` / `codex-cli-subscription`
   (today's CLI providers under an `llm_subscription` binding), `user-api-key`
   (`byo_api_key` — same CLIs with key-injected env, or direct endpoint),
   `self_hosted_endpoint` (ollama/OpenAI-compatible), `market` (`market_rented`).
2. **Add an explicit middleware seam.** `wrapLanguageModel`'s
   transformParams/wrapGenerate/wrapStream is the clean version of concerns we
   currently bake into each provider: quota checks, receipts (R2-1's "provider
   receipt"), redaction/guardrails, logging, budget caps, sandbox flag injection. A
   small `ProviderMiddleware` protocol (before-params / around-call) wrapping
   `BaseProvider` would let R2-1's receipt and fail-closed checks be one chain applied
   to every engine source instead of N per-provider implementations. Cheap, Python-native.
3. **Mine the reference implementations for hardening details.** The claude-code
   provider's **sanitizing subprocess-env allowlist** is the same seam as our
   `subprocess_env_for_provider` — with the same trap R2-1 names: prefix-matching
   `CLAUDE_CODE_OAUTH_TOKEN` through *deliberately inherits ambient host credentials*.
   Ours must invert that default (vault-materialized or nothing). Also worth mining:
   stderr-based auth-failure classification, `codex app-server` JSON-RPC persistent
   mode (lower per-turn spawn cost than `codex exec` — relevant to our writer-capacity
   ceiling, memory `universe-writer-rate-limit`), and session/warm-start handling.
4. **Validated:** our "one writer interface, N swappable engines, binding decided at
   admission" architecture is independently converged-upon by the most active
   community project in this space. No structural rework indicated.
5. **Anti-pattern to keep out:** Gateway-style fallback-to-system-credentials.
   Fail-open on a failed user credential is a product feature for Vercel and an
   identity/billing leak for us.

**Gateway as infrastructure? Not for the core problem.** BYOK cannot carry
subscriptions, so it does not touch our headline gap. Its per-request BYOK is decent
prior art if we ever want a managed multi-provider rail for **API-key** engines
(`byo_api_key` universes could in principle route through it for
observability/fallback-routing), but it adds a paid middleman, its fallback semantics
are wrong for us, and our canonical API-key path already works via direct CLIs/endpoints.

## 6. Answers to the founder's question, compressed

- **Does vercel/ai solve "user's hosted universe on the user's subscription"? No.**
  Its subscription story is the same CLI/setup-token mechanics we already use, wrapped
  for TypeScript consumers; its Gateway explicitly does not accept subscription
  credentials; and nothing in the ecosystem resolves the one open item — legal
  entitlement to consume a user's consumer Pro/Max plan from a hosted third-party
  product (the official Agent SDK runtime is sanctioned; that entitlement is not).
- **What it does solve/offer:** a proven interface *pattern* (spec + middleware +
  registry) our Python layer should mirror where it doesn't already; two
  actively-maintained reference implementations of subscription-CLI wrapping with
  hardening details worth stealing; a first-party sandbox-harness design comparable
  (§2b) for the isolation seam; one per-request-BYOK prior art for per-user API
  keys; one mechanism-only [PRACTICE] datum (subscription traffic transiting a
  third-party proxy, publicly documented — no compliance weight per Codex review) —
  and one vivid reminder (Gemini CLI provider's death) that every subscription-CLI
  engine needs a swappable exit.
- **Recommendation: ADOPT-THE-PATTERN.** No library adoption; no compliance change; no
  new engine_source. Fold items 5.1–5.3 into the existing byo-llm-connect-flow /
  R2-1 lanes as review inputs, not new lanes.

## Watch items / follow-ups

- If the Anthropic contact-sales conversation (structures note §8) happens, the
  Vercel Claude-Code-Max proxy and the `@ai-sdk/harness-claude-code` sandbox shape
  are useful named comparables to raise.
- Watch `@ai-sdk/harness-claude-code` / `harness-codex` (experimental): if either
  ever documents subscription-credential injection or Anthropic announces terms for
  it, that IS the compliance event this note found absent.
- Re-check `ai-sdk-provider-claude-code` on any future Anthropic enforcement event —
  as the most visible community subscription-wrapper (and same-day-maintained), it is
  an early-warning canary for our own `claude -p` exposure.
- If per-turn subprocess spawn cost becomes the writer-capacity bottleneck, evaluate
  the `codex app-server` persistent-process pattern for our codex provider.

## Cross-refs

- `docs/design-notes/2026-08-10-anthropic-subscription-structures.md` (E-numbered
  evidence; verdicts unchanged by this note)
- `docs/design-notes/2026-08-10-cloud-brain-client-inference-options.md` (backbone/
  offload architecture this maps onto)
- Memory: `ai-dev-process-research-2026-08` (prior vercel/ai memory-pattern pass —
  not redone here), `universe-writer-rate-limit`, `ambient-credential-fallback-is-an-identity-leak`,
  `user-subscription-runs-the-universe`
- STATUS.md: R2-1 credential fail-closed lane (middleware-seam + env-allowlist
  findings feed it)

---

## Codex opposite-provider review — NOTE_VERDICT: ADAPT (2026-08-10, folded in)

Dispatched same-day as an adversarial refutation pass (thread
`019feea4-8835-7300-a80a-131c848f8d8d`). Outcome per claim: (1) Gateway BYOK upheld
with terminology correction (provider API/service-account credentials, not
"API-keys-only"; no fail-closed BYOK option found); (2) claude-code provider upheld,
Agent SDK pin corrected to 0.3.226; (3) Claude-Code-Max proxy mechanism upheld,
compliance inference REFUTED ("unenforced-against" is absence-of-evidence; no support
for GRAY precedent; hosted customer-subscription custody stays approval-required by
default); (4) Gemini upheld narrowly (individual-account path ended, not the CLI
wholesale); (5) adopt-pattern upheld with the instruction to extend
`BaseProvider`/`ProviderRouter` rather than add a new interface. Material omission
found and added: Vercel's first-party `@ai-sdk/harness-claude-code` /
`@ai-sdk/harness-codex` sandbox harness tier (§2b). Codex also required the
three-way split now in §4: official runtime status ≠ credential transport ≠
consumer-subscription entitlement — only the last is unresolved, and nothing in
vercel/ai resolves it. All adaptations are folded into the body above.
