## ADDED Requirements

### Requirement: Dataset assets are content-addressed reference manifests
The commons SHALL represent a dataset as an immutable content-addressed manifest containing `manifest_hash`, size, modality, registry-resolved `license_id`, source declarations, curation log, schema, integrity hashes, storage references, pricing terms, contributor shares, and version lineage. Registration SHALL be a declaration plus curation review, not proof of every claim. Marketplace and workflow records SHALL move the manifest reference; bytes SHALL transfer seller-to-trainer directly or through storage the platform does not own, never through platform-owned dataset storage.

#### Scenario: a dataset purchase transfers a reference
- **WHEN** a buyer receives rights to a dataset asset
- **THEN** the settlement records the immutable manifest hash and access grant while the bytes remain at their declared storage locations

### Requirement: Data commons owns fail-closed manifest and license validation
Data commons SHALL own the curated license registry, full-provenance manifest validation, and restriction-union composition contract. Dataset and base-model license identifiers SHALL resolve before any consumer can admit the manifest; unknown, missing, no-derivatives, or incompatible terms SHALL fail validation. `share_alike`, `non_commercial`, named redistribution terms, and every other composed restriction SHALL propagate irrevocably and be frozen into the minted capability's ownership record. Training owns invoking this validated contract before any training bytes or tokens are processed and persisting the composed restrictions and full input lineage at mint.

#### Scenario: no-derivatives input blocks before work
- **WHEN** any admitted manifest resolves to terms that forbid derivatives
- **THEN** the training request is rejected before data transfer, token processing, payment release, or capability minting

### Requirement: Dataset pricing is explicit and independent of compute pricing
Dataset offers SHALL declare one of the three seller-chosen modes from the target design: free with attribution and provenance recording; a flat per-run license fee locked when training starts and released only on completion through the standard escrow transport; or realized-revenue share using declared `data_ppm` as an additional exact attribution leg. Data consideration SHALL remain separate from compute price and platform fee.

#### Scenario: a per-run license fee follows training escrow
- **WHEN** a run admits a dataset under the flat per-run mode
- **THEN** the fee is locked at training start, released only on the declared completion outcome, and otherwise follows the frozen refund rule

#### Scenario: revenue-share data earns only on realized model revenue
- **WHEN** a derivative capability records an attributable paid revenue event
- **THEN** the dataset share is apportioned from that event under the frozen terms, while unrealized valuation creates no payout

### Requirement: Contamination, privacy, and quality gates precede gate-backed use
Dataset manifests SHALL name required contamination, PII/privacy, integrity, deduplication, and quality evaluations. Contamination SHALL compare against the goal gate ladder's held-out evaluation sets so those gates retain meaning. Deduplication within and across registered datasets SHALL run as ordinary priced node work, not a hidden platform service. A gate-backed training or evaluation claim SHALL remain inadmissible until every required check has a versioned result bound to the exact manifest hash, and all check results SHALL remain in provenance.

#### Scenario: contamination check precedes benchmark-backed use
- **WHEN** a dataset overlaps a benchmark or evaluation corpus subject to a contamination rule
- **THEN** the run is blocked until a passing contamination result for that exact version is recorded

### Requirement: Contributor settlement is frozen, exact, and auditable
A collaborative dataset SHALL freeze contributor identities, accepted contribution weights, and payout terms in its version manifest. An annotation campaign SHALL be modeled as a Goal with machine gates, and accepted gated work SHALL become the contributor's share weight. Revenue and campaign payments SHALL use deterministic exact apportionment whose shares conserve the input and whose tie-breaking is recorded.

#### Scenario: contributor payouts conserve exactly
- **WHEN** a dataset revenue event is distributed across its frozen contributors
- **THEN** integer payouts sum exactly to the distributable amount and reproduce from the manifest and event alone

### Requirement: Dataset Forge is a provenance-preserving commons workflow
Dataset Forge SHALL be a commons workflow graph composed from seed intake, license-gated corpus fetch, ordinary priced synthesis nodes, deduplication, contamination gates, and manifest emission rather than a platform service. Every example SHALL carry exactly one provenance class: `user-seed`, `corpus[dataset_id]`, or `synthetic[derived_from: ...]`, plus its transformation lineage. Synthetic examples SHALL inherit every upstream restriction; synthesis conditioned only on the user's own seed SHALL remain unambiguously the user's. No training run SHALL start without a complete admitted manifest whose full provenance set passes the data-commons validation contract.

#### Scenario: synthetic examples inherit upstream terms
- **WHEN** a Forge node derives examples from one or more restricted sources
- **THEN** the output manifest composes those restrictions and cannot publish a more permissive license
- **AND** an example derived only from the user's seed remains classified as `user-seed`

#### Scenario: no manifest means no run
- **WHEN** a training request references bytes without an admitted content-addressed manifest
- **THEN** the request fails before data access or payment
