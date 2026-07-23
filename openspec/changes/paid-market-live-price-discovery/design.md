## Context

The `build-forward-platform-capabilities` umbrella delegates its removed price-index/forward delta to this narrower successor. Draft PR #1542 owns the prerequisite authenticated market transaction/migration transport. PR #1574 compared TinyAssets with current inference aggregators, general-compute schedulers, DEX/RFQ systems, model registries, task protocols, and fabrication standards.

The recurring failure mode is false fungibility. An input token on one model/runtime/privacy envelope is not interchangeable with another; an accelerator-hour without topology and interruption terms is not an executable training quote; and a fabrication unit price without material, inspection, tooling, shipping, and lead time is not a landed quote. The common boundary is quote discovery and provenance, not one execution state machine.

The current fail-closed activation constraint—recorded by the live P0 STATUS concern for #1582 and proposed for PLAN ratification in still-open PR #1574—is that the platform is a control, discovery, routing, evidence, and settlement plane: it does not provide another user's compute, spend maintainer model quota, custody upstream credentials, or silently buy service. This change treats that constraint as a dependency and does not claim the pending PLAN amendment has landed. The user first chooses free, BYOC, or paid fulfillment. Economic routing begins only inside the chosen authority.

## Goals / Non-Goals

**Goals:**

- Define the minimum versioned descriptor needed to compare demand with heterogeneous supply.
- Publish honest per-class price surfaces and a deterministic best currently executable total under explicit policy.
- Let native/community supply compete below public hosted-provider reference ceilings.
- Preserve exact origin, freshness, fees, eligibility, capacity-lock, and rejection evidence.
- Keep quote discovery interoperable while inference, batch, training, bounty, and fabrication execution remain domain-native.
- Keep the economic router separate from provider role/health routing and from settlement authority.

**Non-Goals:**

- Executing, reserving, or settling an external hosted-provider route.
- Storing or using a requester’s upstream credential on the platform.
- Seller-bundled upstream resale, proprietary-model instruments, cash settlement, secondary capacity trading, AMMs, bonding curves, or F3 swarm training.
- Creating a universal job protocol, a global compute-price scalar, or new public MCP actions.
- Enabling market purchases, schemas, routes, or migrations in this planning change.
- Replacing the Wave 2 transaction transport, domain acceptance gates, or provider R2-1 authority/receipt work.

## Decisions

### 1. One embedded capability descriptor, not a new object graph

Existing demand, offer, claim, artifact, gate, and settlement primitives remain authoritative. A versioned `CapabilityDescriptor` is embedded in requests and offers and hashed into firm quotes. Its common envelope identifies stable lane/supply/output identity, immutable resource/runtime revisions, unit semantics, region/privacy/reliability capabilities, and an extensible typed facet map.

Inference facets identify model revision, runtime, quantization, context capability, modalities, structured/tool support, latency/throughput class, and token categories. Training facets identify accelerator class/memory, supported topology/interconnect, runtime/container support, interruption, and attestation classes. Fabrication facets identify supported process/material/tolerance/size, inspection/certification, and service-region classes. Exact request quantity, dimensions, destination, requested window, gang count/topology, deadline, lead time, checkpoint, restart, and similar terms stay in `DemandIntent`; offers declare ranges/sets and the firm quote binds the resolved terms. The owning domain validates its facets; the price index does not redefine them.

Alternative considered: distinct cross-market tables and MCP actions for every lifecycle noun. Rejected because most nouns are roles around existing primitives and would create a second execution platform.

### 2. Indicative and firm quotes are different authority classes

Every quote records quote identity, descriptor/demand digests, origin adapter, issuer, unit semantics, one settlement currency, priced-component coverage/missing fields, canonical fee schedule/version, landed monetary total, verified provider-eligibility facts, observation/issue time, expiry, and terms digest. An indicative quote is browseable and nonbinding. A native firm quote additionally binds authenticated issuer and tenant, nonce, signature domain, exact quantity, offer version, and an immutable domain capacity grant/fence.

The complete authority-bearing record uses a versioned domain-separated canonical encoding, rejects unclassified fields, and is verified against an enrolled revocable issuer key with explicit algorithm/key id/rotation/revocation. Derived totals and canonical bytes are server-recomputed. Only a verified, unexpired firm quote backed by conserved, unconsumed domain capacity is executable; mutable rows may only narrow authority. A catalog listing or reference observation is never promoted to executable status by ranking.

