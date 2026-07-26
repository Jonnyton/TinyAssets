## ADDED Requirements

### Requirement: Durable provider work bindings are non-bearer authorization intent
The system SHALL represent authorization for later provider-capable work as a server-owned `ProviderWorkBinding` whose identifier and serialized fields do not themselves authorize provider, credential, outbound-proxy, auth-health, or quota access.

#### Scenario: Queue identity cannot authorize provider work
- **WHEN** a caller presents a run ID, branch-task ID, queue claim, lease, actor string, schedule ID, subscription ID, receipt ID, or serialized receipt fields without a current server-issued authority receipt
- **THEN** the system holds before every provider authority sink

#### Scenario: Deferred request records intent while request authority is live
- **WHEN** an authenticated connector request authorizes work that will execute after request middleware returns
- **THEN** the system records the bounded work binding transactionally while the current request subject and target authorization are still available
- **AND** the deferred worker receives no inherited or snapshotted request capability

### Requirement: Provider work receipts form a closed bounded union
The system SHALL mint a short-lived `ProviderWorkAuthorityReceipt` for one logical work attempt as exactly one of `universe_work` or `maintainer_maintenance`, with server-owned lifetime, operation, provider-role, invocation, token, and cost ceilings.

#### Scenario: Universe work receipt is fully bound
- **WHEN** the system mints a `universe_work` receipt
- **THEN** it binds the receipt to the current binding and generation, authorized principal and actor or daemon, universe, branch, run and operation lineage, assignment generation and digest, provider binding digest, allowed operation and provider-role set, ceilings, issuer, receipt identity, and revocation generation

#### Scenario: Unknown receipt variant is rejected
- **WHEN** a provider-capable path receives a receipt whose variant is absent from the closed union
- **THEN** the system rejects it before any authority sink

#### Scenario: Receipt scope cannot widen
- **WHEN** work retries, falls back, or creates child work
- **THEN** each resulting attempt uses a fresh receipt or reservation whose operation, provider roles, lineage, depth, lifetime, and budgets are no broader than its authorized parent and current binding

### Requirement: Fresh issuance revalidates durable authority
The system SHALL mint each provider-work receipt just in time from a current binding only after atomically revalidating binding state and digest, principal and actor authority, work lineage, physical work location, provider assignment, revocation state, remaining budget, and eligible runtime.

#### Scenario: Stale assignment blocks issuance
- **WHEN** the current assignment generation, ceiling, provider binding, or assignment digest differs from the binding
- **THEN** receipt issuance fails closed
- **AND** no stale receipt is reconstructed or refreshed

#### Scenario: Cancelled or moved work blocks issuance
- **WHEN** the universe, branch, run, or operation is cancelled, unauthorized, or physically inconsistent with the claimed work
- **THEN** receipt issuance fails before provider authority becomes available

#### Scenario: Binding revocation blocks future attempts
- **WHEN** a binding is revoked, expired, or superseded
- **THEN** the system mints no new receipts from it even if an older task, lease, or process later resumes

### Requirement: Cross-process receipt transfer is an atomic server claim
The system SHALL keep provider-work authority in a server-owned `ProviderWorkAuthorityStore` and SHALL use only an opaque receipt identifier, one-use claim nonce, worker and runtime audience, and expiry for process handoff.

#### Scenario: Authorized worker claims once
- **WHEN** the intended worker presents the unexpired opaque handoff to the authority store
- **THEN** the store atomically consumes the nonce, establishes the execution claim, and reconstructs a non-serializable receipt inside the claimed scope

#### Scenario: Replay or wrong audience fails closed
- **WHEN** a handoff is replayed, expired, or presented by a different worker or runtime audience
- **THEN** the claim fails before provider authority becomes available

#### Scenario: Public and queue artifacts remain authority-free
- **WHEN** branch-task JSON, public connector payloads, environment variables, logs, or scheduler records are inspected
- **THEN** they contain no bearer receipt, reusable claim nonce, credential, or equivalent provider authority

### Requirement: One execution claim owns a receipt
The system SHALL permit at most one active `ProviderWorkExecutionClaim` for a receipt across tasks, threads, and processes, and SHALL never let heartbeat or lease renewal extend the receipt's absolute lifetime or budget.

#### Scenario: Concurrent claim race has one winner
- **WHEN** two workers concurrently claim the same receipt
- **THEN** exactly one claim succeeds atomically
- **AND** the loser cannot reserve or launch a provider invocation

#### Scenario: Provably dead pre-launch owner is reclaimable
- **WHEN** the current claim owner is provably dead and no invocation for the receipt reached `launch_started`
- **THEN** the system may atomically expire the old claim and issue a bounded replacement claim

