## ADDED Requirements

### Requirement: Durable provider work bindings are non-bearer authorization intent
The system SHALL represent authorization for later provider-capable work as a server-owned `ProviderWorkBinding` whose identifier and serialized fields do not themselves authorize provider, credential, outbound-proxy, auth-health, or quota access.

#### Scenario: Queue identity cannot authorize provider work
- **WHEN** a caller presents a run ID, branch-task ID, queue claim, lease, actor string, schedule ID, subscription ID, receipt ID, or serialized receipt fields without a current server-issued authority receipt
- **THEN** the system holds before every provider authority sink

#### Scenario: Deferred request records intent while request authority is live
- **WHEN** an authenticated connector message authorizes a registered background-capable operation that will execute after request middleware returns
- **THEN** TinyAssets middleware creates an inert single-message binding draft for the authenticated principal and registered operation after reading the exact current `request_ctx.get().request` but before awaiting the tool or dispatch augmentation
- **AND** the operation resolves the exact target and consumes that draft transactionally with the deferred work item
- **AND** just-in-time receipt issuance authorizes the resolved target against current server state
- **AND** the deferred worker receives no inherited or snapshotted request capability

#### Scenario: Deferred work misses the recording boundary
- **WHEN** work becomes deferred before the current-message middleware can create and consume the authorized binding draft
- **THEN** the work has no provider issuance root and holds before every provider authority sink

#### Scenario: Synthetic schedule actor cannot create a binding
- **WHEN** provider-authority V2 applies and a schedule or subscription supplies `owner_actor`, caller kwargs, or another synthetic principal without the server-owned record from `harden-background-branch-execution-authority`
- **THEN** the V2 provider-work binding is not created and the provider-capable execution holds without treating the synthetic principal as authority

#### Scenario: Dark schedules retain shipped behavior
- **WHEN** provider-authority V2 is dark for a schedule or subscription
- **THEN** this binding requirement does not deactivate or otherwise change the shipped trigger

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

#### Scenario: Concurrent children conserve parent authority
- **WHEN** one parent creates one or more provider-capable child bindings
- **THEN** the authority store atomically transfers invocation, token, and cost ceilings from the parent's remaining authority before each child becomes claimable
- **AND** concurrent children cannot receive more aggregate authority than the parent's prior remaining ceiling

#### Scenario: Unused child authority returns exactly once
- **WHEN** a child closes conclusively with proven unused authority
- **THEN** the store returns that authority exactly once only if the same parent receipt and generation remain active
- **AND** otherwise the unused authority expires without crediting any parent

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

#### Scenario: Existing fence blocks fresh issuance for the work item
- **WHEN** any prior receipt for the exact physical work-item key is `fenced_indeterminate` or contains a `reserved`, unclosed `launch_started`, or `indeterminate` reservation
- **THEN** the authority store issues no fresh receipt for that work item regardless of binding state, queue/run status, projected error text, or current rollout gate
- **AND** issuance becomes eligible only after ledger reconciliation makes every prior reservation conclusive

### Requirement: Cross-process receipt transfer is an atomic server claim
The system SHALL keep provider-work authority in a server-owned `ProviderWorkAuthorityStore` and SHALL use only an opaque receipt identifier, one-use claim nonce, worker and runtime audience, and expiry for process handoff.

#### Scenario: Authorized worker claims once
- **WHEN** the queue owner has selected an exact worker and that worker presents the resulting unexpired opaque handoff to the authority store
- **THEN** the store atomically consumes the nonce, establishes the execution claim, and reconstructs a non-serializable receipt inside the claimed scope

#### Scenario: Pre-claim queue data carries no worker envelope
- **WHEN** provider-capable work is queued before a worker is selected
- **THEN** the queue carries only a non-authorizing binding reference
- **AND** no claim nonce or worker-audienced envelope is minted until after atomic worker selection

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

#### Scenario: Recovery invalidates an unprovable stale owner
- **WHEN** queue recovery cannot prove an expired-lease owner dead but presents the exact current task, owner, lease, receipt, and claim generations
- **THEN** the authority store atomically invalidates and advances the old execution-claim generation or reports the newer competing state
- **AND** every reservation operation from the invalidated owner fails active-generation validation

