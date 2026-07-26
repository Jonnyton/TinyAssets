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
The system SHALL create or rotate a background target binding only from an authenticated schedule/subscription transition, an authorized universe creation or governed soul transition, an authorized root run, or an attenuating parent-attempt transition. Each root MUST derive identity from canonical request or durable authority state and MUST authorize the exact universe, branch, operation, and source revision. Caller `owner_actor`, process environment, queue possession, stored actor labels, admission evidence, daemon/worker identity, and branch visibility MUST NOT issue or widen a binding.

#### Scenario: Caller-supplied owner cannot become authority
- **WHEN** a schedule request supplies `owner_actor` equal to another account or a private branch author
- **THEN** the system ignores that value for authorization and derives the principal from the authenticated request

#### Scenario: Parent derivation attenuates
- **WHEN** an active parent attempt requests a same-universe child inside its explicit target policy and remaining limits
- **THEN** the service may create an exact child binding while atomically debiting the parent envelope
- **AND** the child receives no operation, target, depth, count, cost, or lifetime authority absent from the parent

### Requirement: Attempts are issued just in time from current canonical state
The system SHALL revalidate an active exact binding generation, authorizing principal, universe ACL, physical universe, branch existence/access, live or pinned target version, source revision/cancellation, executor eligibility, lineage, limits, and prior-attempt state before creating or claiming each attempt. The admitted attempt MUST pin the exact branch version/content digest. A failed check MUST create no runnable attempt and MUST perform no provider, credential, payment, or outbound-effect access.

#### Scenario: Live schedule pins the current version
- **WHEN** a live-target schedule fires after its branch definition has advanced to a newly authorized version
- **THEN** the attempt pins that current exact version
- **AND** a later branch edit cannot alter the admitted attempt

#### Scenario: Revoked principal fails before downstream access
- **WHEN** the authorizing principal loses required universe or branch access before a trigger fires
- **THEN** the source enters an authority hold without a runnable attempt
- **AND** provider, credential, payment, and outbound-effect systems are not consulted

### Requirement: Logical attempt keys are unique and recoverable
The system SHALL derive a deterministic logical-attempt key from the source identity and generation plus its due instant, event ID, soul-cycle ordinal, task generation, or parent/child invocation ordinal as applicable. The authority store MUST enforce one attempt per key across concurrent hosts. A replay MUST follow the existing attempt outcome, while an indeterminate attempt MUST hold until reconciliation rather than minting a replacement.

#### Scenario: Concurrent schedule ticks have one winner
- **WHEN** two hosts process the same schedule generation and due instant concurrently
- **THEN** exactly one attempt is created and both hosts observe that attempt or its terminal projection

#### Scenario: Crash after reservation does not duplicate
- **WHEN** a process crashes after reserving an attempt but before dispatch is durably linked
- **THEN** recovery resumes, terminates, or quarantines that exact attempt
- **AND** retry does not create a second attempt for the logical key

### Requirement: Authority failures are typed holds with monotonic fencing
The system SHALL fence stale work with binding, source, target, attempt, executor-claim, and revocation generations. Missing, mismatched, revoked, expired, exhausted, unauthorized, or indeterminate authority MUST place the source/task in a non-runnable typed `authority_hold` without deleting its definition or history. Reauthorization MUST mint a new generation; it MUST NOT revive or mutate a stale attempt.

#### Scenario: Binding rotation fences a stale worker
- **WHEN** a source is reauthorized and its binding generation advances while an old worker is preparing to execute
- **THEN** the old claim fails before branch resolution or run creation

#### Scenario: Ambiguous state remains recoverable
- **WHEN** recovery cannot prove whether a prior attempt crossed its irreversible execution boundary
- **THEN** the source remains held as indeterminate with its audit evidence intact
- **AND** no replacement authority is guessed

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
The system SHALL derive graph-enqueued child authority from a non-serializable parent delegation and atomically debit the parent's remaining envelope before making the child task pickable. Default delegation MUST be limited to same-universe public targets. A private target MUST require an explicit exact-target allowlist from the authenticated root or parent binding. Existing stable-origin, physical-universe, depth, run-wide, global-active, lifetime-lineage, and integrity guards MUST remain independently enforced.

