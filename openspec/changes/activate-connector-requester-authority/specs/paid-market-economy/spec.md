## ADDED Requirements

### Requirement: Explicit accepted agreement is the only market input to engine activation

The paid-market owner SHALL expose the internal tenant-scoped
`paid_market.accept_agreement_v1` producer, which converts a current canonical
request plus current explicitly accepted quote into an immutable
accepted-agreement result before engine activation may commit. It is not an
MCP action. This producer SHALL be distinct from request submission, bidding,
matching, claiming, and delivery and MUST NOT resubmit or reinterpret any of
those operations as explicit acceptance.
Quote discovery, live-price ranking, a bid, match, claim, reservation,
scheduling record, payment intent, or free queue selection MUST NOT by itself
grant spend, provider, host, capacity, or execution authority.

The accepted terms SHALL bind the canonical request ID/version/digest,
route-selection receipt ID/digest, quote ID/version/digest, immutable
fulfillment descriptor ID/version/digest, currency, positive
`budget_micros`, positive `spend_cap_micros` not exceeding that budget,
fee-schedule version, demand-commitment digest, acceptance-policy digest,
settlement-policy version, deadline, quote expiry, authenticated actor, tenant,
and exact target universe derived from the current authorized activation
scope. The producer SHALL rehydrate the canonical request's
capability digest, payload digest, bid-window close, acceptance policy,
settlement policy, visibility, and fanout. The caller's acceptance object is a
confirmation commitment, not a source of canonical market facts.
The canonical request's `requester_user_id` MUST equal the current
authenticated OAuth subject and its `tenant_id` MUST equal the current
authorized tenant. `MarketRequest` has no universe field: the accepted
agreement SHALL bind the target universe separately from the server-derived
current activation authority and MUST NOT infer universe scope from request
contents. Delegation requires a separately verified owner grant and cannot be
inferred from request contents.

#### Scenario: current bounded terms become an accepted agreement

- **WHEN** the authenticated universe writer confirms a current quote whose canonical request and quote terms exactly match the closed acceptance object and remain within the stated micros-denominated budget and spend cap
- **THEN** the paid-market owner returns an immutable agreement bound to the actor, tenant, universe, request, quote, descriptor, currency, budget, spend cap, fees, demand, acceptance/settlement policy, deadline, and expiry
- **AND** that agreement still grants no B2 execution authority by itself

#### Scenario: ranking or match cannot activate an engine

- **WHEN** the system has a ranked quote, bid, match, claim, payment intent, or scheduling record but no explicit current accepted agreement
- **THEN** accepted-market engine activation is refused with no assignment mutation

#### Scenario: canonical requester must equal current authenticated subject

- **WHEN** the canonical request's requester user or tenant differs from the current authenticated subject/tenant, or the target universe differs from the server-derived exact authorized activation scope
- **THEN** `paid_market.accept_agreement_v1` refuses before agreement or assignment mutation
- **AND** request contents, a match, or caller-supplied identity cannot impersonate the requester

### Requirement: Acceptance is revalidated at the atomic activation boundary

Immediately before commit, the paid-market owner SHALL re-resolve and compare
the canonical request, route-selection receipt, quote and descriptor
versions/digests, currency, budget, spend cap, fee schedule, demand commitment,
acceptance and settlement policies, deadline, expiry, cancellation,
availability, capacity fence, and
actor/tenant/universe scope. Caller-supplied expiry MUST NOT extend the
canonical expiry, and stale or changed terms MUST require a newly explicit
acceptance.

The accepted agreement and provisional non-executable B13-bound
bounded-market mandate SHALL either compose through the provider-routing
assignment owner's atomic activation transaction, which makes the mandate
reference current, or publish no activation state/current mandate. A concrete
later job still requires its own exact B2 grant. Market selection SHALL NOT
silently move the user to a free, BYOC, maintainer, local, desktop, or
differently priced lane.

#### Scenario: terms change before commit