#### Scenario: Provably dead owner with conclusive reservations is reclaimable
- **WHEN** the current claim owner is provably dead and the receipt has no reservation or every reservation is durably `cancelled_before_launch`, `succeeded`, or `failed`
- **THEN** the system may atomically expire the old claim and issue a bounded replacement claim for remaining authorized work
- **AND** `succeeded` and `failed` invocation and budget amounts remain consumed while `cancelled_before_launch` authority is released

#### Scenario: Dead owner reserved before arming is cancellable
- **WHEN** the current claim owner is provably dead and a reservation remains durably `reserved`
- **THEN** the system atomically transitions it to `cancelled_before_launch`, releases its full invocation, token, and cost reservation, and may reclaim remaining work

#### Scenario: Ambiguous launch is fenced
- **WHEN** worker death leaves an unclosed `launch_started` or `indeterminate` reservation, or required authority evidence is unreadable
- **THEN** the receipt enters `fenced_indeterminate`
- **AND** the system performs no automatic retry, reclaim, or fallback from that receipt

### Requirement: Provider launches consume atomic invocation reservations
The system SHALL reserve and durably arm a `ProviderInvocationReservation` before acquiring `ProviderAssignmentAdmission`, after verifying the active claim, current binding and expected assignment tuple, permitted operation and role, and all remaining ceilings.

#### Scenario: Reservation establishes a unique ordinal
- **WHEN** a valid claimed receipt reserves an invocation
- **THEN** the authority store first validates the exact active execution-claim generation, atomically assigns the next unique ordinal, and reserves the receipt's invocation plus worst-case token and cost ceilings derived from the resolved finite `ModelConfig` token cap and server-owned provider/model price ceiling
- **AND** a null token cap is replaced by a finite conservative server-owned provider/model/role ceiling or the attempt holds
- **AND** a subscription CLI provider reserves one server-defined subscription-invocation cost unit instead of fabricated per-token currency

#### Scenario: Launch fence commits before admission and transport
- **WHEN** a reserved provider attempt is ready to enter the parent provider-routing sequence
- **THEN** the authority store durably commits `launch_started` and closes its transaction before assignment admission is acquired
- **AND** the carrier freezes the receipt generation, claim generation, reservation ordinal and digest, expected assignment tuple, and revocation or cancellation generation
- **AND** the parent sequence validates that carried frozen tuple under admission without acquiring the authority store before minting the invocation
- **AND** no authority-store lock is acquired while a queue-file, assignment-admission, or credential lock is held
- **AND** queue-file and assignment-admission locks never nest

#### Scenario: Recovery lock order closes authority before queue CAS
- **WHEN** recovery obtains an authority reconciliation proof and resets a branch-task row
- **THEN** the authority transaction closes before the queue file lock is acquired
- **AND** no authority-store operation occurs while that queue lock is held

#### Scenario: Arming chooses the revocation race winner
- **WHEN** revocation or cancellation commits before `launch_started`
- **THEN** the attempt cannot arm or launch
- **AND** when `launch_started` commits first, that single frozen attempt may proceed if parent assignment admission still validates while the revocation prevents every later reservation

#### Scenario: Launch consumes the slot
- **WHEN** a reservation reaches `launch_started`
- **THEN** the reservation remains consumed whether the provider succeeds, fails, times out, or returns an ambiguous result

#### Scenario: Cancellation before arming releases authority
- **WHEN** a reserved attempt is cancelled before `launch_started` commits
- **THEN** it becomes `cancelled_before_launch` and releases its full invocation, token, and cost reservation

#### Scenario: Proven unused budget settles after admission release
- **WHEN** an authoritative terminal provider record proves actual token and cost usage below the reserved worst case
- **THEN** the system may refund only the proven unused token and cost portion after assignment admission is released
- **AND** absent or ambiguous usage retains the full reservation

#### Scenario: Retry needs another slot
- **WHEN** provider fallback or retry is attempted after a launch
- **THEN** the attempt requires another valid reservation within the same or a fresh no-broader receipt

#### Scenario: Exhausted budget blocks before launch
- **WHEN** a receipt lacks an invocation, token, cost, operation, or role allowance required by the proposed call
- **THEN** reservation fails before credentials, outbound transport, provider auth health, requester quota, or provider execution is reached

#### Scenario: Judge ensemble reserves atomically
- **WHEN** one logical judge operation resolves an ensemble of N direct provider launches
- **THEN** the system atomically reserves N unique ordinals and every member's worst-case budget before any member launches
- **AND** insufficient authority holds the entire ensemble without partial fan-out
- **AND** each member enters the parent `ProviderInvocation` and `ProviderExecutor` sink rather than calling a bare provider directly

