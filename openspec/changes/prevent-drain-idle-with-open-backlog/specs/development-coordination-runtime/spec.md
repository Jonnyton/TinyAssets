## ADDED Requirements

### Requirement: STATUS row lifecycle edits are row-scoped coordination
The claim checker SHALL treat adding, claiming, heartbeating, and retiring a lane's own `STATUS.md` Work row as an implicit coordination operation rather than a whole-file write collision. An exact `STATUS.md` Files atom MUST NOT overlap another lane, while every other product or artifact atom MUST retain the existing symmetric substring collision rule.

#### Scenario: Active row lists STATUS as a legacy file atom
- **WHEN** one live claim lists `STATUS.md` and a disjoint pending row also lists `STATUS.md`
- **THEN** the pending row is not blocked solely by that shared coordination atom
- **AND** any overlapping non-STATUS atom still blocks it

#### Scenario: Prospective row lifecycle edit
- **WHEN** a provider checks a prospective Files set containing only its product paths plus `STATUS.md`
- **THEN** the result ignores the exact STATUS atom and reports collisions from the product paths only

### Requirement: OpenSpec delivery flow supports exact-ref inspection
The OpenSpec flow inspector SHALL support a caller-selected validated Git ref and SHALL classify `STATUS.md`, active change artifacts, task counts, ownership, and recommendations from one immutable snapshot of that ref. Ref inspection MUST remain read-only, MUST NOT move the working tree, and MUST fail closed rather than mixing working-tree and ref content.

#### Scenario: Detached controller is behind current main
- **WHEN** the working tree contains older OpenSpec or STATUS content and the caller selects `origin/main`
- **THEN** the inspector reports only the active changes, tasks, rows, and classifications stored at `origin/main`

#### Scenario: Ref snapshot is unavailable
- **WHEN** the selected ref cannot be validated or its coordination snapshot cannot be read
- **THEN** inspection exits non-zero with a bounded diagnostic
- **AND** it emits no fallback report from the working tree

### Requirement: OpenSpec drain refines visible backlog before idle
When owned, claimable, and policy-qualified stale STATUS candidates are absent, the drain supervisor SHALL inspect exact-current-main OpenSpec flow and SHALL provide one bounded existing-change refinery target before accepting candidate exhaustion. Refinery admission MUST exclude live-owned, host-owned, and invalid-artifact changes, MUST authorize coordination reconciliation only, and MUST NOT authorize product implementation before a normal current-main claim exists.

#### Scenario: STATUS is blocked while untracked changes remain
- **WHEN** claim pressure is zero and exact current main contains an incomplete untracked OpenSpec change
- **THEN** the next worker brief names that change as a refinery target
- **AND** `NO_CANDIDATE` is rejected while that target remains refinable

#### Scenario: Refinery promotes bounded implementation work
- **WHEN** the refinery worker proves one existing change has a safe bounded acceptance contract
- **THEN** it lands one exact pending STATUS row through normal review and returns a continuation result
- **AND** a fresh worker performs ordinary collision checking and claim admission before product edits

#### Scenario: Refinery proves a durable blocker
- **WHEN** the existing change requires a current host, dependency, policy, or review gate
- **THEN** the worker lands that blocker on the exact STATUS row before returning `BLOCKED`
- **AND** recent-block suppression prevents immediate repetitive triage of the same target

#### Scenario: Coordination is genuinely exhausted
- **WHEN** claimable, stale, owned, and refinable counts are all zero after exact-current-main inspection
- **THEN** the supervisor may accept `NO_CANDIDATE` and wait without consuming a failure strike
