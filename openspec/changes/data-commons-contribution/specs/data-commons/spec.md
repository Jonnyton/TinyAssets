## ADDED Requirements

### Requirement: Commons contribution and discovery ride the canonical page handles
Contributing to the data commons SHALL be a write of a commons entry through the canonical `write_page` handle, and discovering contributions SHALL be a read through `read_page`. This capability SHALL NOT introduce a new top-level MCP handle, a dataset tool, a platform-owned contribution registry, or a second commons write path. The commons SHALL remain writable by any authenticated principal without invitation, curation seat, or platform approval, under the existing shared-root commons surface that the per-universe ownership ACL does not gate and the existing auth-scope gate does. A contribution SHALL declare its contribution kind, the Goals it relates to, its resolved license identifier, its provenance class, and its integrity references as frontmatter keys on the entry — additional keys on a knowledge entry whose only structurally required key is a non-empty `type` — so no new profile mechanism, category whitelist, or closed taxonomy is introduced, and a custom category SHALL remain acceptable and queryable exactly as the seed-taxonomy rule already specifies. Selecting the commons as an explicit write destination on `write_page` is a prerequisite this capability consumes and SHALL NOT define; it is owned by the host decision recorded on 2026-07-25 that the commons stays anyone-writable behind an explicit commons scope.

#### Scenario: a contribution lands as an ordinary commons entry
- **WHEN** an authenticated principal contributes a dataset, a corpus description, an annotation set, or a curation note to the data commons
- **THEN** the contribution is written as a commons entry through the canonical page write handle with its declared frontmatter keys
- **AND** no dataset-specific tool, action namespace, or registry surface is required to write it

#### Scenario: the commons accepts a contribution from any authenticated principal
- **WHEN** a principal who is not the platform, not a maintainer, and not on any curation list contributes to the shared commons
- **THEN** the contribution is accepted on the same terms as any other, subject only to the existing auth-scope gate
- **AND** no invitation, allowlist, or platform approval step is consulted

#### Scenario: contributions are discoverable through ordinary commons reads
- **WHEN** a reader searches the commons for contributions related to a Goal without supplying a scope
- **THEN** matching contribution entries are returned through the default discovery scope alongside other commons knowledge
- **AND** no second discovery index, dataset catalog surface, or aggregation path is consulted

#### Scenario: the handle set does not grow
- **WHEN** the live connector's advertised handle set is asserted after this capability is implemented
- **THEN** it is unchanged from the canonical set, and no contribution, dataset, manifest, forge, or promotion handle has been added

### Requirement: A dataset contribution is an immutable content-addressed manifest entry that moves references, not bytes
A dataset contribution SHALL be represented as an immutable content-addressed manifest entry recording `manifest_hash`, size, modality, a registry-resolved `license_id`, source declarations, curation log, schema, integrity hashes, storage references, declared pricing terms, declared contributor shares, and version lineage. Registration SHALL be a declaration plus curation review, not proof of every claim, and the entry SHALL say so rather than implying verification it did not perform. A manifest entry SHALL be immutable once written: changed content SHALL mint a new `manifest_hash` and a new version linked to its predecessor through the entry's lineage, and SHALL NOT mutate an existing manifest in place. Downstream marketplace, training, and workflow records SHALL move the manifest reference; bytes SHALL transfer directly between the parties or through storage the platform does not own, and SHALL NOT be required to pass through platform-owned dataset storage. The manifest entry's **canonical** form SHALL be the commons knowledge bundle, with any entry store, full-text index, or vector index over it treated as a rebuildable derived index that loses to the bundle on disagreement; a catalog, ledger, inbox, or market row referencing the same dataset SHALL be canonical only for its own transactional domain and SHALL NOT be treated as canonical for the manifest.

#### Scenario: a dataset transfer moves a reference
- **WHEN** a consumer receives rights to a dataset contribution
- **THEN** the record binds the immutable manifest hash and the access grant while the bytes remain at their declared storage locations
- **AND** no copy of the bytes is required to exist in platform-owned dataset storage

