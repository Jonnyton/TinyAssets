## ADDED Requirements

### Requirement: Background target bindings and attempts are distinct non-bearer records
The system SHALL represent durable unattended branch authorization as a server-owned `BackgroundBranchBinding` and each logical execution as a separate `BackgroundBranchAttempt`. A binding MUST identify the canonical authorizing principal, universe, exact branch definition, operation, source kind/identity/revision, target mode, generation, revocation state, executor constraints, and bounded delegation. An attempt MUST bind one logical key to the current binding generation, exact branch version/content digest, source generation, executor audience, lineage, limits, and lifecycle. Serialized IDs, digests, trigger rows, task rows, daemon identities, worker leases, and public visibility MUST NOT authorize execution by themselves.

#### Scenario: Copied binding reference grants nothing
- **WHEN** a worker presents a binding ID or task row without resolving and claiming it through the authority service
- **THEN** no branch run starts and no downstream authority is issued

#### Scenario: One durable binding creates bounded attempts
- **WHEN** an active schedule fires at two distinct due instants within its limits
- **THEN** each due instant may receive one separate attempt pinned to its own freshly resolved branch snapshot
- **AND** neither attempt mutates the durable binding into a bearer

### Requirement: Bindings have closed server-owned issuance roots
The system SHALL create or rotate a background target binding only from an authenticated schedule/subscription transition, authenticated Request admission, an authenticated goal subscription or accepted paid-market contract followed by producer emission, an authenticated wiki forward-trigger, an authorized universe creation or governed soul transition, an authorized root run or resume, or an attenuating parent-attempt transition for enqueue or direct child invocation. Each root MUST derive identity from canonical request or durable authority state and MUST authorize the exact universe, branch, operation, and source revision. Caller `owner_actor`, `child_actor`, `posted_by`, process environment, pool or bug content, queue possession, stored actor labels, admission evidence, daemon/worker identity, fresh-install default subscription, branch visibility, and the compiled built-in universe cycle MUST NOT issue or widen a binding.

#### Scenario: Caller-supplied owner cannot become authority
- **WHEN** a schedule request supplies `owner_actor` equal to another account or a private branch author
- **THEN** the system ignores that value for authorization and derives the principal from the authenticated request

#### Scenario: Parent derivation attenuates
- **WHEN** an active parent attempt requests a same-universe child inside its explicit target policy and remaining limits
- **THEN** the service may create an exact child binding while atomically debiting the parent envelope
- **AND** the child receives no operation, target, depth, count, cost, or lifetime authority absent from the parent

#### Scenario: Request admission commits target authority
- **WHEN** an authenticated operator Request is admitted for an exact universe loop or branch target
- **THEN** its Request, admission, protocol task, and source binding commit as one aggregate or none commit
- **AND** the admission verdict alone cannot authorize later execution

#### Scenario: Every detachable root run commits its binding
- **WHEN** a canonical live/version run, selector, leaderboard, or market delegate can continue asynchronously after its request returns
- **THEN** the root run and exact target binding commit before background execution
- **AND** lower-level `_execute_branch_core` callers cannot substitute an actor string

#### Scenario: Producer emission consumes durable subscriber authority
- **WHEN** a goal-pool or paid-market producer emits a task for a subscriber universe
- **THEN** it may derive an exact binding only from that universe's current authenticated goal subscription or accepted market contract generation
- **AND** anonymous default subscriptions, producer identity, pool content, and poster labels grant nothing

#### Scenario: Resume derives from exact run authority
- **WHEN** a canonically authorized principal resumes an interrupted run with a current durable run binding
- **THEN** one resume binding/attempt is fenced to the run's exact checkpoint and branch version
- **AND** startup recovery or the stored run actor cannot mint it

#### Scenario: Wiki bug forwarding binds the filing principal
- **WHEN** an authenticated `file_bug` write commits a bug revision and requests investigation work
- **THEN** the bug revision, exact investigation target binding, and task commit as one transaction or recoverable pair
- **AND** the bug ID, page content, and queue row grant nothing by themselves

#### Scenario: Built-in universe cycle is not an authority root
- **WHEN** a daemon would otherwise stream `branches/universe_cycle.yaml` outside a governed soul/run path
- **THEN** enforcement refuses that bypass until the branch is registered, soul-declared, and bound through authenticated creation or provable migration