### Requirement: Authority lifecycle and restart reconciliation are monotonic
The system SHALL maintain monotonic binding, receipt, claim, and reservation states; conclusive terminal state transitions SHALL be first-writer-wins and SHALL preserve evidence needed to reconcile crashes safely, while `indeterminate` and `fenced_indeterminate` remain non-runnable states that only authoritative evidence may advance to a matching conclusive terminal.

#### Scenario: Startup expires unused receipts
- **WHEN** startup reconciliation finds an expired unclaimed receipt
- **THEN** it marks the receipt expired without making it claimable again

#### Scenario: Startup preserves live work
- **WHEN** startup reconciliation finds a valid live execution claim
- **THEN** it preserves that claim and does not create a competing owner

#### Scenario: Startup cannot prove absence
- **WHEN** reconciliation cannot prove that an invocation was never launched or cannot read required authority evidence
- **THEN** it preserves the evidence, fences or holds the work, and does not retry or delete it

#### Scenario: Autonomous reconciliation resolves a fence
- **WHEN** durable launch-record, outbound-proxy, provider-side idempotency/status, child-process wrapper journal, or durable result evidence conclusively proves non-launch, success, or failure after restart
- **THEN** the reconciler advances the indeterminate reservation once to `cancelled_before_launch`, `succeeded`, or `failed` respectively
- **AND** it reclaims remaining authorized work only after every reservation is conclusive

#### Scenario: Transient attempt receipt is same-process evidence only
- **WHEN** same-process reconciliation inspects a transient provider-attempt receipt
- **THEN** it may use that receipt without persisting it
- **AND** restart reconciliation does not depend on or create a durable sink for the transient receipt

#### Scenario: Ambiguity exceeds the reconciliation window
- **WHEN** bounded autonomous reconciliation cannot obtain conclusive evidence
- **THEN** the work remains non-runnable and emits an explicit `manual_resolution_required` operator action
- **AND** global cutover remains prohibited for any transport unable to surface that state safely

#### Scenario: Ambiguous transport enters indeterminate
- **WHEN** an armed attempt lacks conclusive proof of success, failure, or non-launch
- **THEN** its reservation enters `indeterminate` and its receipt becomes `fenced_indeterminate`

#### Scenario: Conclusive post-arm failure is terminal
- **WHEN** admission or launch fails after arming and durable evidence proves the failure outcome
- **THEN** the reservation becomes `failed`, its invocation slot remains consumed, and only proven unused token or cost budget may settle

#### Scenario: Cancellation is final for future launches
- **WHEN** cancellation wins the receipt's terminal transition before a new reservation reaches `launch_started`
- **THEN** no later reservation or launch is allowed for that receipt

### Requirement: Universe-less maintenance authority is isolated
The system SHALL authorize the fixed private `_AUTH_PROBE_PROMPT` under V2 only through a `maintainer_maintenance` receipt bound to a host or operator principal, exact provider and operation, invoking runtime or daemon, executor or transport, opaque credential reference and current digest, fixed private-prompt digest, separate maintenance binding and budget, and bounded lifetime and invocation count.

#### Scenario: Fixed probe runs without requester authority
- **WHEN** an authorized maintainer operation invokes the exact fixed private probe under its effective maintenance canary
- **THEN** the system may issue a maintenance receipt without universe, branch, run, requester identity, requester content, or requester quota
- **AND** the closed maintenance executor dereferences only the receipt's current opaque credential binding and never ambient `CODEX_HOME`, PATH, or process identity

#### Scenario: Maintenance receipt cannot process user work
- **WHEN** a maintenance receipt is presented with user content, a different prompt digest, graph work, child work, or a different provider operation
- **THEN** the system rejects it before the provider authority sink

