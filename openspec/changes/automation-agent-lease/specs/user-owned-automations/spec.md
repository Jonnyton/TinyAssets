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
Free slots SHALL be handed out one agent per universe per pass.

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
- `skip` SHALL spend the due instant without a run, retiring a one-shot wake;
- `cancel_previous` SHALL request cancellation of the agent's running run,
  and start once it has stopped.

#### Scenario: skip drops the overlapping run
- **WHEN** a `skip` wake falls due while its branch is running
- **THEN** no run starts, its attempt is recorded as skipped, and the wake retires

#### Scenario: cancel_previous stops the running one first
- **WHEN** a `cancel_previous` row falls due while its branch is running
- **THEN** the running run is asked to cancel, and the row runs after it stops

#### Scenario: cancel_previous reaches only its own agent
- **WHEN** another universe runs a branch with the same id
- **THEN** that run is never cancelled