- **WHEN** price, fees, descriptor, demand envelope, policy, currency, expiry, capacity, or scope differs from the explicitly accepted canonical version at commit time
- **THEN** activation is refused as stale or conflicting and the user must accept current terms
- **AND** no accepted-market remote-ready assignment is published

#### Scenario: cancellation or capacity loss wins the race

- **WHEN** quote cancellation, expiry, revocation, or capacity-fence loss commits before activation
- **THEN** activation loses, returns a typed refusal, and publishes no partial agreement-to-engine binding

### Requirement: Market activation is bounded and idempotent without spending maintainer resources

Accepted-market activation SHALL use a domain-separated
`write_graph/engine/activate_accepted_market` idempotency namespace and then
scope by authenticated actor, tenant, universe, and idempotency key. That
namespace MUST NOT collide with request admission or another target/action.
The owner SHALL compute `activation_body_digest` as lowercase SHA-256 over
`UTF8("tinyassets/connector-market-activation/v1\0")` followed by the RFC 8785
JSON Canonicalization Scheme bytes for the exact closed projection
`{"target":"engine","action":"activate_accepted_market","graph_id":graph_id,
"market_acceptance":market_acceptance}`. `market_acceptance` in that projection
contains exactly the v1 fields named by the connector-surface requirement; the
top-level `idempotency_key` is excluded from the body projection because it is
bound separately in the idempotency identity. No transport envelope,
authorization header, omitted/defaulted field, rendering, or unknown field
participates. A new projection, algorithm, or domain requires a new activation
schema version.
Current authenticated subject, tenant, exact-universe write/admin authority,
current-message handler claim, and liveness SHALL be verified before any
idempotency lookup. Authority loss SHALL return a non-enumerating denial that
reveals neither key existence nor historical result.
Replaying the same key with the same `activation_body_digest` SHALL return
the original outcome without
duplicating an agreement, reservation, charge, grant request, or assignment.
Reusing the key with a different canonical body MUST return a conflict.
Concurrent first activations SHALL have one authoritative outcome.
A historical success SHALL NOT reactivate or preserve expired, revoked,
fenced, cancelled, or held authority. Replay output SHALL distinguish the
historical idempotent commit from re-derived current assignment state.

No platform, founder, or maintainer provider quota, credential, wallet, or
compute SHALL satisfy, subsidize, retry, or backstop the accepted agreement.
Payment custody, escrow, verification, settlement, refunds, and reputation
remain with their owning market contracts.

#### Scenario: identical retry is side-effect stable

- **WHEN** a connector retries the same activation key with an RFC-8785-equivalent exact activation-body projection after an ambiguous response
- **THEN** it receives the original typed outcome and no economic or engine side effect is duplicated

#### Scenario: authorization precedes replay lookup

- **WHEN** a subject loses tenant or exact-universe authority and supplies a key that may or may not have a historical activation result
- **THEN** the owner returns the same non-enumerating denial before lookup and discloses no key or result existence

#### Scenario: historical success cannot render stale current readiness

- **WHEN** same-body replay finds a historical success but the committed mandate or assignment is now held, expired, revoked, fenced, or cancelled
- **THEN** the result reports a historical idempotent commit plus the current held/repair state
- **AND** replay performs no reactivation, renewal, spend, reservation, or execution mutation

#### Scenario: maintainer resources cannot cover a failed market path

- **WHEN** the accepted agreement cannot obtain or retain valid mandate, per-job market/funding/capacity, and B2 authority
- **THEN** activation or execution holds without charging or invoking any maintainer credential, quota, wallet, or compute

### Requirement: Every concrete job produces fresh logical market authority for cross-owner composition

