## ADDED Requirements

### Requirement: Request execution authority is immutable, principal-bound, and complete
Before any provider-backed phase begins, the server SHALL construct at a trusted server boundary a strict-schema immutable request execution authority bound to: the stable issuer/subject requester principal on whose behalf work runs; the stable issuer/subject actor principal currently performing the action; MCP/OAuth client id as non-authoritative transport provenance when known; every admitted resource-owner principal; explicit delegation ids when owner, requester, or actor differ; a server-issued globally unique request id; canonical digest of the exact operation/target/inputs; universe; `issued_at`/`not_before`/`expires_at` with bounded clock skew; revocation and persistent-policy snapshots; phase invocation/token/time/cost limits; stable tenant-scoped invocation ids; routes; and verified requester-owned grants or accepted market agreements. Request and authority digests SHALL use the versioned `request-execution-authority/v1` domain, RFC 8785 JSON Canonicalization Scheme, and SHA-256. Callers and stored projections SHALL NOT supply or widen authority fields; unknown versions or fields SHALL fail closed. A phase SHALL be executable only when verified resources cover its compute and every separately required model-access capability. A provider route SHALL cover both only when its verified execution contract supplies both.

#### Scenario: complete self-owned authority permits one phase
- **WHEN** the authenticated requester has verified requester-owned compute and all model access required for reply generation
- **THEN** the resolver emits a request authority bound to that requester, request, universe, and reply phase
- **AND** the reply phase may use only grants contained in that authority

#### Scenario: incomplete authority invokes nothing
- **WHEN** verified compute exists but separately required model access is missing
- **THEN** the reply phase is held before provider invocation and identifies `model_access` as missing

#### Scenario: authority cannot cross a universe audience
- **WHEN** a grant or request authority bound to one universe is presented for another universe
- **THEN** the authority is rejected and no provider is invoked

#### Scenario: caller-supplied widening is rejected
- **WHEN** request JSON attempts to add a route, raise a budget, alter a phase, or replace an authority/request digest
- **THEN** boundary validation rejects the input and the trusted authority remains unchanged

#### Scenario: equal caller-visible request ids cannot collide across tenants
- **WHEN** different requester issuer/subject pairs or universes present the same caller-visible request identifier
- **THEN** their server-issued request identities, tenant-scoped invocation identities, reservations, and receipts remain distinct

### Requirement: Universe access and execution delegation are separate authorities
The server SHALL treat universe visibility and ACL grants as content authority only. Spending resources owned by a different user or organization SHALL require an explicit execution delegation bound to resource-owner principal, requester principal, actor principal, universe, allowed operations/phases and provider/model capabilities, budget, validity window, and revocation state. An OAuth/MCP client id is transport provenance only. Organization membership, universe founder/admin status, platform role, client id, or chatbot identity SHALL NOT create or widen that delegation.

#### Scenario: collaborator does not inherit founder compute
- **WHEN** a collaborator may write a founder's universe but has neither self-owned authority nor an explicit execution delegation
- **THEN** provider-backed work is held and the founder's credentials, quota, accounts, and hardware remain ineligible

#### Scenario: narrow organization delegation is honored
- **WHEN** an organization member has a valid organization-resource delegation for one universe and reply phase within a fixed budget
- **THEN** the resolver may admit only the delegated resources for that universe, phase, and budget
- **AND** the acting chatbot cannot widen any constraint

#### Scenario: revoked delegation fails at the invocation boundary
- **WHEN** a delegation was valid during resolution but its revocation epoch changes before provider invocation
- **THEN** the phase is held as `authority_revoked` and no provider is invoked under that delegation

### Requirement: BYOC and market setup keep secrets outside chatbot and MCP payloads
When authority is missing, the server SHALL return non-secret, short-lived setup descriptors for requester-owned enrollment and accepted-market fulfillment. Raw provider credentials, bearer tokens, auth-home contents, and market capability secrets SHALL NOT appear in chatbot messages, canonical-handle arguments, pages, logs, traces, market records, outcomes, or receipts. A setup challenge SHALL be single-use, requester- and universe-bound, non-executable, and re-authenticated at completion. Completion SHALL use same-origin HTTPS, exact redirects, CSRF state, and authorization code plus PKCE for vendor OAuth; it SHALL atomically verify the unused/unexpired challenge, exact issuer/subject, current universe/tenant access and delegation, and credential-store owner. Static secrets SHALL go directly from a masked authenticated form to encrypted KMS/secret-manager custody; plaintext or base64 custody is ineligible. A trusted broker SHALL vend only purpose/route/phase/job-scoped ephemeral secret leases and SHALL destroy them after use. An inbound MCP access token SHALL authenticate TinyAssets only and SHALL NOT be stored, exchanged, forwarded upstream, or treated as provider, market, or execution authority.

