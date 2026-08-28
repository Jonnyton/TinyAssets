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

### Requirement: The engine compute guard fails closed
A failure to evaluate the engine-triggered admission guard SHALL refuse the request. Once
effect budget is reserved separately, bounding compute is this guard's only remaining job,
and a guard that admits everything when its ledger errors does not perform that job.

This SHALL apply to engine-triggered submission specifically. Ordinary browser or user run
submission is not subject to this dedicated gate and SHALL be unaffected.

The approved-source and destination-allowlist gates constrain *what* may run and SHALL NOT
be treated as a substitute: they place no bound on *how often* a run is submitted.

Accepted runs SHALL be bounded in number, not merely in concurrency. A worker pool that
limits simultaneous execution while accepting unbounded queued work SHALL NOT by itself be
considered a compute bound.

#### Scenario: a ledger error refuses an engine-triggered run
- **WHEN** the admission ledger cannot be evaluated for an engine-triggered run
- **THEN** the run is refused rather than admitted

#### Scenario: ordinary user submission is unaffected
- **WHEN** the same ledger error occurs during ordinary browser or user run submission
- **THEN** that submission proceeds under its own controls

#### Scenario: queue depth is bounded, not just concurrency
- **WHEN** an engine submits far more runs than the guard permits
- **THEN** the excess is refused at admission rather than accumulating as queued work
