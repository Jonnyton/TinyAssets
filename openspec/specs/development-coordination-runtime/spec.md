# development-coordination-runtime Specification

## Purpose
Define the repository's cross-provider orientation, claim, worktree, context, drift, and Agent Village coordination behavior.
## Requirements
### Requirement: Session Orientation Reports Repository Freshness Without Mutating Work

The session sync gate SHALL fetch the configured remote with pruning unless invoked with `--no-fetch`, identify the primary checkout, and report whether that checkout is on `main` and how many commits it trails the configured base reference. Its default mode MUST be advisory and MUST NOT switch branches, pull, reset, clean, or otherwise modify tracked work. In strict mode it SHALL return non-zero when the primary checkout is off `main` or behind the base reference.

#### Scenario: Dirty checkout is behind main

- **WHEN** the primary checkout is behind `origin/main`
- **THEN** the gate prints the behind count and a synchronization instruction
- **AND** it leaves the checkout and its dirty files unchanged

#### Scenario: Strict mode exposes stale orientation to automation

- **WHEN** `--strict` is supplied and the primary checkout is off `main` or behind the configured base
- **THEN** the gate exits non-zero after reporting the condition

### Requirement: STATUS Claims Define Cross-Provider Write Boundaries

The claim checker SHALL parse the `STATUS.md` Work table and classify rows as claimable, blocked, in-flight, host-owned, or stale-claim candidates from their Status, Depends, Files, and active-date information. A pending row SHALL be claimable only when its dependencies are satisfied and its Files do not overlap another provider's claimed or in-flight write set. The prospective `--check-files` path SHALL report a blocking overlap by substring match in either direction. A claimed row with no qualifying file commit for 24 hours and no current active-date heartbeat SHALL be surfaced as a stale-claim candidate; the checker SHALL only report policy state and MUST NOT edit `STATUS.md` itself.

#### Scenario: Prospective files overlap an active claim

- **WHEN** `--check-files` names a path that contains, or is contained by, a Files atom on another provider's claimed row
- **THEN** the checker reports the prospective claim as blocked and identifies the conflicting row

#### Scenario: Fresh heartbeat preserves an uncommitted claim

- **WHEN** a claimed row has no recent file commit but includes an `ACTIVE` date for the current day
- **THEN** the checker keeps it in-flight rather than classifying it as a stale-claim candidate

### Requirement: Worktree Inspection Preserves Lane Intent

The worktree status tool SHALL combine Git worktree state, branch/upstream state, `STATUS.md` references, pull-request/merge evidence, and local `_PURPOSE.md` metadata into a per-worktree classification. Dirty worktrees MUST take precedence over cleanup classifications. A clean lane whose branch is fully merged or whose upstream is gone MAY be marked ready to remove, while an unmerged clean local branch with purpose metadata but no STATUS or pull-request route SHALL be reported as needing promotion. The tool SHALL expose both a human table and machine-readable JSON, and any printed cleanup commands MUST remain suggestions rather than executing removal.

#### Scenario: Dirty merged worktree is not declared removable

- **WHEN** a worktree has local changes even though its branch is merged
- **THEN** the tool classifies it as dirty and does not mark it ready to remove

#### Scenario: Purpose exists but integration route is missing

- **WHEN** a clean local branch has `_PURPOSE.md` but no upstream, pull request, or STATUS reference
- **THEN** the tool reports that the lane needs PR or STATUS promotion

### Requirement: Provider Context Is Recovered At Lifecycle Checkpoints

The provider context feed SHALL scan shared ideas, activity, provider memories, brain notes, execution artifacts, and live worktree purpose files, then rank and cap candidates so one noisy file or source type cannot suppress all other sources. It SHALL accept the lifecycle phases `claim`, `plan`, `build`, `review`, `foldback`, and `memory-write`, and SHALL include cross-provider memory during claim orientation while filtering it from narrower phases unless otherwise shared. Purpose files belonging to merged or dead worktree branches SHALL be excluded when branch evidence is available. The feed MUST remain contextual evidence, not authority to add, claim, or implement work.

#### Scenario: Claim phase surfaces cross-provider history

- **WHEN** a Codex provider requests the claim-phase feed and relevant Claude memory exists
- **THEN** that memory is eligible to appear alongside shared ideas and current lane context

#### Scenario: Merged lane metadata does not masquerade as active context

