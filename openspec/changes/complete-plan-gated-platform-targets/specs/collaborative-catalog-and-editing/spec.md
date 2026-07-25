## ADDED Requirements

### Requirement: The catalog is Postgres-canonical and indexes commons knowledge without duplicating it

The collaborative catalog SHALL treat its own rows — artifact registration, membership, versions, revisions, and collaboration state — as canonical in the platform's transactional store. A catalog row that describes a piece of commons knowledge SHALL be an index entry referencing the OKF bundle, and SHALL NOT be a second canonical copy of that knowledge. When an index row and the referenced bundle disagree, the bundle SHALL be authoritative and the index row SHALL be rebuildable from it. The catalog SHALL NOT require a commons artifact to be re-authored in catalog-native form to become discoverable, and a user-designed brain organization SHALL be catalogable as an artifact rather than encoded as catalog schema.

#### Scenario: Index row diverges from the bundle

- **WHEN** a catalog index row's cached title, summary, or checksum disagrees with the referenced OKF bundle entry
- **THEN** reads resolve to the bundle's values
- **AND** the index row is repaired from the bundle without any write to the bundle

#### Scenario: Index is rebuildable from the commons

- **WHEN** the catalog's commons index is dropped and rebuilt from the bundle
- **THEN** every commons artifact is rediscoverable with equivalent metadata
- **AND** no commons knowledge is lost, because the catalog never held the only copy

#### Scenario: A brain organization is catalog content, not catalog schema

- **WHEN** a user publishes a custom brain organization that is not the default OKF shape
- **THEN** it is registered, discoverable, and remixable as an ordinary catalog artifact
- **AND** the catalog requires no schema change to accept its shape

### Requirement: Collaborative writes are compare-and-swap on a monotonic version

Every write to a shared catalog artifact SHALL carry the version the writer observed and SHALL be applied only if that version is still current. A write carrying a stale version SHALL be refused rather than merged or silently overwritten, and the refusal SHALL return the current version together with enough change description for the caller to retry against fresh state. Version numbers SHALL increase monotonically per artifact, and concurrent writers SHALL NOT both succeed against the same observed version.

#### Scenario: Concurrent writes against the same observed version

- **WHEN** two writers submit changes both citing version N
- **THEN** exactly one write is applied and the artifact advances to version N+1
- **AND** the other write is refused with the current version and a description of what changed

#### Scenario: Stale write is refused, not merged

- **WHEN** a writer submits a change citing a version older than current
- **THEN** the write is refused
- **AND** no partial content from the stale write is persisted

#### Scenario: Retry against fresh state succeeds

- **WHEN** the refused writer re-reads, rebases its change onto the current version, and resubmits
- **THEN** the write is applied and the version advances by one

### Requirement: Every write appends an immutable revision and reverting creates a new revision

Each applied write SHALL append one immutable revision record capturing the resulting content, the authenticated author, the timestamp, and the parent revision. Revision records SHALL NOT be edited or removed by ordinary editing. Any editor authorized to write the artifact SHALL be able to restore the content of any prior revision, and that restoration SHALL be recorded as a new revision citing the restored source rather than by deleting or rewinding intervening revisions. Revision history SHALL remain readable after restoration.

#### Scenario: Write appends a revision

- **WHEN** a compare-and-swap write is applied
- **THEN** exactly one revision record is appended with content, author, timestamp, and parent revision
- **AND** prior revision records are unchanged

#### Scenario: Revert is recorded forward

- **WHEN** an authorized editor restores the artifact to the content of an earlier revision
- **THEN** a new revision is appended recording the restoration and its source revision
- **AND** the intervening revisions remain present and readable

#### Scenario: Revisions resist ordinary editing

- **WHEN** any editing action attempts to modify or remove an existing revision record
- **THEN** the attempt is refused

### Requirement: The two collaboration models bind to content class and the boundary is enforced

The system SHALL apply the wiki-open model to commons artifacts — direct authenticated writes with compare-and-swap, no pre-publication review gate, and post-hoc moderation — and the fork-and-PR model to platform code, which SHALL have no direct write path through the collaborative catalog surface. The applicable model SHALL be determined by the artifact's content class rather than by caller preference, and an attempt to write platform code through the commons path SHALL be refused with the fork-and-PR path named. Tier-2 and tier-3 principals SHALL be able to participate in both models without a single principal's role changing which model an artifact uses.