Alternative considered: treat the newest catalog price as executable. Rejected because catalog freshness proves neither capacity nor authority.

### 3. External hosted providers are reference ceilings only in this phase

Read-only commons adapters may publish public hosted-provider prices with exact source, terms, region, resource envelope, currency, component coverage/missing fields, and freshness. They cannot receive credentials, reserve capacity, execute, claim, or settle. A complete comparable output may appear as an external reference ceiling beside executable native supply; incomplete output remains a partial reference.

A future requester-owned/BYOK route may let a user invoke their own upstream account outside TinyAssets market accounting. Seller-bundled resale needs a separate legal, credential-authority, abuse, invoice, and receipt design. Neither is inferred from price discovery.

Alternative considered: make OpenRouter-like upstreams executable immediately. Rejected because public price discovery does not establish credential ownership, contractual authority, custody, or settlement truth.

### 4. Price is a field-fresh surface per substitutability class

Each exact descriptor class publishes separate fields for raw dispute-cleared native VWAP, lowest executable native ask, external hosted-provider reference/ceiling, and a canonical composite index. Every field carries its own source set, `observed_at`, `valid_until`, sample count, verified economic-principal count, component coverage, and confidence/manipulation state. Missing, stale, unsupported, partial, and zero-volume values remain explicit null/caveat states; a fresh field does not refresh unrelated fields. External references never mutate raw native settlement truth or enter executable ranking. Only a complete, current, valid all-in ceiling may bound the named composite index to `min(raw_native_vwap, ceiling)` with raw, ceiling, and clamp state retained; partial, stale, or invalid references never clamp.

Inference normalizes input/output/cached-token components and landed request total. Training normalizes priced device/accelerator windows, topology premiums, checkpoint/recovery, interruption expectation, data movement, and landed job total. Fabrication exposes priced tooling, material, per-unit, inspection, and shipping in a landed total. Task/bounty price remains the funded amount for a machine-gated accepted outcome. Service attributes remain hard constraints or an explicit versioned requester-weighted objective; cross-currency comparison is refused without a separately approved bound FX oracle.

Alternative considered: publish one market-wide compute midpoint. Rejected because it is not executable and invites hidden substitution between unlike resources.

### 5. Deterministic routing starts after the user’s fulfillment choice

The user chooses free queue, BYOC, or paid market; the platform does not silently move between them. Inside the selected paid/BYOC authority, the economic router:

1. validates immutable artifacts, licenses, privacy, descriptor version, and substitutability;
2. filters candidates that fail hard constraints or authority;
3. computes a landed monetary total in one settlement currency from priced components and the exact canonical fee version;
4. deterministically ranks eligible executable candidates with a stable tie-break;
5. returns the winning quote plus every material rejection reason; and
6. requires a later explicit reservation/purchase transition before execution.

Latency, reliability, lead time, topology, privacy, and acceptance remain hard constraints or use requester-selected versioned utility weights recorded in the receipt; the router invents no monetary value for them. The output never substitutes a cheaper model, topology, region, privacy class, or acceptance profile that the requester did not authorize.

The router and Wave 2 matcher have disjoint scopes. Discovery compares fulfillment lanes and capability-compatible quote envelopes and returns a routing/evaluation receipt; it never allocates hosts or fan-out slots. If the chosen path is a native paid route, the `paid-market-track-e-wave-2-transport` workflow revalidates each selected native firm quote and binds it to one request-scoped bid. Wave 2 then runs the canonical `best_execution` matcher only across those admitted bids for that request/path and atomically claims the resulting host/slot allocation. A direct explicitly paid request may enter Wave 2 without cross-lane discovery, but Wave 2 never performs silent lane substitution. A quote id/version/digest and its derived bid id/version remain linked in both receipts so the two deterministic decisions cannot masquerade as one another.

Alternative considered: optimize nominal unit price or automatically purchase the cheapest route. Rejected because both hide total cost and exceed the requester mandate.

### 6. The economic router does not become the provider router