- **WHEN** a discovered `_PURPOSE.md` belongs to a worktree branch known to be merged
- **THEN** the feed omits that purpose record from active candidates

### Requirement: Cross-Provider Rule Drift Is Detectable

The cross-provider drift checker SHALL inspect substantive rules in provider-specific configuration surfaces and compare them with the project-wide `AGENTS.md` contract. It SHALL report unmirrored cross-provider conventions with a fix prescription and a non-zero collision result, while allowing genuinely harness-specific sections that carry an explicit provider-only marker. The checker MUST be diagnostic and MUST NOT rewrite either canonical or provider-specific instructions.

#### Scenario: Shared convention exists only in a provider file

- **WHEN** a substantive convention in a watched provider-specific file has no equivalent in `AGENTS.md` and no harness-specific marker
- **THEN** the checker reports cross-provider drift and instructs the caller to move or mirror the rule into `AGENTS.md`

#### Scenario: Harness-specific section is explicitly marked

- **WHEN** a provider-specific section is labeled as applying only to that harness
- **THEN** the checker does not treat that section alone as cross-provider drift

### Requirement: Agent Village Observes Durable Coordination State

The `command_center` runtime SHALL serve a zero-build browser interface and a JSON state endpoint that aggregate detected provider sessions, `STATUS.md` claims, worktree status, recent file/git/activity signals, local universes, and reachable public MCP state. Missing transcripts, provider homes, worktree probes, or remote platform data MUST degrade to absent or explicitly unavailable state rather than fabricated agents, universes, or health. The CLI SHALL default to loopback. Every server process SHALL use either a minimum-strength operator-supplied printable ASCII token or a newly generated high-entropy token. Static bootstrap assets and the liveness probe MAY be unauthenticated, but every private state, chat, or provider API request SHALL require the matching token in `X-Village-Token`, compared in constant time. Malformed, control-character, or non-ASCII bearer headers SHALL fail closed with an unauthorized response. Query-string tokens SHALL NOT authenticate any API request. The browser SHALL accept a share token from the URL fragment, remove that fragment from visible history, retain the token for no longer than the browser session, and send it only in the request header. When the browser lacks a valid token, it SHALL display a persistent access-required message that directs the operator to the printed share URL.

#### Scenario: Remote world data is unreachable

- **WHEN** the configured public MCP endpoint cannot be read
- **THEN** the snapshot keeps local coordination and universe evidence available
- **AND** it identifies the remote world as unavailable without synthesizing remote entities

#### Scenario: Zero-config startup is authenticated

- **WHEN** the command center starts without an operator-supplied token
- **THEN** it generates a high-entropy token before serving requests
- **AND** a private API request without that token is rejected

#### Scenario: Static bootstrap does not disclose private state

- **WHEN** a browser requests the app shell or liveness probe without a token
- **THEN** the server may return that static or health response
- **AND** requests for state, chat, or provider data remain unauthorized

#### Scenario: Fragment bootstrap uses header-only API authentication

- **WHEN** the operator opens the printed share URL
- **THEN** the browser obtains the token from the fragment and removes it from visible history
- **AND** subsequent private API requests carry `X-Village-Token` without a token query parameter

#### Scenario: Query bearer is rejected

- **WHEN** a private API request supplies the correct token only as `?token=`
- **THEN** the server returns unauthorized

#### Scenario: Malformed bearer fails closed

- **WHEN** a private API request supplies a non-ASCII bearer header
- **THEN** the server returns unauthorized without raising an unhandled exception

#### Scenario: Browser starts without a bearer

- **WHEN** the app shell loads without a fragment or session token
- **THEN** the browser persistently explains that access is required
- **AND** it directs the operator to reopen the share URL printed by the server

### Requirement: Agent Village Writes Only Through Explicit Talk And Hire Actions

The command center SHALL remain read-only except for explicit authenticated talk and hire requests. It SHALL reject missing, malformed, negative, or greater-than-64-KiB request lengths and non-object JSON before invoking collector code. Talking to an agent SHALL append a durable inbox/chat record and SHALL dispatch a provider CLI only when dispatch mode is enabled. Talking to a running local universe SHALL write an engine-compatible note; talking to a dormant universe SHALL pin an inbox note. Hiring SHALL validate the universe and advertised provider capability, MAY update the universe's preferred-writer preset, and SHALL spawn peer CLI work only for a provider marked available and dispatchable. Hosted or market capacity MUST remain disabled and honestly labeled while that execution stack is absent.

