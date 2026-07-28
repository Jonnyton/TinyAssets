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