#### Scenario: held first contact offers safe setup
- **WHEN** first-contact birth completes but no complete execution authority exists
- **THEN** the result is `held/setup_required` with the new `universe_id`, missing resource kinds, and non-secret BYOC and market setup descriptors
- **AND** no secret is requested in chat or passed to a canonical handle

#### Scenario: leaked setup challenge cannot execute
- **WHEN** another principal obtains a setup challenge identifier or URL
- **THEN** the enrollment flow rejects that principal after authentication
- **AND** the challenge alone cannot authorize or invoke a provider

#### Scenario: revoked access blocks setup completion
- **WHEN** a requester loses universe or tenant access after a setup challenge is issued but before completion
- **THEN** completion is rejected without attaching a credential or grant to that universe

#### Scenario: successful setup requires fresh resolution
- **WHEN** the requester completes out-of-band enrollment or market acceptance
- **THEN** the original held request remains non-executable
- **AND** retry resolves a fresh authority rather than mutating the held authority

#### Scenario: legacy raw-key input is rejected
- **WHEN** a caller sends a raw API key through `set_engine`, `converse`, `write_graph`, or another MCP/chat JSON field
- **THEN** the server rejects the secret input and directs the requester to authenticated out-of-band enrollment without persisting or echoing the key

#### Scenario: MCP bearer token is not upstream authority
- **WHEN** a valid MCP access token authenticates the requester's TinyAssets session
- **THEN** the token may establish requester identity but is never sent to a provider or market, stored as a resource grant, or accepted as execution authority

#### Scenario: insecure credential custody is rejected
- **WHEN** an enrollment backend can store a secret only as plaintext or base64, or can vend an unscoped or retained secret lease
- **THEN** setup cannot complete with that backend and no execution grant is created

### Requirement: Accepted-market authority requires a mandate and exact execution agreement
An accepted-market resource SHALL become request authority only by verifying and admitting an exact execution agreement or lease already created and reserved by the owning paid-market/distributed-execution capability inside an authenticated requester purchase mandate. This authority seam SHALL NOT rank offers, accept offers, reserve capacity/budget, form training groups, or settle payment. The mandate SHALL bind its id/digest, requester and optional bounded actor delegation, target universe and request audience, exact resource/model capability id/version/digest and phases, execution interface/route, allowed venues/providers, privacy/compliance/locality and license/access predicates, normalized integer maximum unit and total all-in spend with explicit unit/currency, `issued_at`/`not_before`/`expires_at`, and bounded clock skew. The agreement SHALL bind the mandate id/digest, accepted offer, accepting actor principal and optional delegation id, acceptance timestamp/idempotency proof, provider/daemon identity and key, reserved capacity, locked normalized integer price/fees and unit basis, capability/manifest/terms digests, allocation or escrow reference, validity and revocation state, typed predicate evidence, sender binding, and current lease fence. Each positive agreement, delegation, grant, and authority-bearing predicate SHALL derive authority from an M1 purpose-separated signature or M3 fresh external verification with registered issuer/trust basis, provider/endpoint/hardware subject binding, and issued/expiry times. M2 content digests MAY bind exact mandate, terms, capability, or evidence bytes inside that verified authority but SHALL NOT establish acceptance, issuer authority, delegation, compliance, or truth alone. Quotes, advertisements, matches, price indexes, mandates, self-attested labels, or platform reachability alone SHALL NOT confer authority.

#### Scenario: cheapest quote is not authority
- **WHEN** routing discovers a lowest-price adequate offer but neither the requester nor an explicitly bounded delegate accepted and reserved it inside the mandate
- **THEN** the offer remains ineligible and no provider is invoked from it

#### Scenario: bounded delegate agreement is admitted by proof
- **WHEN** an already-created exact agreement records a bounded actor's acceptance, mandate proof, locked price, and current reservation inside every delegated constraint
- **THEN** the authority resolver may admit that agreement after verifying the proof and current intersection

#### Scenario: accepted agreement permits only the mandate intersection
- **WHEN** the requester accepts a verified provider agreement satisfying one mandate's model capability, universe, reply phase, privacy tier, and price ceilings
- **THEN** the resolver may admit it only inside the intersection of mandate and agreement constraints

#### Scenario: stale self-attested compliance claim is not authority
- **WHEN** a price- and capability-matching offer asserts ZDR, HIPAA, residency, or another authority-bearing predicate without trusted fresh subject-bound evidence
- **THEN** the offer cannot satisfy that predicate and is excluded or held

#### Scenario: matching digest without positive authority is rejected
- **WHEN** an unsigned or self-authored agreement, delegation, or compliance record has a perfectly matching content digest but no M1 signature or M3 verification
- **THEN** the digest binds those bytes but creates no execution authority

