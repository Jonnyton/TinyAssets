# user-owned-automations (delta)

## ADDED Requirements

### Requirement: Agents in one universe run side by side and never overlap themselves

The automation pump SHALL fence each run by a lease on its agent: its universe
plus its branch. Runs of different branches in one universe SHALL be able to
run at the same time. Two runs of the same branch in one universe SHALL NOT
overlap. A lease SHALL be reclaimable only from a holder that is proven dead
or has expired without being proven alive. A run that ignored cancellation
SHALL keep its agent busy until its worker has ended. A legacy task's
universe lease and any agent lease in that universe SHALL exclude each other.
Free slots SHALL go first to the universe running the fewest agents, one agent per universe per pass, and a run that ignored cancellation SHALL still hold its slot.

#### Scenario: Two agents run at once
- **GIVEN** two automations of different branches in one universe, both due
- **WHEN** the pump polls with free slots
- **THEN** both runs are in flight at the same time

#### Scenario: One owner's agents do not take every slot
- **GIVEN** three due agents in one universe, one due agent in another, and two free slots
- **WHEN** the pump polls
- **THEN** each universe gets one slot

### Requirement: An automation declares what happens when it is due while its agent runs

An automation SHALL carry an `overlap` policy: `queue` (the default), `skip`
or `cancel_previous`. Any other value SHALL be refused at registration. When
a row falls due while its agent is running, in this process or another:
- `queue` SHALL wait and start once the running run ends;
- `skip` SHALL spend a cadence's due instant without a run. A one-shot wake
  has one fire only, so under `skip` it SHALL wait as under `queue` and never
  be retired or dropped for overlapping;
- a row waiting for its agent SHALL record `waiting_for_previous_run` where
  its owner reads the automation;
- `cancel_previous` SHALL request cancellation of the agent's running run,
  and start once it has stopped. A row SHALL never cancel its own running
  occurrence.

The policy SHALL apply even when every consumer slot is full.

#### Scenario: skip drops the overlapping cadence run
- **WHEN** a `skip` cadence falls due while its branch is running
- **THEN** no run starts, its attempt is recorded as skipped, and the next
  instant is owed

#### Scenario: a one-shot wake under skip waits instead of retiring
- **WHEN** a `skip` one-shot wake falls due while its branch is running,
  including the wake a `run_completed` subscription stores while the run that
  fired it still holds the agent
- **THEN** the wake is not retired, the owner sees `waiting_for_previous_run`,
  and it runs once the agent is free

#### Scenario: cancel_previous stops the running one first
- **WHEN** a `cancel_previous` row falls due while its branch is running
- **THEN** the running run is asked to cancel, and the row runs after it stops

#### Scenario: cancel_previous reaches only its own agent
- **WHEN** another universe runs a branch with the same id
- **THEN** that run is never cancelled
