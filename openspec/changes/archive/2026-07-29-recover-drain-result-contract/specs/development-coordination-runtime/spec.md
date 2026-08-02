## MODIFIED Requirements

### Requirement: OpenSpec Drain Runs Through Sequential Fresh Workers

The development coordination runtime SHALL provide a bounded OpenSpec drain
supervisor that invokes one fresh subscription-authenticated provider worker at
a time, gives that worker at most one delivery slice and one PR, and starts
another worker only after interpreting the prior worker's terminal result. The
supervisor MUST NOT maintain a provider utilization floor or run drain workers
in parallel in v1. One run SHALL use one fixed provider/model and one exact
claim identity across every replacement worker. An admitted worker's brief
SHALL identify the exact canonical target token required in its result, and the
supervisor SHALL canonicalize an otherwise literal human-label target through
the same bounded slug rule used for admission.

#### Scenario: A slice merges successfully

- **WHEN** a worker returns a valid `MERGED` result with its target and PR
- **AND** the controller independently verifies with GitHub that the PR state
  is `MERGED`
- **THEN** the supervisor increments the completed-slice count
- **AND** it may dispatch the next fresh worker immediately

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

#### Scenario: Work is blocked

- **WHEN** a worker returns `BLOCKED` or `NO_CANDIDATE`
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

### Requirement: OpenSpec Drain Is Bounded And Recoverable

The drain supervisor SHALL require finite runtime, merged-slice, worker-timeout,
and consecutive-failure budgets; SHALL persist compact atomic state and worker
artifacts in an untracked run directory; SHALL reject a concurrent live
controller lock; and SHALL honor a stop request between workers. It MUST expose
run, single-pass, status, and stop operations. On resume, it SHALL replay the
recorded attempt artifact when a parser improvement makes the immediately
preceding `INVALID_RESULT` valid, undoing only that parser failure strike and
applying ordinary result and admission validation.

#### Scenario: Workday budget expires

- **WHEN** the runtime deadline or merged-slice limit is reached
- **THEN** the supervisor records the terminal budget reason
- **AND** it dispatches no additional worker

#### Scenario: Host requests a stop

- **WHEN** the stop operation creates the run's stop marker
- **THEN** the active worker may reach its finite timeout or terminal result
- **AND** the supervisor exits before dispatching another worker

#### Scenario: Host stops during idle

- **WHEN** a stop request arrives during a blocked/no-candidate idle interval
- **THEN** the supervisor observes it within five seconds
- **AND** it exits without waiting for the full idle interval

#### Scenario: Another controller owns the run

- **WHEN** a live lock already exists for the run directory
- **THEN** a second run invocation exits non-zero without dispatching a worker
- **AND** explicit stale-lock recovery refuses to replace the live PID's lock
- **AND** Windows liveness uses a process handle rather than a console-control
  signal probe

#### Scenario: Provider reports repeated transient failures

- **WHEN** authentication or rate-limit failures recur beyond three consecutive
  free retries
- **THEN** each additional transient consumes a consecutive-failure strike
- **AND** an error containing only a broader word such as `authority` is not
  classified as an authentication transient

#### Scenario: Worker exceeds the outer timeout

- **WHEN** the peer launcher remains live beyond its worker timeout and grace
  interval
- **THEN** the supervisor terminates the launcher process tree
- **AND** it records the attempt as a budgeted worker failure

#### Scenario: Parser improvement recovers the last result

- **WHEN** a resumed run ended with `INVALID_RESULT` and its recorded attempt
  artifact now parses and matches the preserved admission
- **THEN** the supervisor removes exactly the parser failure strike
- **AND** it applies the recovered result before considering another dispatch

#### Scenario: Last result remains invalid

- **WHEN** the recorded artifact remains invalid or fails preserved admission
  validation
- **THEN** the supervisor retains the failure budget and terminal state
- **AND** it dispatches no replacement under that recovery path