#### Scenario: Cross-site-shaped write has no bearer

- **WHEN** a talk or hire request arrives without the matching `X-Village-Token`
- **THEN** the server returns unauthorized before reading or invoking the requested action
- **AND** no inbox, universe, preset, or provider process is mutated

#### Scenario: Oversized write is rejected before collector invocation

- **WHEN** an authenticated talk or hire request declares a body greater than 64 KiB
- **THEN** the server rejects the request without reading a truncated prefix
- **AND** no collector action runs

#### Scenario: Agent talk without dispatch mode

- **WHEN** an authenticated user sends a valid message to an agent while dispatch mode is disabled
- **THEN** the command center appends the message to that agent's durable village inbox and chat history
- **AND** it starts no provider CLI process

#### Scenario: Unsupported market hire is refused

- **WHEN** an authenticated hire request selects hosted or market capacity advertised as unavailable
- **THEN** the command center returns a validation failure and spawns no worker
- **AND** the response preserves the current coming-later limitation

### Requirement: Cross-provider drift checks cover required artifacts and skill mirrors
The cross-provider drift checker SHALL report a `missing-artifact` issue when a watched provider file references a configured guard artifact that does not exist, and SHALL report `skill-mirror-missing-source`, `skill-mirror-missing`, or `skill-mirror-drift` when `.agents/skills/<name>/SKILL.md` and its `.claude/skills/<name>/SKILL.md` mirror are absent or differ. Each issue SHALL carry a path, message, and concrete prescription; detected drift SHALL exit 2, while a clean tree SHALL exit 0.

#### Scenario: Referenced guard artifact is absent
- **WHEN** a watched provider file names a required guard artifact that is missing
- **THEN** the checker emits `missing-artifact` with the missing path and a create-or-retarget prescription

#### Scenario: Canonical skill and Claude mirror differ
- **WHEN** matching project skill files exist under `.agents/skills/` and `.claude/skills/` but their text differs
- **THEN** the checker emits `skill-mirror-drift` and directs the operator to run the skill sync script

#### Scenario: JSON output preserves issue fields
- **WHEN** the checker is invoked with `--format json`
- **THEN** it emits a JSON array whose issue objects preserve `code`, `path`, `message`, and `prescription`

### Requirement: Coordination inspectors expose automation-facing JSON modes
`claim_check.py --json` SHALL emit the same claimable, blocked, in-flight, host-owned, stale, and prospective-file classifications used by its text report as a JSON object. `worktree_status.py --json` SHALL emit its worktree records as a JSON array, and `provider_context_feed.py --json` SHALL emit its ranked context candidates as a JSON array. JSON mode SHALL inspect and report state without claiming work or mutating a worktree.

#### Scenario: Claim classifications are machine-readable
- **WHEN** `claim_check.py` is invoked with a provider and `--json`
- **THEN** the result is a parseable JSON object containing the current classified STATUS rows and any prospective-file result

#### Scenario: Worktree inventory is machine-readable
- **WHEN** `worktree_status.py --json` completes
- **THEN** it emits a parseable array of the same per-worktree status records used by the human table

#### Scenario: Provider context candidates are machine-readable
- **WHEN** `provider_context_feed.py --json` is invoked at a lifecycle phase
- **THEN** it emits a parseable array of the ranked context candidate records without promoting any candidate into authority

### Requirement: Authority resolution uses a frozen fail-closed v1 decision contract
The authority-resolution contract SHALL use schema version `resolver-decision-v1` and SHALL accept only decision statuses `resolved`, `unresolved`, and `needs-human-decision`. A decision SHALL carry confidence in `[0.0, 1.0]`, at least one evidence handle, a source-role-map entry for every handle, a non-empty resolver version and reason, and no unknown payload fields. Resolver input SHALL require a universe-scoped question, conflict type, and at least one citation while allowing unknown source roles or surface types through the input boundary so the taxonomy guard can return an auditable unresolved decision.

#### Scenario: Decision payload round-trips exactly
- **WHEN** a valid v1 decision is serialized and reconstructed
- **THEN** schema version, status, confidence, evidence handles, source-role map, resolver version, and reason are preserved

#### Scenario: Unknown decision field is rejected
- **WHEN** a raw v1 decision payload includes a field outside the frozen dataclass shape
- **THEN** validation raises instead of silently treating a future schema as v1

