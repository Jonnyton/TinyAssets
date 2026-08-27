## ADDED Requirements

### Requirement: Commons contribution and discovery ride the canonical page handles
Contributing to the data commons SHALL be a write of a commons entry through the canonical `write_page` handle, and discovering contributions SHALL be a read through `read_page`. This capability SHALL NOT introduce a new top-level MCP handle, a dataset tool, a platform-owned contribution registry, or a second commons write path. The commons SHALL remain writable by any authenticated principal without invitation, curation seat, or platform approval, under the existing shared-root commons surface that the per-universe ownership ACL does not gate and the existing auth-scope gate does. A contribution SHALL declare its contribution kind, the Goals it relates to, its declared license identifier, its provenance class, and its integrity references as frontmatter keys on the entry — additional keys on a knowledge entry whose only structurally required key is a non-empty `type` — so no new profile mechanism, category whitelist, or closed taxonomy is introduced, and a custom category SHALL remain acceptable and queryable exactly as the seed-taxonomy rule already specifies. Selecting the commons as an explicit write destination on `write_page` is a prerequisite this capability consumes and SHALL NOT define; it is owned by the host decision recorded on 2026-07-25 that the commons stays anyone-writable behind an explicit commons scope.

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
A dataset contribution SHALL be represented as an immutable content-addressed manifest entry recording `manifest_hash`, size, modality, a declared `license_id`, source declarations, curation log, schema, integrity hashes, storage references, and version lineage. Registration SHALL be a declaration, not proof of every claim, and the entry SHALL say so rather than implying verification it did not perform. Curation SHALL be non-blocking: a curation log entry, review annotation, or moderation outcome SHALL annotate an already-admitted entry and SHALL NOT act as a pre-publication review gate, matching the wiki-open model the commons already applies to commons artifacts — direct authenticated writes with compare-and-swap and post-hoc moderation. A manifest entry SHALL be immutable once written: changed content SHALL mint a new `manifest_hash` and a new version linked to its predecessor through the entry's lineage, and SHALL NOT mutate an existing manifest in place. Because the as-built page-write contract overwrites an already-promoted slug in place, immutability SHALL be expressed as an explicit refusal on that write path — a write targeting an already-written manifest entry SHALL be refused with the mint-a-new-version instruction rather than silently overwriting — and that behavior SHALL be carried as a `wiki-commons` MODIFIED delta rather than asserted only here. Any downstream training, workflow, catalog, or transactional record SHALL move the manifest reference; bytes SHALL transfer directly between the parties or through storage the platform does not own, and SHALL NOT be required to pass through platform-owned dataset storage. The manifest entry's **canonical** form SHALL be the commons knowledge bundle, with any entry store, full-text index, or vector index over it treated as a rebuildable derived index that loses to the bundle on disagreement; a catalog, ledger, inbox, or market row referencing the same dataset SHALL be canonical only for its own transactional domain and SHALL NOT be treated as canonical for the manifest.

#### Scenario: a downstream record moves a reference
- **WHEN** a downstream training, workflow, or catalog record references a dataset contribution
- **THEN** the record binds the immutable manifest hash and the entry's declared storage reference while the bytes remain at their declared locations
- **AND** no copy of the bytes is required to exist in platform-owned dataset storage

#### Scenario: changed content mints a new version rather than mutating
- **WHEN** a contributor revises the content behind an already-registered manifest
- **THEN** a new manifest hash and a new version entry are minted with lineage back to the prior version
- **AND** the prior manifest entry remains readable and unchanged at its original hash

#### Scenario: a write to an existing manifest entry is refused, not overwritten
- **WHEN** a write targets the slug of a manifest entry that has already been written
- **THEN** the write is refused and the response instructs the caller to mint a new version at its own content-addressed slug
- **AND** the existing entry's body and frontmatter are unchanged, rather than overwritten in place as an ordinary promoted page would be

#### Scenario: the bundle wins over its derived index
- **WHEN** a derived entry, full-text, or vector index disagrees with the commons bundle about a manifest entry's content
- **THEN** the bundle's content is authoritative and the index is rebuilt from it
- **AND** a market or catalog row referencing the same dataset is not consulted as manifest truth

