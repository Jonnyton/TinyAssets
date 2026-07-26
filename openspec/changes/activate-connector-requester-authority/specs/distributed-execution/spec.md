## ADDED Requirements

### Requirement: Accepted-market activation binds B13 readiness without pre-minting job authority

The accepted-market activation owner SHALL consume a bounded, revocable,
non-executable provisional mandate created through the sole B13 production
composition root and bound to the authenticated owner, tenant, target
universe, accepted agreement, route-selection/pricing policy, mandate-wide
budget, per-job spend ceiling, expiry, revocation generation, and idempotency
digest. The mandate SHALL become current and discoverable only through the
atomically committed activation reference. Failed commits SHALL idempotently
revoke or expire their provisional mandate, and retries MUST NOT accumulate
active mandates. The owner MUST NOT
mint or store a B2 execution grant before a concrete job and capsule exist.
For each later job, only the B13 root may coordinate the owner-native results
and create the exact B2 grant. It SHALL require the live-price/transport
owner's request-bound quote, bid, deterministic match, paid claim/fan-out slot,
selected host/owner, versions, digests, quote-to-bid link, and current fences;
the domain owner's fenced capacity; `paid-market-economy`'s logical budget
reservation/accounting intent; and the full-platform architecture §18.6
wallet/chain-effect successor's requester real-fund authority. The sealed
capsule and B2 grant SHALL bind all of those identities plus owner, tenant,
universe, agreement, mandate, demand, quantity, fee/spend-ledger identity,
`job_id:lease_fence:accepted_result_sha256`, daemon, job, capsule digest,
lease, generation/fence, capability ceiling, expiry, and idempotency identity.
The B2 daemon/host SHALL equal the current paid claimant. B13 coordinates but
MUST NOT write, invent, or promote another owner's authority.

OAuth identity, market quotes/agreements, payment state, requests, queue rows,
scheduling leases/heartbeats, host descriptors, provider-attempt receipts,
admission receipts, sandbox diagnostics, legacy `market_rented` metadata,
fake/test D0 records, and user-authored automation state MAY narrow or reject
execution but MUST NOT be promoted into a B2 grant.

#### Scenario: complete B13 mandate binds the remote assignment

- **WHEN** the B13 production root returns a provisional non-executable mandate bound to the exact accepted agreement, selection policy, budget, per-job spend ceiling, and target universe
- **THEN** activation may atomically store its opaque reference and publish `engine_source="accepted_market"`, `engine_assignment_state="remote_ready"`, and `allowed_providers=[]`
- **AND** the connector result exposes no grant, signature, lease capability, or internal authority carrier

#### Scenario: failed activation cannot strand current mandate authority

- **WHEN** B13 creates the provisional mandate but the activation transaction loses or fails before its reference commits
- **THEN** that mandate never becomes current or discoverable and is idempotently revoked or allowed to expire
- **AND** same-body retry reuses the same provisional identity rather than minting cumulative mandate authority

#### Scenario: activation and market state cannot execute by themselves

- **WHEN** a mandate, quote, agreement, bid, match, claim, slot, payment record, Request, BranchTask, scheduling claim, user automation, provider-attempt receipt, or admission receipt exists without the complete exact owner-native per-job result set and current B2 grant
- **THEN** no external execution lease, provider call, candidate acceptance, or terminal fact is authorized

### Requirement: Accepted-market converse dispatch precedes and bypasses ordinary provider routing

For `engine_source="accepted_market"`, each `converse` execution decision SHALL
re-derive the current accepted agreement and B13-bound mandate, derive exact
job demand/quantity, and use B13 to coordinate and verify the request-bound
quote/bid/match/paid-claim/slot/selected-host result, domain-fenced capacity,
logical budget reservation/accounting intent, §18.6 real-fund result, and
S14/B36 settlement identity before obtaining the B2 grant for the sealed
concrete job/capsule. Only that exact B2 grant SHALL enter the signed
remote-execution seam before the ordinary provider router, and the ordinary
provider ceiling/chains MUST NOT be consulted for that work.

An empty `allowed_providers` list in `remote_ready` state means remote-only
dispatch under a current mandate, complete exact owner-native allocation,
logical-accounting, domain-capacity, real-fund, and S14/B36 authority, and an
exact B2 grant; it MUST NOT mean ambient permission to use maintainer,
requester-host, local, BYOC, free, environment-selected, or role-default
providers.

