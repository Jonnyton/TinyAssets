# Provider Routing

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

Role-based LLM fallback chains terminating at the local model, subscription-only by default, with pinning, per-universe preference and privacy allowlists, auth-health quarantine, per-node policy overrides, and a parallel judge ensemble.

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

### Requirement: Subscription-only provider policy by default
API-key-backed providers (`gemini-free`, `groq-free`, `grok-free`) SHALL be dropped from every chain unless `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is truthy; TinyAssets daemons are subscription-only by default. When this policy removes every provider from a chain, the router SHALL raise `AllProvidersExhaustedError` rather than silently attempting an API-key provider. Primary writers are `claude -p` / `codex exec` subprocesses, never API SDKs (project hard rule).

#### Scenario: api-key providers ignored by default
- **WHEN** `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is unset and a chain contains only API-key-backed providers
- **THEN** the router raises `AllProvidersExhaustedError`
- **AND** the error text states the daemon is subscription-only unless the flag is set

#### Scenario: opt-in re-enables api-key providers
- **WHEN** `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is truthy
- **THEN** `gemini-free`, `groq-free`, and `grok-free` remain eligible in the chain

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

### Requirement: The provider call bridge retries every full-chain exhaustion by exception type
When a router is installed, the shared provider call bridge SHALL retry every `AllProvidersExhaustedError`, including subclasses, for up to three total router attempts. It SHALL use `wait_exponential(multiplier=1, min=2, max=8)` between retryable failures. If all three attempts are needed, it SHALL wait two seconds after the first `AllProvidersExhaustedError` and two seconds after the second, and SHALL perform no wait after the terminal third failure. Retry eligibility SHALL depend on the exception type rather than a transient/permanent cause classification, so permanent policy, allowlist, pinned-provider, credential, and no-eligible-provider exhaustion can also delay the final result for up to three attempts. The bridge SHALL NOT retry unrelated exceptions. After terminal router failure, it SHALL return any caller-supplied non-`None` fallback response, including an empty string, and otherwise re-raise the final original exception. When no router exists, it SHALL make no retry attempts, return a non-`None` fallback response when supplied, and otherwise raise `AllProvidersExhaustedError`, rather than synthesize empty prose.

#### Scenario: Exhaustion clears on a later attempt
- **WHEN** the first router attempt raises `AllProvidersExhaustedError` and the second succeeds
- **THEN** the bridge returns the successful provider text after two attempts

#### Scenario: Three exhaustion attempts use the explicit fallback
- **WHEN** all three router attempts raise `AllProvidersExhaustedError` and `fallback_response` is supplied
- **THEN** the bridge returns that fallback response

#### Scenario: Permanent exhaustion is also retried
- **WHEN** the router represents a permanent policy, allowlist, pinned-provider, credential, or no-eligible-provider failure as `AllProvidersExhaustedError`
- **THEN** the bridge retries that exception for up to three total router attempts before returning a supplied fallback or raising the final exhaustion error

#### Scenario: Exhaustion without fallback fails loudly
- **WHEN** all router attempts exhaust and no fallback response is supplied
- **THEN** the final `AllProvidersExhaustedError` is raised

#### Scenario: Unrelated exception is not retried
- **WHEN** the router raises an exception other than `AllProvidersExhaustedError`
- **THEN** the bridge performs one router attempt and then returns the supplied fallback or re-raises that exception

#### Scenario: No router preserves fallback semantics
- **WHEN** no router is installed
- **THEN** the bridge returns a supplied fallback immediately or raises `AllProvidersExhaustedError` when no fallback exists
