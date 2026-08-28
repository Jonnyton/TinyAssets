## ADDED Requirements

### Requirement: Usage is metered per universe across three dimensions
The platform SHALL maintain one per-universe usage ledger recording **effects**,
**compute-minutes**, and **storage bytes**. Compute-minutes SHALL be measured as run
subprocess wall-time, because a run occupies a worker slot for its full duration including
time blocked on the user's own provider. The ledger SHALL be the single source of truth for
what a universe consumed; no dimension may be reported from a separate store.

There SHALL be no GPU dimension: the platform supplies no inference and owns no GPUs.

#### Scenario: three dimensions report from one ledger
- **WHEN** a universe's usage is read for any dimension
- **THEN** effects, compute-minutes, and storage all resolve from the same per-universe ledger

#### Scenario: compute is measured as wall-time
- **WHEN** a run blocks on the user's provider for the majority of its duration
- **THEN** the full elapsed wall-time is metered, not the CPU time consumed

### Requirement: The billable effect budget is drawn down only by completed effects
An effect quota SHALL decrement only when an external write reaches terminal success.
Reads, branch writes, branch edits, run admissions, and failed or held effects SHALL NOT
decrement it. Exhausting the effect budget SHALL NOT prevent a universe from reading,
authoring, editing, or debugging.

#### Scenario: a failed outbound attempt costs no effect budget
- **WHEN** an outbound write reaches the destination and is rejected (for example an
  authentication or permission failure)
- **THEN** the universe's effect budget is unchanged

#### Scenario: authoring and repairing never consumes the effect budget
- **WHEN** a universe creates, edits, or reads branches while its effect budget is exhausted
- **THEN** those operations succeed and the budget remains exhausted only for effects

### Requirement: A tier resolved per universe decides its limits
Every universe SHALL resolve to a tier that supplies its effect, compute, and storage
limits. Limits SHALL be configurable rather than compiled in, with documented defaults. The
absence of a paid subscription SHALL itself constitute the free tier; no separate free-plan
record is required.

#### Scenario: limits come from the tier, not from constants
- **WHEN** a universe's tier defines an effect limit different from the default
- **THEN** enforcement uses the tier's limit

#### Scenario: an unknown or unresolvable tier fails to the free tier
- **WHEN** a universe's tier cannot be resolved
- **THEN** the free tier's limits apply rather than unlimited access

### Requirement: A refused request states which budget was exhausted and when it refills
A refusal caused by a usage limit SHALL name the exhausted dimension and report when
capacity returns. A refusal SHALL NOT be indistinguishable from an unrelated failure, and
SHALL NOT tell the caller only to retry later without saying when.

#### Scenario: the refusal is actionable
- **WHEN** a request is refused for exceeding a usage limit
- **THEN** the response identifies the dimension and the time at which the budget refills

### Requirement: Usage reporting to an external processor is adapter-isolated
Metering SHALL write to the platform's own ledger independently of any billing processor.
A billing adapter SHALL read that ledger and report usage upward, keyed by the WorkOS
subject identifier. No module outside the billing adapter SHALL import or depend on the
processor SDK, so that metering and enforcement remain correct while the processor is
unreachable.

#### Scenario: metering survives a processor outage
- **WHEN** the billing processor is unreachable
- **THEN** usage continues to be metered and limits continue to be enforced

#### Scenario: the processor stays swappable
- **WHEN** the codebase is searched for the processor SDK outside the billing adapter
- **THEN** no such import exists