#### Scenario: Commons artifact takes the wiki-open path

- **WHEN** an authenticated principal writes a commons artifact within its visibility and ownership authority
- **THEN** the write applies directly under compare-and-swap with no review gate

#### Scenario: Platform code cannot be edited through the commons path

- **WHEN** a caller attempts to write a platform-code artifact through the collaborative catalog surface
- **THEN** the write is refused and the response names the fork-and-PR path
- **AND** no catalog revision is created

#### Scenario: Content class, not caller role, selects the model

- **WHEN** a principal holding elevated platform authority writes a commons artifact
- **THEN** the wiki-open model still applies, with the same compare-and-swap and revision behavior as any other principal

### Requirement: External repository export is derived one-way and imports carry no privilege

Export of catalog content to an external repository SHALL be a derived projection of catalog state and SHALL NOT become an alternate canonical store. Content SHALL flow back only through an import path that re-enters the same authenticated write path as any other write, subject to the same compare-and-swap, authority, visibility, and moderation rules. An import SHALL NOT bypass version checking, SHALL NOT restore artifacts the catalog has removed or hidden, and SHALL be attributed to an identifiable importing principal. Export SHALL exclude anything the exporting projection is not authorized to publish.

#### Scenario: Export is a projection

- **WHEN** the catalog exports to the external repository and the export is later deleted or rewritten externally
- **THEN** catalog state is unaffected and the next export reproduces the projection

#### Scenario: Import re-enters the ordinary write path

- **WHEN** an external change is imported back into the catalog
- **THEN** it is applied through the same authenticated compare-and-swap write path with an identified importing principal
- **AND** a stale-version import is refused exactly as a stale direct write would be

#### Scenario: Import cannot resurrect withheld content

- **WHEN** an import carries an artifact the catalog has hidden, removed, or restricted
- **THEN** the import is refused for that artifact and its prior state is preserved

### Requirement: Catalog projections enforce visibility, including on derived fields

Every catalog read projection SHALL apply the caller's visibility and ownership authority to each artifact it returns, and SHALL apply the same predicate to derived fields — related-artifact lists, parent and child references, collaborator lists, counts, and summaries. A restricted artifact SHALL NOT be represented in any projection returned to an unauthorized caller by identifier, path, title, summary, or count, and its existence SHALL NOT be inferable from a gap or an inflated total. Authority SHALL be resolved from the authenticated subject, never from an environment fallback or a caller-supplied identity claim.

#### Scenario: Derived reference is filtered like a direct read

- **WHEN** a visible artifact's derived related-artifact block would include an artifact the caller cannot read
- **THEN** that entry is omitted from the block
- **AND** no path, title, or summary of the restricted artifact appears anywhere in the response

#### Scenario: Counts do not leak existence

- **WHEN** a projection returns counts alongside a filtered list
- **THEN** the counts reflect only what the caller is authorized to see
- **AND** the response does not reveal that additional entries were withheld

#### Scenario: Authority comes from the authenticated subject

- **WHEN** a request supplies an actor identifier that differs from the authenticated subject, or no authenticated subject is present on a restricted read
- **THEN** the supplied identifier is ignored and the caller is treated as unauthenticated for visibility purposes

### Requirement: Catalog and collaboration behaviors compose under the canonical handle set

Every catalog and collaboration behavior in this capability SHALL be reachable as an action or parameter under the existing canonical MCP handles, and this capability SHALL NOT add an advertised MCP handle. Where the source architecture named a standalone RPC, the implementation SHALL route it as an action under an existing handle. A future top-level handle SHALL be introduced only through a recorded irreducibility finding in its own change.

#### Scenario: Advertised handle set is unchanged

- **WHEN** the live connector's advertised tool list is inspected after this capability ships
- **THEN** it contains exactly the canonical handle set, with no handle added by this capability

#### Scenario: A named RPC lands as an action

- **WHEN** a behavior the architecture named as a standalone RPC is implemented
- **THEN** it is dispatched as an action under an existing canonical handle
- **AND** its authority, visibility, and audit behavior match that handle's contract
