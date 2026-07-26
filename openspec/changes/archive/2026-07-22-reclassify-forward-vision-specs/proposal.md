## Why

Eight files were copied into the canonical OpenSpec tree as forward architecture even though canonical specs are required to describe landed behavior. They mix tested pure helpers, draft SQL, unbuilt transports, and several claims contradicted by `main`, so readers cannot tell what TinyAssets actually guarantees.

## What Changes

- **BREAKING** Remove the eight forward-heavy canonical capabilities instead of presenting their unbuilt end-to-end behavior as shipped.
- Expand `paid-market-economy` with the exact, library-only contracts implemented by `tinyassets/paid_market/`, including its limitations and current pair-based manipulation cap.
- Introduce `external-effect-receipts` for the shipped consent, reservation, reconciliation, and terminal-receipt behavior that the old boundary spec only partially represented.
- Preserve every removed target requirement under the separate active change `build-forward-platform-capabilities`; removal from canonical truth is not cancellation.
- Record requirement-by-requirement BUILT / PARTIAL / FUTURE / CONTRADICTED evidence in the dated reconciliation audit.

## Capabilities

### New Capabilities

- `external-effect-receipts`: Current per-sink consent and external-write receipt lifecycle, including caller-supplied idempotency hints and the absence of whole-batch atomicity.

### Modified Capabilities

- `paid-market-economy`: Replace a generic package-level claim with explicit pure computation contracts for pricing, forwards, training, licenses, pools, fabrication, shuttles, funds, matching, and ledger entries.
- `boundary-layer`: Remove forward connectivity, adapter, inbox, and idealized exactly-once requirements from canonical truth.
- `data-commons`: Remove the unbuilt dataset marketplace and Dataset Forge requirements from canonical truth.
- `demand-side`: Remove the unbuilt standing-goal, onboarding, bounty, and service-volume requirements from canonical truth.
- `hardware-creation`: Remove the unbuilt hardware product lifecycle while retaining its shipped arithmetic in `paid-market-economy`.
- `paid-market-price-index-and-forwards`: Remove unbuilt live transport and quote-market behavior while retaining shipped oracles in `paid-market-economy`.
- `paid-market-training`: Remove unbuilt training-market lifecycle while retaining shipped settlement and license oracles in `paid-market-economy`.
- `pooled-training-ownership`: Remove unbuilt persistence and ownership behavior while retaining shipped apportionment math in `paid-market-economy`.
- `token-architecture`: Remove contradicted launch-policy claims while retaining safe treasury-internal arithmetic in `paid-market-economy`.

## Impact

This changes specifications and coordination artifacts only; it does not change runtime behavior or public APIs. The canonical tree becomes truthful to `main`, the active future change becomes the sole owner of the removed target behavior, and focused paid-market and external-receipt tests provide implementation evidence.
