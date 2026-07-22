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
The router SHALL apply per-universe configuration resolved from an explicit `universe_context` when supplied, otherwise from the process-global universe config. Every successful `set_engine` action that selects a concrete provider SHALL persist `allowed_providers` containing only that provider in addition to `preferred_writer`. A BYO key/provider mismatch SHALL be rejected. Universe-scoped routing SHALL filter out every cloud provider whose credential is not resolvable from the universe vault, including per-node policy attempt orders, and SHALL fail closed rather than fall back to ambient host credentials. `preferred_writer` / `preferred_judge` SHALL reorder the eligible chain, while the allowlist SHALL filter it; `None` preserves the otherwise eligible chain.

#### Scenario: allowlist blocks third-party providers
- **WHEN** a universe sets `allowed_providers=["ollama-local"]`
- **THEN** a `writer` call attempts only `ollama-local`
- **AND** `claude-code`, `codex`, and the api-key providers are not attempted

#### Scenario: empty filtered chain hard-fails, no leak
- **WHEN** `allowed_providers` excludes every provider in the resolved chain
- **THEN** the router raises `AllProvidersExhaustedError` referencing `allowed_providers`
- **AND** no provider is called

#### Scenario: Selected founder engine cannot fall through to host credentials

- **GIVEN** a founder sets a Claude engine with their Anthropic key
- **WHEN** Claude fails
- **THEN** the router does not attempt Codex or any other provider outside `allowed_providers=["claude-code"]`

#### Scenario: BYO key cannot select an incompatible provider

- **GIVEN** an Anthropic key and `preferred_writer="codex"`
- **WHEN** `set_engine` validates the assignment
- **THEN** it rejects the mismatch and does not modify the vault or config

#### Scenario: Unbound host daemon does not authorize platform credentials

- **GIVEN** a founder selects `engine_source="host_daemon"`
- **AND** no founder-hosted runtime credential has been bound yet
- **WHEN** `set_engine` persists the selection
- **THEN** it records the preferred provider with `allowed_providers=[]` and a pending binding status
- **AND** universe calls fail closed rather than use ambient platform credentials

### Requirement: Public provider and credential-payer receipts

Every provider-served public `converse` or `run_graph` operation SHALL expose a non-secret receipt naming the serving provider and credential payer class/owner. `converse` SHALL label its reply and learning-extraction calls separately. Because `run_graph` is asynchronous and may make zero to many calls, enqueue SHALL report `provider_receipt_status="pending"`; the durable run snapshot SHALL expose one receipt per provider-served node after calls occur. Receipts SHALL NOT contain tokens, secret values, or credential file contents.

#### Scenario: Converse reports both paid calls

- **WHEN** a founder conversation produces a reply and runs learning extraction
- **THEN** the response contains two purpose-labelled receipts with provider, credential class, and owner

#### Scenario: Async graph reports pending then durable per-node receipts

- **WHEN** `run_graph` enqueues a run
- **THEN** its immediate response reports pending receipt state without claiming an unserved provider
- **AND WHEN** `get_run` is called after provider-served nodes execute
- **THEN** it returns their durable provider/payer receipts

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
