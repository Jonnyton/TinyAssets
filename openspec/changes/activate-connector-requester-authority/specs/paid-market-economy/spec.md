## ADDED Requirements

### Requirement: Explicit accepted agreement is the only market input to engine activation

The paid-market owner SHALL convert a current explicitly accepted quote into
an immutable accepted-agreement result before engine activation may commit.
Quote discovery, live-price ranking, a bid, match, claim, reservation,
scheduling record, payment intent, or free queue selection MUST NOT by itself
grant spend, provider, host, capacity, or execution authority.

The accepted terms SHALL bind the route-selection receipt ID/digest, quote
ID/version/digest, immutable
fulfillment descriptor ID/version/digest, currency, positive
`max_total_minor`, fee-schedule version, demand-commitment digest,
acceptance-policy digest, quote expiry, authenticated actor, tenant, and exact
universe. The caller's acceptance object is a confirmation commitment, not a
source of canonical market facts.

#### Scenario: current bounded terms become an accepted agreement

- **WHEN** the authenticated universe writer confirms a current quote whose canonical terms exactly match the closed acceptance object and remain within the stated spend cap
- **THEN** the paid-market owner returns an immutable agreement bound to the actor, tenant, universe, quote, descriptor, currency, cap, fees, demand, policy, and expiry
- **AND** that agreement still grants no B2 execution authority by itself

#### Scenario: ranking or match cannot activate an engine

- **WHEN** the system has a ranked quote, bid, match, claim, payment intent, or scheduling record but no explicit current accepted agreement
- **THEN** accepted-market engine activation is refused with no assignment mutation

### Requirement: Acceptance is revalidated at the atomic activation boundary

Immediately before commit, the paid-market owner SHALL re-resolve and compare
the canonical route-selection receipt, quote and descriptor versions/digests,
currency, spend cap, fee schedule, demand commitment, acceptance policy,
expiry, cancellation, availability, capacity fence, and
actor/tenant/universe scope. Caller-supplied expiry MUST NOT extend the
canonical expiry, and stale or changed terms MUST require a newly explicit
acceptance.

The accepted agreement and current non-executable B13-bound activation grant
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

Accepted-market activation SHALL scope idempotency by authenticated actor,
tenant, universe, action, and idempotency key. Replaying the same key with the
same canonical acceptance body SHALL return the original outcome without
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

- **WHEN** the accepted agreement cannot obtain or retain valid market and B2/B13 authority
- **THEN** activation or execution holds without charging or invoking any maintainer credential, quota, wallet, or compute
