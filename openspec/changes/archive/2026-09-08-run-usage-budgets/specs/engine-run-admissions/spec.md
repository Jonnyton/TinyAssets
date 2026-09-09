## ADDED Requirements

### Requirement: Outbound volume is bounded by usage budgets, not by graph shape

The engine SHALL check the current effect-chain dispatch count and delivered-result
byte total before entering another node's effect dispatch, with current defaults
5,000 dispatches and 256 MiB per root run. It SHALL check the universe's recorded
rolling-hour totals against 5,000 dispatches and 2 GiB before dispatch when that
ledger is readable. The count unit SHALL be one node with effects, not each sink
inside that node; workspace nodes SHALL consume this generic count as well as
their workspace-specific accounting. Nodes without effects SHALL not consume it.

Delivered results SHALL contribute reported request_bytes and response_bytes;
an absent integer size SHALL use the corresponding 8 MiB request / 5 MiB response
fallback. Workspace transfer bytes SHALL remain in workspace accounting because
ordinary workspace results do not report delivered=True. The authenticated-call
adapter SHALL report integer request_bytes and response_bytes on delivered results.

A crossed pre-dispatch threshold SHALL fail the node as effect_budget_exhausted,
naming current usage, budget and window; later nodes SHALL not proceed through
that failed chain. These are checks of recorded usage, not atomic pre-wire byte
reservations: an already-admitted dispatch can cross the byte threshold before
a later check, and concurrent runs can consult the same hourly observation.
The existing hourly meter SHALL record after dispatch and tolerate read/write
ledger failures while preserving per-run guards. It SHALL NOT be described as a
transactionally exact global byte cap, a wired commercial tier, or an exact
per-network-request count. These limitations are inputs to the replacement
resource-policy design, not claims of stronger enforcement than shipped.

#### Scenario: The per-run dispatch threshold refuses the next node
- **WHEN** the chain has recorded 5,000 dispatched effect nodes
- **THEN** the next effect node is refused before its adapters run with effect_budget_exhausted and the dispatch count and limit

#### Scenario: Workspace nodes share the generic dispatch count
- **WHEN** a workspace effect node completes without a delivered=True result
- **THEN** it consumes one generic dispatch and no generic delivered-result byte charge, while its workspace accounting remains separate

#### Scenario: The hourly byte observation reaches its threshold
- **WHEN** a readable universe ledger already records at least 2 GiB in its rolling hour
- **THEN** the next effect dispatch is refused with the hourly usage/window explanation

#### Scenario: An admitted response crosses a byte threshold
- **WHEN** recorded bytes are below the threshold before a bounded transport and its result crosses that threshold
- **THEN** the result is recorded and the next dispatch is refused; the meter does not retroactively claim a pre-wire reservation

#### Scenario: An unavailable hourly meter does not invent exact enforcement
- **WHEN** the hourly ledger cannot be read
- **THEN** existing per-run guards still apply but the hourly observation is not asserted to be a transactionally enforced cap
