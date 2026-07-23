## ADDED Requirements

### Requirement: Cross-provider guard artifacts and project skill mirrors are checked

The cross-provider drift checker SHALL detect when watched provider surfaces reference a required guard artifact that is absent, and it SHALL emit a typed issue containing the missing path and a repair prescription. When guard artifacts are referenced, it SHALL also report if `AGENTS.md` lacks the cross-provider convention section. For project-local skills, `.agents/skills/<name>/SKILL.md` SHALL be the canonical source. A repository-wide default scan SHALL inspect every canonical/mirror skill pair, while a `--paths` scan SHALL inspect only pairs represented by the supplied skill paths. For each inspected pair, the checker SHALL report a missing canonical source, a missing `.claude/skills/<name>/SKILL.md` mirror, or different checker-readable UTF-8 text after universal-newline normalization. The comparison MUST NOT be represented as byte-for-byte integrity: unreadable text currently collapses to an empty string. These checks MUST remain diagnostic and MUST NOT create, delete, or rewrite either side automatically.

#### Scenario: A referenced guard artifact is absent

- **WHEN** a watched file names a configured required guard artifact and that path does not exist
- **THEN** the checker emits a `missing-artifact` issue for that path
- **AND** the issue identifies at least one referrer and prescribes creating or retargeting the artifact

#### Scenario: An inspected project skill mirror is missing or text-different

- **WHEN** a repository-wide scan, or a targeted scan naming either side of the pair, finds that a canonical `.agents` skill lacks its `.claude` mirror or their checker-readable normalized text differs
- **THEN** the checker emits `skill-mirror-missing` or `skill-mirror-drift` as applicable
- **AND** it prescribes the project skill synchronization path without editing either file

#### Scenario: An inspected mirror has no canonical skill source

- **WHEN** a repository-wide scan, or a targeted scan naming either side of the pair, finds a `.claude` project skill without the corresponding `.agents` source
- **THEN** the checker emits `skill-mirror-missing-source`
- **AND** it does not promote the mirror into canonical process truth

#### Scenario: A targeted non-skill path is scanned

- **WHEN** `--paths` contains no `.agents` or `.claude` skill path
- **THEN** the checker performs the other applicable targeted drift checks
- **AND** it does not claim to have inspected unrelated project skill pairs

### Requirement: Coordination diagnostics expose machine-readable forms

The claim checker, worktree inspector, provider-context feed, and cross-provider drift checker SHALL each expose their shipped JSON mode. JSON selection MUST preserve the same classification, filtering, and limiting semantics as the corresponding human-readable execution. The claim report SHALL include provider, category counts, classified row arrays, and the prospective-file result when requested; worktree status and provider context SHALL serialize their current record objects; cross-provider drift SHALL serialize typed issue objects. JSON mode MUST NOT itself claim a versioned external API or mutate repository coordination state.

#### Scenario: Claim state is requested as JSON

- **WHEN** `claim_check.py` is invoked with `--json`
- **THEN** it emits an object containing provider, counts, `claimable`, `blocked`, `in_flight`, `host_owned`, and `stale` classifications
- **AND** a supplied prospective Files check is represented in the same object

#### Scenario: Worktree and context records are requested as JSON

- **WHEN** `worktree_status.py --json` or `provider_context_feed.py --json` is invoked
- **THEN** the tool emits a JSON list of the same worktree or candidate records selected by its normal arguments
- **AND** choosing JSON does not change which records qualify

#### Scenario: Drift issues are requested as JSON

- **WHEN** `check_cross_provider_drift.py --format json` is invoked
- **THEN** it emits a JSON list of typed issues with their paths and prescriptions
- **AND** when a valid scan completes, it exits `2` when issues exist and `0` when the issue list is empty
