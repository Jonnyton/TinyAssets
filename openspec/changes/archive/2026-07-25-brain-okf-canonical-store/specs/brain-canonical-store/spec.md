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

### Requirement: Writes are write-through under an explicit commit protocol
A write SHALL be applied transactionally to the operational index AND projected to the OKF bundle under an explicit commit protocol — idempotency key, pending→durable entry states, atomic temp-file+rename bundle projection, file locking, SQLite-transaction/outbox ordering, crash recovery, and rebuild reconciliation. An entry SHALL be considered durable only once it is present in the bundle; the operational index alone SHALL NOT be treated as durable storage; a naive dual-write SHALL NOT be relied upon. (Write-through re-houses, and does NOT by itself resolve, the public-concurrency hazards of research-impl Gap #4.)

#### Scenario: an accepted write reaches the bundle via the outbox
- **WHEN** a write is accepted by the operational layer (passing the candidate gate)
- **THEN** it is enqueued durably (outbox) and projected to a bundle file via atomic temp-file+rename with conformant frontmatter
- **AND** the human-readable change is appended to `log.md`

#### Scenario: a crash before projection is recoverable, not falsely durable
- **WHEN** the process crashes after the operational write but before bundle projection completes
- **THEN** the entry is recovered as `pending` (not reported durable) and re-projected on restart
- **AND** the bundle never contains a half-written file (temp+rename is atomic)

#### Scenario: concurrency is served by the operational layer
- **WHEN** multiple concurrent writers submit entries
- **THEN** the operational layer serializes them transactionally before projection
- **AND** bundle files remain individually well-formed

### Requirement: Tiny's typed entry fields conform to OKF as additional frontmatter keys
Every non-reserved entry file SHALL carry a non-empty `type`. Tiny's typed/scoped/lifecycled fields (`goal_id`, `universe_id`, `visibility`, `lifecycle`, `ttl_class`, `supersedes`, `evidence_refs`) SHALL be carried as additional frontmatter keys, which OKF consumers SHOULD preserve when round-tripping. The bundle SHALL remain OKF-conformant: parseable frontmatter, non-empty `type`, reserved-file structure. The brain SHALL tolerate unknown types, unknown keys, and broken cross-links (which OKF treats as valid — not-yet-written, stale, or typo) rather than rejecting them.

#### Scenario: a generic OKF consumer reads a Tiny entry
- **WHEN** an OKF-generic consumer (no Tiny knowledge) reads a Tiny entry file
- **THEN** it parses the `type` and renders the body
- **AND** it preserves Tiny's extra frontmatter keys when round-tripping (SHOULD)

#### Scenario: a broken cross-link is valid, not malformed
- **WHEN** an entry links to a target that does not exist in the bundle
- **THEN** the brain treats the link as valid (not-yet-written, stale, or typo) and does NOT reject the bundle

### Requirement: Reserved files carry brain semantics; the transactional journal is separate
`index.md` SHALL render the progressive-disclosure manifest and SHALL carry no frontmatter except an optional bundle-root `okf_version`. `log.md` SHALL carry human-readable, OKF-structured update history (generated/appended). The transactional journal / outbox of record SHALL NOT be a single prose markdown file (it is operational state, not a bundle concept). Citations SHALL live under a `# Citations` heading and/or a `references/` subdirectory; an entry's concept ID SHALL be its bundle-relative path with the `.md` suffix removed.

#### Scenario: progressive disclosure via index.md
- **WHEN** a lens assembles a view and needs a manifest of available entries
- **THEN** it reads `index.md` for the entry id + one-line manifest before fetching bodies

#### Scenario: supersession lineage stays queryable
- **WHEN** an entry is superseded
- **THEN** the `supersedes` frontmatter and `log.md` record the lineage
- **AND** default views exclude superseded entries while lineage remains queryable

### Requirement: The existing wiki reaches conformance via a compatibility shim
The current wiki is NOT OKF-conformant as-is (its root `index.md` scaffold carries `title/type/updated`; it uses `[[wikilinks]]` rather than Markdown links). The slice-1 read-only `assemble(lens)` path SHALL consume the existing wiki through an OKF compatibility shim — a lossless `[[wikilink]]`→Markdown-link projection, root-`index.md` normalization to `okf_version`-only, `log.md` date-structure normalization, and a declared rule for whether `drafts/` are bundle concepts or operational staging outside the bundle. No content migration SHALL be required.

#### Scenario: slice-1 reads the wiki through the shim
- **WHEN** slice-1 assembles a lens over the existing wiki
- **THEN** it reads it through the compatibility shim (links projected, index/log normalized)
- **AND** no wiki content is migrated or rewritten in place to achieve conformance

### Requirement: The bundle is the unit of durability, federation, and export
The nightly git snapshot of the bundle SHALL be the canonical durable store (not a backup of a derived DB). Commons federation SHALL aggregate public goal-addressed bundle entries across universes. Self-host and fork export SHALL emit the bundle wholesale as a portable OKF bundle.

#### Scenario: portable self-host export
- **WHEN** an operator exports a universe for self-hosting or forking
- **THEN** the output is a portable OKF bundle consumable without any Tiny-specific tooling

#### Scenario: redaction blocks the operational index first
- **WHEN** an entry is redacted
- **THEN** the operational index stops serving it FIRST (tombstone / block reads before stale content can keep being served), then the bundle body is deleted at the source, then the index is rebuilt and rollups purged
- **AND** for a secrets-class redaction the tombstone OMITS any recoverable content hash

### Requirement: The brain conforms to OKF and auto-syncs to the standard
The bundle root SHALL declare `okf_version`. Conformance VALIDATION SHALL be substrate. A forkable, composable steward SHALL watch the upstream OKF spec and PROPOSE migrations for backward-compatible (minor) revisions; the steward SHALL NOT be platform code.

#### Scenario: a backward-compatible OKF revision is proposed and validated
- **WHEN** OKF publishes a backward-compatible (minor) revision
- **THEN** the composable steward proposes the `okf_version` + convention update
- **AND** substrate conformance validation confirms existing entries remain conformant and readable

#### Scenario: conformance check passes for a Tiny bundle
- **WHEN** the substrate conformance validation runs over a Tiny bundle
- **THEN** every non-reserved `.md` file has parseable frontmatter with a non-empty `type`
- **AND** reserved files follow OKF structure