#### Scenario: Ambiguous launch is fenced
- **WHEN** worker death or transport ambiguity prevents proof that a reserved invocation remained pre-launch
- **THEN** the receipt enters `fenced_indeterminate`
- **AND** the system performs no automatic retry, reclaim, or fallback from that receipt

### Requirement: Provider launches consume atomic invocation reservations
The system SHALL reserve a `ProviderInvocationReservation` immediately before the existing provider authority sink can launch, after verifying the active claim, current binding and assignment, permitted operation and role, and all remaining ceilings.

#### Scenario: Reservation establishes a unique ordinal
- **WHEN** a valid claimed receipt reserves an invocation
- **THEN** the authority store atomically assigns the next unique ordinal and decrements the receipt's available invocation and budget ceilings

#### Scenario: Launch consumes the slot
- **WHEN** a reservation reaches `launch_started`
- **THEN** the reservation remains consumed whether the provider succeeds, fails, times out, or returns an ambiguous result

#### Scenario: Retry needs another slot
- **WHEN** provider fallback or retry is attempted after a launch
- **THEN** the attempt requires another valid reservation within the same or a fresh no-broader receipt

#### Scenario: Exhausted budget blocks before launch
- **WHEN** a receipt lacks an invocation, token, cost, operation, or role allowance required by the proposed call
- **THEN** reservation fails before credentials, outbound transport, provider auth health, requester quota, or provider execution is reached

### Requirement: Authority lifecycle and restart reconciliation are monotonic
The system SHALL maintain monotonic binding, receipt, claim, and reservation states; terminal state transitions SHALL be first-writer-wins and SHALL preserve evidence needed to reconcile crashes safely.

#### Scenario: Startup expires unused receipts
- **WHEN** startup reconciliation finds an expired unclaimed receipt
- **THEN** it marks the receipt expired without making it claimable again

#### Scenario: Startup preserves live work
- **WHEN** startup reconciliation finds a valid live execution claim
- **THEN** it preserves that claim and does not create a competing owner

#### Scenario: Startup cannot prove absence
- **WHEN** reconciliation cannot prove that an invocation was never launched or cannot read required authority evidence
- **THEN** it preserves the evidence, fences or holds the work, and does not retry or delete it

#### Scenario: Cancellation is final for future launches
- **WHEN** cancellation wins the receipt's terminal transition before a new reservation reaches `launch_started`
- **THEN** no later reservation or launch is allowed for that receipt

### Requirement: Universe-less maintenance authority is isolated
The system SHALL authorize the shipped fixed private `_AUTH_PROBE_PROMPT` only through a `maintainer_maintenance` receipt bound to a host or operator principal, exact provider and operation, fixed private-prompt digest, separate maintenance binding and budget, and bounded lifetime and invocation count.

#### Scenario: Fixed probe runs without requester authority
- **WHEN** an authorized maintainer operation invokes the exact fixed private probe under its effective maintenance canary
- **THEN** the system may issue a maintenance receipt without universe, branch, run, requester identity, requester content, or requester quota

#### Scenario: Maintenance receipt cannot process user work
- **WHEN** a maintenance receipt is presented with user content, a different prompt digest, graph work, child work, or a different provider operation
- **THEN** the system rejects it before the provider authority sink

#### Scenario: Status reads never trigger a probe
- **WHEN** a user or operator calls `get_status`
- **THEN** the system reports existing health state without launching `_AUTH_PROBE_PROMPT` or any other provider call

### Requirement: Enforcement rollout is server-owned and fail-closed
The system SHALL preserve shipped behavior while provider-authority V2 is dark and SHALL enable receipt enforcement only through server-owned gates that caller payloads cannot widen or select.

#### Scenario: Universe work follows its effective gate
- **WHEN** provider-capable universe work executes
- **THEN** receipt enforcement follows the effective per-universe V2 gate

#### Scenario: Maintenance canary is exact and default-empty
- **WHEN** the global V2 gate is dark
- **THEN** only an exact operation in the server-owned default-empty maintenance canary set may use maintenance receipt enforcement

#### Scenario: Global cutover requires both canaries
- **WHEN** an operator attempts global provider-authority V2 cutover
- **THEN** the system requires successful isolated universe-work and maintenance canary evidence, including concurrent claim and launch proof

### Requirement: Authority observability is secret-free
The system SHALL emit receipt, claim, reservation, hold, fence, and reconciliation observability without prompts, outputs, credentials, claim nonces, reusable bearer material, or raw private identity.

#### Scenario: Operator diagnoses a fenced attempt
- **WHEN** an invocation becomes indeterminate
- **THEN** logs and status expose stable non-secret binding, receipt, operation, ordinal, state, reason, and timestamp identifiers sufficient for diagnosis
- **AND** they expose no content or reusable authority
