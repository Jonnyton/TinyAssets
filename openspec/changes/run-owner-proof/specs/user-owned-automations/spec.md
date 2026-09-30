## ADDED Requirements

### Requirement: An event subscription SHALL store at most one wake per event occurrence
An event subscription SHALL store at most one wake for a given subscription and event occurrence (a run's terminal transition, or one answer on a request), enforced by the store, so that at-least-once delivery of a terminal event wakes the subscribed branch exactly once and a self-following loop never forks into two chains.

#### Scenario: A redelivered terminal event wakes once
- **WHEN** the terminal event of one run is delivered twice
- **THEN** exactly one wake exists for each matching subscription
