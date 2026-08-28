## ADDED Requirements

### Requirement: Engine-triggered run admission is a compute guard, separate from the billable budget
Engine-triggered runs SHALL be bounded by a rolling per-universe admission guard whose
purpose is protecting platform compute from a prompt-injected or runaway engine. This guard
SHALL be distinct from the billable effect budget: exhausting one SHALL NOT exhaust the
other, and authoring operations SHALL NOT draw down the run guard's capacity in a way that
prevents running what was just authored.

The guard's limit SHALL be configurable with a documented default, and SHALL be set high
enough that ordinary iterative debugging does not reach it.

Admission SHALL remain atomic: the count and the insert SHALL occur in one transaction so
concurrent callers cannot both pass a full cap.

#### Scenario: authoring does not starve running
- **WHEN** a universe repairs a branch and immediately runs the repair
- **THEN** the authoring operations have not consumed the capacity the run requires

#### Scenario: concurrent admissions cannot both pass a full cap
- **WHEN** two engine-triggered runs are admitted concurrently at the limit
- **THEN** exactly one is admitted

#### Scenario: the guard still bounds runaway compute
- **WHEN** an engine triggers runs far in excess of the configured guard
- **THEN** further runs are refused regardless of remaining effect budget

### Requirement: Admission failure posture is explicit per call site
A failure to evaluate the admission guard SHALL fail open for ordinary run submission,
whose primary controls are the approved-source gate and destination allowlist, and SHALL
fail closed for autonomous writes, where the rolling cap is itself the safety bound. This
asymmetry SHALL be explicit rather than incidental.

#### Scenario: a ledger error does not wedge legitimate runs
- **WHEN** the admission ledger cannot be read during ordinary run submission
- **THEN** the run is admitted and the primary gates still apply

#### Scenario: a ledger error refuses an autonomous write
- **WHEN** the admission ledger cannot be read during an autonomous write
- **THEN** the write is refused