#### Scenario: valid accepted-market universe executes remotely

- **WHEN** the next authenticated `converse` targets an accepted-market universe whose agreement and mandate are current, every named owner supplies its exact current job result, the current paid claimant equals the B2 daemon/host, and B13 returns the matching grant
- **THEN** that concrete job dispatches through the signed remote seam without invoking the ordinary provider router

#### Scenario: empty provider list never falls through

- **WHEN** accepted-market state contains `remote_ready + []`
- **THEN** only a current mandate plus the complete exact allocation/logical-budget/domain-capacity/real-fund/S14-B36 result set and matching B2 can authorize work, and no ordinary provider chain or maintainer resource is attempted

### Requirement: Cancellation and dispatch have one fenced winner

Before B2 becomes observable, the B13 production composition root SHALL own
and require one global dispatch/cancel CAS/fence transition from `reserved` to exactly one of
`dispatch_committed` or `cancelled_and_released`. If cancellation wins, B2
SHALL be absent or revoked and each owning contract SHALL release its prepared
result exactly once. If dispatch wins, pre-dispatch release SHALL be forbidden
and later settlement/refund SHALL require the current platform-signed
`ExecutionTerminalV1`, including its current generation/fence and
distributed-execution owner-CAS completion proof, plus domain acceptance
bound to `job_id:lease_fence:accepted_result_sha256`. Host self-attestation
and generic accepted-use text MUST NOT satisfy settlement.

#### Scenario: cancellation wins before dispatch

- **WHEN** cancellation commits `cancelled_and_released` before the dispatch fence
- **THEN** B13 creates no usable B2 or revokes an unpublished one, all prepared owner results release once, and dispatch cannot commit

#### Scenario: dispatch wins before cancellation

- **WHEN** B13 commits `dispatch_committed` with every current owner result and exact B2 binding
- **THEN** pre-dispatch release is refused and any later cancellation follows the fenced terminal settlement/refund path

### Requirement: Invalid remote authority holds and downgrades without widening

At activation and every later execution sink, the system SHALL fail closed on
an absent, expired, revoked, cancelled, superseded, fenced, consumed,
overspent, inconsistent, or unverifiable mandate, per-job quote/capacity/
funding result, or B2 grant. The assignment owner SHALL atomically downgrade
stale `remote_ready` to `held + []`, preserve signed economic/execution
evidence and monotonic generation/fence facts, and return a typed
accepted-market repair or renewal cause. Rollback or recovery MUST NOT convert
a quote, market agreement, mutable row, legacy source, request, scheduling
lease, or fake key into positive authority.

#### Scenario: activation or job revocation races first converse

- **WHEN** mandate revocation, funding/capacity loss, per-job B2 revocation, or a higher generation/fence commits before the first accepted-market `converse` authority decision
- **THEN** execution does not start, stale `remote_ready` becomes `held + []`, and the connector receives a typed accepted-market repair cause
- **AND** no local, BYOC, free, maintainer, desktop, or ordinary-router fallback occurs

#### Scenario: signer or verifier outage preserves fail-closed state

- **WHEN** current mandate, per-job market/funding/capacity, or B2 authority cannot be verified because an owning signer, trust root, or verifier is unavailable
- **THEN** work remains held and rollback does not widen or reinterpret authority

### Requirement: Market authority does not bypass per-job execution admission

Every accepted-market job SHALL still satisfy the independent
distributed-execution capability preflight, capsule binding, lease and
generation/fence checks, runner/backend enforcement assertions, and applicable
sandbox admission before dispatch. A market agreement or B2 grant MUST NOT be
treated as sandbox-readiness evidence, while an admission or sandbox receipt
MUST NOT become B2 authority.

#### Scenario: grant without execution admission cannot run

- **WHEN** a current accepted-market mandate, exact per-job market/funding/capacity results, and B2 grant exist but capability preflight, capsule binding, sandbox admission, or runner enforcement evidence is incomplete
- **THEN** the job fails closed before backend or provider dispatch
- **AND** the market agreement and grant do not promote the missing admission evidence

#### Scenario: admission receipt without grant cannot run

- **WHEN** a job has valid admission and sandbox evidence but lacks its current mandate, exact per-job market/funding/capacity results, or matching B2 grant
- **THEN** no remote execution occurs because admission can only narrow or reject execution authority
