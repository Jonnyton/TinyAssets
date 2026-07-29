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
  owned, claimable, or policy-qualified stale candidate
- **THEN** the supervisor considers that candidate without the configured idle
  delay
- **AND** it does not create or claim work itself

#### Scenario: Work is globally blocked

- **WHEN** a worker returns `BLOCKED` and no different eligible candidate
  remains, or returns `NO_CANDIDATE`
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
run, single-pass, status, and stop operations. On resume, it SHALL consume a
valid unrecorded result for the persisted current attempt before enforcing the
failure budget or dispatching a replacement. It SHALL replay the recorded
attempt artifact when a parser improvement makes the immediately preceding
`INVALID_RESULT` valid, undoing only that parser failure strike and applying
ordinary result and admission validation.

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
- **AND** no stable valid terminal artifact is available
- **THEN** the supervisor terminates the launcher process tree
- **AND** it records the attempt as a budgeted worker failure

#### Scenario: Resume finds an unconsumed terminal result

- **WHEN** the persisted current attempt has a valid terminal artifact absent
  from `last_result`
- **AND** its target matches the preserved admission
- **THEN** the supervisor applies the ordinary result transition before
  failure-budget enforcement or replacement dispatch

#### Scenario: Resume result is ambiguous

- **WHEN** the artifact is invalid, names a different admission target, or its
  attempt cannot be determined safely
- **THEN** the supervisor fails closed without applying it
- **AND** does not erase a failure strike

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

### Requirement: Drain Health Is Continuously Visible And Actionable

The Windows integration SHALL maintain atomic health state and a system-tray
indicator that distinguishes running, waiting/recovering, and down/failure
states. A completed current-attempt result that is not represented by
`last_result` MUST be reported as waiting rather than active progress. The tray
MUST provide actions to open status/logs, request a restart, stop until the
next sign-in, and exit only the indicator.

#### Scenario: Worker is active

- **WHEN** the watchdog observes a live controller with running state
- **AND** no settled current-attempt result awaits consumption
- **THEN** the tray displays healthy/running status
- **AND** its tooltip identifies the active drain

#### Scenario: Terminal result awaits controller consumption

- **WHEN** the current attempt's non-empty result artifact is older than the
  write-settle threshold
- **AND** `last_result` does not represent that attempt
- **THEN** the tray displays a waiting/warning state
- **AND** its diagnostic identifies the unconsumed result handoff

#### Scenario: Drain is blocked or recovering

- **WHEN** the controller is idle, blocked, stopping, or being resumed
- **THEN** the tray displays a waiting/warning state rather than false healthy
  progress

#### Scenario: Drain is down

- **WHEN** health is stale, the watchdog exits unexpectedly, or the supervisor
  reaches a terminal failure
- **THEN** the tray displays an error/down state
- **AND** the diagnostic message and status folder remain accessible

#### Scenario: Host closes the tray icon

- **WHEN** the host selects exit indicator
- **THEN** the tray process exits
- **AND** it does not stop the watchdog or active drain