#### Scenario: registration does not claim verification it did not perform
- **WHEN** a manifest entry records source declarations and a curation log
- **THEN** the entry distinguishes declared claims from checked results
- **AND** no consumer can read an unchecked declaration as a passed validation

#### Scenario: curation annotates and does not gate
- **WHEN** a curation reviewer records a concern, a correction, or a rejection note against a contributed manifest entry
- **THEN** the entry remains admitted and readable, and the review is recorded as an annotation on it
- **AND** no pre-publication review step is required before the contribution is accepted

### Requirement: Manifest admission is a fail-closed gate consumers invoke rather than reimplement
This capability SHALL own full-provenance manifest validation, and that contract SHALL be enforced server-side as an admission gate at the run and mint boundaries rather than exposed as a new caller-facing handle. Admission SHALL fail closed, with a recorded reason and no partial admission, when a manifest is incomplete, when a required field is missing or unparseable, when an example carries other than exactly one provenance class, or when a required check result is absent or is not bound to the exact `manifest_hash` being admitted. Downstream consumers SHALL invoke this validated contract before data transfer, token processing, payment release, or capability minting, and SHALL NOT reimplement manifest admission logic of their own.

This capability SHALL NOT define a license restriction policy, SHALL NOT own or ship a license registry, and SHALL NOT enforce license terms at any boundary. Where a declared license identifier must be resolved or composed, the caller SHALL invoke the single landed license lattice owned by `paid-market-economy` — whose own resolution and rejection behavior is unchanged and remains that owner's — and SHALL NOT reimplement it here. Whether a dataset contribution sits outside the CC0 default that the landed architecture pins for commons content, and whether legal license enforcement is authorized as platform behavior at all, are unresolved host decisions recorded in `design.md`; until they are answered this capability SHALL specify no license-restriction, license-rejection, or restriction-propagation policy in normative text.

#### Scenario: an incomplete manifest fails closed
- **WHEN** a consumer attempts to admit a manifest whose required fields are incomplete or unparseable
- **THEN** admission fails with a recorded reason and the manifest is not admitted
- **AND** no partial admission, permissive default, best-effort match, or caller-asserted override admits it

#### Scenario: a consumer admits only through the shared contract
- **WHEN** a training, evaluation, or fabrication consumer needs to admit a dataset manifest
- **THEN** it calls this capability's manifest-admission contract and records the result it received
- **AND** it does not carry a second, local manifest admission implementation

#### Scenario: license resolution is delegated, never reimplemented
- **WHEN** a declared license identifier must be resolved or composed for a dataset contribution
- **THEN** the landed `paid-market-economy` license lattice is invoked as the single implementation
- **AND** no second registry, restriction policy, or license enforcement path is defined by this capability

#### Scenario: no license policy is asserted while the host decision is open
- **WHEN** a manifest declares a license identifier and is admitted
- **THEN** the identifier is recorded as a declaration on the entry
- **AND** admission neither rejects the contribution on a license-restriction class nor propagates a restriction to derived artifacts, because no host decision authorizes either

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
Every example in a contributed dataset SHALL carry exactly one provenance class — `user-seed`, `corpus[dataset_id]`, or `synthetic[derived_from: ...]` — together with its transformation lineage, and an example SHALL NOT be admitted without one. A synthetic example SHALL record every upstream source it was derived from in that lineage, so a reader can recover the full derivation set from the record alone. Synthesis conditioned only on the contributing user's own seed SHALL remain unambiguously classified `user-seed` and SHALL NOT be attributed to sources it was not derived from. What legal terms a recorded derivation carries is not specified here — restriction inheritance and propagation await the license host decision named in the admission requirement above. Dataset Forge SHALL be a commons workflow graph — seed intake, grant-gated corpus fetch, ordinary synthesis nodes, deduplication, contamination gates, and manifest emission composed from existing graph primitives — that any user can fork, replace, or author from scratch through the canonical graph handles, and the platform SHALL ship at most a replaceable seed set of such graphs rather than a platform Forge service or a closed catalog. No training or gate-backed run SHALL start without a complete admitted manifest whose full provenance set passes the admission contract above.

