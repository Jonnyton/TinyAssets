> Sync-order note. `harden-background-provider-execution-authority` also
> modifies the resume requirement below. That provider change MUST sync first;
> this complete merged provider-plus-target block MUST sync second. Task 8.9
> enforces the order so neither authority protocol is deleted.

## MODIFIED Requirements

### Requirement: Interrupted runs resume from checkpoint under owner, status, checkpoint, and version guards
`resume_run` SHALL resume a run only from its `SqliteSaver` checkpoint and only when the canonical authenticated request principal owns/can administer the run and retains universe/branch access, the run is `interrupted`, a checkpoint exists for its `thread_id`, the exact branch version still resolves, the run is not cancelled, and its mandatory durable initial-run target binding generation revalidates. Caller or stored `actor` strings MUST NOT satisfy ownership. A run already `resumed` SHALL idempotently return the same outcome; another status raises `not_interrupted`, a missing checkpoint raises `no_checkpoint`, and a mismatched version raises `branch_version_mismatch`.

One conditional durable resume-attempt idempotency record MUST coordinate both authority domains against the expected `interrupted` status. Only its winner may create/follow one exact `BackgroundBranchAttempt` bound to the run, checkpoint, stored branch version/content digest, canonical principal, and executor, then idempotently issue a provider-work receipt from the current server-owned run binding when the run is provider-capable. A losing concurrent caller MUST attach to the same resume attempt and return its eventual outcome or exact authority hold without issuing, submitting, or invoking again. Provider-work issuance MUST validate the active target attempt; neither receipt substitutes for the other.

The public run MUST remain `interrupted` until the winner links every applicable target/provider receipt and conditionally commits `resumed`. `resume_run` MUST query current ledger truth for the exact work item: an active provider ledger fence raises `ResumeError` reason `provider_authority_fenced`, an active target ledger fence raises reason `target_authority_fenced`, and flat error sentinels alone are diagnostic and cannot block after their ledger fence resolves. Fence resolution MUST clear or replace the corresponding sentinel with a conclusive diagnostic projection. A crash MUST resume, revoke, or hold that exact resume attempt and MUST NOT mint a second target attempt or provider receipt. For every live, dark, provider-capable, and non-provider-capable path, the run MUST be marked `resumed` before background re-invocation with `None` inputs and the resumed graph MUST receive child delegation only from the claimed target attempt.

Under the effective authority gates, the lazy first-use recovery coordinator and `recover_in_flight_runs` SHALL sweep a provider/target-capable `queued` or `running` row to `interrupted` only after every applicable authority domain reconciles. Provider reconciliation MUST prove no reservation exists or every reservation is durably conclusive as `cancelled_before_launch`, `succeeded`, or `failed`; succeeded/failed slots and budgets remain consumed while cancelled-before-launch authority is released. A dead/invalidated-owner `reserved` reservation MUST first be atomically cancelled before launch. Target reconciliation MUST prove the prior attempt never crossed an irreversible boundary or is durably conclusive. Recovery MUST prove the old process owner dead or atomically invalidate/advance every applicable execution-claim generation before cancellation or sweep.

An unclosed provider `launch_started`, `indeterminate`, or unreadable reservation MUST fence its receipt and set the stable `provider_authority_fenced` diagnostic. An indeterminate target boundary MUST fence its attempt and set `target_authority_fenced`. The public run becomes/remains `interrupted` but non-runnable until authoritative reconciliation resolves every fence. The shipped process-global recovery boolean MUST become a synchronized per-universe state machine: a universe becomes done only after all applicable reconciliation and sweep work succeeds; an effective-gate universe failure remains retryable and fails closed only affected run operations for that universe; dark/unlisted universes complete the shipped sweep independently unless a row already has an authority record, which remains subject to reconciliation/fencing regardless of gate state. As-built limitations retained until implementation: the `recover_in_flight_runs` docstring incorrectly says `interrupted` is terminal and checkpoint resume is unavailable, and dark-mode `resume_run` retains the shipped non-CAS read/write race that can submit two concurrent resumes. Background-target clauses introduced here MUST remain dark/non-authorizing until the live-activation requirement and store-owner decision are satisfied.

