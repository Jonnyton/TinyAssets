## ADDED Requirements

### Requirement: Task Automation Is User-Authored Primitive Composition

TinyAssets SHALL expose domain-agnostic composition and execution primitives
without shipping a privileged bug-investigation, patch-shipping, or recurring
task loop. Investigation, patch generation, scheduling, shipping, and other
automation SHALL run only as user-authored workflows under the same identity,
authority, execution, and effect rules as other graph designs. Authors MAY
publish those designs to the commons for copying, remixing, or combination.

#### Scenario: Filing does not select a platform-owned workflow

- **WHEN** a user files a bug, feature, design, or patch-request page
- **THEN** TinyAssets does not select, enqueue, or execute a platform-owned
  investigation or shipping workflow
- **AND** any later automation requires an explicit user-authored composition

#### Scenario: A user composes automation from generic primitives

- **WHEN** an authorized user wants to connect intake, graph execution,
  evaluation, and an external or wiki effect
- **THEN** the user can design or install a workflow composed from the ordinary
  primitives that are available to other graph designs
- **AND** the workflow receives no hidden product-specific action, request type,
  credential, or effect authority

#### Scenario: Generic completed-run reuse has no packet writeback

- **WHEN** a generic branch task reuses a matching completed durable run
- **THEN** the executor may return its ordinary reused-run evidence without
  executing again
- **AND** it does not interpret output field names as authority to mutate a wiki
  page or repository

### Requirement: Retired Request Classes Fail Closed Before Generic Execution

Dispatcher admission and claim SHALL reject the retired
`bug_investigation` request class before branch-run or universe-cycle
execution. An idempotent pre-worker upgrade migration SHALL quarantine or
terminally refuse every pending/queued v1/v2 row of that class, fence and
cancel every claimed/running row before lease recovery, and retain completed
rows as immutable historical evidence. Trigger receipts associated only with
the retired loop SHALL be archived or removed under recorded retention policy.
No row, payload, receipt, or completed replay MAY be reinterpreted as a generic
request, branch run, universe cycle, or user-authored workflow.

The migration SHALL be the first ordered stage of the startup/first-use
recovery boundary and SHALL complete for the applicable store before the
`harden-background-provider-execution-authority` (#1803) coordinator performs
provider-authority reconciliation or sweeps provider-capable or non-provider
runs. That coordinator SHALL NOT issue or recover authority for, resume, sweep
as ordinary work, or reinterpret a retired row.

#### Scenario: Pending retired row cannot reach a worker

- **WHEN** upgrade encounters a pending or queued `bug_investigation` row
- **THEN** migration atomically records a retirement reason and moves it to a terminally refused or quarantined state before workers start
- **AND** dispatcher selection and claim both refuse the retired class

#### Scenario: Claimed or running retired row loses execution race

- **WHEN** upgrade encounters a claimed or running retired row or its lease later recovers
- **THEN** migration fences and cancels it before generic execution can start or resume
- **AND** migration completes before #1803 provider-authority reconciliation or ordinary run recovery begins for the applicable store
- **AND** no branch, universe cycle, task, run, or wiki write-back is produced

#### Scenario: Completed retired history is non-executable

- **WHEN** a caller reads or replays a completed historical retired row
- **THEN** its immutable evidence remains readable under retention policy
- **AND** replay cannot resubmit, requeue, reinterpret, or execute it
