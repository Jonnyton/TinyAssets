## ADDED Requirements

### Requirement: Approved source nodes enqueue paced same-universe BranchTasks under trusted bounded context
When the node-enqueue capability is enabled and an approved `source_code` node declares the enqueue tool, `enqueue_branch_run` SHALL append one `BranchTask` and SHALL NOT start a run synchronously. The task SHALL target the trusted current universe; use forced `trigger_source=owner_queued` and `request_type=branch_run`; copy only object inputs; use server-derived parent/origin lineage and parent depth plus one; and target an existing public branch or a private branch owned by the trusted actor. Every trusted root run SHALL derive one stable origin shared by all sibling enqueues. Missing trusted/run context, a foreign universe, a missing or unauthorized target, invalid inputs, depth or per-run exhaustion, or a shared-cap refusal SHALL fail before append or surface the atomic refusal as `CompilerError`.

#### Scenario: Enabled enqueue appends but does not execute
- **WHEN** an approved source node enqueues an existing branch with valid trusted context and remaining capacity
- **THEN** exactly one forced `owner_queued` `branch_run` task is appended to that trusted universe
- **AND** the target run is left for paced daemon dispatch rather than started synchronously

#### Scenario: Trusted context and target authority fail closed
- **WHEN** enqueue lacks trusted universe or run context, names a foreign universe, or targets a missing or unauthorized private branch
- **THEN** it raises `CompilerError` without appending a task

#### Scenario: Branch-authored routing metadata cannot escalate
- **WHEN** source-authored arguments attempt to control the universe, request type, trigger source, parent, origin, or depth
- **THEN** the trusted server context and forced routing fields remain authoritative and no privileged scheduler class can be selected

#### Scenario: Root siblings share one stable origin
- **WHEN** one trusted root run with no supplied parent or origin enqueues multiple children
- **THEN** every child receives the same server-derived run origin and competes for one lineage budget

### Requirement: Shared in-node enqueue growth caps are atomic under concurrent producers
The in-node enqueue append SHALL read required history, count, and append under the same exclusive per-universe cross-process queue lock. The global cap SHALL count live `pending` and `running` rows. The lineage cap SHALL count unique non-empty `branch_task_id` values across live and archived rows carrying the same trusted `origin_branch_task_id`, plus every matching row without an ID conservatively. Concurrent contenders SHALL admit no more than remaining capacity, preserve every admitted row exactly once in readable queue JSON, and reject every excess contender without append. An unreadable required queue or archive SHALL fail closed.

#### Scenario: Concurrent distinct-origin writers stop exactly at global capacity
- **WHEN** more distinct-origin producers contend concurrently than the global active queue has remaining capacity
- **THEN** exactly the remaining number are appended and every excess producer receives a cap refusal
- **AND** the queue contains no duplicate, lost, or corrupt admitted row

#### Scenario: Concurrent same-origin writers stop exactly at lineage capacity
- **WHEN** more producers with one trusted origin contend concurrently than that lineage has remaining lifetime capacity
- **THEN** exactly the remaining number are appended and every excess producer receives a cap refusal
- **AND** unrelated origins remain admissible while global capacity remains

#### Scenario: Archived descendants still consume lineage capacity
- **WHEN** terminal descendants of an origin have moved from the live queue to the archive
- **THEN** those archived rows still count toward later lineage admission

#### Scenario: Crash-window overlap counts one identified descendant
- **WHEN** one identified task row exists in both the archive and live queue after an interrupted archive-first collection
- **THEN** lineage admission counts that `branch_task_id` once rather than falsely exhausting two slots

#### Scenario: Corrupt lineage history refuses admission
- **WHEN** a lineage-capped enqueue requires an archive that cannot be read or decoded
- **THEN** admission fails without appending or resetting lineage history