#### Scenario: a non-owner cannot resume
- **WHEN** a caller-supplied actor matches the stored run actor but the canonical authenticated principal lacks run/universe authority
- **THEN** `ResumeError` with reason `auth_failed` is raised and no resume attempt is created

#### Scenario: only interrupted runs resume
- **WHEN** `resume_run` is called on a run whose status is not `interrupted` and not `resumed`
- **THEN** `ResumeError` with reason `not_interrupted` is raised carrying the current status

#### Scenario: a second resume is idempotent
- **WHEN** `resume_run` is called on a run already marked `resumed`
- **THEN** it returns the same run and linked target/provider attempt outcome without launching another resume

#### Scenario: every resume commits status before invocation
- **WHEN** any dark, live, provider-capable, or non-provider-capable resume passes its applicable guards
- **THEN** the run is marked `resumed` before background re-invocation with `None` inputs

#### Scenario: concurrent resume callers share one attempt
- **WHEN** two authorized callers concurrently resume the same interrupted checkpoint/binding generation
- **THEN** exactly one conditional resume-attempt claim succeeds and creates/follows one exact target attempt
- **AND** only that winner may issue/link one provider receipt when applicable
- **AND** the loser follows the same attempt and outcome without a second submission

#### Scenario: target authority failure preserves resumability
- **WHEN** the winning resume attempt cannot create or claim a valid exact target attempt
- **THEN** no invocation or provider issuance starts and the public run remains `interrupted`
- **AND** reconciliation revokes, safely retries, or holds that exact resume attempt

#### Scenario: provider authority failure preserves resumability
- **WHEN** a valid target attempt exists but the winning provider-capable resume cannot issue or link provider authority
- **THEN** no provider-capable invocation starts
- **AND** reconciliation revokes or safely retries that exact resume attempt while the public run remains `interrupted`

#### Scenario: first-use recovery interrupts work with conclusive authority
- **WHEN** `_ensure_runs_recovery` first invokes `recover_in_flight_runs` for rows whose provider reservations and target boundaries are all absent or durably conclusive
- **THEN** those rows become `interrupted` with a restart message and the count is returned
- **AND** succeeded/failed provider budgets remain consumed, cancelled-before-launch authority is released, and no new target attempt is minted

#### Scenario: first-use recovery cancels a dead-owner reservation
- **WHEN** recovery proves the owner dead or invalidates its claim generation and finds a durable provider `reserved` reservation
- **THEN** it transitions the reservation to `cancelled_before_launch`, releases provider authority, and then performs the interrupted sweep

#### Scenario: unprovable run owner is invalidated before sweep
- **WHEN** first-use recovery cannot prove the old run worker dead
- **THEN** the authority stores atomically advance every applicable old execution-claim generation before cancellation or sweep
- **AND** later provider reservations or target claims from that stale process fail validation

#### Scenario: first-use recovery fences ambiguous provider work
- **WHEN** recovery finds an unclosed provider `launch_started`, `indeterminate`, or unreadable reservation
- **THEN** the receipt becomes `fenced_indeterminate` and the run becomes `interrupted` with `provider_authority_fenced`
- **AND** it remains non-runnable until authoritative reconciliation resolves the fence

#### Scenario: first-use recovery fences ambiguous target work
- **WHEN** recovery finds an indeterminate target irreversible boundary
- **THEN** the target attempt is fenced and the run becomes `interrupted` with `target_authority_fenced`
- **AND** no resume or provider issuance starts until reconciliation resolves it

#### Scenario: resolved fences update diagnostic projections
- **WHEN** ledger reconciliation makes every prior provider reservation and target boundary conclusive and clears the work-item fences
- **THEN** the run remains or becomes `interrupted` with stale fence sentinels cleared or replaced by conclusive diagnostics
- **AND** `resume_run` may claim its one coordinated attempt instead of being blocked by stale text