#### Scenario: changed content mints a new version rather than mutating
- **WHEN** a contributor revises the content behind an already-registered manifest
- **THEN** a new manifest hash and a new version entry are minted with lineage back to the prior version
- **AND** the prior manifest entry remains readable and unchanged at its original hash

#### Scenario: the bundle wins over its derived index
- **WHEN** a derived entry, full-text, or vector index disagrees with the commons bundle about a manifest entry's content
- **THEN** the bundle's content is authoritative and the index is rebuilt from it
- **AND** a market or catalog row referencing the same dataset is not consulted as manifest truth

#### Scenario: registration does not claim verification it did not perform
- **WHEN** a manifest entry records source declarations and a curation log
- **THEN** the entry distinguishes declared claims from checked results
- **AND** no consumer can read an unchecked declaration as a passed validation

### Requirement: Manifest and license validation is a fail-closed admission gate consumers invoke rather than reimplement
This capability SHALL own the curated license registry, full-provenance manifest validation, and the restriction-union composition contract, and that contract SHALL be enforced server-side as an admission gate rather than exposed as a new caller-facing handle. Dataset and base-model license identifiers SHALL resolve against the curated registry before any consumer admits a manifest; an unknown, missing, expired, no-derivatives, or incompatible term SHALL fail validation closed, with a recorded reason and no partial admission. Composed restrictions — `share_alike`, `non_commercial`, named redistribution terms, and every other restriction in the union — SHALL propagate irrevocably to every derived artifact and SHALL be frozen into the record of any capability minted from the admitted inputs. Downstream consumers SHALL invoke this validated contract before data transfer, token processing, payment release, or capability minting, and SHALL NOT reimplement license or manifest admission logic of their own.

#### Scenario: a no-derivatives input blocks before any work
- **WHEN** an admitted manifest resolves to terms that forbid derivatives
- **THEN** the consuming request is rejected before data transfer, token processing, payment release, or capability minting
- **AND** the refusal records which resolved term caused it

#### Scenario: an unresolvable license fails closed
- **WHEN** a manifest declares a license identifier that is absent from the curated registry
- **THEN** validation fails with a recorded reason and the manifest is not admitted
- **AND** no permissive default, best-effort match, or caller-asserted override admits it

#### Scenario: restrictions compose and cannot be narrowed downstream
- **WHEN** a derived artifact is produced from two admitted manifests carrying different restrictions
- **THEN** the derived artifact carries the union of both restriction sets
- **AND** it cannot be published, licensed, or minted under terms more permissive than that union

#### Scenario: a consumer admits only through the shared contract
- **WHEN** a training, evaluation, or fabrication consumer needs to admit a dataset manifest
- **THEN** it calls this capability's validation contract and records the result it received
- **AND** it does not carry a second, local license or manifest admission implementation

### Requirement: Contamination, privacy, and quality gates precede gate-backed use
A dataset manifest SHALL name the contamination, PII/privacy, integrity, deduplication, and quality evaluations its use requires. Contamination SHALL be evaluated against the held-out evaluation sets used by the Goal outcome-gate ladders, so that passing a gate backed by that data retains meaning. Deduplication within and across registered datasets SHALL run as ordinary node work under the caller's own authority and budget, and SHALL NOT be provided as a hidden platform service. A gate-backed training, evaluation, or outcome claim SHALL remain inadmissible until every named check has a versioned result bound to the exact `manifest_hash` it was run against, and every check result — pass or fail — SHALL remain in the manifest's provenance rather than being overwritten by a later run.

#### Scenario: a contamination check precedes benchmark-backed use
- **WHEN** a dataset overlaps a benchmark or evaluation corpus subject to a contamination rule
- **THEN** the run is blocked until a passing contamination result for that exact manifest version is recorded

#### Scenario: a result bound to a different version does not admit
- **WHEN** a gate-backed claim cites a check result recorded against a different `manifest_hash` than the one being admitted
- **THEN** the claim is inadmissible and the check is required again for the exact version in use

