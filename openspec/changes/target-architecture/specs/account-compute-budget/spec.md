## ADDED Requirements

### Requirement: Compute is metered from the box lifecycle

The platform SHALL meter each account's compute per second while any of its
boxes is awake, weighted by the box's memory ceiling. One compute-hour SHALL be
one awake hour of a box whose ceiling is at most 512 MiB. A suspended or
stopped box SHALL NOT be metered. Agent turns that are waiting on a model in
the control plane's loop SHALL NOT be metered as box time.

#### Scenario: A waiting turn costs no box time
- **WHEN** a turn waits 40 seconds for a model reply and its box suspends after its last tool call
- **THEN** only the box's awake seconds are metered, not the 40 seconds of waiting

### Requirement: Admission waits and never refuses

A run beyond the account's seats SHALL wait for a seat. A run from an account
past its monthly priority compute-hours SHALL be admitted through the
spare-capacity lane: only while the host has headroom, at lower priority than
in-budget work, and never dropped. A scheduled trigger that fires while its
previous run is still waiting SHALL be coalesced into that pending run. The
waiting state SHALL name the limit that applies and when it resets. One
account's runs SHALL NOT delay another account's admission except through the
spare-capacity lane, which yields to in-budget work. No compute-hour number
SHALL be enforced until the founder sets the numbers.

#### Scenario: A fan-out cannot block a neighbour
- **WHEN** one account starts 20 parallel agents on 2 seats and another account starts one run
- **THEN** the first account runs 2 at a time while the rest wait, and the other account's run is admitted without waiting behind them

#### Scenario: Past the budget, work still runs
- **WHEN** an account past its compute-hours triggers a run while the host has idle capacity
- **THEN** the run is admitted through the spare-capacity lane and completes
