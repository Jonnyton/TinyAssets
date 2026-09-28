# engine-run-admissions (delta)

## ADDED Requirements

### Requirement: Usage, not shape, bounds a universe's runs

Every run admission SHALL also count the universe's runs (write and read
rows, not engine edits) over a rolling 24 hours, and SHALL refuse a run once
that count reaches the day limit, naming the day limit in the refusal. Every
sub-branch run started by invoke_branch in a universe SHALL be charged as a
run and bound to it. Every triggered run (schedule, Source event, webhook)
SHALL be charged as a run, failing closed. There SHALL be no depth cap on a
blocking invoke by definition. Invokes that run on the shared sub-branch pool
(async, or by version) SHALL nest no deeper than that pool has threads. The
ledger SHALL keep a day of rows whichever caller admits.

#### Scenario: A 10-agent squad on 2-minute heartbeats runs all day
- **WHEN** ten automations fire every two minutes for 24 hours in one universe
- **THEN** none of the ~7,200 runs is refused by any cap

#### Scenario: A refusal tells the owner when capacity returns
- **WHEN** a run, schedule fire, automation or sub-branch run is refused by a cap
- **THEN** the owner can read which cap and the time capacity returns

#### Scenario: A chain paced under the hourly caps meets the day's
- **WHEN** a universe's runs are spread across hours so that no hourly cap refuses them
- **THEN** a run is refused once the day's count reaches the limit, and one frees up a day after the oldest

#### Scenario: A self-invoking branch is stopped by the meter, not by depth
- **WHEN** a branch blocking-invokes itself in a universe
- **THEN** it runs deeper than the old depth cap of 5, and ends when the universe's meter refuses a child, with that refusal on the innermost run

#### Scenario: A triggered run is metered
- **WHEN** a schedule or event fires while the universe's meter is full
- **THEN** no run starts and the refusal names the cap