#### Scenario: failed checks stay in provenance
- **WHEN** a check fails and is later re-run to a pass on the same manifest version
- **THEN** both results remain readable in the manifest's provenance with their versions and order
- **AND** the failing result is not deleted, overwritten, or hidden from a reader of the manifest

### Requirement: Every contributed example carries exactly one provenance class, and Forge is a remixable commons workflow
Every example in a contributed dataset SHALL carry exactly one provenance class — `user-seed`, `corpus[dataset_id]`, or `synthetic[derived_from: ...]` — together with its transformation lineage, and an example SHALL NOT be admitted without one. Synthetic examples SHALL inherit every restriction of every upstream source they were derived from, and an output manifest SHALL NOT publish under terms more permissive than that inherited union. Synthesis conditioned only on the contributing user's own seed SHALL remain unambiguously classified `user-seed` and SHALL NOT acquire restrictions from sources it was not derived from. Dataset Forge SHALL be a commons workflow graph — seed intake, license-gated corpus fetch, ordinary synthesis nodes, deduplication, contamination gates, and manifest emission composed from existing graph primitives — that any user can fork, replace, or author from scratch through the canonical graph handles, and the platform SHALL ship at most a replaceable seed set of such graphs rather than a platform Forge service or a closed catalog. No training or gate-backed run SHALL start without a complete admitted manifest whose full provenance set passes the validation contract above.

#### Scenario: synthetic examples inherit upstream terms
- **WHEN** a Forge node derives examples from one or more restricted sources
- **THEN** the output manifest composes those restrictions and cannot publish a more permissive license
- **AND** an example derived only from the contributor's own seed remains classified `user-seed`

#### Scenario: an unclassified example is not admitted
- **WHEN** a manifest is submitted containing an example with no provenance class or with more than one
- **THEN** validation fails and the manifest is not admitted

#### Scenario: a user-authored forge graph is first-class
- **WHEN** a user forks a seeded Forge graph, changes its synthesis and dedup nodes, and runs it
- **THEN** the resulting manifest is admitted on the same terms as one produced by a platform-seeded graph
- **AND** no platform approval, allowlisting, or platform code edit is required to run the fork

#### Scenario: no manifest means no run
- **WHEN** a training or gate-backed request references bytes without an admitted content-addressed manifest
- **THEN** the request fails before data access or payment

### Requirement: Contribution lineage and attribution ride the platform's existing append-only ledgers
Contribution and derivation provenance SHALL be recorded on the platform's existing append-only contribution ledger and attribution-edge substrate, and this capability SHALL NOT create a second provenance store, lineage table, credit graph, or attribution surface. A contribution event SHALL be idempotent on its caller-supplied event identifier, a derivation SHALL be recorded as a parent-to-child attribution edge whose credit share is clamped into the unit interval and whose generation depth derives from its parents, and a cycle SHALL be rejected before insert under the existing ancestor-walk bound. Every admitted manifest, every derived manifest, and every commons entry promoted from one SHALL be resolvable to the contributors and upstream sources recorded on those ledgers. This capability SHALL record **who contributed what, and from what**; it SHALL NOT define contributor share weights, payout terms, apportionment, or settlement, which remain with the monetary owner named in the money-edge requirement below.

#### Scenario: a derivation records an edge on the existing ledger
- **WHEN** a contributed dataset is derived from one or more existing commons contributions
- **THEN** parent-to-child attribution edges are written on the existing attribution substrate with clamped credit shares and derived generation depth
- **AND** no dataset-specific lineage table is created to hold the same facts

#### Scenario: a replayed contribution event is ignored
- **WHEN** the same contribution event identifier is recorded twice
- **THEN** only the first is inserted and the second is silently skipped

#### Scenario: a cyclic derivation is refused
- **WHEN** a derivation edge would make a child an ancestor of its own parent
- **THEN** the edge is rejected with a cycle-detected error and no edge is written

