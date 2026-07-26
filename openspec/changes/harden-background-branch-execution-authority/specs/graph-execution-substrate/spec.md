## MODIFIED Requirements

### Requirement: Approved source nodes enqueue paced same-universe BranchTasks under trusted bounded context
When the node-enqueue capability is enabled and an approved `source_code` node declares the enqueue tool, `enqueue_branch_run` SHALL append one epoch-1 `BranchTask` carrying only a non-authorizing background-binding reference/digest and SHALL NOT start a run synchronously. The server MUST derive and commit an exact child binding from the non-serializable root/parent delegation before the task becomes pickable. The task SHALL target the trusted physical queue universe; use forced `trigger_source=owner_queued` and `request_type=branch_run`; copy only object inputs; use server-derived parent/origin lineage and parent depth plus one; and target an existing branch permitted by the delegation. Default delegation SHALL permit only same-universe public targets; a private target MUST be on an explicit exact-target allowlist derived from authenticated root/parent authority. Every trusted root run SHALL derive one stable origin shared by all sibling enqueues. One atomic successful-enqueue budget SHALL be shared across every source node in the compiled run. Missing trusted/run/delegation context, a foreign universe, mismatched persisted universe metadata, an unauthorized target, invalid inputs, depth or run-wide budget exhaustion, a child-authority refusal, or a shared-cap refusal SHALL fail before a pickable append or surface the atomic refusal as `CompilerError`.

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
The production in-node enqueue primitive SHALL emit only the epoch-1 file-backed task shape until transactional v2 is activated. Epoch-1 MUST remain public-by-default and MUST NOT admit a private target without an exact authenticated parent allowlist and a committed child binding/attempt path. The primitive MUST NOT emit epoch-2 tasks until the transactional v2 path provides a stable server-owned root origin, one atomic run-wide budget, physical tenant/universe binding, attenuated background target authority, atomic global-active and lifetime-lineage count/check/insert, fail-closed integrity, and a migration proof that every dark-era row is linked, drained, or held with zero unclassified work.

#### Scenario: Current enqueue emits epoch-1 work
- **WHEN** a valid in-node enqueue is admitted by the current runtime
- **THEN** it writes the file-backed `owner_queued` `branch_run` task with only an opaque authority reference and does not select the v2 transport

#### Scenario: V2 migration is guard-complete
- **WHEN** a future change routes in-node enqueue through transactional v2 storage
- **THEN** that change must prove every stable-origin, run-budget, scope-binding, target-authority, shared-cap, integrity, and dark-row classification invariant before enabling the route
