# provider-routing (delta)

## MODIFIED Requirements

### Requirement: Served-provider budget admission bounds concurrency, not lifetime spend

The served-provider budget ceiling on a serving binding SHALL bound only
UNSETTLED (in-flight) reserved token/cost spend, so a settled turn releases its
reservation and the binding serves indefinitely. The ceiling is a concurrency
runaway guard, NOT a cumulative spend limit — real spend is metered on the
user's own deposited subscription upstream. The ceiling SHALL be sized so that a
single user driving their universe from multiple surfaces at once, alongside
concurrent LangGraph automations, does not exhaust it under normal use. Each
universe's binding has its own independent ceiling, so concurrent users do not
contend.

#### Scenario: Many concurrent turns across surfaces on one binding

- **GIVEN** a ready serving binding for a universe
- **AND** ten simultaneous served turns are in flight for that binding, each
  reserving a realistic (~20 KB system+prompt) amount of budget
- **WHEN** each turn reserves served-provider budget before launch
- **THEN** all ten reservations are admitted (none is held with
  "Provider authority budget is exhausted")
- **AND** the rolling per-hour invocation cap and the user's metered
  subscription remain the effective runaway/spend backstops

#### Scenario: Runaway invocation guard still fires

- **GIVEN** a serving binding whose rolling-window invocation count has reached
  its per-hour cap
- **WHEN** another served turn attempts to reserve budget
- **THEN** the reservation is held (the invocation runaway guard is unchanged by
  the concurrency-sized token ceiling)
