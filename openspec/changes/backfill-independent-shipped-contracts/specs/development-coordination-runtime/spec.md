## ADDED Requirements

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