#### Scenario: admission cannot create or repair a reservation
- **WHEN** concurrent admission attempts reference an agreement whose paid-market reservation is missing, stale, superseded, or not the current fenced winner
- **THEN** the resolver holds every invalid attempt and cannot create, repair, or choose a reservation

#### Scenario: replayed or superseded market evidence is rejected
- **WHEN** an accepted agreement's replay identity was consumed, its fence was superseded, or its validity expired
- **THEN** the agreement is ineligible even if its original signed or stored record is still reachable

#### Scenario: only a complete current training group is admitted
- **WHEN** an already-formed group agreement for `hardware class × interconnect tier × gang size × window` has frozen full compatible membership, one current window/fence, and one group allocation/escrow identity
- **THEN** the resolver may admit the group only while every recorded member and proof remains current

#### Scenario: separate compute and model agreements must be compatible
- **WHEN** compute and model access come from separate agreements that differ in exact capability/model identity, execution interface, phase, audience, overlapping validity, privacy/locality, or license/access terms
- **THEN** they do not compose and the phase is held before provider invocation

#### Scenario: pre-agreement market material is never consumed as authority
- **WHEN** a quote, demand, match, or pre-agreement workload-content reference reaches the authority resolver without an exact accepted agreement
- **THEN** it is rejected as non-authoritative and the resolver does not dereference or disclose the workload content

### Requirement: Every phase revalidates the intersection of persistent and request authority
For each provider invocation, the server SHALL derive eligibility as the intersection of the persistent engine ceiling, verified request grants or exact accepted agreements, phase requirements, and current policy/privacy constraints. Each boundary SHALL only narrow authority. Immediately before invocation it SHALL re-check the authority and exact-request digest, ceiling version/digest, request and universe audience, phase scope, `not_before`/expiry with bounded skew, revocation, evidence status, current lease fence, and budget or capacity reservation. It SHALL atomically reserve a stable tenant-scoped invocation id domain-separated over schema, requester issuer/subject, universe, server request id, request digest, operation, phase, and ordinal plus its budget before dispatch. That id SHALL survive authority re-resolution; duplicate or outcome-unknown retries under the same or a replacement authority SHALL NOT create a second unaccounted spend. Provider selection, retries, fallbacks, and model substitution SHALL remain inside the resulting set and SHALL NOT rediscover ambient resources.

#### Scenario: request grant cannot widen persistent ceiling
- **WHEN** a valid request grant names a provider excluded by the universe's persistent engine ceiling
- **THEN** that provider remains ineligible and the phase is held if no intersection remains

#### Scenario: persistent ceiling is not positive request authority
- **WHEN** the persistent engine ceiling names a provider but the requester has no verified resource grant for it
- **THEN** the provider remains ineligible and no ambient credential is used

#### Scenario: fallback narrows without escape
- **WHEN** an admitted provider fails and another admitted provider remains eligible for the phase
- **THEN** routing may try the second admitted provider
- **AND** it never tries a reachable provider outside the authority intersection

#### Scenario: authority expires between phases
- **WHEN** reply generation succeeds but the authority expires before learning extraction
- **THEN** the reply is preserved, extraction is held as `authority_expired`, and no provider is invoked for extraction

#### Scenario: duplicate invocation cannot spend twice
- **WHEN** concurrent or retried dispatches use the same stable request/operation/phase/ordinal invocation identity
- **THEN** at most one atomic reservation can dispatch and consume budget
- **AND** an unknown upstream outcome remains reserved until idempotent reconciliation resolves it

#### Scenario: authority replacement does not reset spend state
- **WHEN** expiry, revocation, or policy change causes fresh authority resolution for the same logical request and invocation
- **THEN** the replacement authority reuses the stable invocation identity and cannot redispatch a consumed or outcome-unknown slot

#### Scenario: separately initiated graph run gets new authority
- **WHEN** a user starts `run_graph` after a `converse` request
- **THEN** the graph run receives a new request id, exact operation/input digest, invocation identities, and authority
- **AND** it cannot inherit the conversation authority

