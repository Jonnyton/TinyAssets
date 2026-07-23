## Why

The full-platform architecture still calls for outbound connectivity, data and demand commons, and paid production markets, but those targets are not landed behavior and therefore cannot remain in canonical `openspec/specs/`. This active change preserves the intended outcomes while making their implementation and verification status explicit.

## What Changes

- **HARD DEPENDENCY:** This change MUST NOT be applied, synced, or archived until `reclassify-forward-vision-specs` has landed, physically removed the eight old canonical capability directories, passed strict validation, and archived.
- Build an outbound boundary with resource-ledger grants, action caps, credential-blind adapters, durable inboxes, typed artifacts, and batch-safe external effects.
- Build first-class dataset assets, provenance, licensing enforcement, quality gates, contribution accounting, and Dataset Forge workflows.
- Build standing-goal demand, onboarding outcomes, and goal-bounty market composition before introducing direct universe services.
- Build the verified design-to-fabrication hardware ladder on top of commons artifacts, gates, and paid-market primitives.
- Delegate replacement of direct accounting side paths, schema history, and the single versioned logical-accounting transaction transport to `paid-market-track-e-wave-2-transport`; preserve its single-path guarantee without treating database accounting as proof of wallet funding or chain settlement. Delegate live price/forward quote surfaces, order lifecycle, caps, collateral, and privacy controls to `paid-market-live-price-discovery`.
- Build F1/F2 training instruments, attestation, checkpoint release, gates, mint/license enforcement, and buyer-data provenance; keep F3 research-gated.
- Build persisted pooled-training ownership and revenue lifecycles without secondary transfers in v1.
- Introduce any public TINY/stablecoin architecture only behind legal, security, and launch gates, preserving the separation from settlement until those gates pass.

## Capabilities

### New Capabilities

- `boundary-layer`: Outbound connections, adapters, inboxes, typed artifacts, caps, and end-to-end effect guarantees.
- `data-commons`: Dataset assets, provenance, pricing, quality gates, contribution settlement, and Dataset Forge.
- `demand-side`: Standing goals, binding onboarding outcomes, goal bounties, and the measured gate for later universe services.
- `hardware-creation`: Verified design-to-silicon and physical-fabrication product workflows.
- `paid-market-training`: Training instruments, verification, checkpoint payment, gate integration, capability minting, and input provenance.
- `pooled-training-ownership`: Persisted funding, frozen lineage ownership, refunds, and revenue distribution.
- `token-architecture`: Counsel-gated public token, valuation, liquidity, and mint/redemption behavior.

### Modified Capabilities

- None in this umbrella. `paid-market-track-e-wave-2-transport` is the sole successor owner of the released `paid-market-economy` transaction delta.

## Impact

This is an active, unimplemented cross-platform change and is blocked on the completed canonical reclassification. It will affect MCP/HTTP surfaces, identity and credential boundaries, SQLite migrations, paid-market transports, commons workflows, gates, provenance, deployment flags, legal review, and the complete-system concurrency/load proof. It depends on authenticated distributed execution for execution evidence and rollout authority but owns market behavior separately. `paid-market-track-e-wave-2-transport` is the sole successor owner for the released logical-accounting transaction delta, and `paid-market-live-price-discovery` is the sole successor owner for the removed price-index/forward delta; each must preserve its delegated umbrella invariants before it can sync or archive. Real-fund wallet and chain effects remain owned by the required separately reviewed §18.6 successor.