### Requirement: Attempts are issued just in time from current canonical state
The system SHALL revalidate an active exact binding generation, authorizing principal, universe ACL, physical universe, branch existence/access, live or pinned target version, source revision/cancellation, executor eligibility, lineage, limits, and prior-attempt state before creating or claiming each attempt. The admitted attempt MUST pin the exact branch version/content digest. A failed check MUST create no runnable attempt and MUST perform no provider, credential, payment, or outbound-effect access.

#### Scenario: Live schedule pins the current version
- **WHEN** a live-target schedule fires after its branch definition has advanced to a newly authorized version
- **THEN** the attempt pins that current exact version
- **AND** a later branch edit cannot alter the admitted attempt

#### Scenario: Revoked principal fails before downstream access
- **WHEN** the authorizing principal loses required universe or branch access before a trigger fires
- **THEN** the source enters a target-authority hold without a runnable attempt
- **AND** provider, credential, payment, and outbound-effect systems are not consulted

### Requirement: Logical attempt keys are unique and recoverable
The system SHALL derive a deterministic logical-attempt key from the source identity and generation plus its due-period identity, event ID, soul-cycle ordinal, Request/admission/task identity and body digest, producer item/subscription-or-contract revision, wiki bug ID/filing revision/principal, resume checkpoint/generation, task generation, or parent/node/child/retry invocation ordinal as applicable. The authority store MUST enforce one attempt per key across concurrent hosts. A replay MUST follow the existing attempt outcome, while an indeterminate attempt MUST hold until reconciliation rather than minting a replacement.

#### Scenario: Concurrent schedule ticks have one winner
- **WHEN** two hosts process the same schedule generation and due instant concurrently
- **THEN** exactly one attempt is created and both hosts observe that attempt or its terminal projection

#### Scenario: Crash after reservation does not duplicate
- **WHEN** a process crashes after reserving an attempt but before dispatch is durably linked
- **THEN** recovery resumes, terminates, or quarantines that exact attempt
- **AND** retry does not create a second attempt for the logical key

#### Scenario: Child retry has a stable distinct ordinal
- **WHEN** one live or frozen direct child invocation retries within its bounded policy
- **THEN** each retry receives one deterministic retry-ordinal key and exact pinned target attempt
- **AND** replay cannot add an unbudgeted retry

### Requirement: Authority failures are typed holds with monotonic fencing
The system SHALL fence stale work with binding, source, target, attempt, executor-claim, and revocation generations. Missing, revoked, expired, exhausted, unauthorized, or indeterminate target authority MUST place a queue row in the persisted non-runnable `target_authority_held` state, or an equivalent source-owned hold for a non-queue source, without deleting its definition or history. An audience/lease mismatch from a provably dead or atomically invalidated predecessor MUST instead permit generation-checked automatic claim recovery of the same attempt when every irreversible boundary is conclusively absent or closed. A queue transition to held, recovery-proven held-to-pending transition, and authenticated held-to-pending reauthorization MUST be generation-checked. Reauthorization MUST mint a new binding generation only when binding/target authority must rotate and MUST NOT revive or mutate a stale attempt; recovery may advance only the attempt-claim generation.

#### Scenario: Binding rotation fences a stale worker
- **WHEN** a source is reauthorized and its binding generation advances while an old worker is preparing to execute
- **THEN** the old claim fails before branch resolution or run creation

#### Scenario: Ambiguous state remains recoverable
- **WHEN** recovery cannot prove whether a prior attempt crossed its irreversible execution boundary
- **THEN** the source remains held as indeterminate with its audit evidence intact
- **AND** no replacement authority is guessed

#### Scenario: Held queue work has explicit cap accounting
- **WHEN** a BranchTask enters `target_authority_held`
- **THEN** it stops consuming the global active pending/running capacity
- **AND** it continues to consume exactly one non-refundable lifetime-lineage unit
- **AND** reauthorizing that same row does not consume another lineage unit

