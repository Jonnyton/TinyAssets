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

#### Scenario: Agent guidance cannot recreate the retired product

- **WHEN** a coding or operations agent selects an active TinyAssets skill
- **THEN** no skill or catalog route instructs it to file a synthetic request into, wait for, repair, or verify a platform-owned investigation/shipping loop
- **AND** historical incident evidence is not packaged as an invocable loop skill

#### Scenario: Repository effects require explicit workflow authority

- **WHEN** a pull request opens or a deployment/main push completes
- **THEN** TinyAssets does not implicitly enroll the pull request for merge or automatically compose and post a patch announcement
- **AND** any later merge or outbound announcement is an explicitly selected workflow with its own narrow authority and receipt

### Requirement: Retired Request Classes Fail Closed Before Generic Execution

Dispatcher admission and claim SHALL reject the retired
`bug_investigation` request class before branch-run or universe-cycle
execution. An idempotent pre-worker upgrade migration SHALL quarantine or
terminally refuse every pending/queued v1/v2 row of that class, make every
claimed/running row non-admissible and non-claimable, and retain completed rows
as immutable historical evidence. Trigger receipts associated only with the
retired loop SHALL be archived or removed under recorded retention policy. No
row, payload, receipt, or completed replay MAY be reinterpreted as a generic
request, branch run, universe cycle, or user-authored workflow.

For a claimed/running retired row, the retirement coordinator SHALL use the
`harden-background-provider-execution-authority` (#1803) authority-store-first
protocol before queue mutation: prove the old owner dead or invalidate its
execution-claim generation; cancel and release only `reserved`-before-launch
authority; preserve consumed authority for conclusive `succeeded`/`failed`
work; preserve readable `launch_started` or `indeterminate` receipts as
`fenced_indeterminate` without release, retry, resume, or inferred outcome; and
on an unreadable authority store preserve the existing row/receipt and hold
without queue mutation. After releasing a successful authority transaction,
it SHALL queue-CAS the exact
task/claim/lease generation into the matching retired terminal or fenced
state. A changed tuple restarts reconciliation. An ambiguous fence remains
non-runnable until authoritative evidence becomes conclusive, then finishes
the retirement transition without re-execution.

Retirement classification and fail-closed admission SHALL precede ordinary
startup/first-use recovery. #1803 SHALL NOT issue new authority for, resume, or
sweep a retired row as ordinary provider-capable or non-provider work, while
its authority reconciliation remains mandatory before queue terminalization.

#### Scenario: Pending retired row cannot reach a worker

- **WHEN** upgrade encounters a pending or queued `bug_investigation` row
- **THEN** migration atomically records a retirement reason and moves it to a terminally refused or quarantined state before workers start
- **AND** dispatcher selection and claim both refuse the retired class

#### Scenario: Claimed or running retired row loses execution race

- **WHEN** upgrade encounters a claimed or running retired row or its lease later recovers
- **THEN** admission and claim reject it before generic execution can start or resume
- **AND** retirement reconciles its authority record under #1803 before queue-CAS against the exact task/claim/lease generation
- **AND** only reserved-before-launch authority is cancelled and released, while ambiguous authority remains fenced-indeterminate
- **AND** no branch, universe cycle, task, run, or wiki write-back is produced

#### Scenario: Unreadable authority cannot be retired by inference

- **WHEN** the authority or lineage store for a claimed/running retired row is unreadable
- **THEN** retirement preserves the current row and receipt and records a non-runnable hold
- **AND** it does not release authority, queue-CAS a terminal state, retry, resume, or infer absence

#### Scenario: Completed retired history is non-executable

- **WHEN** a caller reads or replays a completed historical retired row
- **THEN** its immutable evidence remains readable under retention policy
- **AND** replay cannot resubmit, requeue, reinterpret, or execute it