#### Scenario: synthetic examples record their upstream sources
- **WHEN** a Forge node derives examples from one or more upstream sources
- **THEN** the output manifest records every one of those sources in the example's transformation lineage
- **AND** an example derived only from the contributor's own seed remains classified `user-seed` with no source it was not derived from

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

### Requirement: Contribution lineage rides the existing ledgers without redefining their guarantees
Contribution and derivation provenance SHALL be recorded on the platform's existing append-only contribution ledger and attribution-edge substrate, and this capability SHALL NOT create a second provenance store, lineage table, credit graph, or attribution surface. Event idempotency, per-edge credit clamping, generation-depth derivation, and cycle rejection are guarantees of `evaluation-outcomes-and-attribution` and SHALL be consumed unchanged rather than restated as this capability's own; multi-parent derivation — atomic all-parent recording, aggregate credit of at most one, retry idempotency on a derivation identity, and recorded rationale — is the generic artifact-derivation contract owned by `node-discovery-and-remix` and SHALL likewise be consumed rather than redefined for the dataset case. What this capability owns is narrower: every admitted manifest, every derived manifest, and every commons entry promoted from one SHALL be resolvable to the contributors and upstream sources recorded on those ledgers, and the endpoint-domain widening that lets a commons artifact be an edge endpoint at all is carried as the `evaluation-outcomes-and-attribution` MODIFIED delta. This capability SHALL record **who contributed what, and from what**; it SHALL NOT define contributor share weights, payout terms, apportionment, or settlement, which remain with the monetary owner named in the money-edge requirement below.

#### Scenario: a derivation records on the existing substrate
- **WHEN** a contributed dataset is derived from one or more existing commons contributions
- **THEN** parent-to-child attribution edges are written on the existing attribution substrate under that capability's own edge guarantees
- **AND** no dataset-specific lineage table, credit graph, or provenance store is created to hold the same facts

#### Scenario: provenance resolves from the existing ledgers alone
- **WHEN** a reader asks who contributed an admitted manifest and what it was derived from
- **THEN** the answer resolves from the existing contribution ledger and attribution edges with no dataset-specific surface consulted

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

### Requirement: The contribution half of data-commons is non-monetary and carries no pricing surface
Contribution, manifest registration, validation, gate evaluation, provenance recording, discovery, and promotion SHALL create no escrow, fee, price, ledger, or settlement record, and SHALL NOT constitute a payment surface. A manifest entry written under this capability SHALL carry no pricing term, fee, price, contributor share weight, or settlement field at all — those fields belong to the retained monetary requirements *Dataset pricing is explicit and independent of compute pricing* and *Contributor settlement is frozen, exact, and auditable*, and SHALL be introduced by that owner rather than staged here as inert declarations. This capability SHALL NOT specify, imply, or stage a dataset-rights market or any second paid surface: the landed architecture position is that the existing paid-request bid market is the only paid surface, and whether a separate dataset paid surface is authorized is an unresolved host decision recorded in `design.md`. An action in this capability whose execution would move value SHALL refuse, record the refusal, and name the capability it requires — the single authenticated double-entry transaction boundary owned by `paid-market-economy` — rather than opening a second accounting path or degrading to a best-effort local debit. The refusal SHALL name that capability rather than a change slug, since change names are provenance and expire on archive while the capability is the durable contract.

#### Scenario: a value-moving action refuses and names its owner
- **WHEN** an action in this capability would create or move a balance, escrow, fee, or settlement record
- **THEN** the action refuses, records the refusal, and names the `paid-market-economy` transaction boundary it requires
- **AND** no local balance, escrow, or ledger row is written as a substitute

#### Scenario: a pricing field is absent rather than inert
- **WHEN** a manifest entry is written and read back under this capability
- **THEN** it carries no pricing term, fee, price, contributor share weight, or settlement field
- **AND** a consumer looking for one finds the retained monetary owner named instead of an unenforced declaration
