# Provider Routing

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

Role-based LLM fallback chains terminating at the local model, subscription-only by default, with pinning, per-universe preference and privacy allowlists, auth-health quarantine, per-node policy overrides, and a parallel judge ensemble.
## Requirements
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
`bwrap_available` truthy SHALL select `--full-auto`, while falsey SHALL select
`--dangerously-bypass-approvals-and-sandbox`; both modes also include
`--skip-git-repo-check` and `--ephemeral`. A call with
`sandbox_workspace=True` SHALL refuse before probing or selecting either mode.
This probe is a CLI-readiness heuristic, not an OS backend or proof that the
subsequent workload is confined. In particular, an unavailable ordinary call
bypasses Codex approvals and sandboxing rather than failing closed.

#### Scenario: Successful version and functional probes select full-auto

- **WHEN** `bwrap` is found and its version and minimal launch subprocesses both exit zero
- **THEN** the first cached result is `{"bwrap_available": true, "reason": null}`
- **AND** an ordinary Codex call includes `--full-auto` and omits `--dangerously-bypass-approvals-and-sandbox`

#### Scenario: An unavailable probe selects the dangerous bypass

- **WHEN** the cached probe is false because of win32, a missing executable, a nonzero version or launch result, or a probe exception
- **THEN** an ordinary Codex call includes `--dangerously-bypass-approvals-and-sandbox` and omits `--full-auto`
- **AND** the result carries a reason for the unavailable classification

#### Scenario: Repeated status reads retain the first mutable result

- **WHEN** `get_sandbox_status` is called repeatedly and a caller mutates the returned dictionary
- **THEN** the underlying probe is invoked once
- **AND** every read returns the same cached dictionary, including the mutation

#### Scenario: Founder-facing sandbox configuration refuses before mode selection

- **WHEN** a Codex call has `sandbox_workspace=True`
- **THEN** it raises `ProviderError` before consulting Bubblewrap readiness
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

### Requirement: Provider routing uses one assigned credential authority
Every universe-scoped provider call SHALL carry exactly one current server-resolved authority: an authenticated served request, an armed background binding, or the daemon's assigned-serving-credential context. The router SHALL attempt only the provider named by that authority and SHALL NOT read a process writer pin, fallback chain, free-provider chain, preferred-provider order, or ambient host credential to widen the route.

The assigned context SHALL carry the actual provider-work binding identity, generation, digest, assignment generation/digest, revocation generation, custody identity, and durable token/cost/invocation ceilings. The router SHALL require the canonical serving binding's `converse`/`writer` scope and SHALL reserve and reconcile durable binding spend for assigned calls. When an armed background invocation carrier is also present, its provider, assignment generation/digest, custody digest, and revocation generation SHALL match the assigned context; its exact operation and role SHALL validate without substitution, and the effective token ceiling SHALL be the lower of the binding and invocation ceilings. The serving binding validates credential assignment; the separately store-minted workflow carrier authorizes its internal operation and role without changing the selected credential.

#### Scenario: Assigned credential is the only attempted provider
- **WHEN** a daemon branch run carries an assigned credential for provider `codex`
- **THEN** the router attempts only `codex`
- **AND** a registered Claude, API-key, or local provider is never attempted for that run

#### Scenario: Missing authority holds before provider access
- **WHEN** a universe-scoped call has no current serving or background credential authority
- **THEN** it raises the typed provider-authority hold before invoking any provider

#### Scenario: Assigned provider exhaustion does not widen
- **WHEN** the provider selected by the assigned credential is unavailable, rate-limited, or exhausted
- **THEN** the call fails with evidence for that provider and does not attempt another registered provider

#### Scenario: Binding and invocation ceilings both apply
- **WHEN** an assigned workflow call also carries a single-use background invocation reservation
- **THEN** the carrier's declared operation and role are validated exactly
- **AND** the call is refused when it exceeds either the invocation ceiling or the assigned binding's remaining durable budget

#### Scenario: Retired router constructor option fails loudly
- **WHEN** a caller supplies a retired fallback, pin, or auth-health router option
- **THEN** router construction raises `TypeError` naming the retired option

### Requirement: Node policy cannot change credential authority
Per-node LLM policy SHALL be allowed to refine non-authority model settings, but any policy provider preference SHALL be ignored or rejected when it differs from the provider named by the run's assigned credential.

#### Scenario: Policy names a different provider
- **WHEN** a workflow node prefers Claude while the serving binding assigns Codex
- **THEN** the node runs only on Codex or holds
- **AND** Claude is not invoked

#### Scenario: Retired fallback-chain policy is rejected
- **WHEN** a branch policy contains `fallback_chain`
- **THEN** validation fails loudly and no provider is invoked
- **AND** the user is directed to model alternatives as explicit workflow branches with independently assigned credentials