#### Scenario: failed first-use reconciliation is isolated and retryable
- **WHEN** authority reconciliation or run sweep raises for one effective-gate universe
- **THEN** the coordinator does not mark that universe done and a later use retries it
- **AND** affected run operations fail closed only for that universe while independent universes remain live

#### Scenario: non-provider runs retain target-aware first-use recovery
- **WHEN** first-use recovery finds a non-provider-capable row left queued or running
- **THEN** provider authority adds no precondition while applicable target reconciliation still completes before the interrupted sweep

#### Scenario: dark mode retains the shipped first-use sweep
- **WHEN** effective authority gates are dark and recovery finds rows with no authority-ledger record left queued or running
- **THEN** those rows receive the shipped interrupted sweep and count
- **AND** any existing provider or target record is reconciled and fenced regardless of gate state

### Requirement: Live child invocation maps state and supports blocking or async execution

A live child-invocation node SHALL resolve the current Branch definition, map declared parent keys into child input keys, and derive one exact attenuated child binding/attempt from the non-serializable parent delegation before every initial invocation or retry. A branch definition containing `child_actor` MUST fail validation rather than select execution identity. The child authorizer SHALL come from the current parent attempt and its executor SHALL be recorded separately. Each node-execution/invocation/retry ordinal MUST produce one deterministic logical key and pin the current exact branch version/content digest. Target-authority clauses introduced by this change MUST remain dark/non-authorizing until the parent-binding, store-owner, and live-activation prerequisites pass.

Blocking mode MUST invoke the child synchronously without a child-poll timeout and map declared child outputs on success. A non-completed terminal child SHALL apply `propagate`, `default`, or `retry`; node-local `retry_budget=N` permits up to N retries after the initial attempt, with zero coerced to the default of one. The thread-local aggregate counter is reset by synchronous child execution and therefore does not reliably cap live nested retries beyond the local budget; target-authority transfer MUST nevertheless debit every retry and enforce the parent envelope. Live validation does not reject an unknown failure-mode value, which reaches runtime and follows the propagate path on child failure. Async mode MUST return immediately, place the child run ID in the first declared parent output key, and SHALL NOT apply blocking failure policy, but MUST satisfy the same target-authority gate before starting the detached child.

#### Scenario: Blocking live invocation returns mapped child output

- **WHEN** an authorized live child Branch completes in blocking mode
- **THEN** each declared parent output key receives the corresponding child output value

#### Scenario: Async live invocation returns its run identity

- **WHEN** an authorized live child Branch is started in async mode with an output mapping
- **THEN** the first parent output key receives the child run ID and the parent node does not wait for completion
- **AND** the detached run remains bound to its exact child attempt

#### Scenario: Live blocking retry is locally and authoritatively bounded

- **WHEN** a live blocking child repeatedly ends non-completed with `on_child_fail=retry`
- **THEN** the node stops after its local retry budget and propagates, while every retry has one stable ordinal and consumes parent target-authority budget

#### Scenario: Branch-authored child actor is rejected

- **WHEN** a live child-invocation definition contains `child_actor`
- **THEN** validation fails before branch execution rather than treating the value as identity or provenance

### Requirement: Frozen child invocation binds a version and applies blocking failure policy

A frozen child-invocation node SHALL execute the exact stored `branch_version_id` snapshot, map the same input/depth/output fields as live invocation, and derive one exact attenuated child binding/attempt from the non-serializable parent delegation before every initial invocation or retry. A branch definition containing `child_actor` MUST fail validation rather than select execution identity. The exact frozen version/content digest, node-execution/invocation/retry ordinal, canonical authorizer, and separate executor MUST be bound into each attempt. Target-authority clauses introduced by this change MUST remain dark/non-authorizing until the parent-binding, store-owner, and live-activation prerequisites pass.

