## ADDED Requirements

### Requirement: OpenSpec Delivery Flow Is Inspectable

The development coordination runtime SHALL provide a read-only OpenSpec flow
inspector that enumerates active change directories, counts completed and
unchecked task checkboxes, maps exact active change names to `STATUS.md` Work
rows and owners, reports global and exact-session provider WIP, and reports
recent active-change admission and archive counts when a git comparison window
is requested. It MUST expose equivalent human-readable and JSON results and
MUST NOT create, edit, claim, split, sync, archive, or delete any change.
Audit mode SHALL be invoked on demand for dispatch/triage, not as a mandatory
session-start step.

#### Scenario: Current flow is reported without mutation

- **WHEN** a provider runs the inspector against a repository with active
  OpenSpec changes
- **THEN** the result includes aggregate task totals and one record per change
- **AND** the tracked working tree is byte-identical before and after inspection

#### Scenario: Incomplete active change is absent from live coordination

- **WHEN** an active change with unchecked tasks appears in no `STATUS.md` Work
  row
- **THEN** the inspector classifies that change as `untracked`
- **AND** it does not infer implementation authority from the change artifacts

#### Scenario: Automation requests JSON

- **WHEN** the inspector is invoked in JSON mode
- **THEN** it emits a parseable object containing the same aggregate, change,
  provider-WIP, warning, and recommendation information as text mode

### Requirement: New OpenSpec Delivery Changes Are Bounded

The inspector's named change-admission check SHALL reject a candidate with more
than 12 total task checkboxes, completed or unchecked, and SHALL reject
admission when the requesting exact session-specific provider identity already
owns another claimed or in-flight OpenSpec change. It SHALL report global WIP
with the result and SHALL treat minting a provider suffix to evade the limit as
a process-review violation. It SHALL report umbrella/full-vision language as a
semantic-review warning rather than claiming keyword detection proves invalid
scope. Existing oversized changes MUST remain reportable in default audit mode
and MUST NOT make default inspection fail. The 12-task ceiling is a 2026-07-28
calibration that SHALL be reviewed on 2026-08-11 against observed cycle time and
current model capability. Admission mode SHALL run only after scaffolding and
before claiming or building a change.

#### Scenario: Candidate exceeds the task ceiling

- **WHEN** a named candidate change contains 13 task checkboxes
- **THEN** admission exits 2 and identifies the 12-task ceiling

#### Scenario: Provider already owns delivery WIP

- **WHEN** the requesting provider owns one claimed active change and asks to
  admit a different active change
- **THEN** admission exits 2 and identifies the existing change
- **AND** reports global active delivery WIP

#### Scenario: Legacy oversized change is audited

- **WHEN** default audit encounters a pre-existing change with more than 12
  total task checkboxes
- **THEN** it reports the change as oversized
- **AND** the audit remains read-only and exits successfully

### Requirement: OpenSpec Dispatch Is Finish-First

The inspector SHALL recommend complete-but-unarchived changes before any
change with unchecked tasks, then claimed changes by ascending unchecked-task
count, then queued changes by ascending unchecked-task count. It MUST report
untracked changes for triage without recommending that they be built.

#### Scenario: Completed active change exists

- **WHEN** one active change has zero unchecked tasks and another claimed
  change has unchecked tasks
- **THEN** the completed change is the first recommendation

#### Scenario: Claimed slices differ in remaining size

- **WHEN** two claimed changes have no completed change ahead of them
- **AND** one has fewer unchecked tasks than the other
- **THEN** the smaller claimed change is recommended first

#### Scenario: Only untracked changes remain

- **WHEN** every active change is absent from the STATUS Work table
- **THEN** the inspector reports no build recommendation
- **AND** it directs the provider to triage coordination state first
