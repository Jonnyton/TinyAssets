## ADDED Requirements

### Requirement: The daemon owns one bounded assigned queue consumer
When explicitly enabled, `universe_server.main` SHALL start one stoppable assigned queue consumer in the daemon process with a fixed global concurrency cap and at most one active task per universe.

#### Scenario: Enabled startup and shutdown
- **WHEN** the opt-in flag is truthy and the daemon starts then stops
- **THEN** exactly one consumer starts and its polling/executor resources receive a bounded stop request

#### Scenario: Saturated queue
- **WHEN** more tasks are pending than the configured global cap
- **THEN** no more than the cap execute concurrently and HTTP serving remains in the daemon main thread