Frozen blocking SHALL queue the child and poll it with a 300-second default timeout rather than invoke synchronously; a poll timeout MUST follow the parent receipt-wait interruption path before any failure policy is applied. A non-completed terminal child MUST use `propagate`, `default`, or `retry` behavior. `retry_budget=N` permits up to N retries after the initial attempt, with zero coerced to the default of one, and each retry MUST also consume the thread-local per-parent-run aggregate configured by `TINYASSETS_MAX_CHILD_RETRIES_TOTAL` plus the parent target-authority envelope; this counter is not process-wide. Frozen async mode SHALL return the child run ID without applying blocking failure policy but MUST satisfy the same target-authority gate before the detached child becomes runnable.

#### Scenario: Later live edits do not change a frozen child

- **WHEN** a child is invoked by stored version after its live definition changes
- **THEN** execution reconstructs and runs the frozen version snapshot pinned by the child attempt

#### Scenario: Default policy returns declared fallback outputs

- **WHEN** a blocking child ends non-completed with `on_child_fail=default`
- **THEN** the node returns its declared default outputs through the parent mapping instead of failing the parent

#### Scenario: Retry policy is bounded

- **WHEN** a blocking child continues failing under `on_child_fail=retry`
- **THEN** retries stop at the first exhausted node-local, thread-local parent, or target-authority budget and the failure then propagates

#### Scenario: Frozen blocking timeout precedes failure policy

- **WHEN** a frozen blocking child remains non-terminal for the polling timeout
- **THEN** the parent is interrupted into receipt-waiting rather than applying `on_child_fail`

#### Scenario: Frozen child actor is not authority

- **WHEN** a frozen child-invocation definition contains `child_actor`
- **THEN** validation fails before its stored version is queued or executed

### Requirement: Approved source nodes enqueue paced same-universe BranchTasks under trusted bounded context
When the node-enqueue capability is enabled and an approved `source_code` node declares the enqueue tool, `enqueue_branch_run` SHALL append one epoch-1 `BranchTask` carrying only a non-authorizing background-binding reference/digest and SHALL NOT start a run synchronously. The server MUST derive and commit an exact child binding from the non-serializable root/parent delegation before the task becomes pickable. The task SHALL target the trusted physical queue universe; use forced `trigger_source=owner_queued` and `request_type=branch_run`; copy only object inputs; use server-derived parent/origin lineage and parent depth plus one; and target an existing branch permitted by the delegation. Default delegation SHALL permit only same-universe public targets; a private target MUST be on an explicit exact-target allowlist derived from authenticated root/parent authority. Every trusted root run SHALL derive one stable origin shared by all sibling enqueues. One atomic successful-enqueue budget configured by `TINYASSETS_NODE_ENQUEUE_MAX_PER_RUN` SHALL be shared across every source node in the compiled run. A conclusive queue-cap/append refusal MUST abort its prepared child and return the reserved envelope exactly once to the active parent generation, preserving exact admission when capacity exists; an indeterminate boundary remains held and cannot double-credit. Missing trusted/run/delegation context, a foreign universe, mismatched persisted universe metadata, an unauthorized target, invalid inputs, depth or run-wide budget exhaustion, a child-authority refusal, or a shared-cap refusal SHALL fail before a pickable append or surface the atomic refusal as `CompilerError`. Private-target and target-authority clauses introduced by this change MUST remain dark until row-shape, reconciliation, worker-claim, store-owner, and live-activation prerequisites pass.

#### Scenario: Enabled enqueue appends but does not execute
- **WHEN** an approved source node enqueues an existing allowed branch with valid trusted delegation and remaining authority/queue capacity
- **THEN** exactly one forced `owner_queued` `branch_run` task with a non-authorizing binding reference is appended to that trusted universe
- **AND** the target run is left for paced daemon dispatch rather than started synchronously

#### Scenario: Trusted context and target authority fail closed
- **WHEN** enqueue lacks trusted universe, run, or parent-delegation context; names a foreign universe; or targets a branch outside the delegation policy
- **THEN** it raises `CompilerError` without committing a child binding or pickable task

