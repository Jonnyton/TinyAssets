## ADDED Requirements

### Requirement: Provider bridge receipts are immutable and result-local
The provider call bridge SHALL expose a result-returning operation whose immutable result contains the response text and one immutable provider-attempt receipt for that exact invocation. The existing `call_provider(...)` operation MUST delegate to the same result-producing path while continuing to return only `str` and preserving its current fallback text and exception behavior. Each receipt SHALL carry an opaque call ID, routing role, call phase, outcome, route condition, final response evidence, and ordered immutable attempt entries. `outcome` SHALL identify how text or failure completed as `provider_success`, `explicit_fallback`, `forced_mock`, `degraded_sentinel`, `exhausted`, or `error`; `route_condition` SHALL independently identify `none`, `chain_exhausted`, `router_missing`, or `provider_error`. Receipt attribution MUST come only from the `ProviderResponse` and attempt evidence threaded through that invocation; `_last_provider`, any other process-global last-call state, and later status observations MUST NOT populate receipt fields.

#### Scenario: Legacy string caller remains compatible
- **WHEN** an existing caller invokes `call_provider(...)` on a successful, explicit-fallback, forced-mock, degraded-judge-sentinel, or error path
- **THEN** it observes the same string return type, exact configured fallback, mock, or degraded-sentinel text, and exception type that the bridge contract provided before receipts
- **AND** it is not required to understand the result or receipt types

#### Scenario: Result-aware caller receives its own evidence
- **WHEN** the result-returning operation completes through a provider
- **THEN** its result contains the provider text and the receipt built from that same provider response
- **AND** provider, model, family, degraded state, and latency are not read from a global last-call slot

#### Scenario: Interleaved calls cannot exchange receipts
- **WHEN** two provider bridge invocations overlap and complete in either order
- **THEN** each result or raised error retains a distinct call ID and its own immutable receipt
- **AND** neither receipt contains provider, model, family, attempt, credential, authority, role, or phase evidence from the other invocation

### Requirement: Receipt identity and authority fields are typed and secret-free
Every provider-attempt receipt SHALL distinguish `provider`, `model`, and `family` as separate final-response fields copied from the successful `ProviderResponse`, with all three absent when no provider produced the returned text. Each invoked attempt and successful final response SHALL classify `credential_kind` as `llm_subscription`, `llm_api_key`, `local`, `none`, or `unknown`, and `authority_class` as `universe`, `host`, `local`, `none`, or `unknown`. `universe` SHALL mean authority resolved from the explicitly selected universe vault or its materialized auth home; `host` SHALL mean host process authority used only when no universe is resolved; `local` SHALL mean no external credential was required; `none` SHALL mean no provider authenticated; and `unknown` SHALL mean the mechanism or origin was not proven. Classification MUST be captured at the credential-resolution/provider-execution boundary for that exact call and MUST NOT be inferred from a provider name or ambient state observed after completion.

#### Scenario: Universe subscription classification is call-local
- **WHEN** a remote provider succeeds using subscription material resolved for an explicit universe
- **THEN** the successful attempt and final receipt report `credential_kind=llm_subscription` and `authority_class=universe`
- **AND** a concurrent host-local or other-universe call cannot change those values

#### Scenario: Host authority is invalid for a universe-scoped remote success
- **WHEN** an explicit universe is resolved for a successful remote provider call
- **THEN** its receipt MUST NOT report `authority_class=host`
- **AND** implementation of this invariant remains blocked until #1606 / R2-1a or its declared successor settles the fail-closed routing boundary

#### Scenario: Local and synthetic classifications are not remote authority
- **WHEN** a local provider succeeds
- **THEN** its receipt reports `credential_kind=local` and `authority_class=local`
- **AND WHEN** text comes from an explicit fallback or forced-mock path
- **THEN** final provider, model, and family are absent and the receipt reports `credential_kind=none` and `authority_class=none`

#### Scenario: Pre-resolution skip is not guessed
- **WHEN** a provider is skipped before its credential mechanism or authority origin is resolved
- **THEN** the attempt reports `credential_kind=unknown` and `authority_class=unknown`
- **AND** it does not infer either classification from the provider name

#### Scenario: Receipt redaction excludes secret-bearing material
- **WHEN** any success, skip, failure, fallback, mock, missing-router, or exhaustion receipt is produced
- **THEN** neither the receipt nor its attempt entries contain tokens, keys, base64 credential material, cookies, authorization headers, environment values, credential record IDs, auth-home paths, prompts, completions, or raw exception text
- **AND** failures are represented only by stable non-secret outcome and reason classes

