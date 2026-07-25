> **Partial release, 2026-07-25 (umbrella tasks 3.1 non-monetary half and 3.2).**
> Four requirements were **physically moved** out of this delta into
> `openspec/changes/data-commons-contribution/`, the successor that now owns the
> non-monetary contribution half: *Dataset assets are content-addressed reference
> manifests*, *Data commons owns fail-closed manifest and license validation*,
> *Contamination, privacy, and quality gates precede gate-backed use*, and
> *Dataset Forge is a provenance-preserving commons workflow* (each restated
> there in the successor's own terms, and re-expressed as commons-entry behavior
> per the host's 2026-07-25 framing of the commons as an OKF system anyone can
> write to). They were moved rather than copied so each requirement keeps exactly
> one active owner — the granularity the ownership convention in `proposal.md`
> is stated at. It otherwise follows the release pattern of umbrella tasks 1.1,
> 1.2, and 2.1.
>
> The two requirements below stay with the umbrella because both are value
> movement and both need D3's single transaction transport: pricing modes consume
> escrow and revenue-share legs, and contributor settlement is exact
> apportionment. Neither is required for a downstream consumer to *admit* a
> manifest, which is the seam the split was made on — **admission is
> non-monetary; consideration is monetary.** So the `data-commons` capability has
> two active owners split disjointly **by requirement** — never two owners of one
> requirement.

## ADDED Requirements

### Requirement: Dataset pricing is explicit and independent of compute pricing
Dataset offers SHALL declare one of the three seller-chosen modes from the target design: free with attribution and provenance recording; a flat per-run license fee locked when training starts and released only on completion through the standard escrow transport; or realized-revenue share using declared `data_ppm` as an additional exact attribution leg. Data consideration SHALL remain separate from compute price and platform fee.

#### Scenario: a per-run license fee follows training escrow
- **WHEN** a run admits a dataset under the flat per-run mode
- **THEN** the fee is locked at training start, released only on the declared completion outcome, and otherwise follows the frozen refund rule

#### Scenario: revenue-share data earns only on realized model revenue
- **WHEN** a derivative capability records an attributable paid revenue event
- **THEN** the dataset share is apportioned from that event under the frozen terms, while unrealized valuation creates no payout

### Requirement: Contributor settlement is frozen, exact, and auditable
A collaborative dataset SHALL freeze contributor identities, accepted contribution weights, and payout terms in its version manifest. An annotation campaign SHALL be modeled as a Goal with machine gates, and accepted gated work SHALL become the contributor's share weight. Revenue and campaign payments SHALL use deterministic exact apportionment whose shares conserve the input and whose tie-breaking is recorded.

#### Scenario: contributor payouts conserve exactly
- **WHEN** a dataset revenue event is distributed across its frozen contributors
- **THEN** integer payouts sum exactly to the distributable amount and reproduce from the manifest and event alone