### Requirement: Phase outcomes and authority receipts are typed, linked, and redacted
The server SHALL return a typed `success`, `partial`, `held`, or `failed` outcome linked by request, authority, universe, stable invocation, and phase identifiers. `held` SHALL mean no authorized provider attempt began; `failed` SHALL mean an authorized attempt began and MAY include `provider_exhausted`. Each attempted provider invocation SHALL extend the race-safe provider result object with an append-only idempotent receipt identifying the stable invocation id, authority/request digests, universe and turn/run, phase/ordinal, provider and model, redacted route/endpoint-audience digest, authority class, redacted requester/actor/resource-owner and mandate/agreement/grant/evidence references, timestamps, outcome including `unknown`, upstream idempotency id, normalized integer usage and cost with explicit unit/currency, quoted and actual all-in price and fee split, group/budget allocation and lease fence, policy digest, and revocation epoch. A canonical private endpoint MAY appear only in a tenant-private access-controlled receipt class required by policy. Receipts SHALL NOT contain prompts, completions, emails, raw secrets, authorization headers, bearer tokens, endpoint queries, setup challenges, auth-home contents, or process-global last-provider state. A receipt SHALL record a decision and SHALL NOT grant authority or release payment. Settlement SHALL reference the exact agreement, terminal independently verified execution evidence, and canonical oracle/transaction receipt; provider self-report SHALL NOT suffice, and unknown outcomes SHALL remain fenced until reconciliation.

#### Scenario: reply succeeds while extraction is held
- **WHEN** authority covers reply generation but not learning extraction
- **THEN** the outcome is `partial`, returns the reply, and records extraction as held
- **AND** linked phase records show that no uncovered extraction provider was invoked

#### Scenario: concurrent calls keep their own receipts
- **WHEN** two requests invoke different providers concurrently
- **THEN** each returned result carries only its own request, authority, phase, provider, and grant references
- **AND** receipt persistence cannot swap providers through shared process state

#### Scenario: retry does not duplicate a receipt
- **WHEN** the same invocation result is persisted more than once with the same receipt identity
- **THEN** storage remains idempotent and records one logical receipt

#### Scenario: receipt cannot release settlement alone
- **WHEN** a provider receipt exists without terminal independently verified execution evidence and the canonical settlement oracle or transaction receipt
- **THEN** payment remains fenced even when the provider reports success

#### Scenario: held without an authorized pool is not provider exhaustion
- **WHEN** authority is missing, expired, revoked, over budget, or empty before any authorized provider attempt
- **THEN** the outcome reports the corresponding authority hold reason and does not report `provider_exhausted`

#### Scenario: authorized provider exhaustion is failed, not held
- **WHEN** at least one authorized provider attempt begins and every admitted provider fails
- **THEN** the outcome is `failed` with `provider_exhausted` and retains the attempted invocation receipts

### Requirement: Provider adapters default-deny ambient credential and compute surfaces
For explicit request authority, every provider adapter SHALL declare and isolate its API-key environment, CLI subscription authentication, home/profile/config directories, cloud credential chains and metadata, local sockets, hardware devices, in-process clients, and brokered market capabilities. The invocation environment SHALL start from a minimal allowlist with empty auth/profile roots and receive only the approved phase resource; it SHALL NOT copy ambient state and delete known names, and any isolation error SHALL fail closed. Self-hosted endpoint authority SHALL require a canonical HTTPS audience, explicit requester ownership or consent, controlled redirects, and SSRF, DNS-rebinding, cloud-metadata, and cross-origin protections. Every remote or accepted-market grant SHALL be sender-bound at each use to the authenticated executor through DPoP, mTLS, or the distributed-execution device-key signed-request mechanism; proof-of-possession is mandatory even when the mechanism differs. An adapter with an unknown or undeclared credential or compute surface SHALL be ineligible. Project-maintainer, project-founder, platform-operator, and unrelated tenant resources SHALL never be used for requester workloads or tests.

#### Scenario: hostile ambient resources remain ineligible
- **WHEN** maintainer API keys, subscription homes, cloud profiles, local model sockets, and accelerator hardware are reachable by the host process but absent from request authority
- **THEN** none is exposed to or selected by the provider invocation

#### Scenario: unknown provider surface fails closed
- **WHEN** a provider adapter cannot declare how it discovers credentials or compute
- **THEN** the adapter is excluded from explicit-authority execution

#### Scenario: untrusted self-hosted endpoint is ineligible
- **WHEN** an endpoint uses an unsafe scheme, userinfo, fragment, unauthorized private or metadata address, DNS-rebinding result, or cross-origin redirect
- **THEN** endpoint authority is rejected before any credential or workload is sent

#### Scenario: cross-daemon market grant replay is rejected
- **WHEN** a different daemon or key presents a copied remote or accepted-market grant reference
- **THEN** sender-binding verification rejects the invocation before workload or credential release

#### Scenario: private endpoint is redacted from ordinary receipts
- **WHEN** an authorized private or LAN endpoint is used
- **THEN** ordinary outcomes, logs, and receipts expose only its redacted route or audience digest

#### Scenario: verification uses fake authority only
- **WHEN** contract, concurrency, replay, fallback, or receipt tests run before live acceptance
- **THEN** they use fake providers and fake grants without real provider keys, subscriptions, quota, hardware, market funds, or maintainer resources
