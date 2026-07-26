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

#### Scenario: Patch announcements require explicit workflow authority

- **WHEN** a deployment or main push completes
- **THEN** TinyAssets does not automatically compose and post a patch-loop announcement
- **AND** any later outbound announcement is an explicitly selected workflow with its own narrow authority and receipt

### Requirement: Retired Request Classes Fail Closed Before Generic Execution

Dispatcher admission and claim SHALL reject the retired
`bug_investigation` request class before branch-run or universe-cycle
execution. An idempotent pre-worker upgrade migration SHALL quarantine or
terminally refuse every pending row of that class through the exact existing
v1/v2 transitions owned by `daemon-runtime-and-dispatch`, make every
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
without queue mutation. After releasing a successful authority transaction, it
SHALL apply only the existing-state transitions owned by
`daemon-runtime-and-dispatch`: conclusive work may exact-CAS to `cancelled`;
readable ambiguous work is not reset or terminalized and only its receipt is
fenced (a v2 row may additionally become disabled/quarantined by exact CAS);
unreadable work receives no queue mutation. A changed tuple restarts
reconciliation. An ambiguous fence remains non-runnable until authoritative
evidence becomes conclusive, then may finish retirement without re-execution.

Retirement classification and fail-closed admission SHALL precede ordinary
startup/first-use recovery. #1803 SHALL NOT issue new authority for, resume, or
sweep a retired row as ordinary provider-capable or non-provider work, while
its authority reconciliation remains mandatory before queue terminalization.

#### Scenario: Pending retired row cannot reach a worker

- **WHEN** upgrade encounters a pending `bug_investigation` row
- **THEN** migration atomically records the daemon-runtime-owned v1 `cancelled` or v2 `cancelled` plus disabled/quarantine transition before workers start
- **AND** dispatcher selection and claim both refuse the retired class

#### Scenario: Claimed or running retired row loses execution race

- **WHEN** upgrade encounters a claimed or running retired row or its lease later recovers
- **THEN** admission and claim reject it before generic execution can start or resume
- **AND** retirement reconciles its authority record under #1803 before queue-CAS against the exact task/claim/lease generation
- **AND** only reserved-before-launch authority is cancelled and released, while ambiguous authority remains fenced-indeterminate
- **AND** no new or resumed branch, universe cycle, task, run, or wiki write-back is produced after retirement classification
- **AND** any pre-cutover execution evidence remains immutable

#### Scenario: Unreadable authority cannot be retired by inference

- **WHEN** the authority or lineage store for a claimed/running retired row is unreadable
- **THEN** retirement preserves the current row and receipt and records a non-runnable hold
- **AND** it does not release authority, queue-CAS a terminal state, retry, resume, or infer absence

#### Scenario: Completed retired history is non-executable

- **WHEN** a caller reads or replays a completed historical retired row
- **THEN** its immutable evidence remains readable under retention policy
- **AND** replay cannot resubmit, requeue, reinterpret, or execute it
