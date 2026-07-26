## MODIFIED Requirements

### Requirement: Live child invocation maps state and supports blocking or async execution

A live child-invocation node SHALL resolve the current Branch definition, map declared parent keys into child input keys, and derive one exact attenuated child binding/attempt from the non-serializable parent delegation before every initial invocation or retry. A branch definition containing `child_actor` MUST fail validation rather than select execution identity. The child authorizer SHALL come from the current parent attempt and its executor SHALL be recorded separately. Each node-execution/invocation/retry ordinal MUST produce one deterministic logical key and pin the current exact branch version/content digest.

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

A frozen child-invocation node SHALL execute the exact stored `branch_version_id` snapshot, map the same input/depth/output fields as live invocation, and derive one exact attenuated child binding/attempt from the non-serializable parent delegation before every initial invocation or retry. A branch definition containing `child_actor` MUST fail validation rather than select execution identity. The exact frozen version/content digest, node-execution/invocation/retry ordinal, canonical authorizer, and separate executor MUST be bound into each attempt.

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
When the node-enqueue capability is enabled and an approved `source_code` node declares the enqueue tool, `enqueue_branch_run` SHALL append one epoch-1 `BranchTask` carrying only a non-authorizing background-binding reference/digest and SHALL NOT start a run synchronously. The server MUST derive and commit an exact child binding from the non-serializable root/parent delegation before the task becomes pickable. The task SHALL target the trusted physical queue universe; use forced `trigger_source=owner_queued` and `request_type=branch_run`; copy only object inputs; use server-derived parent/origin lineage and parent depth plus one; and target an existing branch permitted by the delegation. Default delegation SHALL permit only same-universe public targets; a private target MUST be on an explicit exact-target allowlist derived from authenticated root/parent authority. Every trusted root run SHALL derive one stable origin shared by all sibling enqueues. One atomic successful-enqueue budget configured by `TINYASSETS_NODE_ENQUEUE_MAX_PER_RUN` SHALL be shared across every source node in the compiled run. Missing trusted/run/delegation context, a foreign universe, mismatched persisted universe metadata, an unauthorized target, invalid inputs, depth or run-wide budget exhaustion, a child-authority refusal, or a shared-cap refusal SHALL fail before a pickable append or surface the atomic refusal as `CompilerError`.

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
- **THEN** the run commits no more than the smaller remaining budget across all nodes and every excess attempt is refused

#### Scenario: Process identity cannot authorize a private target
- **WHEN** enqueue targets a private branch outside the exact allowlist and the process or context actor string equals its author
- **THEN** enqueue still fails because process identity and actor strings cannot derive child target authority

### Requirement: In-node enqueue remains epoch-1 until transactional v2 preserves its guards
The production in-node enqueue primitive SHALL emit only the epoch-1 file-backed task shape until transactional v2 is activated. Epoch-1 MUST remain public-by-default and MUST NOT admit a private target without an exact authenticated parent allowlist and a committed child binding/attempt path. The primitive MUST NOT emit epoch-2 tasks until the transactional v2 path provides a stable server-owned root origin, one atomic run-wide budget, physical tenant/universe binding, attenuated background target authority, atomic global-active and lifetime-lineage count/check/insert, fail-closed integrity equivalent to this capability, and a migration proof that every dark-era row is linked, drained, or held with zero unclassified work.

#### Scenario: Current enqueue emits epoch-1 work
- **WHEN** a valid in-node enqueue is admitted by the current runtime
- **THEN** it writes the file-backed `owner_queued` `branch_run` task with only an opaque authority reference and does not select the v2 transport

#### Scenario: V2 migration is guard-complete
- **WHEN** a future change routes in-node enqueue through transactional v2 storage
- **THEN** that change must prove every stable-origin, run-budget, scope-binding, target-authority, shared-cap, integrity, and dark-row classification invariant before enabling the route

## ADDED Requirements

### Requirement: Held child tasks preserve capacity and lifetime accounting
An epoch-1 or epoch-2 BranchTask SHALL persist `target_authority_held` as a non-pickable status with generation-checked transitions from pending/running and back to pending only after authenticated reauthorization creates a new binding generation. Held rows MUST be excluded from the global active pending/running cap and MUST continue to count exactly once against the non-refundable lifetime-lineage cap, including after cancellation or archival. Reauthorization of the same row MUST NOT append a replacement or consume a second lineage unit.

#### Scenario: Held work frees active capacity without refunding lifetime growth
- **WHEN** a child task enters `target_authority_held`
- **THEN** unrelated pending work may use the released global active slot
- **AND** that child still consumes one lifetime-lineage unit

#### Scenario: Reauthorization revives the same row
- **WHEN** an authenticated principal repairs a held task with a new valid binding generation
- **THEN** a fenced transition returns that same row to pending without adding another descendant or lineage charge