#### Scenario: Ordinary V2 routing keeps the non-completion auth ladder
- **WHEN** universe or request provider routing evaluates subscription auth health under an effective V2 gate
- **THEN** it retains the shipped read-only subscription-auth presence and freshness ladder exactly
- **AND** codex yields `not_logged_in` for a missing `auth.json` or a cached positive `not_logged_in` verdict, while an existing empty, corrupt, stale, or cache-miss file with no positive dead verdict and probing disabled remains eligible with presence or inconclusive evidence
- **AND** claude-code first accepts a non-empty `CLAUDE_CODE_OAUTH_TOKEN` regardless of config-directory state, and only without that token yields `not_logged_in` for an absent, empty, or unreadable config directory
- **AND** the viability-probe kill switch retains its shipped eligible verdict and router unknown/inconclusive results remain eligible
- **AND** it cannot launch the `_AUTH_PROBE_PROMPT` completion, borrow the universe receipt for that completion, dereference maintainer credentials, or start the maintainer CLI

### Requirement: Enforcement rollout is server-owned and fail-closed
The system SHALL preserve shipped behavior while provider-authority V2 is dark and SHALL enable new receipt issuance/enforcement only through server-owned gates that caller payloads cannot widen or select; every authority-ledger record created while a gate was effective SHALL continue lifecycle reconciliation and fencing regardless of later gate state.

#### Scenario: Darkening a gate preserves existing fences
- **WHEN** rollback, canary removal, or maintenance-evidence expiry makes a gate dark while a binding, receipt, claim, or reservation remains in the authority ledger
- **THEN** the system reconciles and fences that record under the authority lifecycle requirements
- **AND** dark shipped recovery applies only to work with no authority-ledger record

#### Scenario: Universe work follows its effective gate
- **WHEN** provider-capable universe work executes
- **THEN** receipt enforcement follows the effective per-universe V2 gate

#### Scenario: Universe gate waits for worker maintenance readiness
- **WHEN** a worker/provider lacks current conclusive maintenance-canary evidence or has not proven authenticated spawn plus unauthenticated/unknown quarantine
- **THEN** provider-authority V2 remains dark for that worker/provider even if the universe is listed
- **AND** missing maintenance authority does not invent a replacement auth-health verdict

#### Scenario: Maintenance canary is exact and default-empty
- **WHEN** the global V2 gate is dark
- **THEN** only an exact operation and invoking runtime or daemon identity in the server-owned default-empty maintenance canary set may use maintenance receipt enforcement
- **AND** the canary uses an isolated credential binding and budget that affect no other production probe caller

#### Scenario: Global cutover requires both canaries
- **WHEN** an operator attempts global provider-authority V2 cutover
- **THEN** the system requires successful isolated universe-work and maintenance canary evidence, including concurrent claim and launch proof

### Requirement: Every provider-capable call site has one authority classification
The background provider execution authority owner SHALL maintain a mechanically checked whole-runtime inventory in which every production provider-capable caller, injected callable, router-internal completion, and packaged runtime mirror has exactly one authority classification.

#### Scenario: Call-site inventory is complete
- **WHEN** CI scans universe intelligence, compiled nodes and routers, the async judge-ensemble `gather` and direct provider members, run and child bridges, schedules and daemon workers, maintenance probes, editorial and ingestion paths, retrieval and RAPTOR paths, reflexion, entity extraction, community evaluation, and the mirrored Claude plugin
- **THEN** each provider-capable call site is classified as live-request authority, host authority, background receipt authority, maintenance authority, accepted-market remote dispatch, or proven non-provider or mock-only

#### Scenario: Successor-owned classifications remain empty
- **WHEN** `activate-requester-host-engines` or `activate-connector-requester-authority` has not landed its authority owner
- **THEN** attested host-request and accepted-market remote classifications respectively contain no production call site
- **AND** any attempted use fails the call-site closure gate

#### Scenario: Unclassified provider call fails the gate
- **WHEN** a new or changed production call site can reach provider execution without one exact classification and carrier path
- **THEN** the call-site closure check fails before the change can land

#### Scenario: Mirrored runtime remains equivalent
- **WHEN** authority-carrier behavior changes in the canonical runtime
- **THEN** the packaged Claude-plugin mirror exposes the same background receipt enforcement or is proven not to contain the affected provider path

### Requirement: Authority observability is secret-free
The system SHALL emit receipt, claim, reservation, hold, fence, and reconciliation observability without prompts, outputs, credentials, claim nonces, reusable bearer material, or raw private identity.

#### Scenario: Operator diagnoses a fenced attempt
- **WHEN** an invocation becomes indeterminate
- **THEN** logs and status expose stable non-secret binding, receipt, operation, ordinal, state, reason, and timestamp identifiers sufficient for diagnosis
- **AND** they expose no content or reusable authority