#### Scenario: Unknown taxonomy fails closed
- **WHEN** a citation uses a surface type or source role outside the known v1 sets
- **THEN** the guard returns `unresolved` with confidence `0.0`, preserves every evidence handle, labels the unknown entry in `source_role_map`, and names the unknown taxonomy in its reason

### Requirement: The deterministic resolver preserves evidence and never forces a conflicting winner
`resolve_authority` SHALL first apply the unknown-taxonomy guard. For known taxonomy it SHALL return `resolved` with confidence `0.9` when all non-empty normalized claim texts agree; SHALL return `unresolved` with confidence `0.0` when normalized claims conflict; SHALL return `needs-human-decision` with confidence `0.0` when no citation has claim text; and SHALL reframe `surface-mismatch` as `resolved` with confidence `0.82` while preserving every evidence handle and typed surface label. It SHALL preserve the input source role for every known citation and SHALL not implement a configurable precedence policy.

#### Scenario: Matching claims resolve deterministically
- **WHEN** all cited claim texts differ only by case or whitespace
- **THEN** the resolver returns `resolved` at confidence `0.9` with all evidence handles preserved

#### Scenario: Direct conflict remains unresolved
- **WHEN** known citations make different non-empty normalized claims
- **THEN** the resolver returns `unresolved` at confidence `0.0` and does not choose a winner

#### Scenario: Surface mismatch is reframed rather than discarded
- **WHEN** the conflict type is `surface-mismatch` and all citation taxonomy is known
- **THEN** the resolver returns `resolved` at confidence `0.82` and its reason lists every evidence handle with its surface type

#### Scenario: Missing claim text needs human judgment
- **WHEN** no citation provides non-empty claim text
- **THEN** the resolver returns `needs-human-decision` at confidence `0.0`

### Requirement: OpenSpec Delivery Flow Is Inspectable

The development coordination runtime SHALL provide a read-only OpenSpec flow
inspector that enumerates active change directories, counts completed and
unchecked task checkboxes, maps exact active change names to `STATUS.md` Work
rows and owners, reports global and exact-session provider WIP, and reports
recent active-change admission and archive counts when a git comparison window
is requested. It MUST expose equivalent human-readable and JSON results and
MUST NOT create, edit, claim, split, sync, archive, or delete any change.
Audit mode SHALL be invoked on demand for dispatch/triage, not as a mandatory
session-start step.

#### Scenario: Current flow is reported without mutation

- **WHEN** a provider runs the inspector against a repository with active
  OpenSpec changes
- **THEN** the result includes aggregate task totals and one record per change
- **AND** the tracked working tree is byte-identical before and after inspection

#### Scenario: Incomplete active change is absent from live coordination

- **WHEN** an active change with unchecked tasks appears in no `STATUS.md` Work
  row
- **THEN** the inspector classifies that change as `untracked`
- **AND** it does not infer implementation authority from the change artifacts

#### Scenario: Automation requests JSON

- **WHEN** the inspector is invoked in JSON mode
- **THEN** it emits a parseable object containing the same aggregate, change,
  provider-WIP, warning, and recommendation information as text mode

### Requirement: New OpenSpec Delivery Changes Are Bounded

The inspector's named change-admission check SHALL reject a candidate with more
than 12 total task checkboxes, completed or unchecked, and SHALL reject
admission when the requesting exact session-specific provider identity already
owns another claimed or in-flight OpenSpec change. It SHALL report global WIP
with the result and SHALL treat minting a provider suffix to evade the limit as
a process-review violation. It SHALL report umbrella/full-vision language as a
semantic-review warning rather than claiming keyword detection proves invalid
scope. Existing oversized changes MUST remain reportable in default audit mode
and MUST NOT make default inspection fail. The 12-task ceiling is a 2026-07-28
calibration that SHALL be reviewed on 2026-08-11 against observed cycle time and
current model capability. Admission mode SHALL run only after scaffolding and
before claiming or building a change.

#### Scenario: Candidate exceeds the task ceiling

- **WHEN** a named candidate change contains 13 task checkboxes
- **THEN** admission exits 2 and identifies the 12-task ceiling

#### Scenario: Provider already owns delivery WIP

- **WHEN** the requesting provider owns one claimed active change and asks to
  admit a different active change
- **THEN** admission exits 2 and identifies the existing change
- **AND** reports global active delivery WIP

#### Scenario: Legacy oversized change is audited

- **WHEN** default audit encounters a pre-existing change with more than 12
  total task checkboxes