The paid-market owner SHALL treat activation as a non-executable bounded
mandate, not a reusable quote, market allocation, capacity reservation, or
real-fund authority. After a later message establishes exact job demand and
quantity, it SHALL consume the live-price/transport owner's fresh executable
firm quote and exact request-bound bid, deterministic match, atomic paid
claim/fan-out slot, selected host/owner, versions, digests, quote-to-bid link,
and fences. It SHALL revalidate descriptor, demand, quantity, landed total,
currency, fee schedule, service terms, expiry, and remaining
`budget_micros`/`spend_cap_micros`, then atomically record only its
job-bound logical budget reservation/accounting intent.

The domain owner alone creates and fences capacity. The separately reviewed
wallet/chain-effect successor required by
`docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6 alone
produces requester-owned or explicitly delegated real-fund
reservation/receipt authority. `paid-market-economy` MUST NOT create, consume,
release, settle, or refund either resource. B13 consumes and binds all
owner-native results plus distributed-execution S14/B36; none may promote
itself into execution authority.

The cross-owner job identity SHALL bind activation, actor, tenant, universe,
canonical request/bid/match/claim/slot, selected host, job, demand/quantity,
lease fence, and idempotency key. Each owner SHALL serialize only its resource
and expose body-bound idempotent prepare/commit/cancel results. Same-job retries
reuse those results; changed-body reuse conflicts. No B2 becomes observable
until every owner result is current.

The distributed-execution B13 production composition root SHALL own the one
global dispatch/cancel CAS/fence that chooses
`reserved -> dispatch_committed` or
`reserved -> cancelled_and_released`. If cancellation wins, B2 is absent or
revoked and every owner releases its reservation exactly once. If dispatch
wins, pre-dispatch release is forbidden. Later settlement/refund SHALL consume
the current platform-signed `ExecutionTerminalV1`, including its current
generation/fence and distributed-execution owner-CAS completion proof, plus
domain acceptance bound to `job_id:lease_fence:accepted_result_sha256`; host
self-attestation or generic accepted-use text is insufficient.

#### Scenario: exact job composes owner-native authority without owner theft

- **WHEN** the transport owner has a current request-bound quote/bid/match/paid-claim/slot and selected host, the domain owner has current fenced capacity, paid-market has one logical budget reservation, and the §18.6 successor has current requester real-fund authority for the same exact job identity
- **THEN** B13 may seal those exact owner-native identities, versions, digests, fences, and S14/B36 identity into the capsule and B2 request
- **AND** the B2 daemon/host equals the current paid claimant and none of the inputs grants execution authority by itself

#### Scenario: concurrent jobs cannot oversubscribe any owner

- **WHEN** two jobs contend for a paid claim slot, logical budget, domain capacity, or requester funds that can satisfy only one
- **THEN** each owning contract serializes its own resource, B13 observes at most one complete current result set, and the loser holds before B2 creation
- **AND** paid-market never claims that its logical reservation proves conserved capacity or real-fund custody

#### Scenario: cancellation and dispatch have one fenced winner

- **WHEN** cancellation races B2 creation or dispatch for a reserved job
- **THEN** the B13-owned global dispatch/cancel fence commits exactly one of `dispatch_committed` or `cancelled_and_released`
- **AND** the losing path cannot release active work, dispatch cancelled work, double-consume, double-charge, or double-refund

#### Scenario: settlement requires signed terminal and domain evidence

- **WHEN** a dispatched job reaches settlement or refund
- **THEN** the owning contracts require the current platform-signed `ExecutionTerminalV1`, its current generation/fence and distributed-execution owner-CAS completion proof, and domain acceptance for the exact `job_id:lease_fence:accepted_result_sha256`
- **AND** a host claim, mutable row, or generic accepted-use assertion cannot move logical or real funds

#### Scenario: allocation price capacity or funding drift requires repair

- **WHEN** the quote-to-bid link, match, claim, slot, selected host, fee/currency/policy, logical budget, domain capacity, requester funding, or any current fence is absent or changed
- **THEN** the job holds with a typed owner-specific repair or new-acceptance requirement and no B2 grant is created
- **AND** no maintainer or alternative fulfillment lane silently substitutes