### Requirement: Fallback and exhaustion receipts preserve bounded attempt history
One provider-attempt receipt SHALL aggregate attempts in routing order across every bounded full-chain retry wave for the bridge invocation. Each attempt SHALL identify its retry ordinal, provider, `succeeded`, `failed`, or `skipped` status, stable non-secret reason class, and credential/authority classification known at that boundary. A provider success SHALL set `outcome=provider_success` and `route_condition=none`. An explicit fallback SHALL set `outcome=explicit_fallback` while preserving prior attempts, leaving final provider/model/family absent, and reporting `route_condition=chain_exhausted`, `provider_error`, or `router_missing` according to why routing stopped. Forced mock SHALL set `outcome=forced_mock` and `route_condition=none`. When the canonical single-judge path exhausts and returns its degraded quality-floor sentinel, the receipt SHALL set `outcome=degraded_sentinel` and `route_condition=chain_exhausted`, retain the ordered attempts, leave final provider/model/family absent, and report `credential_kind=none` and `authority_class=none`; the synthetic `none` / `quality-floor-only` response markers MUST NOT be represented as a winning provider identity. A missing router SHALL be distinguishable from an exhausted installed router. Final exhaustion without fallback outside that judge sentinel path MUST continue to raise `AllProvidersExhaustedError` with `outcome=exhausted`, and the raised error SHALL carry the immutable receipt without changing the existing exception type. An unrelated exception MUST retain its existing type and retry behavior, use `outcome=error` and `route_condition=provider_error` when a receipt is attached, and MUST NOT be masked or replaced by receipt handling.

#### Scenario: Later retry wave succeeds
- **WHEN** an earlier full-chain wave exhausts and a later bounded retry wave succeeds
- **THEN** the returned receipt reports `outcome=provider_success`
- **AND** contains the earlier skipped or failed attempts followed by the successful wave in routing order

#### Scenario: Explicit fallback preserves failed routing evidence
- **WHEN** provider routing exhausts or errors and the caller supplied a fallback response
- **THEN** the result returns that exact fallback text with `outcome=explicit_fallback`
- **AND** retains any attempts made before fallback without claiming a winning provider, model, family, credential, or authority

#### Scenario: Exhaustion without fallback remains loud and inspectable
- **WHEN** every bounded retry wave exhausts and no fallback response exists
- **THEN** the bridge raises `AllProvidersExhaustedError` with `outcome=exhausted` and `route_condition=chain_exhausted` on its attached receipt
- **AND** the receipt contains the ordered redacted attempt history without synthesizing response text

#### Scenario: Exhausted judge preserves its degraded sentinel contract
- **WHEN** the canonical single-judge path exhausts and returns its stable quality-floor sentinel
- **THEN** the bridge returns the exact existing sentinel text with `outcome=degraded_sentinel` and `route_condition=chain_exhausted`
- **AND** the receipt retains the ordered redacted attempt history without claiming a final provider, model, family, credential, or authority

#### Scenario: Missing router is not chain exhaustion
- **WHEN** no router is installed
- **THEN** a supplied fallback returns with `outcome=explicit_fallback` and `route_condition=router_missing`, or absence of fallback raises the existing exhaustion error with `outcome=exhausted` and that route condition
- **AND** the receipt does not claim that a provider was attempted

### Requirement: Reply and learning calls retain separate phase receipts
The result-aware bridge SHALL accept `reply`, `learning`, or `unspecified` as its call phase, defaulting generic callers to `unspecified`. Universe intelligence MUST invoke its founder-facing writer call with phase `reply` and its separate learning-extraction writer call with phase `learning`. Its result-aware internal turn operation SHALL retain the reply text and the ordered per-phase receipts, while the existing `converse(...)` surface continues to return only the reply string. A learning failure SHALL remain non-fatal to an already produced reply and MUST NOT overwrite, relabel, or replace the reply receipt.

#### Scenario: Successful turn has independently attributable phases
- **WHEN** a universe turn completes both the founder-facing reply call and the learning-extraction call
- **THEN** the result-aware turn contains one `reply` receipt and one distinct `learning` receipt
- **AND** each reports the provider, model, family, credential kind, authority class, and attempts for its own call

#### Scenario: Learning failure preserves reply evidence
- **WHEN** the reply call succeeds and the learning call later exhausts or errors
- **THEN** the founder-facing reply remains available with its unchanged `reply` receipt
- **AND** the learning outcome is represented separately and cannot be mistaken for the provider that produced the reply

#### Scenario: Concurrent turns keep both phase pairs isolated
- **WHEN** two universe turns interleave their reply and learning calls
- **THEN** each turn retains only its own result-local `reply` and `learning` receipts
- **AND** completion order cannot cross-assign either phase

### Requirement: Provider-attempt receipts have no implicit durable or public sink
Provider-attempt receipts introduced by this change SHALL remain transient on the in-memory result or raised error. The implementation MUST NOT persist or emit them to application logs, a database, run receipts, wiki pages, conversation history, or an MCP response. Any durable, logged, or public sink requires a separate OpenSpec change that names the owning capability and defines authorization and visibility, correlation keys, schema versioning, retention and deletion, size and cardinality limits, redaction, sink-failure behavior, and whether the evidence is operator-only or user-visible.

#### Scenario: Result-aware call performs no receipt side effect
- **WHEN** a result-aware provider call succeeds, falls back, is forced-mock, or raises
- **THEN** its receipt exists only on the returned result or raised error
- **AND** no receipt record is written or publicly emitted by this change

#### Scenario: Existing run receipt store is not selected implicitly
- **WHEN** implementation considers durable storage for a universe conversation that has no guaranteed run ID
- **THEN** it does not write the provider-attempt receipt into the generic run receipt store
- **AND** first requires the separate sink change and its authorization, retention, and correlation decisions
