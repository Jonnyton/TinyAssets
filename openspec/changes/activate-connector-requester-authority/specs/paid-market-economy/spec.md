## ADDED Requirements

### Requirement: Explicit accepted agreement is the only market input to engine activation

The paid-market owner SHALL expose an explicit accepted-agreement producer
that converts a current canonical request plus current explicitly accepted
quote into an immutable accepted-agreement result before engine activation may
commit. This producer SHALL be distinct from request submission, bidding,
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
and exact universe. The producer SHALL rehydrate the canonical request's
capability digest, payload digest, bid-window close, acceptance policy,
settlement policy, visibility, and fanout. The caller's acceptance object is a
confirmation commitment, not a source of canonical market facts.

#### Scenario: current bounded terms become an accepted agreement

- **WHEN** the authenticated universe writer confirms a current quote whose canonical request and quote terms exactly match the closed acceptance object and remain within the stated micros-denominated budget and spend cap
- **THEN** the paid-market owner returns an immutable agreement bound to the actor, tenant, universe, request, quote, descriptor, currency, budget, spend cap, fees, demand, acceptance/settlement policy, deadline, and expiry
- **AND** that agreement still grants no B2 execution authority by itself

#### Scenario: ranking or match cannot activate an engine

- **WHEN** the system has a ranked quote, bid, match, claim, payment intent, or scheduling record but no explicit current accepted agreement
- **THEN** accepted-market engine activation is refused with no assignment mutation

### Requirement: Acceptance is revalidated at the atomic activation boundary

Immediately before commit, the paid-market owner SHALL re-resolve and compare
the canonical request, route-selection receipt, quote and descriptor
versions/digests, currency, budget, spend cap, fee schedule, demand commitment,
acceptance and settlement policies, deadline, expiry, cancellation,
availability, capacity fence, and
actor/tenant/universe scope. Caller-supplied expiry MUST NOT extend the
canonical expiry, and stale or changed terms MUST require a newly explicit
acceptance.

The accepted agreement and current non-executable B13-bound bounded-market mandate
SHALL either compose with the engine assignment in one atomic activation
outcome or publish no activation state. A concrete later job still requires
its own exact B2 grant. Market selection SHALL NOT silently move the user to a
free, BYOC, maintainer, local, desktop, or differently priced lane.

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
Replaying the same key with the same canonical acceptance body SHALL return
the original outcome without
duplicating an agreement, reservation, charge, grant request, or assignment.
Reusing the key with a different canonical body MUST return a conflict.
Concurrent first activations SHALL have one authoritative outcome.

No platform, founder, or maintainer provider quota, credential, wallet, or
compute SHALL satisfy, subsidize, retry, or backstop the accepted agreement.
Payment custody, escrow, verification, settlement, refunds, and reputation
remain with their owning market contracts.

#### Scenario: identical retry is side-effect stable

- **WHEN** a connector retries the same activation key and byte-equivalent canonical acceptance after an ambiguous response
- **THEN** it receives the original typed outcome and no economic or engine side effect is duplicated

#### Scenario: maintainer resources cannot cover a failed market path

- **WHEN** the accepted agreement cannot obtain or retain valid mandate, per-job market/funding/capacity, and B2 authority
- **THEN** activation or execution holds without charging or invoking any maintainer credential, quota, wallet, or compute

### Requirement: Every concrete job consumes fresh bounded market and requester-funding authority

The paid-market owner SHALL treat activation as a non-executable bounded
mandate, not a reusable firm quote or capacity reservation. After a later
message establishes exact job demand and quantity, the owner SHALL obtain and
verify a fresh executable firm quote under the accepted selection policy,
revalidate its descriptor, demand, quantity, landed total, currency, fee
schedule, service terms, expiry, and capacity fence, and atomically reserve or
consume both conserved capacity and requester-owned or explicitly delegated
funding within the mandate's remaining `budget_micros` and per-job
`spend_cap_micros`. Those owner-native quote, capacity, funding, fee, and spend
references/digests SHALL be available for sealing into the job capsule and B2
derivation. A platform, maintainer, founder, provider, or mutable row MUST NOT
substitute for requester funding or conserved capacity.

The job economic identity SHALL bind activation, actor, tenant, universe, job,
canonical demand/quantity, and idempotency key. Same-job retries SHALL reuse
the original reservation/consumption outcome; changed-body reuse SHALL
conflict. Concurrent jobs SHALL serialize against remaining mandate budget and
capacity. Cancellation or failure before dispatch SHALL release both
reservations exactly once. After dispatch, settlement SHALL charge only
owner-verified accepted use and release or refund unused reserved value under
the owning wallet/settlement contracts.

#### Scenario: exact job receives executable economic authority

- **WHEN** a concrete job has a fresh executable quote matching its exact demand and quantity, current capacity, requester funding, and remaining mandate limits
- **THEN** the market owner atomically records one job-bound capacity consumption and one requester-funded spend reservation
- **AND** the returned references/digests grant no execution authority until B13 seals them into the exact capsule and B2 grant

#### Scenario: concurrent jobs cannot oversubscribe mandate or capacity

- **WHEN** two jobs concurrently contend for budget or capacity that can satisfy only one
- **THEN** one atomic reservation wins and the loser holds before B2 creation
- **AND** total reserved or settled value and capacity never exceed the mandate or conserved supply

#### Scenario: retry cancellation and settlement are exactly-once

- **WHEN** the same job retries after an ambiguous response, cancels before dispatch, or settles after verified execution
- **THEN** it reuses the original reservation identity, never double-consumes capacity or funds, and releases, charges, or refunds each reserved unit exactly once

#### Scenario: price or funding drift requires repair

- **WHEN** the fresh job quote exceeds the accepted per-job or remaining budget policy, the fee/currency/policy changes, requester funding is unavailable, or capacity is no longer executable
- **THEN** the job holds with a typed market repair or new-acceptance requirement and no B2 grant is created
- **AND** no maintainer or alternative fulfillment lane silently substitutes
