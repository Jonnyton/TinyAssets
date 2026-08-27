## Why

Inference, training, task, and fabrication supply is heterogeneous and perishable, so a single “compute price” or nominal unit-price sort would misroute work. TinyAssets needs one interoperable, non-custodial quote-discovery contract that publishes the best currently executable total under the requester’s policy while keeping external hosted prices reference-only and leaving each lane’s execution protocol intact.

## What Changes

- Define a versioned stable capability descriptor, normally embedded in existing requests and offers, while keeping exact quantity/location/window terms in the existing demand intent and binding resolved compatibility into a firm quote.
- Define one canonical signed quote provenance envelope for indicative references and expiring firm native offers, including exact capability/demand, issuer/adapter origin, units, currency, component coverage, canonical fee version, verified provider eligibility, freshness, and domain-owned fenced-capacity facts.
- Publish a separate price surface for each substitutability class: settled VWAP, lowest executable native ask, external hosted-provider ceiling, and field-level freshness/sample/confidence state. There is no global compute scalar.
- Rank only eligible candidates by deterministic landed monetary total in one currency under the requester’s hard constraints or explicit versioned service-utility objective, expose rejection reasons, and forbid silent substitution, hidden platform purchasing, or automatic movement from free/BYOC to paid fulfillment.
- Keep external provider adapters read-only and price-only in this phase. User-owned upstream accounts, seller-bundled resale, proprietary-model instruments, secondary/cash-settled capacity, and F3 swarm execution remain separately gated.
- Keep economic discovery separate from provider role/health routing and from the domain-native execution contracts for interactive inference, batch work, training, bounties, and fabrication.
- Keep public surfaces aggregate-only and tenant-private evaluations, quotes, commitments, capacity grants, and receipts non-enumerable, tenant-bound, retention-governed, and revocation-aware.

## Capabilities

### New Capabilities

- `paid-market-price-index-and-forwards`: Refines the build-forward umbrella’s proposed live-price slice into the successor contract for capability descriptors, quote provenance, per-class price surfaces, reference ceilings, and deterministic executable-total discovery.

### Modified Capabilities

- None.

## Impact

- Planning only: no runtime, schema, MCP/API, provider, credential, settlement, or deployment behavior changes in this proposal.
- Future implementation will consume the single authenticated logical-accounting transport from `paid-market-economy`, the required wallet/chain-effect successor from `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6 and its verified receipts, the outbound boundary authority/receipt successor, identity/tenant authority, domain facets and fenced capacity from the training/hardware/task owners, distributed-execution evidence, and provider identity/credential-class receipts without modifying the provider role router.
- Executable purchase and paid price observations remain gated on those owners, the matching verified wallet/chain receipt from `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6, opposite-provider review, strict security/concurrency/load proof, and explicit rollout approval. Reference adapters and public reads remain blocked until their applicable boundary, privacy, and identity dependencies land.
