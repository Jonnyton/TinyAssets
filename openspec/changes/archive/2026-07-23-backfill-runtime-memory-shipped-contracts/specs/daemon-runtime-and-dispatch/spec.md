## ADDED Requirements

### Requirement: Claimed-task heartbeats refresh only the current running lease

The branch-task queue SHALL refresh heartbeat and lease timestamps only for a
`running` task under the queue file lock. When both a supplied worker owner and
an existing owner are non-empty, an owner mismatch MUST return no update; a
heartbeat refresh MUST NOT reclaim or transition the task.

#### Scenario: Current owner refreshes a running task

- **WHEN** the claiming worker refreshes a running task heartbeat
- **THEN** the task remains running and receives new `heartbeat_at` and `lease_expires_at` values

#### Scenario: A stale worker cannot overwrite another owner lease

- **WHEN** a worker owner different from the stored owner attempts a heartbeat refresh
- **THEN** the helper returns no task and leaves the stored lease unchanged

#### Scenario: Heartbeat is inert for a non-running task

- **WHEN** heartbeat refresh targets a pending or terminal task
- **THEN** the helper returns no task without changing its status or lease fields

### Requirement: Branch-task cancellation distinguishes observed pending and running work

The queue-cancel action SHALL mark a task observed as pending terminally
`cancelled` through a later locked mutation. For a task observed as `running`,
it MUST require either the claiming daemon identity or the
`cancel_branch_task` capability and set an idempotent cooperative-cancel flag
under the queue lock. The legacy wrapper graph stream SHALL poll that flag at
inter-node events and finalize an observed cancellation as `cancelled`, not
`failed`. Current direct BranchTask and NodeBid execution paths do not poll the
BranchTask flag and therefore do not guarantee cooperative cancellation. The
initial status read and later cancellation mutation are separate locked
operations, so a concurrent pending-to-running claim can enter the immediate
cancel path without the running-task authorization check.

#### Scenario: Work observed pending is cancelled immediately

- **WHEN** queue cancellation targets a pending branch task
- **THEN** the task is marked `cancelled` without entering cooperative running-task cancellation

#### Scenario: Unauthorized running-task cancellation is refused

- **WHEN** an actor is neither the claiming daemon nor authorized with `cancel_branch_task`
- **THEN** queue cancellation returns `cancel_not_authorized` and does not set the cancel flag

#### Scenario: Legacy wrapper cancellation is cooperative and idempotent

- **WHEN** an authorized actor requests cancellation one or more times for a running task executing through the legacy wrapper stream
- **THEN** the cancel flag remains set, that stream observes it between node events, and finalizes the task as `cancelled`

#### Scenario: Direct execution can finish after a cancellation request

- **WHEN** cancellation is requested during direct BranchTask or NodeBid execution
- **THEN** the flag is retained, but the current executor may still finalize the task from its execution outcome

#### Scenario: Pending classification has a claim race

- **WHEN** a task is claimed after queue-cancel observes it as pending but before the immediate status mutation
- **THEN** the running task can be marked cancelled without passing the running-task authorization branch

### Requirement: Queue garbage collection archives only old terminal tasks

The branch-task garbage collector SHALL, under the queue file lock, move only
terminal tasks whose string-valued `queued_at` parses before the configured
cutoff into the archive. It MUST retain pending, running, recent terminal,
missing/empty-date, and terminal rows whose string date raises `ValueError` in
`datetime.fromisoformat`; a truthy non-string date currently raises `TypeError`
and aborts collection. It SHALL replace the archive atomically before rewriting
the live queue; if the existing archive is unreadable or invalid JSON, it SHALL
log a warning and start a fresh archive with the newly collected rows.

#### Scenario: Active and recent tasks survive collection

- **WHEN** garbage collection sees old pending or running tasks and a recent terminal task
- **THEN** all of those rows remain in the live queue

#### Scenario: Old terminal work moves to the archive

- **WHEN** a terminal task has a parseable `queued_at` before the cutoff
- **THEN** it is appended to the archive and removed from the live queue

#### Scenario: Corrupt prior archive is not preserved

- **WHEN** old terminal rows are collected while the existing archive cannot be decoded
- **THEN** the collector logs the corruption and writes a fresh archive containing the newly collected rows

### Requirement: Blanket running-task recovery remains a callable unsafe helper

The current `recover_claimed_tasks` helper SHALL remain callable and, under the
queue file lock, reset every `running` task to `pending` while clearing claim,
worker-owner, heartbeat, and lease fields. It SHALL retain executor-worker,
executor-runtime, progress, and cancel-request fields. The helper currently has no production
call site; startup behavior remains owned by the existing canonical lease-aware
and worker-scoped recovery requirement.

#### Scenario: Direct blanket recovery clears every running claim

- **WHEN** a caller explicitly invokes `recover_claimed_tasks` on a queue with running tasks
- **THEN** every running row becomes pending with `claimed_by`, `worker_owner_id`, `heartbeat_at`, and `lease_expires_at` cleared while executor identity, progress, and `cancel_requested` are retained
