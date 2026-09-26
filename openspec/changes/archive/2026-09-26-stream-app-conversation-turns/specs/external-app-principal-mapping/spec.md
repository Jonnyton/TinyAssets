# External app principal mapping — concurrent turn admission deltas

## ADDED Requirements

### Requirement: Concurrent conversations do not head-of-line block each other

An inbound app event SHALL be admitted to a bounded worker rather than executed
synchronously on the ingress event loop, so that a long-running turn for one
conversation does not block processing of events for other conversations. Turns
for the same conversation `(workspace, channel, thread)` SHALL execute strictly in
arrival order; turns for different conversations MAY execute concurrently up to a
bounded limit. The ingress SHALL acknowledge an event without waiting for its turn
to complete.

#### Scenario: A slow turn does not block another conversation

- **WHEN** a long-running turn is executing for conversation A and an event arrives
  for a different conversation B
- **THEN** B's turn begins and can complete while A's turn is still running

#### Scenario: A conversation's messages stay in order

- **WHEN** two events arrive for the same conversation in sequence
- **THEN** the second turn does not begin until the first has completed

### Requirement: Concurrency is bounded and overload is truthful

The number of turns (and provider subprocesses) running at once SHALL be bounded by
configuration; the pending backlog SHALL also be bounded. When the bound is
exceeded, the ingress SHALL respond with a truthful overload notice and SHALL NOT
silently drop the event or grow the backlog without limit. An event SHALL be
treated as accepted only once it has been admitted to a worker (or an overload
notice has been delivered).

#### Scenario: Saturation returns a truthful notice, not a drop

- **WHEN** the worker pool and its bounded queue are saturated and another event
  arrives
- **THEN** the caller receives a truthful "busy, try again" outcome and the event
  is not silently discarded

#### Scenario: The concurrency bound holds

- **WHEN** more turns are submitted than the configured concurrency limit
- **THEN** no more than the limit run at once and the rest wait their turn
