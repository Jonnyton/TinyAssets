## ADDED Requirements

### Requirement: The OKF bundle is the canonical source of truth
The brain's canonical knowledge representation SHALL be an OKF (Open Knowledge Format) bundle — a directory of markdown files with YAML frontmatter, one file per entry, cross-links forming the graph, plus reserved `index.md` and `log.md`. The SQLite entry store, FTS index, and vector index SHALL be a derived, fully rebuildable operational index over the bundle and SHALL NOT be the source of truth.

#### Scenario: index rebuilds from the bundle
- **WHEN** the SQLite/FTS/vector index is deleted and rebuilt from the bundle
- **THEN** the rebuilt operational store reproduces every entry, its typed fields, and its links
- **AND** no knowledge is lost (the index is disposable by design)

#### Scenario: bundle is authoritative on conflict
- **WHEN** the operational index and the bundle disagree about an entry's content
- **THEN** the bundle is treated as authoritative and the index is corrected from it

### Requirement: Writes are write-through and bundle-durable
A write SHALL be applied transactionally to the operational index AND projected to the OKF bundle. An entry SHALL be considered durable only once it is present in the bundle; the operational index alone SHALL NOT be treated as durable storage.

#### Scenario: an accepted write reaches the bundle
- **WHEN** a write is accepted by the operational layer (passing the candidate gate)
- **THEN** the entry is projected to a bundle file with conformant frontmatter
- **AND** the change is recorded in `log.md`

#### Scenario: concurrency is served by the operational layer
- **WHEN** multiple concurrent writers submit entries
- **THEN** the operational layer serializes them transactionally before projection
- **AND** bundle files remain individually well-formed

### Requirement: Tiny's typed entry fields conform to OKF as additional frontmatter keys
Every non-reserved entry file SHALL carry a non-empty `type`. Tiny's typed/scoped/lifecycled fields (`goal_id`, `universe_id`, `visibility`, `lifecycle`, `ttl_class`, `supersedes`, `evidence_refs`) SHALL be carried as additional frontmatter keys. The bundle SHALL remain OKF-conformant: parseable frontmatter, non-empty `type`, reserved-file structure. The brain SHALL tolerate unknown types, unknown keys, and broken cross-links rather than rejecting them.

#### Scenario: a generic OKF consumer reads a Tiny entry
- **WHEN** an OKF-generic consumer (no Tiny knowledge) reads a Tiny entry file
- **THEN** it parses the `type` and renders the body
- **AND** it preserves Tiny's extra frontmatter keys when round-tripping

#### Scenario: a broken cross-link is valid, not malformed
- **WHEN** an entry links to a target that does not yet exist in the bundle
- **THEN** the link is treated as valid not-yet-written (candidate) knowledge
- **AND** the bundle is still conformant

### Requirement: Reserved files and sections carry brain semantics
`index.md` SHALL render the progressive-disclosure manifest (and per OKF carry no frontmatter except an optional bundle-root `okf_version`); `log.md` SHALL carry change and supersession-lineage history; citations SHALL live under a `# Citations` heading and/or a `references/` subdirectory; an entry's concept ID SHALL be its bundle-relative path with the `.md` suffix removed.

#### Scenario: progressive disclosure via index.md
- **WHEN** a lens assembles a view and needs a manifest of available entries
- **THEN** it reads `index.md` for the entry id + one-line manifest before fetching bodies

#### Scenario: supersession lineage stays queryable
- **WHEN** an entry is superseded
- **THEN** the `supersedes` frontmatter and `log.md` record the lineage
- **AND** default views exclude superseded entries while lineage remains queryable

### Requirement: The bundle is the unit of durability, federation, and export
The nightly git snapshot of the bundle SHALL be the canonical durable store (not a backup of a derived DB). Commons federation SHALL aggregate public goal-addressed bundle entries across universes. Self-host and fork export SHALL emit the bundle wholesale as a portable OKF bundle.

#### Scenario: portable self-host export
- **WHEN** an operator exports a universe for self-hosting or forking
- **THEN** the output is a portable OKF bundle consumable without any Tiny-specific tooling

#### Scenario: redaction deletes from the canonical bundle first
- **WHEN** an entry is redacted
- **THEN** its body is removed from the bundle first (tombstone retained)
- **AND** the operational index is rebuilt to drop the content

### Requirement: The brain conforms to OKF and auto-syncs to the standard
The bundle root SHALL declare `okf_version`. A forkable steward SHALL track the published OKF spec and absorb backward-compatible (minor) revisions without breaking existing entries. Conformance SHALL be checkable against the declared version. The steward SHALL be a composable forkable branch, never platform code.

#### Scenario: a backward-compatible OKF revision is absorbed
- **WHEN** OKF publishes a backward-compatible (minor) revision
- **THEN** the steward updates the declared `okf_version` and conventions
- **AND** existing entries remain conformant and readable

#### Scenario: conformance check passes for a Tiny bundle
- **WHEN** the conformance check runs over a Tiny bundle
- **THEN** every non-reserved `.md` file has parseable frontmatter with a non-empty `type`
- **AND** reserved files follow OKF structure
