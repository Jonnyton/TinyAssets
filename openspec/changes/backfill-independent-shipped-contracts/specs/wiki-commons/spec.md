## ADDED Requirements

### Requirement: Similar filings can be cosigned without minting a second id
`cosign_bug` SHALL require a filing id and reporter context, resolve `BUG-`, `FEAT-`, `DESIGN-`, and `PR-` prefixes to their typed page directories, preserve the original filing id and content, append or extend a dated `## Cosigns` section, increment `cosign_count` in frontmatter, and append a wiki log entry. An unknown filing SHALL return an error and write nothing.

#### Scenario: Similar report cosigns the existing filing
- **WHEN** a caller chooses an existing similar filing and supplies `cosign_bug` with reporter context
- **THEN** the existing page retains its id, gains the dated context, and returns the incremented `cosign_count`

#### Scenario: Repeated cosigns increment monotonically
- **WHEN** the same filing is cosigned in later calls
- **THEN** each successful call increments the stored count by one without creating another typed filing

### Requirement: Wiki deletion is dry-run first, hash-guarded, and protects anchors
Wiki deletion SHALL resolve only an exact categorized `pages/<category>/<slug>` or `drafts/<category>/<slug>` path with an optional `.md` extension, or a unique slug; it SHALL reject traversal, ambiguity, and protected anchor pages. It SHALL default to a dry run that returns the current SHA-256 and `would_delete=true`; a real delete SHALL require a non-empty reason, SHALL reject a supplied mismatched expected hash, and SHALL log the exact deletion.

#### Scenario: Default delete is non-mutating
- **WHEN** a caller requests deletion without setting `dry_run=false`
- **THEN** the page remains and the response includes its hash and `would_delete=true`

#### Scenario: Hash mismatch blocks deletion
- **WHEN** a caller supplies an `expected_sha256` different from the current page hash
- **THEN** deletion returns `status=conflict` with expected and actual hashes and leaves the page intact

#### Scenario: Protected anchor cannot be deleted
- **WHEN** a caller targets `index`, `log`, `schema`, or the root wiki document
- **THEN** deletion returns a protected error even if a reason is supplied

### Requirement: Draft consolidation is seed-clustered and best-effort
Wiki consolidation SHALL compare each unmerged draft seed with later unmerged drafts and place every threshold match in that seed's cluster; members therefore need not meet the threshold with one another. It SHALL default to reporting clusters without mutation. In execution mode it SHALL choose the longest-body draft as primary, build content containing the other bodies with source/date markers, attempt to remove each secondary, and only then attempt to write the primary. Secondary unlink and primary-write errors are swallowed and the cluster is still reported as executed. This ordering can lose a removed secondary if the later primary write fails and is an explicit as-built limitation.

#### Scenario: Consolidation defaults to preview
- **WHEN** similar drafts exist and the caller omits `dry_run=false`
- **THEN** the response reports candidate clusters and no draft file changes

#### Scenario: Seed matches need not be pairwise matches
- **WHEN** two later drafts each meet the threshold against the cluster seed but not against one another
- **THEN** consolidation reports all three drafts in the same seed-based cluster

#### Scenario: Execution remains best-effort on filesystem failure
- **WHEN** a secondary unlink or the subsequent primary write raises an `OSError`
- **THEN** consolidation swallows that operation error and still reports the cluster in executed mode, without guaranteeing that every source body remains on disk

### Requirement: Wiki lint reports local and whole-wiki integrity without repairing it
Page-scoped lint SHALL report missing link targets and, for drafts, promotion blockers; for published pages it SHALL also report orphan/index and current metadata-freshness issues. Whole-wiki lint SHALL report orphaned, missing, unindexed, ghost, supersession, stale-confidence, source, and pending-draft conditions, returning `healthy` only when no issue is found. Lint SHALL not mutate pages or the index.

#### Scenario: Draft lint reports promotion blockers only for that page
- **WHEN** a caller lints one draft with missing required metadata or too little body content
- **THEN** the result identifies that page and its promotion blockers without adding unrelated whole-wiki backlog

#### Scenario: Whole-wiki lint exposes graph drift
- **WHEN** published pages contain missing links, orphans, index ghosts, or broken supersession targets
- **THEN** whole-wiki lint returns `issues_found` with the corresponding issue entries and performs no repair

### Requirement: Project sync creates only missing sibling-project pages
`sync_projects` SHALL scan non-hidden sibling directories of the wiki root while excluding `Wiki`, `wiki-mcp`, `.git`, and `node_modules`; it SHALL skip projects already represented by page slug or stored path. For each missing project it SHALL create a typed project page with an auto-discovered description/tags, add it to the projects index, append one sync log when anything was created, and return the created list without overwriting existing project pages.

#### Scenario: Missing sibling project is indexed
- **WHEN** a visible sibling directory has no project page
- **THEN** sync creates a slugged project page, adds the index entry, and includes it in `created`

#### Scenario: Existing project is skipped
- **WHEN** a project page already identifies a sibling by slug or stored path
- **THEN** sync leaves that page unchanged and does not create a duplicate
