# Data Commons: Datasets as First-Class Assets

## Purpose

Make datasets first-class TinyAssets — registered, provenanced, license-carrying,
priceable, and attributable — so "you can rent GPUs" becomes "you can actually
train something good, legally." Data is the last moat: compute is fungible and
priced (Tracks E/F), capital is pooled (Track H); what incumbents still uniquely
hold is curated, licensed, deduplicated training data.

Historical source of record (untouched): `docs/exec-plans/active/2026-07-08-track-g-data-commons.md`.
License-composition core (implemented, fail-closed): `tinyassets/paid_market/license_terms.py`.
Composes: Track E (escrow/pricing), Track F (training, capability minting), Track H (apportionment for contributor payouts).

## Requirements

### Requirement: The dataset asset is content-addressed and reference-only

A registered dataset SHALL be `{manifest_hash (content-addressed), size,
modality, license_id (registry-resolved), provenance (source declarations,
curation log), pricing_terms, contributor_shares}`. The manifest hash SHALL be
the identity: the market moves references; bytes transfer seller→trainer directly
(or via storage the platform never needs to own). Registration SHALL be
declaration plus curation review, not proof.

#### Scenario: the market moves a reference, not the bytes
- **WHEN** a dataset is used in a training run
- **THEN** the manifest hash is the referenced identity
- **AND** the bytes transfer seller-to-trainer directly, never through platform-owned storage

### Requirement: License propagation is fail-closed (implemented)

Every training run SHALL declare its input license ids (base model plus every
dataset). `check_trainable` SHALL compose them as a restriction-union lattice and
return the terms the minted capability MUST carry. Any `no_derivatives` input
SHALL block the run before a single token trains. Any unregistered license SHALL
block the run (fail-closed: the expensive failure is minting a model the platform
had no right to mint). `share_alike` / `non_commercial` / named terms SHALL
propagate irrevocably into the minted capability, and Track H SHALL freeze them
into the ownership record.

#### Scenario: an unregistered license blocks the run
- **WHEN** a run declares an input whose license id is not in the registry
- **THEN** the run is blocked before training starts (fail-closed)
- **AND** registry additions go through curation/legal review, not code review

#### Scenario: no-derivatives input blocks before any token trains
- **WHEN** any declared input carries `no_derivatives`
- **THEN** the run is blocked before a single token trains

### Requirement: Data pricing is not compute pricing

The system SHALL offer three seller-chosen pricing modes per dataset:
free/attribution (usage still recorded in provenance), per-run license fee (flat
fee escrowed at training start, released at completion, reusing Track E escrow
verbatim), and revenue-share (the dataset takes `data_ppm` of the minted model's
revenue, wired as an additional attribution leg in Track H's `distribute_revenue`
so the dataset earns only if the model earns).

#### Scenario: a revenue-share dataset earns only when the model earns
- **WHEN** a dataset is licensed under revenue-share and its minted model earns
- **THEN** `data_ppm` of each revenue event flows to the dataset as an attribution leg
- **AND** the apportionment conserves exactly across all legs

### Requirement: Contamination and quality checks gate gate-meaning (transport, named)

Before a dataset is usable against a goal with a gate ladder, it SHALL pass a
contamination check against that ladder's eval sets (n-gram/embedding overlap
against held-out benchmarks) — otherwise gate claims are meaningless. Dedup
within and across registered datasets SHALL be a curation service priced as
ordinary node work. Both SHALL record their results in provenance.

#### Scenario: contamination check precedes gate-backed use
- **WHEN** a dataset is used against a goal whose gates rely on eval sets
- **THEN** a contamination check runs against those eval sets first
- **AND** the check result is recorded in provenance

### Requirement: Contributor attribution reuses exact apportionment

Datasets built by many contributors SHALL carry `contributor_shares`, and payouts
on any earning mode SHALL reuse `apportion_exact` unchanged. An annotation
campaign SHALL be modeled as a goal with gates; contributors' accepted work
becomes their share weight.

#### Scenario: contributor payouts conserve exactly
- **WHEN** a multi-contributor dataset earns
- **THEN** payouts split by `contributor_shares` via `apportion_exact`
- **AND** the sum of payouts equals the revenue exactly

### Requirement: Dataset Forge is a commons workflow, not a platform service (design law)

Design law applied: primitives + commons, never features. Dataset expansion SHALL
be a commons workflow graph ("Dataset Forge" archetype) composed entirely from
existing primitives (seed intake → license-gated corpus fetch → style-conditioned
synthesis as ordinary priced inference nodes → dedup node → contamination gate →
manifest emit), NOT a platform service.

The one new platform rule is provenance classes: the dataset manifest SHALL
record, per example, `user-seed` | `corpus[dataset_id]` |
`synthetic[derived_from: ...]`. Synthetic examples SHALL inherit the composed
license terms of everything upstream of their generation via the existing
fail-closed `compose_terms` lattice, and `check_trainable` SHALL run over the
manifest's full provenance set before any training run starts. No manifest, no
run.

#### Scenario: synthetic examples inherit upstream license terms
- **WHEN** synthesis is conditioned on a share-alike corpus
- **THEN** the resulting synthetic examples carry share-alike in the manifest
- **AND** synthesis conditioned only on the user's own seed is unambiguously the user's

#### Scenario: no manifest, no run
- **WHEN** a training run has no provenance manifest to check
- **THEN** the run does not start
- **AND** `check_trainable` must first pass over the full provenance set

## Open founder decisions

- **License registry contents** (Track G §2): which licenses populate the
  registry and the curation/legal-review policy for additions is a founder /
  counsel decision, not a code-review decision. The mechanism is fail-closed; the
  registry contents are open.
- **Privacy/PII scanning gate** (§7): PII scanning is its own review before G-W1
  ships publicly; that review is a pending gate.