#### Scenario: Dynamic private target cannot inherit principal rights
- **WHEN** branch-authored code names a private same-universe branch that is not in the parent binding's exact allowlist
- **THEN** enqueue fails before binding creation or task append even if an actor string matches the branch author

#### Scenario: Concurrent children cannot overspend
- **WHEN** multiple source nodes concurrently derive children from one nearly exhausted parent envelope
- **THEN** at most the remaining authority and queue capacity is committed
- **AND** every excess derivation fails without a pickable task

### Requirement: Authority domains compose without promotion
The system SHALL keep background target authority distinct from trigger admission, queue/lease reservation, daemon control, distributed B2 execution grants, provider-work authority, provider-attempt receipts, credentials, payment, moderation, and outbound-effect authority. Execution MUST satisfy every applicable domain independently, and no identifier, signature, verdict, or receipt from one domain may mint or substitute for another.

#### Scenario: Queue claim without target attempt cannot execute
- **WHEN** a worker owns a valid branch-task lease but cannot claim the exact current background target attempt
- **THEN** the task is held before branch resolution or run creation

#### Scenario: Target attempt does not authorize a provider call
- **WHEN** an exact branch attempt is valid but the branch reaches a provider sink without current provider-work and provider-attempt authority
- **THEN** the provider call is refused while the target attempt remains independently auditable

### Requirement: Provenance separates authorizer, target, source, and executor
The system SHALL persist the canonical authorizing principal, binding and attempt IDs/digests/generations, source and logical key, universe, exact branch version/content digest, lineage, executing daemon/runtime/worker, hold or terminal reason, and applicable cross-domain receipt references. User-visible provenance MUST distinguish “authorized by” from “executed by” and MUST NOT expose credentials or bearer material.

#### Scenario: Environment actor cannot rewrite provenance
- **WHEN** the daemon process has an `UNIVERSE_SERVER_USER` value different from the binding principal
- **THEN** run provenance uses the canonical binding principal as authorizer and records the daemon separately as executor

### Requirement: Legacy migration never guesses unattended authority
The system SHALL inventory every legacy schedule, subscription, soul or `PROGRAM.md` loop, live/archive branch task, and enqueue producer before enforcement. It MUST backfill a binding only from canonical durable evidence that independently proves principal, ACL, exact target, source generation, and physical universe. Ambiguous work MUST remain preserved but paused or held as `reauthorization_required`; `owner_actor`, environment, public visibility, queue possession, or daemon/worker identity MUST NOT be treated as proof.

#### Scenario: Legacy owner string is insufficient
- **WHEN** a schedule has only an `owner_actor` value and no canonical principal/ACL record
- **THEN** migration preserves the schedule in a non-runnable reauthorization hold

#### Scenario: Dark-era queue is fully classified before activation
- **WHEN** epoch-2 or enforced target authority is enabled
- **THEN** every pre-authority queue row is linked to provable authority, drained under the bounded old public-only path, or held
- **AND** the unclassified count is zero

### Requirement: Live activation requires concurrency, failure, and chatbot proof
The system SHALL remain dark or non-authorizing until focused tests prove duplicate-fire uniqueness, revocation and mutable-target fencing, child-budget atomicity, crash-boundary convergence, multi-host claim safety, legacy holds, and call-site closure. Live activation MUST additionally satisfy the project concurrency/load proof, public canary checks, a rendered chatbot conversation through the installed connector, and fresh post-fix real-user evidence or an explicit watch item.

#### Scenario: Unit success alone cannot activate
- **WHEN** focused unit and integration tests pass but rendered connector or required load evidence is absent
- **THEN** background target enforcement remains non-live and the change is not accepted as complete