- **THEN** it reports the change as oversized
- **AND** the audit remains read-only and exits successfully

### Requirement: OpenSpec Dispatch Is Finish-First

The inspector SHALL recommend complete-but-unarchived changes before any
change with unchecked tasks, then claimed changes by ascending unchecked-task
count, then queued changes by ascending unchecked-task count. It MUST report
untracked changes for triage without recommending that they be built.

#### Scenario: Completed active change exists

- **WHEN** one active change has zero unchecked tasks and another claimed
  change has unchecked tasks
- **THEN** the completed change is the first recommendation

#### Scenario: Claimed slices differ in remaining size

- **WHEN** two claimed changes have no completed change ahead of them
- **AND** one has fewer unchecked tasks than the other
- **THEN** the smaller claimed change is recommended first

#### Scenario: Only untracked changes remain

- **WHEN** every active change is absent from the STATUS Work table
- **THEN** the inspector reports no build recommendation
- **AND** it directs the provider to triage coordination state first

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

### Requirement: Drain Workers Preserve Delivery Governance

Every generated drain-worker brief SHALL require current-main orientation, a
clean purpose-named worktree, exact STATUS collision/admission checks, one
concrete acceptance contract, tests and required independent review, at most one
PR, verified merge, spec sync/archive when complete, and STATUS foldback. It
MUST forbid umbrella conversion, silent claim theft, primary-checkout edits, and
mechanical legacy-change fan-out. A legacy oversized change MAY be attempted
only as one concrete recovery slice containing at most 12 unchecked tasks and
SHOULD prefer materially fewer tasks within the finite worker timeout. The brief
MUST state that local peer workers are write-capable without a reliable OS
sandbox on the supported Windows host, so worktree/claim/review/CI/budget
controls are the safety boundary.

#### Scenario: No safe candidate exists

- **WHEN** every candidate is live-claimed, host-owned, blocked, or lacks a
  concrete bounded acceptance contract
- **THEN** the worker returns `NO_CANDIDATE` or `BLOCKED`
- **AND** it does not invent a new change merely to stay busy

#### Scenario: Global worktree inspection exceeds its drain-worker cap

- **WHEN** `worktree_status.py` does not complete within 90 seconds for a
  controller-launched worker
- **THEN** the worker records the timeout and may continue only after creating a
  clean current-main worktree with `_PURPOSE.md`
- **AND** it still runs exact claim/collision and provider-context checks before
  editing

#### Scenario: Legacy change is selected

- **WHEN** the worker selects a grandfathered oversized active change
- **THEN** it limits the delivery attempt to at most 12 unchecked tasks and one
  PR
- **AND** it does not mechanically create child changes for the remaining work

### Requirement: OpenSpec Drain Starts With The Interactive Windows Session

The development coordination runtime SHALL provide an idempotent current-user
Windows sign-in task that launches exactly one drain watchdog and one tray
indicator without requiring a daily prompt or terminal. It MUST use the
interactive user boundary rather than SYSTEM startup because provider
subscription credentials and the notification area belong to that session.

#### Scenario: User signs in after boot

- **WHEN** the configured Windows user signs in
- **THEN** Task Scheduler launches the drain tray/watchdog automatically
- **AND** duplicate task invocations do not start another watchdog

#### Scenario: Installer runs more than once

- **WHEN** the host installs the autostart integration again
- **THEN** the existing task is replaced with the current controller path
- **AND** no duplicate scheduled task remains

### Requirement: Drain Watchdog Preserves Identity Across Abrupt Shutdown

The drain watchdog SHALL attach to a live unfinished drain, SHALL resume an
unfinished drain whose recorded controller is dead using the same run directory
and exact identity, and SHALL start a fresh bounded run only when no unfinished
run exists. It MUST NOT automatically restart fatal or failure-budget terminal
outcomes.

#### Scenario: Existing manual drain is alive

- **WHEN** the watchdog starts while an unfinished drain lock belongs to a live
  controller
- **THEN** it attaches to that run for health monitoring
- **AND** it does not dispatch another worker

#### Scenario: Computer was shut down abruptly

- **WHEN** the newest drain has no `ended_at` and its recorded controller PID is
  dead
- **THEN** the watchdog resumes that run with stale-lock recovery
- **AND** replacement workers retain the original drain identity

#### Scenario: Previous run failed terminally

- **WHEN** the latest completed run ended at its failure budget or a fatal peer
  error
