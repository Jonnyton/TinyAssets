## ADDED Requirements

### Requirement: Drain Candidate Selection Uses Fresh Current-Main State

A long-lived OpenSpec drain controller SHALL refresh `origin` before each
controller-side candidate selection and SHALL classify candidates from the
exact fetched `origin/main:STATUS.md` state without moving or rewriting its
live checkout. The canonical claim helper SHALL support explicit read-only
classification from a caller-selected Git ref while preserving working-tree
classification as its default. Fetch failure, unreadable ref state, or invalid
claim JSON MUST fail the snapshot closed and MUST NOT fall back to a stale
working-tree candidate or dispatch a worker without a current snapshot. A live
controller retrying that bounded failure SHALL report waiting health until it
recovers or reaches its visible terminal failure budget. Admission SHALL still
create a fresh current-main
worktree and revalidate the candidate there after writing its local claim, so a
merge race or changed row cannot dispatch invalid work.

#### Scenario: A merged slice retires the formerly selected row

- **WHEN** a worker merge removes or changes a STATUS row while the detached
  controller checkout still contains the old row
- **THEN** the next selection fetches origin and classifies
  `origin/main:STATUS.md`
- **AND** the retired working-tree row is not offered again

#### Scenario: Current-main refresh fails

- **WHEN** origin fetch or `origin/main:STATUS.md` inspection fails
- **THEN** candidate snapshot inspection fails with an observable diagnostic
- **AND** the controller dispatches no worker from its stale checkout
- **AND** watchdog health reports waiting until recovery or terminal failure

#### Scenario: Admission writes a local claim after current-main selection

- **WHEN** the controller selects a current-main candidate and admission writes
  its claim into the newly created worktree
- **THEN** admission revalidation classifies that worktree state
- **AND** it can observe the local owned claim before dispatch

#### Scenario: A provider checks an uncommitted coordination edit

- **WHEN** `claim_check.py` is invoked without an explicit status ref
- **THEN** it retains working-tree STATUS classification
- **AND** no fetch or ref mutation occurs