#### Scenario: Branch-authored routing metadata cannot escalate
- **WHEN** source-authored arguments attempt to control the universe, request type, trigger source, parent, origin, depth, principal, or binding reference
- **THEN** the trusted server context and forced routing/authority fields remain authoritative and no privileged scheduler or target class can be selected

#### Scenario: Root siblings share one stable origin
- **WHEN** one trusted root run with no supplied parent or origin enqueues multiple children
- **THEN** every child receives the same server-derived run origin and competes for one lineage and parent-authority budget

#### Scenario: Source nodes share one run-wide enqueue budget
- **WHEN** multiple source nodes in one compiled run attempt more successful enqueues than the run-wide limit or remaining parent envelope
- **THEN** the run commits exactly the smaller remaining run/parent budget across all nodes when queue capacity is sufficient and every excess attempt is refused

#### Scenario: Process identity cannot authorize a private target
- **WHEN** enqueue targets a private branch outside the exact allowlist and the process or context actor string equals its author
- **THEN** enqueue still fails because process identity and actor strings cannot derive child target authority

### Requirement: In-node enqueue remains epoch-1 until transactional v2 preserves its guards
The production in-node enqueue primitive SHALL emit only the epoch-1 file-backed task shape. Epoch-2 is not considered activated for this producer until its transactional path provides a stable server-owned root origin, one atomic run-wide budget, physical tenant/universe binding, attenuated background target authority, atomic global-active and lifetime-lineage count/check/insert, fail-closed integrity equivalent to this capability, and a migration proof that every dark-era row is linked, drained, or held with zero unclassified work. Epoch-1 MUST remain public-by-default and MUST NOT admit a private target until the exact authenticated parent allowlist, committed child binding/attempt, held-row state, recovery, and worker-claim path are all live. Target-authority clauses MUST remain dark until the live-activation requirement and `operator-request-trigger-contract` owner pass.

#### Scenario: Current enqueue emits epoch-1 work
- **WHEN** a valid in-node enqueue is admitted by the current runtime
- **THEN** it writes the file-backed `owner_queued` `branch_run` task with only an opaque authority reference and does not select the v2 transport

#### Scenario: V2 migration is guard-complete
- **WHEN** a future change routes in-node enqueue through transactional v2 storage
- **THEN** that change must prove every stable-origin, run-budget, scope-binding, target-authority, shared-cap, integrity, and dark-row classification invariant before enabling the route

## ADDED Requirements

### Requirement: Held child tasks preserve capacity and lifetime accounting
An epoch-1 or epoch-2 BranchTask SHALL persist `target_authority_held` as a non-pickable status with generation-checked transitions from pending/running, back to pending after either recovery proves a dead/invalidated predecessor and conclusive pre-execution boundary or authenticated reauthorization creates a required new binding generation, and to cancelled under canonical principal/admin authority. Held rows MUST be excluded from the global active pending/running cap and MUST continue to count exactly once against the non-refundable lifetime-lineage cap, including after cancellation and archival. Recovery or reauthorization of the same row MUST NOT append a replacement or consume a second lineage unit. This status MUST remain dark until cancellation, garbage collection, recovery, row-shape, and store-owner prerequisites pass.

#### Scenario: Held work frees active capacity without refunding lifetime growth
- **WHEN** a child task enters `target_authority_held`
- **THEN** unrelated pending work may use the released global active slot
- **AND** that child still consumes one lifetime-lineage unit

#### Scenario: Reauthorization revives the same row
- **WHEN** an authenticated principal repairs a held task with a new valid binding generation
- **THEN** a fenced transition returns that same row to pending without adding another descendant or lineage charge

#### Scenario: Proven dead worker recovers the same row autonomously
- **WHEN** recovery proves the predecessor dead or invalidates its claim generation and proves no indeterminate target boundary
- **THEN** a fenced recovery transition returns the same held row and attempt to claimable work without user reauthorization
