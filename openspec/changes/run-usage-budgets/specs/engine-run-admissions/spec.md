## ADDED Requirements

### Requirement: Outbound volume is bounded by usage budgets, not by graph shape

With no maximum on nodes or effect nodes per branch (change
`no-graph-size-caps`), the engine SHALL bound outbound volume per root run
(at most 500 effect dispatches and 256 MiB of outbound bytes — request body
plus response body, charged at the per-call caps when a size is unknown)
and per universe per rolling hour (at most 5,000 dispatches and 2 GiB),
tier-raisable. A dispatch past a budget SHALL fail its node as
`effect_budget_exhausted`, naming the budget, the usage and the window, and
later nodes SHALL NOT run. The authenticated-call adapter SHALL report
`request_bytes` and `response_bytes` on every delivered result.

#### Scenario: a runaway graph is stopped by its budget, not its shape
- **WHEN** a branch with 600 effect nodes runs
- **THEN** the 501st dispatch fails the node as `effect_budget_exhausted` naming the per-run dispatch budget; the first 500 fired normally

#### Scenario: the hourly bytes are exhausted across runs
- **WHEN** a universe's runs in the rolling hour have moved 2 GiB
- **THEN** the next dispatch fails its node as `effect_budget_exhausted` naming the hourly bytes budget and when it clears
