## ADDED Requirements

### Requirement: Retired Investigation Rows Use Existing Queue States And Authority-Safe Quarantine

Before cutover, dispatcher admission and claim SHALL reject
`request_type=bug_investigation`. A deployment without the effective #1803
`ProviderWorkAuthorityStore` and reconciler SHALL quiesce every legacy worker
capable of executing that request type and prove no v1 `running` or v2
`running`/`cancel_requested` retired row exists; otherwise deployment SHALL
stop before runtime replacement. An absent, unimplemented, unavailable, or
unreadable authority store never authorizes queue mutation of a claimed row.

The idempotent migration SHALL use only existing persisted queue states and
fields:

- a v1 `pending` row conditionally becomes `cancelled` under the file lock,
  with its existing `error` and `terminal_at` fields recording the stable
  retirement reason/time;
- a v2 `pending` row conditionally becomes `cancelled`, `disabled=1`, with
  `quarantine_reason=retired_request_type:bug_investigation`, matching
  `terminal_at`, linked request/admission terminal projection, and one
  retirement event in the same transaction;
- a claimed v1/v2 row changes only after #1803 proves the owner dead or
  invalidates its exact claim generation and returns a reconciliation proof
  bound to the unchanged task, owner, and lease generation;
- no-reservation or durably conclusive `cancelled_before_launch`,
  `succeeded`, or `failed` authority permits an exact queue CAS to the existing
  `cancelled` state; succeeded/failed authority and consumed budget remain
  immutable in the authority ledger;
- a readable `launch_started` or `indeterminate` reservation fences the
  receipt as `fenced_indeterminate`; the v1 row retains its existing running
  state, while a v2 row retains `running` or `cancel_requested` and may only be
  marked `disabled=1` with
  `quarantine_reason=retired_request_provider_authority_fenced` by the exact
  post-reconciliation CAS; and
- unreadable authority preserves the row and receipt unchanged under a
  non-runnable hold with no release, retry, resume, or queue CAS.

Rows already `succeeded`, `failed`, or `cancelled` SHALL remain unchanged
historical evidence. Every migration attempt SHALL emit bounded counts and
identifiers/digests for prior/final state and retention action without
reinterpreting or resubmitting work.

When #1803's bounded autonomous reconciliation window cannot resolve a retired
ambiguous receipt, the #1803 owner SHALL emit its
`manual_resolution_required` operator action. Manual resolution may advance
only from authoritative launch/result evidence to the matching conclusive
authority terminal, after which retirement may finish its existing-state queue
transition; it SHALL never authorize a retry or replacement execution.

#### Scenario: Pre-1803 deployment cannot strand a live legacy worker

- **WHEN** #1803 runtime authority is unavailable and any legacy worker is not quiesced or any retired v1/v2 claimed row exists
- **THEN** deployment stops before replacing runtime or deleting its evidence readers
- **AND** no missing authority store is treated as proof that provider work did not launch

#### Scenario: Pending v1 row uses cancelled

- **WHEN** migration observes an unchanged v1 retired row in `pending`
- **THEN** one file-locked CAS records `cancelled`, the stable retirement reason, and terminal time
- **AND** no new queue status or execution is introduced

#### Scenario: Pending v2 row uses disabled quarantine

- **WHEN** migration observes an unchanged v2 retired row in `pending`
- **THEN** one transaction records `cancelled`, `disabled=1`, the stable quarantine reason, matching linked terminal projections, and one retirement event
- **AND** admission and claim cannot select it

#### Scenario: Conclusive claimed work terminalizes after authority proof

- **WHEN** #1803 returns an exact current-generation proof with no reservation or only conclusive cancelled-before-launch, succeeded, or failed authority
- **THEN** migration CASes the unchanged v1/v2 queue tuple to `cancelled`
- **AND** it releases only cancelled-before-launch authority while preserving succeeded/failed consumption and evidence

#### Scenario: Ambiguous claimed work is fenced without reset

- **WHEN** #1803 finds readable `launch_started` or `indeterminate` authority for a retired claimed row
- **THEN** its receipt becomes `fenced_indeterminate` and the row is not reset or terminalized
- **AND** v1 retains its current running state while v2 retains `running` or `cancel_requested` and may only add the disabled quarantine fields by exact CAS
- **AND** no new or resumed execution starts after retirement classification

#### Scenario: Completed history remains exact

- **WHEN** migration encounters an already succeeded, failed, or cancelled retired row
- **THEN** its existing status and evidence remain unchanged
- **AND** replay and recovery cannot resubmit or reinterpret it

#### Scenario: Retired ambiguity retains the operator action

- **WHEN** bounded #1803 reconciliation cannot resolve a retired fenced receipt
- **THEN** the work remains non-runnable and emits `manual_resolution_required`
- **AND** only authoritative evidence may resolve the fence, never a rerun or compatibility execution

### Requirement: Completed Branch Tasks Reuse Stable Durable Runs Without Product Writeback

The daemon branch-task executor SHALL derive the stable run name
`branch-task-<branch_task_id>` and reuse a matching completed durable run
rather than execute it again. It SHALL return metadata containing the reused
run id, status, actor, branch definition, and `reused_existing_run=true`; the
stored output remains internal execution evidence. Generic reuse SHALL NOT
inspect product packet field names or mutate a wiki/repository.

#### Scenario: Completed durable run is reused after restart

- **WHEN** a claimed branch task has a matching completed run under its stable run name
- **THEN** the executor returns the exact reused-run metadata and does not invoke branch execution again
- **AND** it performs no Patch Packet recovery or writeback

#### Scenario: Nonmatching or incomplete run is not reused

- **WHEN** no matching completed durable run exists for the stable task name
- **THEN** the executor follows the ordinary authorized execution path
- **AND** no stale or differently named run is treated as the task result