Provider role/health routing chooses a writer or evaluator based on runtime role, availability, privacy, and policy. Economic discovery compares already-described market/BYOC capacity. It may later consume the provider attempt receipt identity and credential class, but it does not mutate fallback chains, resolve secrets, create capacity authority, lock money, or treat provider health as payment authority. The domain owner creates/fences capacity and alone produces the semantic completion-acceptance verdict under its native gates. `paid-market-economy` owns the request lifecycle transition and logical budget/accounting intent but may advance `completed` to accepted/auto-accepted only from that bound domain verdict plus the requester action or policy allowed by that domain; it never invents domain acceptance. The wallet/chain-effect successor defined in `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6 remains the sole wallet/chain-effect authority; discovery only evaluates and revalidates. A paid settlement becomes a price observation only after the logical-accounting result, domain acceptance evidence, and independently verified receipt from that architecture-defined successor agree on tenant/universe-scoped settlement identity, fence-bound accepted-result identity, parties, currency/token/chain, and gross/net/fee amounts under the successor's finality/reorg policy. Wallet/chain mismatches route only through that successor's reconciliation, never a domain delivery dispute.

Similarly, the commercial envelope does not replace execution: interactive inference uses a streaming contract; market-selected repo/source jobs enter the fenced B2 lease protocol; training uses checkpoint/evaluation acceptance; bounties use first verified machine gates; fabrication uses work-order, inspection, delivery, cure/rework, and rejection states.

Alternative considered: one universal market worker protocol. Rejected because the delivery and cancellation semantics are materially different.

### 7. Discovery produces a reproducible, privacy-minimal receipt

Each tenant-private evaluation records opaque tenant-keyed descriptor/policy commitments, objective version/weights, candidate quote IDs/versions, field freshness, eligible/rejected status and reason codes, selected quote, monetary-total/service-attribute breakdown, and evaluation time. It excludes prompts, datasets, CAD, private endpoints, credentials, and private demand details. Receipts are non-enumerable, owner/admin/auditor scoped, retention/hold/deletion governed, and never exposed through public aggregate reads. The receipt is evidence of ranking, not proof of reservation, execution, acceptance, invoice, or settlement.

Alternative considered: retain only the winner. Rejected because route disputes, manipulation review, and deterministic replay require the considered snapshot and reasons.

### 8. Manipulation and scale controls are part of discovery correctness

Settled observations aggregate by a verified economic-principal root (payout/funding, legal-entity, or common-operator linkage), not merely account or counterparty pair, so split offers cannot manufacture owner diversity. Unknown linkage is excluded or conservatively downweighted. Discovery only consumes the transaction owner's classification: exact same-owner requester/host observations must carry `self_hosted_zero_fee` and never enter paid-market price formation. Broader linked-party paid observations cannot manufacture breadth: their volume is excluded or downweighted and their recorded ordinary fee remains visible unless the transaction owner applied that exact self-host exemption. Thin or concentrated samples publish low confidence rather than a false price. Adapters fail independently; one stale source does not erase fresh native fields. Public reads are bounded and cacheable by descriptor digest, while tenant-private receipts/quotes/locks use composite tenant keys and firm-quote eligibility is revalidated against current authority, offer version, expiry, and capacity. Matching is capability-sharded and event-driven; no router poll-scans every host.

Alternative considered: unqualified last-price or AMM liquidity. Rejected because perishable heterogeneous capacity cannot be made honest by a fungible curve.

## Risks / Trade-offs

- **[Risk] Descriptor facets become a frozen taxonomy.** → Version the envelope, keep domain facets extensible and owner-validated, and require immutable revisions only where settlement/substitutability needs them.
- **[Risk] Reference ceilings look purchasable.** → Label authority class and executable state explicitly; price-only adapters cannot return routes or capacity locks.
- **[Risk] Cheapest nominal supply wins despite retry or movement cost.** → Rank expected all-in total and expose the component breakdown and objective version.
- **[Risk] A stale firm quote double-sells capacity.** → Short expiry, signed nonce, offer version, capacity-lock identity, and atomic revalidation before a later reservation.
- **[Risk] Public demand leaks sensitive work or this change silently decides the private-storage dispute.** → Match on the minimum descriptor/policy envelope and tenant-keyed digests; under PR #1574's Commons-first research assumption, private payloads remain requester/authorized-execution-host-resident. This change stores only opaque commitments and market/evidence facts and does not decide whether the platform may store private blobs; that remains the STATUS `Resolve target-spec PLAN conflicts` host decision.
- **[Risk] Low-entropy digests expose private demand.** → Use tenant-keyed opaque commitments, private ACLs/non-enumerable ids, explicit retention/hold/deletion, and aggregate-only public surfaces.
- **[Risk] Seller compliance labels become routing authority.** → Intersect workload/org constraints only with signed/verified provider, contract, subprocessor, region, retention, incident, and attestation facts; fail closed when none qualify.
- **[Risk] Mixed currencies or service attributes create hidden exchange rates.** → Use one settlement currency per ranking run; no FX without a versioned oracle; service quality stays a hard constraint or explicit requester-weighted objective.
- **[Risk] One shared envelope erases domain semantics.** → Share only quote/provenance fields; each lane retains its own descriptor facets, execution, evidence, acceptance, and settlement owners.
- **[Risk] Physically delivered capacity forwards are mistaken for categorically unregulated products.** → Physical delivery, collateral, no secondary transfer, and no cash settlement are product boundaries, not a legal safe harbor. Before any jurisdictional activation, specialist counsel must document the applicable [CFTC/SEC facts-and-circumstances forward-contract-exclusion analysis](https://www.cftc.gov/LawRegulation/FederalRegister/finalrules/2015-11946.html)—including actual delivery, commercial intent, non-severable optionality, and the purpose of any volume variation—and applicable commodities, derivatives, securities, consumer, and money-transmission rules.
- **[Risk] Export-control eligibility becomes a false legal conclusion.** → The [May 2025 BIS AI-training policy statement](https://www.bis.gov/media/documents/ai-policy-statement-training-ai-models-may-13-2025) identifies narrower transaction/end-user/end-use and knowledge-based EAR triggers, not a blanket AI-training ban or classification oracle. Provider facts and policy profiles may fail closed, but advertised training/hardware routes require current specialist export-control review; the platform does not certify legality from a self-reported label.
- **[Trade-off] External references are initially non-executable.** → This delays one-click upstream routing but preserves the no-custody/no-hidden-purchase boundary until authority and legal terms are explicit.

## Migration Plan

1. Land the Wave 2 transport proposal as the single transaction/migration owner; the build-forward umbrella has delegated and removed its price-index delta.
2. Obtain opposite-provider review of this successor against PR #1574 sources and TinyAssets context; resolve blocking findings before implementation.
3. Land the applicable outbound boundary authority/receipts successor, tenant identity/isolation, provider R2-1 receipts, distributed-execution/domain capacity authority, and Wave 2 money transport before their dependent adapter/public/executable tasks.
4. In a later apply lane, add pure descriptor/quote models and deterministic evaluation with unit/property/mutation tests, keeping all adapters and routes dark.
5. Add read-only external reference adapters and native indicative asks behind a default-off flag only after boundary/privacy dependencies; prove independent failure, staleness, provenance, and bounded aggregate public reads.
6. Add native signed firm quotes only after domain owners can create/fence tenant-bound capacity and Wave 2 can bind budget; discovery itself never reserves either.
7. Prove capability-sharded concurrency, tenant isolation, manipulation resistance, no-host honesty, live canaries, rendered-chatbot behavior, and post-fix clean-user evidence before public activation.
8. Sync and archive only after the implemented behavior and rollout evidence exist; otherwise retain this as an active forward contract.

Rollback before activation is removal of the dark route/flag with no data or money migration. After activation, quote observations and evaluation receipts remain immutable evidence; disabling publication or execution does not rewrite them.

## Open Questions

- Exact public presentation and jurisdictional availability remain downstream money-product decisions; a ranking run still binds one settlement currency, canonical fee version, and every priced component.
- Native inference streaming, training reservation, and fabrication work-order schemas each need their own successor changes before executable routing.
- User-owned/BYOK upstream execution and seller-bundled hosted-provider resale remain separate host-approved designs.
- Private-payload/platform-storage posture remains gated by the STATUS `Resolve target-spec PLAN conflicts` host decision; this change authorizes only opaque commitments and bounded market/evidence facts.