- **THEN** the watchdog reports down
- **AND** it waits for an explicit restart request instead of spending more
  subscription calls

#### Scenario: Clean budget ends during the signed-in session

- **WHEN** a supervisor ends at its runtime or slice budget while the watchdog
  remains active
- **THEN** the watchdog may start a new finite supervisor run
- **AND** it still runs only one worker at a time

### Requirement: Drain Health Is Continuously Visible And Actionable

The Windows integration SHALL maintain atomic health state and a system-tray
indicator that distinguishes running, waiting/recovering, and down/failure
states. The tray MUST provide actions to open status/logs, request a restart,
stop until the next sign-in, and exit only the indicator.

#### Scenario: Worker is active

- **WHEN** the watchdog observes a live controller with running state
- **THEN** the tray displays healthy/running status
- **AND** its tooltip identifies the active drain

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

### Requirement: OpenSpec Drain Proves Work Exhaustion Before Idling

The OpenSpec drain supervisor SHALL accept `NO_CANDIDATE` only when the
canonical claim checker reports zero claimable rows, zero policy-qualified
stale-claim candidates, and zero in-flight rows owned by the drain's exact
identity. Every drain-worker brief MUST require the worker to resume its own
claim, select claimable finish-first work, reap policy-qualified stale claims,
freshness-check blocker labels, and consider safe cross-cutting promotion in
that order before reporting no candidate. Live foreign claims, host-owned
actions, unresolved decisions, and overlapping write sets MUST remain excluded.
Immediately before dispatch, the supervisor SHALL provide a bounded ordered
snapshot of exact-identity-owned, claimable, and policy-qualified stale rows.
The controller MUST revalidate that snapshot on current main and durably claim
the first still-valid row before dispatch; the worker MUST verify and reuse the
prepared claim before beginning a broad backlog audit.
Codex drain dispatches SHALL use a balanced reasoning effort suitable for the
preselected single-slice contract rather than inherit a higher interactive
session effort setting.
When the first ordered candidate is claimable or policy-qualified stale, the
supervisor SHALL create a clean current-main worktree, write its purpose
metadata, commit the exact STATUS claim, persist the admission record, and
launch the worker from that prepared worktree. The worker MUST reuse that lane
and MUST NOT repeat selection or create a second worktree.

#### Scenario: Claimable work exists

- **WHEN** the pre-dispatch claim check reports one or more claimable rows
- **THEN** the supervisor injects their ordered labels and bounded file scope
- **AND** the worker revalidates and durably claims the first still-admissible
  row before a broad audit
- **AND** a later `NO_CANDIDATE` is rejected while any claimable row remains

#### Scenario: Codex worker is dispatched

- **WHEN** the supervisor launches a disposable Codex drain worker
- **THEN** the peer command carries balanced `medium` reasoning effort
- **AND** tests, independent review, CI, and finite worker budgets remain the
  quality boundary

#### Scenario: First claimable candidate is admitted

- **WHEN** the canonical pre-dispatch snapshot has a claimable first row
- **THEN** the controller runs the bounded claim-phase context feed
- **AND** creates a clean branch/worktree from current `origin/main`
- **AND** commits `claimed:<exact-drain-identity> ACTIVE <date>` before dispatch
- **AND** launches the worker with that worktree as its cwd

#### Scenario: First stale candidate is admitted

- **WHEN** no claimable row precedes a policy-qualified stale first row
- **THEN** the controller commits the policy reaping status before the claim
- **AND** commits the exact drain claim in the same prepared worktree

#### Scenario: Admission target collides

- **WHEN** the deterministic worktree path or branch already exists
- **THEN** the controller refuses to overwrite or delete it
- **AND** records a bounded visible admission failure

#### Scenario: Admitted target is blocked

- **WHEN** the worker returns `BLOCKED` for its exact assigned target
- **THEN** the controller preserves the worktree and records the recent blocker
- **AND** releases active admission so the next snapshot can select a different
  non-blocked candidate

#### Scenario: Admission operation fails

- **WHEN** fetch, context feed, claim check, worktree I/O, or git admission
  times out or errors
- **THEN** the controller records a bounded `admission-failed` result
- **AND** it does not remain falsely `running` or dispatch an unclaimed worker

#### Scenario: Worker reports a different target

- **WHEN** an admitted worker's terminal marker names a target other than its
  assigned target
- **THEN** the controller rejects the result and retains admission for recovery

