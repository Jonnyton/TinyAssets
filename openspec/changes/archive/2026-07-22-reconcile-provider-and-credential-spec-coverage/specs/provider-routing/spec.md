## ADDED Requirements

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
