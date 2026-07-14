# Paid Market: Training Market (Fine-Tuning to Pretraining)

## Purpose

Close the harness-to-hardware gap so users design, train, and OWN their own
models. Structurally the training market is the capacity-forward machinery with a
different instrument (device-hours of a hardware class, not tokens) and a
different settlement rhythm (per verified checkpoint, not once at window end).
The hardened forward properties carry over unchanged: exact conservation,
pro-rata payment with threshold-gated slashing only, demand-relative obligation
so buyer cancellation cannot grief sellers, and slash-to-buyer never treasury.

Historical source of record (untouched): `docs/exec-plans/active/2026-07-08-track-f-training-market.md`.
Settlement math (implemented, invariants inherited from the adversarially-reviewed forwards core): `tinyassets/paid_market/training.py`.
Depends: Track E Waves 3–4 (price index, capacity forwards, escrow/collateral machinery).

## Requirements

### Requirement: Training reuses the hardened forward properties unchanged

The system SHALL enforce, for training settlement, the same four hardened
properties proven in the forwards core: exact conservation, pro-rata payment with
threshold-gated slashing only, demand-relative obligation (so buyer cancellation
cannot grief sellers), and slash-to-buyer never treasury. These SHALL be enforced
in code with a conservation sweep, not merely asserted in prose.

#### Scenario: buyer early-cancel with all reached checkpoints verified pays in full
- **WHEN** a buyer cancels early and every checkpoint reached is verified
- **THEN** the seller is paid in full — the window was reserved (the B-1 lesson applied to training)
- **AND** conservation holds exactly

### Requirement: Three-tier instrument ladder with a democratization tier that never blocks the base

The instrument key SHALL be `hardware class × interconnect tier × gang size ×
window`. Tier F1 (single-node fine-tune windows) SHALL ship first. Tier F2
(colocated pretraining gang windows) SHALL sell all-or-nothing — a gang has no
partial-fill path. Tier F3 (swarm pretraining) SHALL ship behind its own flag and
SHALL never block F1/F2.

#### Scenario: a gang window has no partial-fill path
- **WHEN** an F2 gang window cannot be fully allocated
- **THEN** it does not partially fill (partial allocation of a gang is worthless)
- **AND** the state machine offers no partial-fill transition

#### Scenario: F3 swarm stays flag-gated and non-blocking
- **WHEN** the F3 swarm tier is experimental or disabled
- **THEN** F1 and F2 continue to operate unaffected

### Requirement: Checkpoint-based settlement (implemented)

`settle_training_window` SHALL compute `seller_gross = total × (contracted −
unserved) / contracted` where `unserved = scheduled − verified`; the refund SHALL
be the exact remainder; slashing SHALL apply pro-rata to `unserved/contracted`
ONLY when `verified/scheduled` falls below the threshold (training default 100%,
tunable per instrument class). A checkpoint SHALL count as verified only when it
is delivered AND attestation-passed. Escrow releases MAY be streamed per
checkpoint, and the module SHALL compute the end-state the stream must sum to.

#### Scenario: a missed checkpoint below threshold triggers pro-rata slashing
- **WHEN** `verified/scheduled` falls below the instrument's threshold
- **THEN** collateral is slashed pro-rata to `unserved/contracted`
- **AND** the refund is the exact remainder, conserving to the penny

### Requirement: Verification prices fraud above honest work

Checkpoints SHALL be verified by layered cheaper signals — artifact attestation
(weights hash + optimizer-state hash chained to the prior checkpoint),
loss-curve continuity, spot re-execution of randomly sampled short segments, and
eval probes on held-out slices. The settlement math trusts verified counts; the
attestation layer SHALL make them trustworthy (the explicit trust boundary,
review finding B-5). F3 SHALL remain flagged experimental until its acceptance
checks are specified.

#### Scenario: a fraudulent checkpoint is priced above honest work
- **WHEN** a seller submits a checkpoint that does not plausibly descend from its parent
- **THEN** the layered signals flag it and it is not counted as verified
- **AND** faking it costs more than doing the work honestly for F1/F2

### Requirement: Gates are the native training abstraction

A training run SHALL bind to a goal; eval benchmarks SHALL be its gate ladder;
checkpoints SHALL claim gates with eval evidence. Buyers MAY structure payment as
base (per-checkpoint) plus bonus (per-gate) using the existing `gates` machinery
(`define_ladder` / `claim` / `stake_bonus`) — coupling, not new machinery.

#### Scenario: payment structures as base plus gate bonus
- **WHEN** a run binds to a goal with a gate ladder
- **THEN** checkpoints claim gates with eval evidence
- **AND** the buyer can pay base per checkpoint and bonus per gate via existing gates

### Requirement: Capability minting closes the loop with license propagation enforced at mint

A completed run SHALL mint a new capability `{weights_uri, weights_hash,
base_model, training_provenance, license}`. License propagation SHALL be enforced
at mint (Llama-derived weights carry Llama terms; Apache/MIT bases mint freely).
The minted capability SHALL immediately be a priceable inference instrument on
the Track E market, referenceable by any commons node/branch, and serveable by
any host that pulls the weights.

#### Scenario: a Llama-derived model carries Llama terms
- **WHEN** a run trains from a Llama-licensed base
- **THEN** the minted capability's license carries the Llama terms
- **AND** an Apache/MIT base mints freely

### Requirement: Data is buyer-supplied in Wave 1 (scoped deliberately)

Wave 1 SHALL take data as buyer-supplied URIs with a content hash in provenance —
the market moves compute, not datasets. A data marketplace is its own track and
SHALL NOT be swallowed into Track F.

#### Scenario: Wave 1 does not become a data marketplace
- **WHEN** a Wave 1 run needs data
- **THEN** the buyer supplies a URI plus content hash recorded in provenance
- **AND** dataset licensing/dedup/contamination is out of scope for this track

## Open founder decisions

- **Training slashing threshold** (Track F §2): the default `verified/scheduled`
  slashing threshold is 100% (one missed checkpoint in a coarse schedule already
  matters) but is tunable per instrument class — the per-class default set is a
  founder decision.
- **F3 swarm acceptance checks** (§1 F3, §3): the verification and coordinator
  design for swarm pretraining are research-adjacent; F3 stays flag-gated and
  experimental pending a research review (F-W3 gate) before its acceptance checks
  are pinned.