#### Scenario: attribution is recorded without defining payout
- **WHEN** a contribution and its derivations are fully recorded
- **THEN** the ledgers resolve the contributors and upstream sources for the artifact
- **AND** no share weight, payout term, apportionment, or settlement record is produced by this capability

### Requirement: Promotion from private material into the commons is an explicit user act and custody-agnostic
Publishing private material into the commons SHALL happen only as an explicit act by the principal who holds that material, naming exactly what is published. There SHALL be no automatic promotion: no background crawl, no publish-on-run-completion, no promotion inferred from adjacency, similarity, co-location, or prior sharing, and no promotion performed on a principal's behalf by the platform, a maintainer, or another universe. The promotion path SHALL be custody-agnostic and SHALL NOT assume the platform holds the private source: material whose custody mode is the user's own host machine, their private universe brain, a vault whose key is outside platform reach, or platform-held storage SHALL promote through the same path with the same result, and where the source is unreachable because no host is online the attempt SHALL report that condition rather than degrading to a different custody mode or a cached copy. A commons entry SHALL NOT imply, require, or create platform custody of the private original, and revoking or relocating the private source SHALL NOT be prevented by the existence of the promoted entry. This capability SHALL record its own custody position explicitly: **commons entries are public-by-definition and platform-held as commons content**, exportable in full as a portable bundle, while the custody of the private source remains the user's choice and is not answered here in either direction.

#### Scenario: nothing reaches the commons without an explicit act
- **WHEN** a principal holds private material that is related, similar, or adjacent to existing commons contributions
- **THEN** none of it appears in the commons until that principal explicitly publishes the specific material
- **AND** no scan, run completion, similarity match, or platform-side process publishes any part of it

#### Scenario: every custody mode promotes identically
- **WHEN** the same material is promoted from a host machine, from a private universe brain, from a vault, or from platform-held storage
- **THEN** registration, validation, lineage recording, and discoverability of the resulting commons entry are identical
- **AND** the promotion path requires no platform-held copy of the private source

#### Scenario: an unreachable source reports rather than degrades
- **WHEN** a promotion needs material from a custody mode that is currently unreachable because no host is online
- **THEN** the attempt reports that condition and completes nothing
- **AND** it does not fall back to a cached copy, a different custody mode, or a platform-held substitute

#### Scenario: the commons entry does not capture the private original
- **WHEN** a contributor later revokes, relocates, or deletes the private source behind a promoted contribution
- **THEN** the private source's custody remains entirely under the contributor's control
- **AND** the platform asserts no custody claim over the original by virtue of the commons entry existing

### Requirement: The contribution half of data-commons is non-monetary and fails closed at the money edge
Contribution, manifest registration, validation, gate evaluation, provenance recording, discovery, and promotion SHALL create no escrow, fee, price, ledger, or settlement record, and SHALL NOT constitute a payment surface. A manifest's declared pricing terms and declared contributor shares SHALL be recorded declarations readable as terms, not authorization to move value, and no spend or settlement path SHALL accept them as authority. An action in this capability whose execution would move value SHALL refuse, record the refusal, and name the capability it requires — the single authenticated double-entry transaction boundary owned by `paid-market-economy` — rather than opening a second accounting path or degrading to a best-effort local debit. The refusal SHALL name that capability rather than a change slug, since change names are provenance and expire on archive while the capability is the durable contract. Dataset pricing-mode semantics and frozen contributor settlement SHALL NOT be specified, implemented, or partially staged here.

#### Scenario: a value-moving action refuses and names its owner
- **WHEN** an action in this capability would create or move a balance, escrow, fee, or settlement record
- **THEN** the action refuses, records the refusal, and names the `paid-market-economy` transaction boundary it requires
- **AND** no local balance, escrow, or ledger row is written as a substitute

#### Scenario: declared terms grant no authority
- **WHEN** a manifest declares pricing terms and contributor shares and is then admitted by a consumer
- **THEN** the declarations are persisted and readable as terms
- **AND** no spend, escrow, or settlement path accepts them as authorization to move value
