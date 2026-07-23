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

The `command_center` runtime SHALL serve a zero-build browser interface and a JSON state endpoint that aggregate detected provider sessions, `STATUS.md` claims, worktree status, recent file/git/activity signals, local universes, and reachable public MCP state. Missing transcripts, provider homes, worktree probes, or remote platform data MUST degrade to absent or explicitly unavailable state rather than fabricated agents, universes, or health. When a token is configured, every HTTP request SHALL require that token.

#### Scenario: Remote world data is unreachable

- **WHEN** the configured public MCP endpoint cannot be read
- **THEN** the snapshot keeps local coordination and universe evidence available
- **AND** it identifies the remote world as unavailable without synthesizing remote entities

#### Scenario: Token protects the village

- **WHEN** the command center is started with a token
- **THEN** a request without the matching token is rejected
- **AND** the same request with the matching token may read the state endpoint

### Requirement: Agent Village Writes Only Through Explicit Talk And Hire Actions

The command center SHALL remain read-only except for explicit talk and hire requests. Talking to an agent SHALL append a durable inbox/chat record and SHALL dispatch a provider CLI only when dispatch mode is enabled. Talking to a running local universe SHALL write an engine-compatible note; talking to a dormant universe SHALL pin an inbox note. Hiring SHALL validate the universe and advertised provider capability, MAY update the universe's preferred-writer preset, and SHALL spawn peer CLI work only for a provider marked available and dispatchable. Hosted or market capacity MUST remain disabled and honestly labeled while that execution stack is absent.

#### Scenario: Agent talk without dispatch mode

- **WHEN** a user sends a valid message to an agent while dispatch mode is disabled
- **THEN** the command center appends the message to that agent's durable village inbox and chat history
- **AND** it starts no provider CLI process

#### Scenario: Unsupported market hire is refused

- **WHEN** a hire request selects hosted or market capacity advertised as unavailable
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