#### Scenario: Admitted target needs foldback

- **WHEN** a verified merged implementation returns `PARTIAL`
- **THEN** replacement-worker instructions require current-main restacking
  before any foldback PR is published

#### Scenario: Policy-qualified stale claim exists

- **WHEN** a worker returns `NO_CANDIDATE`
- **AND** `claim_check.py --json` reports one or more stale-claim candidates
- **THEN** the supervisor rejects the result
- **AND** the next worker brief requires policy-compliant reaping before idle

#### Scenario: Drain identity already owns work

- **WHEN** a worker returns `NO_CANDIDATE`
- **AND** an in-flight row is claimed by the drain's exact identity
- **THEN** the supervisor rejects the result
- **AND** the next worker must resume that owned row before selecting new work

#### Scenario: Coordination state is genuinely exhausted

- **WHEN** claimable and stale counts are both zero
- **AND** the worker has revalidated blockers and found no safe cross-cutting
  recovery task to promote
- **THEN** the supervisor may accept `NO_CANDIDATE`
- **AND** it waits the configured idle interval without consuming a failure
  strike

#### Scenario: A foreign claim is live

- **WHEN** a row has a current heartbeat or otherwise fails the stale-claim
  policy
- **THEN** the drain MUST NOT reap or overwrite that claim
- **AND** it selects non-overlapping work or remains idle

### Requirement: OpenSpec Drain Hosts Are Consoleless On Windows

The development coordination runtime SHALL start the sign-in tray host and all
provider subprocesses without creating a visible Windows console, so closing an
unrelated terminal cannot terminate the tray or active drain.

#### Scenario: Scheduled tray starts after sign-in

- **WHEN** the current-user scheduled task starts the drain tray
- **THEN** no command or PowerShell console is displayed
- **AND** the scheduled host remains alive while the tray process is alive

#### Scenario: Provider CLI resolves through a command shim

- **WHEN** a Windows worker launches a provider CLI whose executable is a
  `.CMD` shim
- **THEN** the launcher creates the subprocess with no console window
- **AND** stdout and stderr remain captured for the attempt artifact

### Requirement: Drain Workers Can Deliver From Linked Worktrees

The development coordination runtime SHALL resolve and grant a write-capable
Codex worker access to its assigned linked worktree's Git common directory,
SHALL use an explicit Git-metadata-capable write mode, SHALL direct the worker
to publish with repository-local `git` and `gh` commands, and MUST preserve the
existing worktree, branch, claim, review, CI, and finite-budget safety
boundaries. Read-only peers MUST remain read-only.

#### Scenario: Codex worker receives a linked worktree

- **WHEN** write mode launches Codex from a linked worktree
- **THEN** the launcher resolves that worktree's absolute Git common directory
- **AND** passes it as an additional writable directory
- **AND** selects the explicit write sandbox mode required to stage and commit

#### Scenario: Read-only worker is launched

- **WHEN** the peer launcher runs in read-only mode
- **THEN** it does not add Git metadata as a writable directory

#### Scenario: Verified work is ready to publish

- **WHEN** a drain worker has completed its acceptance, tests, and required
  review
- **THEN** it uses shell `git` and `gh` from the assigned worktree for
  commit, push, and pull-request delivery

### Requirement: Delivery Failure Is Distinct From Durable Work Blocking

The OpenSpec drain supervisor SHALL reserve `BLOCKED` for durable task, host,
dependency, review, or policy gates and SHALL treat failure to stage, commit,
push, or create a pull request as a retryable `FAILED` delivery result. A
delivery failure MUST preserve the admitted target and worktree so the next
fresh worker resumes it under the existing finite failure budget.

#### Scenario: Git metadata cannot be written

- **WHEN** a worker has verified local work but staging or committing fails
- **THEN** it returns `FAILED` for the admitted target
- **AND** the supervisor preserves the admission for the next worker
- **AND** it does not add the target to the recent-blocked set

#### Scenario: Pull-request publication is unavailable

- **WHEN** commit or push succeeds but the supported pull-request publication
  route fails
- **THEN** the worker returns `FAILED` for the admitted target
- **AND** a fresh worker resumes delivery immediately within the finite budget

#### Scenario: Work requires a host-only test subject

- **WHEN** the remaining acceptance contract requires an unavailable host
  action or external test identity
- **THEN** the worker returns `BLOCKED` with the durable reason
- **AND** the supervisor may select different work after its blocked interval
