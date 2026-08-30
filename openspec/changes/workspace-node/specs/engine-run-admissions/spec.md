## ADDED Requirements

### Requirement: Workspace jobs are admitted and settled through their own ledger kind

The engine SHALL admit every `workspace` operation (`checkout`, `push`,
`discard`, `pin`, provisioning) as kind `workspace` in the same per-universe
rolling ledger, bounded by jobs per hour (default 10) and bytes per hour
(default 20 GiB), both tier-raisable; a refusal SHALL name the exhausted
bound. A run whose only workspace operation is `checkout` SHALL settle its
external-write admission as a read; `push` SHALL settle it as a write;
`pin` and `discard` are storage mutations charged as workspace jobs and
SHALL NOT be classified as reads.

#### Scenario: a checkout does not spend the external-write budget
- **WHEN** a run checks out a repository, reads and runs it, and writes nothing externally
- **THEN** its admission settles as `read` and one `workspace` job is charged

#### Scenario: the hourly workspace bytes are exhausted
- **WHEN** a universe's checkouts in the rolling hour have moved 20 GiB
- **THEN** the next `checkout` is refused as `workspace_quota_exceeded`, naming the bytes bound and when it clears

### Requirement: Outbound volume is bounded by usage budgets, not by graph shape

With no maximum on nodes or effect nodes per branch (change
`no-graph-size-caps`), the engine SHALL bound outbound volume per root run
(at most 500 effect dispatches and 256 MiB of outbound bytes) and per
universe per rolling hour (at most 5,000 dispatches and 2 GiB), tier-
raisable; a dispatch past a budget SHALL fail its node as
`effect_budget_exhausted`, naming the budget and the window, and later
nodes SHALL NOT run. (Built in the companion change `run-usage-budgets`.)

#### Scenario: a runaway graph is stopped by its budget, not its shape
- **WHEN** a branch with 600 effect nodes runs
- **THEN** the 501st dispatch fails the node as `effect_budget_exhausted` and the run ends `failed` with the budget named; the first 500 fired normally