#### Scenario: Dead predecessor recovers without human reauthorization
- **WHEN** recovery proves the prior worker dead or invalidates its claim generation and proves the target attempt never crossed an irreversible boundary
- **THEN** it advances the attempt-claim generation and returns the same task/attempt to claimable work
- **AND** it does not rotate the binding, append a task, or require a user

#### Scenario: Indeterminate boundary remains held
- **WHEN** predecessor death is known but the target attempt's irreversible boundary is indeterminate
- **THEN** recovery keeps the row in `target_authority_held` until reconciliation produces conclusive evidence

### Requirement: Source and authority lifecycle transitions are crash-consistent
The system SHALL create, rotate, pause, revoke, and remove trigger/soul/task sources and their authority records in one transaction where they share a store or through a prepared, digest-bound, idempotently recoverable pair where they do not. A source MUST NOT become pickable before its binding is committed, and a revoked generation MUST NOT become runnable because one store rolled back independently.

#### Scenario: Trigger creation crashes between stores
- **WHEN** a crash occurs after preparing a binding but before the schedule or subscription is committed
- **THEN** recovery either commits the exact prepared pair or aborts it
- **AND** no orphan binding or trigger becomes runnable

#### Scenario: Event delivery has an explicit outcome
- **WHEN** a subscription event is deduplicated
- **THEN** its delivery record is linked to one attempt or one explicit denial/hold record before delivery is considered complete

### Requirement: Child target authority is transferred under existing growth guards
The system SHALL derive graph-enqueued and live/frozen direct-child authority from a non-serializable parent delegation and atomically debit the parent's remaining envelope before making a child task pickable or starting direct execution. Default delegation MUST be limited to same-universe public targets. A private target MUST require an explicit exact-target allowlist from the authenticated root or parent binding. Branch definitions containing `child_actor` MUST fail validation after enforcement rather than selecting execution identity. Initial invocations and every retry MUST have stable ordinals and independently pinned attempts. Existing stable-origin, physical-universe, depth, retry, run-wide, global-active, lifetime-lineage, and integrity guards MUST remain independently enforced.

#### Scenario: Dynamic private target cannot inherit principal rights
- **WHEN** branch-authored code names a private same-universe branch that is not in the parent binding's exact allowlist
- **THEN** enqueue fails before binding creation or task append even if an actor string matches the branch author

#### Scenario: Concurrent children cannot overspend
- **WHEN** multiple source nodes concurrently derive children from one nearly exhausted parent envelope
- **THEN** at most the remaining authority and queue capacity is committed
- **AND** every excess derivation fails without a pickable task

#### Scenario: Direct async child cannot bypass enqueue authority
- **WHEN** a live or frozen `invoke_branch` node uses async mode or a retry
- **THEN** it derives and claims the same class of exact attenuated child authority before execution
- **AND** neither `child_actor` nor the stored parent run actor grants access

### Requirement: Authority domains compose without promotion
The system SHALL keep background target authority distinct from trigger admission, queue/lease reservation, daemon control, distributed B2 execution grants, provider-work authority, provider-attempt receipts, credentials, payment, moderation, and outbound-effect authority. Execution MUST satisfy every applicable domain independently, and no identifier, signature, verdict, or receipt from one domain may mint or substitute for another. For any provider-capable background source, the exact current target attempt MUST be claimed before a `ProviderWorkAuthorityReceipt` can be issued; provider-work issuance MUST revalidate the referenced target attempt and generation without becoming target authority.

#### Scenario: Queue claim without target attempt cannot execute
- **WHEN** a worker owns a valid branch-task lease but cannot claim the exact current background target attempt
- **THEN** the task is held before branch resolution or run creation

#### Scenario: Target attempt does not authorize a provider call
- **WHEN** an exact branch attempt is valid but the branch reaches a provider sink without current provider-work and provider-attempt authority
- **THEN** the provider call is refused while the target attempt remains independently auditable

#### Scenario: Provider-work issuance consumes a current target attempt
- **WHEN** provider-capable schedule, subscription, soul, request, producer, resume, claimed-task, or child work requests provider-work authority
- **THEN** issuance succeeds only after it validates the exact actively claimed target attempt and generation

