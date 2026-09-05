# Provider Routing

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

Role-based LLM fallback chains terminating at the local model, running on user-brought compute of any allowed access method (subscription CLI, API-key HTTP, or another published standard) — never platform-supplied — with pinning, per-universe preference and privacy allowlists, auth-health quarantine, per-node policy overrides, a parallel judge ensemble, and open user-defined provider definitions that can also serve converse/writer turns.
## Requirements
### Requirement: Every role chain terminates at the local model
The provider router (`tinyassets/providers/router.py`) SHALL define a fallback chain for each LLM role (`writer`, `judge`, `extract`, `embed`) that ends at the `ollama-local` provider, so a call keeps producing output with zero cloud providers reachable. Roles with no explicit chain SHALL default to the `writer` chain. The system SHALL only stop for provider unavailability when the local model itself is also unavailable.

#### Scenario: writer routes to local when all cloud providers are gone
- **WHEN** a `writer` call is routed and every non-local provider is unregistered, in cooldown, or filtered out
- **THEN** the router attempts `ollama-local`
- **AND** returns its response instead of raising

#### Scenario: chains cover the four canonical roles
- **WHEN** the router resolves a chain for `writer`, `judge`, `extract`, or `embed`
- **THEN** the resolved chain ends with `ollama-local`
- **AND** an unknown role name resolves to the `writer` chain

