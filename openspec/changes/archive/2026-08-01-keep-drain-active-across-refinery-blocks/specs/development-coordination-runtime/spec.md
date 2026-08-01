## MODIFIED Requirements

### Requirement: OpenSpec Drain Runs Through Sequential Fresh Workers

The development coordination runtime SHALL provide a bounded OpenSpec drain
supervisor that invokes one fresh subscription-authenticated provider worker at
a time, gives that worker at most one delivery slice and one PR, and starts
another worker only after interpreting the prior worker's terminal result. A
stable, valid terminal result artifact SHALL complete the worker handoff even
when the provider launcher remains alive. The supervisor MUST NOT maintain a
provider utilization floor or run drain workers in parallel in v1. One run
SHALL use one fixed provider/model and one exact claim identity across every
replacement worker. An admitted worker's brief SHALL identify the exact
canonical target token required in its result, and the supervisor SHALL
canonicalize an otherwise literal human-label target through the same bounded
slug rule used for admission.

#### Scenario: A slice merges successfully

- **WHEN** a worker returns a valid `MERGED` result with its target and PR
- **AND** the controller independently verifies with GitHub that the PR state
  is `MERGED`
- **THEN** the supervisor increments the completed-slice count
- **AND** it may dispatch the next fresh worker immediately

#### Scenario: Stable terminal artifact precedes process exit

- **WHEN** the assigned result file contains the same valid terminal result on
  two observations separated by the stability interval
- **AND** the provider launcher remains alive
- **THEN** the supervisor terminates the launcher process tree
- **AND** applies the ordinary admission and result validation without waiting
  for the outer worker timeout

#### Scenario: Worker cites a stale or foreign merged PR

- **WHEN** a terminal result cites a PR outside the controller repository or
  one whose merge predates the drain run
- **THEN** the supervisor rejects merge verification
- **AND** it does not count a completed slice

#### Scenario: Merge succeeded but foldback remains

- **WHEN** a worker returns `PARTIAL` with a controller-verified merged PR
- **THEN** the supervisor records that target for one immediate resume
- **AND** it does not increment completed slices

#### Scenario: Foldback remains partial repeatedly

- **WHEN** another worker returns `PARTIAL` for the same resume target
- **THEN** the supervisor consumes a consecutive-failure strike
- **AND** it waits the configured idle interval before another attempt

#### Scenario: A target is blocked and another candidate exists

- **WHEN** a worker returns `BLOCKED` for its admitted target
- **AND** the recent-block-filtered snapshot contains a different eligible
  owned, claimable, policy-qualified stale, or refinery candidate
- **THEN** the supervisor considers that candidate without the configured idle
  delay
- **AND** it does not create or claim work itself

#### Scenario: Work is globally blocked

- **WHEN** a worker returns `BLOCKED` and no different eligible owned,
  claimable, policy-qualified stale, or refinery candidate remains, or returns
  `NO_CANDIDATE`
- **THEN** the supervisor persists that outcome and waits the configured idle
  interval before another selection attempt
- **AND** it does not create or claim work itself

#### Scenario: Human task label is returned

- **WHEN** an admitted worker returns exactly one otherwise valid literal
  marker using `main-red round 2` for target `main-red-round-2`
- **THEN** the supervisor canonicalizes the reported target to
  `main-red-round-2`
- **AND** admission validation accepts the matching identity

#### Scenario: Worker result is malformed

- **WHEN** a worker exits without exactly one literal terminal result marker as
  the final non-empty line
- **THEN** the supervisor records a failure
- **AND** it stops when the configured consecutive-failure limit is reached

#### Scenario: Result echoes the contract template

- **WHEN** output contains a placeholder marker, a marker containing `|`,
  multiple markers, or a `[peer_agent] ERROR` block
- **THEN** the supervisor rejects it as a terminal success

#### Scenario: Run identity already owns a claim

- **WHEN** a replacement worker starts and STATUS contains a claim held by the
  run's exact identity
- **THEN** its brief requires that target to be resumed before selecting
  different work