### Requirement: Provenance separates authorizer, target, source, and executor
The system SHALL persist the canonical authorizing principal, binding and attempt IDs/digests/generations, source and logical key, universe, exact branch version/content digest, lineage, executing daemon/runtime/worker, hold or terminal reason, and applicable cross-domain receipt references. User-visible provenance MUST distinguish “authorized by” from “executed by” and MUST NOT expose credentials or bearer material.

#### Scenario: Environment actor cannot rewrite provenance
- **WHEN** the daemon process has an `UNIVERSE_SERVER_USER` value different from the binding principal
- **THEN** run provenance uses the canonical binding principal as authorizer and records the daemon separately as executor

### Requirement: Legacy migration never guesses unattended authority
The system SHALL inventory every legacy schedule, subscription, Request admission, goal/market producer subscription/contract and emitted task, wiki bug forward-trigger, soul or `PROGRAM.md` loop, compiled built-in universe cycle, live/archive branch task, enqueue/direct-child path, interrupted run/resume, `_current_actor` seam, and dispatcher before enforcement. It MUST backfill a binding only from canonical durable evidence that independently proves principal, ACL, exact target, source generation, and physical universe. The built-in cycle MUST be registered as an ordinary branch and declared/bound in governed soul state before it can continue. Ambiguous work MUST remain preserved but paused or held as `reauthorization_required`; `owner_actor`, `child_actor`, `posted_by`, environment, pool/bug content, public visibility, queue possession, admission verdict, built-in branch identity, or daemon/worker identity MUST NOT be treated as proof.

#### Scenario: Legacy owner string is insufficient
- **WHEN** a schedule has only an `owner_actor` value and no canonical principal/ACL record
- **THEN** migration preserves the schedule in a non-runnable reauthorization hold

#### Scenario: Dark-era queue is fully classified before activation
- **WHEN** epoch-2 or enforced target authority is enabled
- **THEN** every pre-authority queue row is linked to provable authority, drained under the bounded old public-only path, or held
- **AND** the unclassified count is zero

### Requirement: Live activation requires concurrency, failure, and chatbot proof
The system SHALL remain dark or non-authorizing until a host-approved `PLAN.md` reconciliation assigns exactly one live scheduling/task-claim mutation authority, `demand-side-signals`, `operator-request-trigger-contract`, `harden-background-provider-execution-authority`, the relevant universe/run owners, and the accepted paid-market contract owner have landed their dependencies, and focused tests prove duplicate-fire uniqueness, revocation and mutable-target fencing, child-budget atomicity, crash-boundary convergence, multi-host claim safety, autonomous dead-worker recovery, legacy holds, and call-site closure. Dark mode MUST preserve shipped source behavior only for work with no target-authority record; any record already present remains subject to reconciliation and fencing. Live activation MUST additionally satisfy the project concurrency/load proof, public canary checks, a rendered chatbot conversation through the installed connector, and fresh post-fix real-user evidence or an explicit watch item.

#### Scenario: Unit success alone cannot activate
- **WHEN** focused unit and integration tests pass but rendered connector or required load evidence is absent
- **THEN** background target enforcement remains non-live and the change is not accepted as complete

#### Scenario: Store ownership is unresolved
- **WHEN** no host-approved PLAN decision assigns one live scheduling/task-claim mutation authority
- **THEN** models, inventory, dark classification, and tests may proceed but no target-authority persistence or claim path becomes production-authorizing

#### Scenario: Dark records still reconcile
- **WHEN** the live gate is dark but a work item already has a target-authority record
- **THEN** recovery applies current generation, reconciliation, and fencing rules rather than falling back to actor/environment/public/queue authority

### Requirement: Rollback never downgrades target authority
The system SHALL roll back by stopping new binding/attempt issuance and claims, fencing in-flight claim generations, and leaving sources/tasks pending or held while retaining generations, prepared-state evidence, and audit history. Rollback MUST NOT restore `owner_actor`, `child_actor`, `posted_by`, environment, public visibility, built-in-cycle identity, queue possession, daemon/worker identity, or any legacy record as target authority.

#### Scenario: Enforcement rollback preserves the authority floor
- **WHEN** operators disable live target-authority issuance after partial activation
- **THEN** in-flight generations are fenced and work remains pending or held
- **AND** no legacy or ambient execution fallback is re-enabled
