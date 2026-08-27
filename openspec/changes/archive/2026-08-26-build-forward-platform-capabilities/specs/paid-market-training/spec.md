## ADDED Requirements

### Requirement: Training settlement inherits canonical reservation invariants
Every paid training window SHALL settle through the single market transaction transport using the canonical checkpoint oracle, preserving exact buyer-fund and collateral conservation, demand-relative obligation, pro-rata payment, threshold-only slashing, and buyer-directed slash compensation.

#### Scenario: an early buyer cancellation cannot slash honest completed work
- **WHEN** a buyer legitimately stops a window early and every reached checkpoint verifies
- **THEN** the transport applies the canonical full reservation payment and collateral release

### Requirement: F1 and F2 are explicit instruments while F3 remains research-gated
Every instrument SHALL use the exact key `hardware class × interconnect tier × gang size × window`. F1 single-node fine-tuning SHALL ship first and bind one seller capability, data manifest, schedule, and checkpoint plan. F2 colocated pretraining gang windows SHALL bind an atomic set of compatible resources and SHALL have no partial-fill state or transition. F3 swarm pretraining SHALL remain dark behind a separate research-reviewed flag and SHALL never block F1 or F2 availability.

#### Scenario: an F2 gang cannot partially start
- **WHEN** fewer than all resources in the frozen gang are durably admitted for its start window
- **THEN** the instrument does not start and follows its explicit expiry/refund rule

#### Scenario: F3 stays non-blocking
- **WHEN** F3 is disabled or lacks its research acceptance gate
- **THEN** F1 and F2 discovery and execution continue without an F3 dependency

### Requirement: Checkpoint payment follows verified durable evidence
Each scheduled checkpoint SHALL bind weights hash, optimizer-state hash chained to its parent, training state, attestation inputs, verifier version, and terminal verdict before its payment becomes releasable. Escrow releases MAY stream per checkpoint, but their sum SHALL equal the canonical end-state oracle. Missed or failed checkpoints SHALL feed that oracle, and replay SHALL return the same receipt without paying twice.

#### Scenario: a missed checkpoint releases only its canonical settlement
- **WHEN** a scheduled checkpoint lacks passing evidence at the settlement cutoff
- **THEN** the window records the miss and applies the oracle's exact refund and slash once

### Requirement: Verification makes fraud economically dominated
Training admission SHALL define layered cheaper signals: artifact attestation over chained weights and optimizer state, loss-curve continuity, spot re-execution of randomly sampled short segments, and evaluation probes on held-out slices. Collateral, sampling, and penalties SHALL be calibrated and load-tested so the expected cost of a fraudulent checkpoint exceeds honest execution for F1/F2, with ambiguous evidence held rather than auto-paid. F3 SHALL remain experimental until its acceptance checks are separately specified.

#### Scenario: fraudulent checkpoint evidence is not paid
- **WHEN** independent verification detects inconsistent artifact, loss, execution, or evaluation evidence
- **THEN** payment is held or disputed, the evidence is retained, and no passing checkpoint is minted

### Requirement: Goals and gates structure training acceptance and bonus payment
A training request SHALL bind a shared Goal plus immutable base checkpoint terms and optional gate bonuses. Base settlement SHALL depend only on verified scheduled checkpoints; each bonus SHALL release only after its frozen machine gate passes, and a gate failure SHALL not retroactively erase earned base payment.

#### Scenario: base and bonus settle independently
- **WHEN** all required checkpoints verify but an optional outcome gate fails
- **THEN** base payment settles under the checkpoint oracle while that gate's bonus remains unpaid or refunded

### Requirement: Capability minting enforces license and provenance before publication
A completed training run SHALL invoke data commons' manifest/license validation contract at admission and mint, then mint exactly `{weights_uri, weights_hash, base_model, training_provenance, license}` only after required gates pass. The immutable capability SHALL immediately be priceable as an inference instrument, referenceable by any commons node or branch, and serveable by any authorized host that pulls and verifies the weights. Training owns invocation and mint enforcement; data commons owns registry resolution and restriction composition.

#### Scenario: Llama-derived output retains named terms
- **WHEN** a run uses a registered Llama-community input and otherwise compatible data
- **THEN** the minted capability carries the composed share-alike and named-redistribution restrictions

### Requirement: Wave 1 data is buyer-supplied by immutable reference
F1/F2 Wave 1 requests SHALL take buyer-supplied data as a URI plus content hash recorded in training provenance and SHALL not list, resell, price, or transfer those datasets as marketplace assets. Access SHALL be scoped to the run and revoked or expired under declared terms. Dataset licensing, deduplication, contamination, and registry semantics remain owned by `data-commons`, not swallowed into the training-market capability.

#### Scenario: Wave 1 does not create a dataset listing
- **WHEN** a buyer supplies a private admitted manifest for one training request
- **THEN** the run may access it under scope, but no public dataset offer or ownership transfer is created