### Requirement: User-brought compute of any allowed access method
The platform SHALL NOT enumerate a compiled provider set. A universe runs on compute the user brings, of any allowed access method — subscription (via CLI), API key (via HTTP), or another published standard — never on platform-supplied compute. This REPLACES the earlier "subscription-only by default" requirement: subscription is one access method, not the only one. "No host writer ever" is preserved — the compute is always the user's own. API-key providers are honored only when the credential is held under the custody owner's contract (no raw key in the control plane / JSON vault). The legacy fixed api-key providers (`gemini-free`, `groq-free`, `grok-free`) remain gated off unless `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is truthy; primary subscription writers are `claude -p` / `codex exec` subprocesses, never API SDKs (project hard rule).

#### Scenario: an api-key provider serves a universe
- **GIVEN** a universe whose owner has registered an `api_key_http` provider definition and deposited its credential through the custody owner's path
- **WHEN** the universe runs a turn selecting that provider
- **THEN** the turn executes on that provider via the HTTP protocol encoder over the outbound proxy, drawing on the user's own credential, with no platform fallback

#### Scenario: no compute without a user-authorized provider
- **GIVEN** a universe with no enrolled requester-owned provider
- **WHEN** a turn or automation attempts to run
- **THEN** it fails closed (`no_requester_owned_executor`), never borrowing an ambient host credential and never falling back to a platform-supplied model

### Requirement: Role chains resolve through the open routing equation
Routing SHALL resolve candidates through the equation `selected ordered candidates ∩ allowed_providers ceiling ∩ live requester-owned enrollment ∩ request capability`, not a static per-role provider list. The router filters WITHIN the selected ordered set and never synthesizes a candidate the selection did not produce. The existing fail-loud, bounded-cooldown, hard-writer-pin, and per-universe privacy-allowlist requirements are preserved unchanged; the privacy ceiling DOMINATES capability routing (capability may only narrow, never widen or override a privacy exclusion).

#### Scenario: router never adds an unselected provider
- **GIVEN** an ordered selected set `[A, B]` and an enrolled-but-unselected provider C
- **WHEN** both A and B are exhausted or capability-filtered out
- **THEN** the call fails closed naming the empty effective set — C is never invoked

#### Scenario: privacy ceiling dominates capability
- **GIVEN** a provider that is capability-best for the request but excluded by the universe privacy allowlist
- **WHEN** the router resolves candidates
- **THEN** the excluded provider is never selected, regardless of capability rank

### Requirement: Hard writer pin disables fallback and fails loud
When `TINYASSETS_PIN_WRITER` is set, the `writer` chain SHALL be narrowed to that single provider with NO fallback. If the pinned provider is exhausted, blocked by the privacy allowlist, disabled by the subscription-only policy, or has dead subscription login, the router SHALL raise `AllProvidersExhaustedError` and SHALL NOT silently route to any other provider. The error message SHALL name the pinned provider and how to clear the pin.

#### Scenario: pinned writer runs alone
- **WHEN** `TINYASSETS_PIN_WRITER=codex` and `codex` is healthy
- **THEN** only `codex` is attempted for `writer` calls
- **AND** no fallback provider is attempted

#### Scenario: exhausted pin fails loud
- **WHEN** the pinned writer provider fails or is unavailable
- **THEN** the router raises `AllProvidersExhaustedError` naming the pinned provider
- **AND** does not fall through to the default chain

### Requirement: Per-universe engine preference and privacy allowlist
The router SHALL apply per-universe configuration resolved from an explicit `universe_context` when supplied, otherwise from the process-global universe config. `preferred_writer` / `preferred_judge` SHALL reorder the chain so the preferred provider is tried first (a no-op if absent from the chain). The `allowed_providers` allowlist SHALL filter the chain down to permitted providers; `None` is a no-op preserving the full chain. When the allowlist filters the chain to empty, the router SHALL raise `AllProvidersExhaustedError` rather than leak to a disallowed provider.

#### Scenario: allowlist blocks third-party providers
- **WHEN** a universe sets `allowed_providers=["ollama-local"]`
- **THEN** a `writer` call attempts only `ollama-local`
- **AND** `claude-code`, `codex`, and the api-key providers are not attempted

#### Scenario: empty filtered chain hard-fails, no leak
- **WHEN** `allowed_providers` excludes every provider in the resolved chain
- **THEN** the router raises `AllProvidersExhaustedError` referencing `allowed_providers`
- **AND** no provider is called

#### Scenario: preference reorders without dropping fallback
- **WHEN** a universe sets `preferred_writer` to a provider already in the chain
- **THEN** that provider is attempted first
- **AND** the remaining chain stays available as fallback

### Requirement: Auth-health quarantine of dead-login subscription providers
When an auth-health probe is injected into the router, a provider whose subscription login is definitively `not_logged_in` SHALL be dropped from fallback chains, policy attempt orders, and the judge ensemble, so routing goes straight to a healthy provider instead of burning a failed attempt and a misleading cooldown. The gate SHALL be conservative: only a definitive `not_logged_in` drops a provider — `unknown` and `ok` statuses are kept, and a probe that raises is treated as "keep". A pinned writer with dead login SHALL fail loud rather than route elsewhere. As-built limitation: with no probe injected (the default for script/test routers), the gate is a no-op and no provider is quarantined.

#### Scenario: dead-auth writer skipped in fallback
- **WHEN** the probe reports `claude-code` as `not_logged_in` and no writer is pinned
- **THEN** the router routes straight to the next healthy provider
- **AND** `claude-code` is never called

#### Scenario: unknown and local providers are never stranded
- **WHEN** both subscription writers report `not_logged_in` and the local provider probes `unknown`
- **THEN** the router falls through to `ollama-local`
- **AND** returns its response

#### Scenario: pinned dead-auth writer fails loud
- **WHEN** the pinned writer's probe reports `not_logged_in`
- **THEN** the router raises `AllProvidersExhaustedError` referencing subscription login
- **AND** no other provider is called

### Requirement: Per-node policy routing honors llm_policy overrides
`call_with_policy` SHALL honor an explicit `llm_policy` dict by building an attempt order from `difficulty_override` (matched against the call's difficulty), then `preferred`, then `fallback_chain` entries, de-duplicated in that order. The same subscription-only, allowlist, and auth-health filters SHALL apply to the policy attempt order. When the policy is empty or all policy-derived providers are exhausted or filtered out, the method SHALL fall through to the standard role-based `call()`, which re-applies every policy gate. It SHALL return `(response_text, provider_name_used, call_meta)`.

#### Scenario: preferred policy provider is tried first
- **WHEN** a policy names a healthy `preferred` provider
- **THEN** that provider is attempted before the policy fallback chain
- **AND** the returned tuple reports it as the provider used

#### Scenario: policy respects the privacy allowlist
- **WHEN** a policy names providers outside the universe's `allowed_providers`
- **THEN** those providers are not attempted
- **AND** routing continues with the allowed policy providers or falls through to the role chain

#### Scenario: exhausted policy falls through to the role chain
- **WHEN** every policy-derived provider is filtered out or exhausted
- **THEN** the method invokes the role-based `call()` for the same role
- **AND** returns that result

### Requirement: Judge ensemble fans out to all healthy judges in parallel
`call_judge_ensemble` SHALL call every registered, non-cooldown judge provider once, in parallel, for model-family diversity, and SHALL never call the same provider twice. The allowlist, subscription-only, and auth-health filters SHALL apply to the ensemble. It SHALL return 1-N responses depending on how many judges are healthy, and SHALL return an empty list when no judge provider is available. Separately, a single `call()` with role `judge` SHALL return a degraded sentinel response when its chain is exhausted rather than raising.

#### Scenario: fan-out returns one response per healthy judge
- **WHEN** the ensemble runs with several healthy judge providers
- **THEN** each is called exactly once in parallel
- **AND** the result list contains one response per provider that responded

#### Scenario: empty ensemble returns an empty list
- **WHEN** the allowlist or filters remove every judge provider
- **THEN** `call_judge_ensemble` returns an empty list

#### Scenario: exhausted single judge call returns a degraded sentinel
- **WHEN** a `call()` with role `judge` exhausts its chain
- **THEN** it returns the degraded judge response
- **AND** does not raise `AllProvidersExhaustedError`

### Requirement: Chain-drain backoff prevents committing empty prose (BUG-029)
When all API providers in the effective (registered) chain are in cooldown and the local provider returns empty prose for a configured number of consecutive calls (default 2), the router SHALL raise `AllProvidersExhaustedError` to force operator/daemon backoff rather than committing empty output. The consecutive-empty counter SHALL reset on any non-empty response. The drain check SHALL run against the effective chain, so an unregistered API provider neither triggers nor blocks drain detection. When the chain simply falls through to local-only, the router SHALL emit a structured `CHAIN_DRAINED` warning.

#### Scenario: repeated empty local output under a drained chain raises
- **WHEN** all API providers are in cooldown and the local provider returns empty prose for the configured consecutive count
- **THEN** the router raises `AllProvidersExhaustedError` naming the provider and count

#### Scenario: non-empty local response resets the counter
- **WHEN** the local provider returns non-empty prose after an empty one
- **THEN** the consecutive-empty counter resets
- **AND** the next single empty response does not raise

#### Scenario: an available api provider suppresses the drain raise
- **WHEN** an API provider in the chain is not in cooldown
- **THEN** an empty local response does not raise, because the chain is not drained

### Requirement: Provider calls use one explicit immutable contract
The provider layer SHALL represent per-call routing with an immutable `UniverseContext`, immutable `ModelConfig`, and immutable `ProviderResponse`, and every `BaseProvider` implementation MUST expose async `complete(prompt, system, config, *, universe_dir=None)` returning that response envelope. `UniverseContext` carries the optional universe directory and resolved universe configuration; an explicit context wins over process-global configuration, while absent fields preserve the single-universe global fallback. `ModelConfig` carries timeout, token cap, temperature, reasoning effort, workspace-sandbox, allowed-tool, and disallowed-tool settings. `ProviderResponse` carries text, provider, model, family, latency, and the degraded flag.

#### Scenario: explicit context isolates interleaved universes
- **WHEN** synchronous calls for two universes are interleaved through the router's thread pool and each supplies a `UniverseContext` with its own directory and resolved configuration
- **THEN** each call applies that context's provider preference and passes that context's directory to the selected provider, so vault authentication and routing do not bleed from the process-global universe or the other call

#### Scenario: absent context preserves single-universe behavior
- **WHEN** a caller supplies no explicit universe context or supplies a context without a resolved configuration
- **THEN** routing falls back to the process-global universe configuration where available and otherwise uses the default model configuration

#### Scenario: provider response carries model evidence
- **WHEN** a provider completes a model call
- **THEN** it returns text together with provider name, model name, model family, latency in milliseconds, and whether the response is degraded

#### Scenario: policy routing returns response telemetry
- **WHEN** `call_with_policy` completes through a policy provider or the role fallback chain
- **THEN** it returns response text, the provider used, and call metadata containing model, family, latency, degraded state, and attempt count

### Requirement: Runtime eligibility and exhaustion produce bounded cooldowns and structured evidence
The provider runtime SHALL distinguish imported/registered providers, quota or cooldown eligibility, subscription-auth eligibility, and call failure. The standalone fallback router MUST independently guard optional provider imports, register CLI providers only when their binary availability probe succeeds, and expose only registered names through `available_providers`. `QuotaTracker` SHALL keep process-local monotonic cooldown and rate-window state, applying 120 seconds after unavailable or timeout failures and 30 seconds after other provider failures; successful API-backed calls record their configured rolling-window usage. When an unpinned non-judge role chain exhausts, `AllProvidersExhaustedError` SHALL carry per-provider attempt diagnostics and a chain-state snapshot rather than requiring log parsing.

#### Scenario: absent provider is reported as unregistered
- **WHEN** a provider name appears in the configured role chain but has not been registered
- **THEN** the effective chain excludes it and the exhaustion diagnostics record `status=skipped` with `skip_class=not_in_registry`

#### Scenario: cooldown skips include remaining time
- **WHEN** a registered provider is still in cooldown during routing
- **THEN** the provider is not invoked and its diagnostic records `skip_class=quota_or_cooldown` plus integer seconds remaining

#### Scenario: provider failures receive typed diagnostics and cooldowns
- **WHEN** a provider raises a timeout, an unavailable error, another provider error, or an unexpected exception
- **THEN** routing classifies the attempt as `timed_out`, conservatively classifies unavailable auth-like errors as `auth_invalid` and other unavailable errors as `endpoint_unreachable`, classifies other provider errors as `provider_error` and unexpected exceptions as `unknown`, and applies the corresponding bounded cooldown before trying the next eligible provider

#### Scenario: exhaustion snapshot records routing policy
- **WHEN** an unpinned non-judge role exhausts all eligible providers
- **THEN** the raised error carries the role, effective chain, serialized attempts, API-key-provider policy, and any active allowlist in `chain_state`

#### Scenario: cooldowns expire locally
- **WHEN** a provider's monotonic cooldown expiry has passed
- **THEN** the next availability check clears that cooldown and treats the provider as available subject to its rolling rate windows

#### Scenario: status exposes best-effort cooldown evidence
- **WHEN** `get_status` can reach the shared router and its quota tracker
- **THEN** top-level `per_provider_cooldown_remaining` contains every provider name present in the configured fallback chains with zero or integer seconds remaining, and a missing router or observation failure yields an empty object instead of failing status

### Requirement: Subscription auth health is conservative, cached, and non-blocking on status reads
The provider layer SHALL expose `subscription_auth_health(provider_name, allow_probe=True)` with `ok`, `not_logged_in`, or `unknown` status and human-readable detail. When `TINYASSETS_AUTH_VIABILITY_PROBE` is not explicitly falsy, Codex health MUST use a layered presence, freshness, and live-viability policy: a missing `CODEX_HOME/auth.json` is `not_logged_in`; a recent parseable `last_refresh`, or the recent mtime of a valid JSON object that omits that field, is `ok`; and stale, corrupt, or suspicious state consults a TTL-cached verdict or one small real `codex exec` probe when probing is allowed. When that flag is falsy, any present `auth.json` yields presence-only `ok` without freshness parsing or probing. Only a recognized dead-auth signature produces `not_logged_in`; missing binaries, timeout, unexpected nonzero exit, or empty output without such a signature are inconclusive and remain `ok` with diagnostic detail. Probe-derived Codex verdicts SHALL be cached beside `auth.json` for cross-process visibility with an in-memory fallback. Claude health SHALL be `ok` for a non-empty OAuth token or populated config directory, `not_logged_in` for an absent, empty, or unreadable config directory without a token, and all unrecognized providers SHALL be `unknown`.

#### Scenario: fresh Codex auth avoids a subprocess
- **WHEN** Codex `auth.json` is a valid object with a parseable `last_refresh` younger than the configured freshness window
- **THEN** health is `ok` with refresh-viability detail and no live probe runs

#### Scenario: valid object without refresh timestamp uses mtime
- **WHEN** Codex `auth.json` is a valid JSON object without a usable `last_refresh` field and its file mtime is fresh
- **THEN** health is `ok` without a live probe, while corrupt JSON or a present unparseable timestamp does not receive that mtime fast path

#### Scenario: stale dead Codex credential is quarantined and shared
- **WHEN** stale or suspicious Codex auth triggers a live probe whose combined output matches a configured dead-auth signature, or whose empty stdout pairs with a broad auth signal on stderr
- **THEN** health is `not_logged_in`, the verdict is cached in memory and best-effort atomically beside `auth.json`, and a separate non-probing process sharing that home can observe the cached dead verdict

#### Scenario: inconclusive Codex probe does not falsely quarantine
- **WHEN** the live probe is unavailable, times out, exits unexpectedly without a dead-auth signature, or returns empty output without an auth signal
- **THEN** health remains `ok` with the inconclusive reason in its detail so only positive dead evidence quarantines the worker

#### Scenario: viability flag disables freshness and probing
- **WHEN** `TINYASSETS_AUTH_VIABILITY_PROBE` is explicitly set to a falsy value and Codex `auth.json` exists
- **THEN** health is presence-only `ok` without reading freshness, consulting cached viability, or running the live probe

#### Scenario: status never launches a live Codex probe
- **WHEN** the chatbot-facing status path reads writer auth health
- **THEN** it calls the health function with probing disabled, consumes presence, freshness, and any cached verdict, and reports stale uncached auth as `ok` with deferred-probe detail instead of blocking on a subprocess

#### Scenario: worker gate owns live quarantine
- **WHEN** a cloud worker is pinned or explicitly assigned to a subscription writer
- **THEN** it performs the probing health check before runtime registration or queue work and self-quarantines only on `not_logged_in`; a generic worker without a resolvable writer is not gated by this check

#### Scenario: status summarizes subscription-writer loss only
- **WHEN** supervisor liveness computes auth health for `codex` and `claude-code`
- **THEN** `provider_auth.writers` contains each status and detail, `all_writers_unauthenticated` is true only when both checked subscription writers are `not_logged_in`, and warnings distinguish that condition from partial subscription-writer loss
- **AND** the roll-up does not inspect `ollama-local` or opted-in API-key providers and MUST NOT be treated as proof that every possible provider route is unavailable

### Requirement: The provider call bridge retries only transient full-chain exhaustion
The shared provider call bridge SHALL retry `AllProvidersExhaustedError` up to three total router attempts with exponential waits bounded from two through eight seconds. It SHALL NOT retry unrelated exceptions. After failure or when no router exists, it SHALL return the caller-supplied fallback response when present and otherwise re-raise the original unrelated error, or raise `AllProvidersExhaustedError` for exhaustion or a missing router, rather than synthesize empty prose.

#### Scenario: Transient exhaustion clears
- **WHEN** the first router attempt raises `AllProvidersExhaustedError` and the second succeeds
- **THEN** the bridge returns the successful provider text after two attempts

#### Scenario: Three exhaustion attempts use the explicit fallback
- **WHEN** all three router attempts raise `AllProvidersExhaustedError` and `fallback_response` is supplied
- **THEN** the bridge returns that fallback response

#### Scenario: Exhaustion without fallback fails loudly
- **WHEN** all router attempts exhaust and no fallback response is supplied
- **THEN** the final `AllProvidersExhaustedError` is raised

#### Scenario: Unrelated exception is not retried
- **WHEN** the router raises an exception other than `AllProvidersExhaustedError`
- **THEN** the bridge performs one router attempt and then returns the supplied fallback or re-raises that exception

#### Scenario: No router preserves fallback semantics
- **WHEN** no router is installed
- **THEN** the bridge returns a supplied fallback immediately or raises `AllProvidersExhaustedError` when no fallback exists

### Requirement: Bubblewrap readiness is a cached two-stage provider probe that selects ordinary Codex mode

`tinyassets.providers.base.probe_sandbox_available` SHALL return a dictionary
with `bwrap_available` and `reason`. It SHALL report unavailable immediately on
win32, when `bwrap` is absent from `PATH`, when `bwrap --version` exits
nonzero, when a minimal `bwrap --ro-bind / / /bin/sh -c true` launch exits
nonzero, or when either subprocess attempt raises; each subprocess SHALL have
a five-second timeout. It SHALL report available with a null reason only when
both subprocesses exit zero.

`get_sandbox_status` SHALL lazily cache and return the first probe dictionary
for the remainder of the process. It returns that same mutable dictionary,
does not refresh it, and does not copy it.

For an ordinary `CodexProvider.complete` call,
`bwrap_available` truthy SHALL select `--sandbox workspace-write`, while falsey SHALL select
`--dangerously-bypass-approvals-and-sandbox`; both modes also include
`--skip-git-repo-check` and `--ephemeral`. A call with
`sandbox_workspace=True` SHALL require a universe directory, a directly
executable CLI, available Bubblewrap, and an auth home inside that universe;
otherwise it SHALL refuse before starting a subprocess. Accepted served calls
use `--sandbox workspace-write` inside the outer OS sandbox.
This probe is a CLI-readiness heuristic, not an OS backend or proof that the
subsequent workload is confined. In particular, an unavailable ordinary call
bypasses Codex approvals and sandboxing rather than failing closed.

#### Scenario: Successful version and functional probes select workspace-write

- **WHEN** `bwrap` is found and its version and minimal launch subprocesses both exit zero
- **THEN** the first cached result is `{"bwrap_available": true, "reason": null}`
- **AND** an ordinary Codex call includes `--sandbox workspace-write` and omits `--dangerously-bypass-approvals-and-sandbox`

#### Scenario: An unavailable probe selects the dangerous bypass

- **WHEN** the cached probe is false because of win32, a missing executable, a nonzero version or launch result, or a probe exception
- **THEN** an ordinary Codex call includes `--dangerously-bypass-approvals-and-sandbox` and omits `--sandbox workspace-write`
- **AND** the result carries a reason for the unavailable classification

#### Scenario: Repeated status reads retain the first mutable result

- **WHEN** `get_sandbox_status` is called repeatedly and a caller mutates the returned dictionary
- **THEN** the underlying probe is invoked once
- **AND** every read returns the same cached dictionary, including the mutation

#### Scenario: Founder-facing sandbox configuration fails closed when confinement is unavailable

- **WHEN** a Codex call has `sandbox_workspace=True` without a universe directory or available Bubblewrap
- **THEN** it raises `ProviderError` rather than selecting the dangerous bypass
- **AND** no Codex subprocess is started

### Requirement: Recognized provider CLI sandbox failures are loud only after earlier quick-exit classification

On non-win32 paths, `tinyassets.providers.base.check_bwrap_failure` SHALL
case-insensitively recognize:
`bwrap: No permissions to create a new namespace`,
`bwrap: No permissions to create new namespace`,
`bwrap: No such file or directory`, and
`sandbox initialization failed`. A match SHALL raise the provider-layer
`SandboxUnavailableError` with at most the first 400 stderr characters and
three remediation options. Empty or unmatched text SHALL pass. On win32 the
helper SHALL be a no-op.

Claude text completion, Claude JSON completion, and Codex completion SHALL pass
stderr through this helper when control reaches their post-communicate sandbox
check, including an exit-zero invocation that emitted a recognized failure.
The check does not dominate every error path: each CLI provider's quick
return-code-1 classification at elapsed time under five seconds occurs first and raises
`ProviderUnavailableError`, so such a Bubblewrap failure is not guaranteed to
retain the sandbox-specific type.

#### Scenario: A recognized exit-zero stderr failure raises the provider sandbox error

- **WHEN** a provider invocation reaches the sandbox check with any recognized signature in mixed-case stderr
- **THEN** it raises `tinyassets.providers.base.SandboxUnavailableError`
- **AND** the error carries a bounded stderr excerpt and remediation guidance

#### Scenario: Normal output and win32 do not trigger the recognizer

- **WHEN** stderr is empty or unmatched, or the process platform is win32
- **THEN** `check_bwrap_failure` returns without raising a sandbox error

#### Scenario: A return-code-1 failure under five seconds is classified before sandbox recognition

- **WHEN** a Claude or Codex subprocess exits with return code 1 at elapsed time under five seconds and its stderr also contains a recognized signature
- **THEN** the provider's earlier quick-exit path raises `ProviderUnavailableError`
- **AND** the sandbox-specific recognizer is not reached for that invocation

### Requirement: Background carrier mint authority is store-proven
The system SHALL mint a background provider carrier only from a one-use,
process-bound proof issued after the durable authority store commits the exact
reservation transition from `reserved` to `launch_started`; receipt, claim,
reservation, identifier, or recomputed digest records alone grant no mint
authority.

#### Scenario: Self-consistent forged reservation grants nothing
- **WHEN** a caller derives a new reservation identifier and invocation key from otherwise valid receipt and claim records, recomputes the reservation digest, and marks the forged record `launch_started`
- **THEN** the forged record cannot obtain a mint proof, mint a carrier, or validate a provider call
- **AND** the durable invocation, token, and cost ledger remains the sole launch authority

#### Scenario: Winning store arm mints once
- **WHEN** the authority store commits the first valid arm of a reserved invocation
- **THEN** it issues one opaque mint proof bound to that exact armed reservation digest and the issuing process
- **AND** mint-proof reuse, launch replay, a different reservation digest, or a different process fails before provider selection

#### Scenario: Carrier cannot cross a process fork
- **WHEN** a carrier or unconsumed mint proof is copied into a process other than its issuer
- **THEN** validation or minting fails before acquiring a copied process lock or selecting a provider

#### Scenario: Registry publication is cleanup-safe
- **WHEN** the system publishes a mint proof or carrier into its active process registry
- **THEN** cleanup is installed before the identity becomes active
- **AND** abandoned-object verification does not depend on immediate reference-count collection

#### Scenario: Packaged runtime preserves the same authority boundary
- **WHEN** provider-carrier authority changes in the canonical runtime
- **THEN** the packaged Claude-plugin model and store enforce byte-equivalent store provenance, one-use, and process boundaries

### Requirement: Providers are open, user-defined definitions; registration is not authority
A universe owner SHALL be able to register a compute provider definition for any reachable provider by describing it (access method, protocol shape, endpoint, model) without a code change or a platform allowlist. A registered definition is an immutable, server-issued-id descriptor and creates ONLY a candidate: it does not enroll, authorize, select, or make the provider routable. `allowed_providers` and selection resolve stable server-issued definition/binding ids, never user-chosen labels.

#### Scenario: registering a novel provider creates a candidate only
- **GIVEN** an owner who registers a provider we never integrated (e.g. Kimi)
- **WHEN** registration succeeds
- **THEN** a `ProviderDefinition` with a server-issued id exists, but the provider is not enrolled, not selected, and not routable until the downstream owners act

#### Scenario: a commons/remixed definition never carries a credential
- **GIVEN** a provider definition published to the commons by another user
- **WHEN** a second user remixes it into their universe
- **THEN** they receive the descriptor only, and must supply their own credential through the custody owner — the original owner's credential is never auto-bound

### Requirement: Access-method executors are selected by provenance with no cross-method fallback
Execution SHALL select an executor deterministically by the definition's access method: `subscription_cli` selects the vendor CLI adapter (preserving the existing `codex exec` sandbox/auth-health/budget/telemetry behavior and the `codex` identity); `api_key_http` selects an HTTP protocol encoder over the SSRF-hardened outbound proxy (never a vendor SDK pointed at an arbitrary `base_url`). A failed subscription-CLI provider SHALL NOT fall back to an SDK/API using ambient credentials.

#### Scenario: api_key_http never bypasses the outbound proxy
- **GIVEN** an `api_key_http` provider with a user-supplied `base_url`
- **WHEN** a turn executes on it
- **THEN** the request goes through the credential-blind outbound proxy with full SSRF enforcement (HTTPS-only, private/loopback/metadata blocked, DNS revalidated, redirects/env-proxies disabled), and the credential ref is bound to the registered endpoint so a changed `base_url` cannot redirect the key

#### Scenario: subscription CLI does not silently degrade to an API
- **GIVEN** a `subscription_cli` provider whose CLI auth is unhealthy
- **WHEN** routing evaluates it
- **THEN** it is skipped by the existing auth-health quarantine — never retried as an API/SDK call on an ambient credential

### Requirement: Capability observations and compliance advisories are not authority
Capability observations and compliance advisories SHALL be advisory only: neither SHALL grant, widen, or veto execution authority, and they MUST only narrow an already-authorized route or inform the UX. Capability observations comprise user-declared capabilities (validated on use), passive health/rate observations from real calls, and at most one bounded same-origin `/models` probe (TTL, per-owner rate/concurrency/cost limited, cache keyed by connection generation). Compliance advisories are freshness-stamped, provenance-carrying "what's allowed" records. Hard prohibitions SHALL be enforced at the access-method/connect boundary, not as a routing-time authority decision.

#### Scenario: an advisory cannot widen authority
- **GIVEN** a compliance advisory marking a provider as "allowed" for a use case
- **WHEN** that provider is outside the `allowed_providers` ceiling or unenrolled
- **THEN** it is still not routable — the advisory does not add authority

#### Scenario: capability filter only narrows
- **GIVEN** a capability observation that a selected provider cannot serve the request
- **WHEN** the router resolves candidates
- **THEN** that provider is removed from the effective set; no new provider is added to compensate

### Requirement: A universe can serve on a registered open compute provider
A universe owner SHALL be able to serve converse/writer turns on a registered open (`api_key_http`) compute provider, authorized SOLELY by the connection grant (no subscription snapshot or custody), through the SAME served-authority / assignment / work-binding / CAS machinery as subscription providers — via one `ServedProviderAuthority` with an explicit `authority_kind` discriminator (`subscription_snapshot` | `connection_grant`), never inferring the open kind from a missing snapshot. The credential SHALL be resolved only inside the credential-blind broker at call time; the control plane holds a grant reference, never the secret. The subscription-CLI serving path SHALL be behaviorally unchanged.

#### Scenario: Open provider serves a converse turn
- **GIVEN** an owner who registered an `api_key_http` provider (`connect_compute`) whose connection grant is current + bound to the universe, and selected it via `set_engine open_provider`
- **WHEN** a converse/writer turn runs for that universe
- **THEN** a `connection_grant`-kind served authority is minted (no snapshot/custody), the turn executes on that provider through the credential-blind proxy, and the reservation is scoped by the work-binding id/generation

#### Scenario: Open serving respects the allowed_providers ceiling
- **GIVEN** an open provider not within the universe's `allowed_providers`
- **WHEN** serving is attempted
- **THEN** it is refused — a minted served authority does NOT bypass the ceiling

#### Scenario: Cross-universe / revoked / substituted grant is refused
- **GIVEN** an open provider whose grant is bound to another universe, revoked, or whose registered executor instance's definition/grant identity does not match the authority
- **WHEN** authorization, reservation, or launch runs
- **THEN** it fails closed (`ProviderAuthorityHeldError`) with no ambient fallback, and a possibly-dispatched request CONSUMES (never releases) its reservation

#### Scenario: An absent open snapshot never becomes open authority
- **GIVEN** a `subscription_snapshot` authority whose snapshot is unexpectedly absent
- **WHEN** it is evaluated
- **THEN** it fails closed — the missing snapshot is NOT treated as a `connection_grant` (kind is explicit, never inferred)

### Requirement: Foreground prompt runs derive exact provider authority from the active serving assignment
A user-authorized foreground Branch run that reaches a prompt node SHALL derive
provider authority from the owner's current ACTIVE serving assignment for that
universe. Each actual provider attempt SHALL use a distinct, one-use run carrier
bounded by the immutable Branch subject, exact provider assignment, owner,
universe, role, invocation budget, token budget, cost budget, expiry, and current
parent binding. Subscription providers SHALL receive only a sealed run-scoped
credential snapshot. Registered open (`api_key_http`) providers SHALL receive no
subscription snapshot and SHALL continue through their current connection-grant
custody and the credential-blind outbound proxy. Provider registration alone
SHALL NOT authorize a foreground run.

#### Scenario: The selected subscription provider runs once
- **GIVEN** a user-authorized foreground Branch run with one prompt node and a current ACTIVE subscription-backed serving assignment whose exact provider is allowed by the node policy
- **WHEN** the node requests its provider completion
- **THEN** one run carrier is reserved and consumed, the selected provider is invoked exactly once with its sealed run-scoped snapshot, and the reservation settles from the actual outcome

#### Scenario: The selected open provider runs once
- **GIVEN** a user-authorized foreground Branch run with one prompt node and a current ACTIVE registered open provider whose connection grant is current, universe-bound, and allowed by the node policy
- **WHEN** the node requests its provider completion
- **THEN** one run carrier is reserved and consumed, and the exact open provider is invoked exactly once through the credential-blind proxy without a subscription snapshot
- **AND** the reservation settles `succeeded` only when the provider supplies complete trustworthy token and cost telemetry; otherwise it settles `indeterminate` and remains conservatively charged without inventing zero-cost usage

#### Scenario: Registration without active serving selection grants nothing
- **GIVEN** a registered open provider that is not the owner's current ACTIVE serving assignment for the run's universe
- **WHEN** a foreground prompt node requests a provider completion
- **THEN** the run fails with `permission_denied:provider_not_bound`, no provider is invoked, and no effect fires

#### Scenario: Any authority mismatch launches nothing
- **GIVEN** a foreground prompt run whose serving authority is missing, stale, revoked, cross-universe, owned by another principal, outside the node policy, or no longer matches the exact current assignment
- **WHEN** provider admission or an attempt is evaluated
- **THEN** the run fails closed with `permission_denied:provider_not_bound`, no different or ambient provider is substituted, and no effect fires

#### Scenario: A refreshed serving assignment replaces stale run-class authority
- **GIVEN** the owner's serving assignment is current and valid, but a deterministic run-class binding remains from an earlier assignment generation or credential
- **WHEN** a foreground prompt node requests its first provider completion
- **THEN** the stale run-class binding is transactionally rebound from the exact current serving authority before the run receipt is admitted
- **AND** the selected provider is invoked under the refreshed binding without widening owner, universe, provider, policy, role, budget, expiry, or settlement authority

### Requirement: A served interactive completion is judged by progress, not a total wall-clock

A served writer completion SHALL be read as an incremental event stream and judged
by an idle watchdog: its deadline resets on ANY recognized protocol event that
proves the provider is actively working — an assistant text delta, a tool
start/result, a documented provider retry event, the terminal result, OR a
recognized non-relayed liveness event (provider/reasoning heartbeat, thinking
progress, hooks, status, stream framing, tool progress, an informational
rate-limit event). It SHALL NOT reset on whitespace, stderr, or unparseable
output. Internal reasoning MAY reset the watchdog as a liveness signal but SHALL
NEVER be relayed into the assembled reply; only assistant text and the terminal
result are relayed. When a documented provider retry event states a retry delay,
the idle budget for that wait SHALL be extended to cover it (so a real provider
retry is not misclassified as a hang). A completion that keeps making progress
SHALL NOT be failed for total elapsed time; a completion that stops making progress
SHALL be ended at the idle boundary. An absolute safety cap MAY end an over-long
interactive turn, but it SHALL be generous enough that a genuinely progressing turn
survives well past the old total deadline, and reaching it SHALL be reported as an
interactive-deadline outcome, not as provider unavailability.

#### Scenario: A long but progressing turn is not timed out

- **WHEN** a served completion keeps emitting protocol events past the old total
  deadline
- **THEN** it continues and is not failed for elapsed time

#### Scenario: A reasoning-only stretch keeps the turn alive

- **WHEN** a served completion emits only recognized reasoning/heartbeat events
  (no assistant text) for longer than the idle interval
- **THEN** the attempt continues (the events are liveness) and their content is
  not relayed into the reply

#### Scenario: A known provider retry wait is not misclassified as a hang

- **WHEN** a documented provider retry event states a retry delay longer than the
  idle interval and the stream then recovers
- **THEN** the attempt is not ended as `provider_idle_timeout` during that wait

#### Scenario: A hung turn is ended at the idle boundary

- **WHEN** a served completion emits no recognized protocol event for the idle
  interval
- **THEN** the attempt is ended and classified `provider_idle_timeout`

#### Scenario: Silence inside a codex turn is the model generating, not idle

- **GIVEN** a codex-served completion (`codex exec --json`), which emits NO
  reasoning or assistant-text deltas — between one protocol event and the next
  there is one whole model round-trip of silence (31s live on 2026-08-29;
  ~100s per round-trip observed), and whose `turn.started` / `item.started` /
  `item.completed` are delivered best-effort (the in-process queue of
  codex-cli 0.146.0 guarantees only `TurnCompleted`, projected as
  `turn.completed` / `turn.failed`; `thread.started` is printed by exec itself
  before the turn is requested)
- **WHEN** any protocol event has been read and no terminal turn event
  (`turn.completed` / `turn.failed`) has arrived yet
- **THEN** the turn is running (`codex exec` runs exactly one) and silence is
  allowed for `min(absolute cap, 900s)` (`_TURN_WAIT_S`, the same bound as a
  tool wait `_TOOL_WAIT_S` — with `item.started` equally droppable, "in a tool"
  and "generating" are not reliably distinguishable); the profile's idle
  interval guards only the launch edge (no event at all within `init_s`)
- **NOTE (as-built boundary):** for codex the idle boundary inside a turn IS
  900s — the CLI offers no finer liveness signal to judge progress by. Two
  signal-less windows share that bound rather than a shorter one: a stall
  between `thread.started` and the `turn/start` request (an in-process RPC,
  never a model wait), and a shutdown that stalls after
  `TurnCompleted(Interrupted)`, which projects no terminal JSONL event (only
  SIGINT interrupts an exec turn; the daemon never sends one). A finished
  stream whose `agent_message` item was dropped under backpressure fails loud
  in `complete()` ("omitted result or usage") —
  `docs/concerns/2026-08-29-codex-agent-message-can-be-dropped-under-backpressure.md`.
  The claude reader does not honor a tool wait; its `tool_phase` is telemetry
  only (`docs/concerns/2026-08-29-claude-reader-tool-wait-idle-gap.md`)

#### Scenario: A completed codex turn is never failed by its own shutdown

- **GIVEN** the reader has read `turn.completed` (or `turn.failed`) — the
  projections of the one guaranteed notification, `TurnCompleted`
- **WHEN** the child has not exited `_TAIL_WAIT_S` (60s) later — codex exec
  unsubscribes the thread and awaits `client.shutdown()`, bounded at 45s in
  0.146.0
- **THEN** the reader ends the child and RETURNS the finished stream; any tool
  left open is closed with the turn; and the caller treats a non-zero exit code
  after a stream that carries `turn.completed` as process trivia (logged, never
  raised — the protocol's word beats the exit code)

#### Scenario: A provider `error` event that may retry is liveness, not termination

- **WHEN** codex emits a top-level `error` event (its `will_retry` flag is not
  projected into the JSONL) while a tool is in flight
- **THEN** the tool stays in flight and the watchdog treats the event as liveness;
  only the terminal `turn.completed` / `turn.failed` close the turn and its
  in-flight tools (verified on codex-cli 0.146.0)

#### Scenario: The served absolute cap is a runaway backstop with per-universe overrides

- **GIVEN** a granted served founder turn (`_sandboxed_config(..., granted=True)`)
- **THEN** its absolute cap is 3600s (`_SERVED_ABSOLUTE_CAP_S`) unless the universe
  context carries a numeric `absolute_cap_s` / `idle_timeout_s`; a non-numeric
  override falls back to the default rather than disabling the cap; non-granted
  paths (the learning extractor) keep the library default profile

### Requirement: Provider failures are classified, and transient attempt timeouts do not cool the provider

Each served attempt outcome SHALL carry a `failure_class` derived from the stream
and process exit — at least `provider_rate_limited`, `provider_overloaded`,
`authority_held`, `provider_idle_timeout`, `interactive_deadline`, and
`provider_protocol_error`. A `provider_idle_timeout` or `interactive_deadline`
SHALL NOT place the sole served writer on a provider-wide cooldown; the next turn
SHALL remain eligible. A genuine `provider_rate_limited`/`provider_overloaded`
SHALL cool the provider until its own retry-after. The interactive request path
SHALL NOT sleep (no synchronous backoff) while holding the inbound request or a
turn-worker slot.

#### Scenario: One idle timeout does not poison the next messages

- **WHEN** a served turn ends with `provider_idle_timeout`
- **THEN** no provider-wide cooldown is applied and the user's next message is
  attempted normally

#### Scenario: A real rate limit is honored

- **WHEN** the stream reports a documented rate-limit/overload retry event
- **THEN** the provider is cooled until its retry-after and the outcome is
  classified `provider_rate_limited`/`provider_overloaded`

### Requirement: The user notice reflects the true failure class, never mislabeling a timeout as capacity

The failure notice delivered to the user SHALL be derived from the structured
`failure_class`. A timeout or interactive-deadline outcome SHALL NOT be presented as
"model capacity" or a rate limit. A completion SHALL NOT be recorded as a completed
assistant response unless a terminal provider result was produced.

#### Scenario: An ended turn is described as ended, and the resend as a repeat

- **WHEN** a served turn ends with `provider_idle_timeout` or `interactive_deadline`
- **THEN** the user notice (`_served_failure_notice`) says the turn was ended and
  that what it finished stands, states that sending again repeats the whole
  request (the turn may already have acted) and that asking it to continue is
  usually better, and never contains "exhausted", "fallback", "capacity" or
  "quota"; every other failure keeps the exception text verbatim
- **AND** the web app keeps the message resendable (the in-flight record is not
  forgotten on a served `error`), shows the server's sentence, and does not
  reload for a new build while a send is in flight (bounded at 3 hours — past
  the default 3600s cap and any plausible per-universe `absolute_cap_s`; a
  fetch that truly never settles is cut by the proxy long before) or a failed
  message is younger than 20 minutes

#### Scenario: A timeout is described honestly

- **WHEN** a turn ends with `provider_idle_timeout` or `interactive_deadline`
- **THEN** the user notice states the model stopped making progress / the reply
  exceeded the interactive window — not that the model is at capacity

### Requirement: Realtime voice transport cannot alter primary-writer routing
Enabling Realtime voice SHALL NOT enroll, select, replace, or fall back to any provider as the universe's primary writer; capability discovery SHALL inspect only the provider already selected by the existing routing equation, every spoken turn SHALL continue to use that writer through `converse`, and the voice bridge SHALL remain auxiliary transport on that provider's existing user-owned connection.

#### Scenario: Current provider advertises realtime transport
- **GIVEN** a universe with an assigned writer whose exact user-owned connection declares authorized `tinyassets.voice.v1` support
- **WHEN** the founder completes a spoken turn
- **THEN** `converse` runs the primary turn on the assigned writer
- **AND** the same provider connection's voice bridge is used only for speech transport and function-call relay

#### Scenario: Assigned writer lacks a compatible voice capability
- **GIVEN** a universe whose assigned writer works but whose current provider exposes no compatible realtime capability
- **WHEN** the founder starts Voice
- **THEN** the writer remains selected and typed conversation continues
- **AND** supported browser/device speech relays recognized text through that same writer's canonical `converse` path
- **AND** TinyAssets does not open provider setup, request a Voice-only credential, infer Realtime API entitlement, or widen to platform compute

#### Scenario: Generic outbound bridge transport is disabled
- **GIVEN** generic outbound HTTP transport is disabled
- **WHEN** the founder starts Voice without compatible current-provider authority
- **THEN** supported browser/device speech remains available because it uses canonical `converse`, not the outbound bridge
- **AND** TinyAssets makes no Voice session request and does not change provider authority

#### Scenario: Another provider has realtime capability
- **WHEN** another connection or provider could supply realtime Voice but is not the current serving provider
- **THEN** capability discovery does not select or call it
- **AND** only an explicit user change through the existing provider-authority path can make it eligible

#### Scenario: Voice bridge fails
- **WHEN** the current provider's bridge is unavailable, exhausted, or unauthorized
- **THEN** the app reports Voice unavailable and preserves typed conversation
- **AND** the router does not substitute an API-key writer or any unselected provider

#### Scenario: General API-key writer allowance remains disabled
- **GIVEN** an exact user-owned Voice capability is ready and `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is disabled
- **WHEN** provider routing selects a writer
- **THEN** the voice allowance does not make API-key writer providers eligible
