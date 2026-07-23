## ADDED Requirements

### Requirement: Capability descriptors define substitutability without defining execution
The market SHALL bind every demand intent, native offer, and quote to a versioned capability descriptor whose canonical digest identifies stable supply/output identity, immutable resource/runtime revisions, unit semantics, and policy/evidence classes required to decide substitutability. Inference descriptors SHALL cover model revision, runtime, quantization, context capability, modalities, structured/tool support, token categories, latency/throughput class, region coverage, privacy, and reliability class. Training descriptors SHALL cover accelerator class/memory, supported topology/interconnect, container/runtime support, interruption class, region coverage, privacy, and attestation class. Fabrication descriptors SHALL cover supported process/material families, tolerance/size capabilities, inspection/certification class, and service-region coverage. Exact request quantity, dimensions, destination, requested window, gang size/count/topology, deadline, lead time, checkpoint cadence, restart terms, and similar demand-specific values SHALL remain in the existing demand intent digest; offers SHALL declare compatible ranges/sets, and the firm quote SHALL hash the resolved demand/offer terms. Domain owners SHALL validate their facets; the descriptor SHALL NOT replace their execution, acceptance, or settlement protocols.

#### Scenario: incompatible supply is not substituted
- **WHEN** an offer differs from a hard descriptor facet such as model revision, topology, region, privacy class, material, or tolerance
- **THEN** the offer is ineligible for that demand intent
- **AND** the router records the exact mismatch instead of treating a lower price as substitutable

#### Scenario: unsupported descriptor version fails loud
- **WHEN** a reader cannot validate the descriptor schema version or required lane facets
- **THEN** it returns an unsupported-descriptor result
- **AND** it publishes no executable quote or route for that descriptor

#### Scenario: demand terms resolve against supply ranges
- **WHEN** exact requested quantity, location, window, topology, or lead time falls inside an offer's declared compatible range or set
- **THEN** compatibility is evaluated without creating a new capability identity for every request
- **AND** the resolved terms are bound into the firm quote and demand digest

### Requirement: Settlement records normalized delivery evidence
The price index SHALL consume immutable accepted settlement observations emitted jointly by the `paid-market-economy` logical-accounting owner, the required §18.6 wallet/chain-effect successor, and the domain execution owners; it SHALL NOT create or mutate settlement truth. A paid settlement SHALL NOT become an accepted price observation until its logical-accounting result, domain acceptance evidence, and independently verified §18.6 wallet/chain receipt agree on the same settlement identity and amount. A new-version inference observation SHALL carry integer `tokens_in`, integer `tokens_out`, applicable integer cached-token counts, integer `unit_price_micros_per_mtok`, the capability descriptor digest, accepted evidence digest, verified chain-receipt digest, and canonical fee schedule/version. Existing v1 settlement records SHALL remain byte-for-byte unchanged, and any new observation shape SHALL use a schema-version bump. Training, task, and fabrication observations SHALL retain their domain-native delivered units and accepted evidence digest rather than translating them into tokens. Missing, mismatched, or implausible delivery or wallet/chain evidence SHALL fail loud or enter the domain dispute path and SHALL NOT silently produce a final paid price observation.

#### Scenario: inference completion without counts is rejected
- **WHEN** an inference completion omits required normalized token evidence
- **THEN** the price index rejects ingestion and publishes no null-count settlement observation or derived price
- **AND** completion acceptance and funds movement remain exclusively controlled by the domain owner and `paid-market-economy`

#### Scenario: non-inference work keeps its native units
- **WHEN** accepted training, task, or fabrication work becomes a market observation
- **THEN** the observation retains the domain-native units, descriptor, and acceptance evidence
- **AND** it is not converted to a fictitious token price

#### Scenario: price index cannot rewrite settlement truth
- **WHEN** an index calculation or adapter disagrees with an immutable accepted settlement observation
- **THEN** the observation remains unchanged and the index computation fails or flags divergence
- **AND** no price-discovery component writes a replacement settlement

#### Scenario: logical accounting without a verified chain receipt is not a paid observation
- **WHEN** domain acceptance and a logical `market.apply_tx` result exist but the matching §18.6 wallet/chain receipt is absent, invalid, or mismatched
- **THEN** the index rejects paid-settlement ingestion
- **AND** no paid-market price, volume, breadth, or confidence evidence is created

### Requirement: Quote provenance distinguishes indicative references from executable firm offers
Every quote SHALL identify its quote id, capability descriptor digest/version, resolved demand digest, authority class, issuer, origin adapter, unit semantics, settlement currency, every priced component, component-coverage/missing-fields state, canonical fee schedule/version, landed monetary total, verified eligibility-fact digest, region/policy result, terms digest, issued/observed time, and expiry. An indicative quote SHALL be explicitly nonbinding. A native firm quote SHALL additionally bind authenticated issuer and tenant, nonce, signature domain, offer version, exact quantity, and an immutable capacity grant containing tenant, demand, quote, descriptor, offer version, quantity, expiry, and fence. A versioned domain-separated canonical encoding SHALL reject unknown/unclassified fields and SHALL be signed by an enrolled revocable issuer key whose algorithm, key id, validity, rotation, and revocation are verified through the shared record-verifier pattern. The server SHALL recompute all derived totals and canonical bytes. Mutable database state MAY narrow or prove current non-consumption but SHALL NOT grant positive authority. Only a verified, unexpired native firm quote whose aggregate capacity is conserved and whose capacity grant is unconsumed for the requested quantity SHALL be marked executable.

#### Scenario: catalog listing cannot become executable
- **WHEN** a listing or indicative observation has no verified native issuer signature and capacity lock
- **THEN** it remains nonbinding
- **AND** ranking cannot promote it to an executable route

#### Scenario: stale firm quote loses eligibility
- **WHEN** a firm quote is expired or its offer version or capacity lock is no longer current
- **THEN** it is excluded before route selection
- **AND** no reservation, claim, or settlement is attempted from it

#### Scenario: signature covers every authority-bearing field
- **WHEN** any quote identity, descriptor, demand, unit, price, fee, total, currency, eligibility, terms, quantity, tenant, issue/expiry, offer-version, or capacity field changes after signing
- **THEN** canonical record verification fails before ranking
- **AND** a caller cannot preserve authority by supplying an old signature or hash

#### Scenario: revoked issuer key or consumed capacity fails closed
- **WHEN** the issuer key is revoked/invalid or aggregate capacity would be oversold by single or partial consumption
- **THEN** the quote is non-executable
- **AND** mutable catalog state cannot recreate the missing authority

### Requirement: Verified provider eligibility constrains price routing
The router SHALL intersect workload, tenant/organization, contract, jurisdiction, and provider eligibility before considering price. Eligibility facts SHALL be signed or independently verified and SHALL bind evidence issuer/digest, provider legal/service identity, applicable contract/BAA/DPA reference and version where required, subprocessor/market-host chain, allowed regions/data flows, retention/training/logging rules, incident/deletion obligations, isolation/attestation class, validity, and revocation. Seller self-assertion alone SHALL NOT satisfy a regulated or privacy-sensitive constraint, and no eligible provider SHALL yield a fail-closed no-route result.

#### Scenario: unverified compliance label cannot win
- **WHEN** a seller labels an offer private, region-bound, or regulated-eligible without current verified facts and required contract chain
- **THEN** the offer is ineligible for a workload requiring those controls
- **AND** a lower price cannot override the missing evidence

#### Scenario: revoked eligibility removes a route
- **WHEN** a provider fact, contract, subprocessor, region, or attestation becomes expired or revoked
- **THEN** the route is excluded before firm-quote selection
- **AND** the evaluation receipt records the failed eligibility class without exposing protected data

### Requirement: Price surfaces are field-fresh and scoped to one substitutability class
For each exact capability descriptor class, the live price service SHALL publish separate raw dispute-cleared settled VWAP, lowest executable native ask, external hosted-provider reference/ceiling, and canonical composite-index fields. Every field SHALL carry its own source set, `observed_at`, `valid_until`, sample count, distinct verified economic-principal count, component coverage, and confidence/manipulation state. An external field SHALL be called an all-in ceiling only when every mandatory component for the demand envelope is covered; otherwise it SHALL be labeled partial/incomparable with missing components. Missing, unsupported, zero-volume, and stale values SHALL remain explicit null or stale states; freshness of one field SHALL NOT refresh another. External references SHALL NOT mutate raw native settlement truth or enter executable ranking. When and only when a complete, current, valid all-in ceiling exists, the canonical composite-index price SHALL equal the lesser of raw native VWAP and that ceiling and SHALL identify the clamp; an incomplete, stale, or invalid reference SHALL NOT clamp any field. The system SHALL NOT publish one global compute scalar or a midpoint that is not executable.

#### Scenario: zero volume stays honest
- **WHEN** no sufficient dispute-cleared settlement window exists but a fresh external ceiling or native ask exists
- **THEN** VWAP remains null while the independently fresh field remains visible
- **AND** the surface publishes its sample count and freshness state

#### Scenario: stale ceiling is visible
- **WHEN** an external reference source fails beyond its freshness bound
- **THEN** the bounded last-known ceiling is marked stale or becomes null according to policy
- **AND** it is not presented as current or executable

#### Scenario: incomplete external price is not called a ceiling
- **WHEN** an external source omits mandatory tax, request, egress, region, discount/minimum, or other priced coverage for the demand envelope
- **THEN** the field lists the missing components and remains partial/incomparable
- **AND** it is not labeled all-in or used to rank native executable supply

#### Scenario: valid external ceiling bounds only the composite index
- **WHEN** a fresh external reference is below the raw dispute-cleared native VWAP
- **THEN** raw native VWAP remains unchanged while the canonical composite-index price is clamped to the complete all-in ceiling and flagged
- **AND** the non-executable reference cannot alter native executable ranking

#### Scenario: incomplete external reference never clamps
- **WHEN** an external reference is stale, invalid, or missing any mandatory landed-price component
- **THEN** raw native VWAP and the canonical composite-index price are not clamped by that reference
- **AND** the reference remains explicitly partial, stale, or invalid

### Requirement: Each lane publishes an executable all-in total in its native economics
The price service SHALL compute and display a deterministic landed monetary total in one declared settlement currency for each ranking run, containing only priced components and the exact canonical market-fee schedule/version. Inference totals SHALL distinguish input, output, cached-token, request, and priced transfer components. Training totals SHALL include priced accelerator/device windows, topology premiums, checkpoint/recovery, interruption/retry expectation, data movement, and fees. Task totals SHALL bind the funded accepted outcome and machine gates. Fabrication totals SHALL include priced tooling, material, quantity/per-unit amount, inspection/QA, shipping, and fees. Latency, reliability, gang size, lead time, privacy, and acceptance terms SHALL remain hard constraints or separately ranked service attributes; if a requester elects a cost-versus-service utility objective, its explicit weights and version SHALL be bound to the demand and evaluation receipt. Quotes in different currencies SHALL NOT be compared unless a separately approved versioned FX oracle binds source, timestamp, expiry, rate, and conversion digest. Every executable native total SHALL include the current canonical fee; fee-version drift before reservation SHALL fail and require a requote, and settlement SHALL use the quote-bound fee schedule/version.

#### Scenario: nominally cheap interrupted training is not misranked
- **WHEN** a training ask has a lower device-hour price but higher expected interruption, recovery, movement, or topology cost
- **THEN** the router ranks by the deterministic expected job total under the requester policy
- **AND** exposes the component breakdown

#### Scenario: fabrication quote is landed rather than ex-works
- **WHEN** fabrication supply is compared for a destination and acceptance profile
- **THEN** the executable total includes tooling, material, inspection, shipping, and any priced cure/rework amounts
- **AND** unpriced cure/rework and acceptance terms remain disclosed constraints or service attributes rather than silently entering the monetary total
- **AND** a bare unit price is not presented as the buyer’s total

#### Scenario: service attributes are not silently monetized
- **WHEN** two eligible quotes differ in latency, reliability, lead time, or interruption class
- **THEN** the router applies hard constraints or the requester-selected versioned utility weights
- **AND** it does not invent an implicit currency exchange rate for service quality

#### Scenario: fee drift requires requote
- **WHEN** the canonical fee schedule/version changes after a firm quote is signed but before reservation
- **THEN** the old quote is no longer executable and the requester receives a requote
- **AND** settlement cannot omit or substitute the canonical fee

#### Scenario: currencies are not compared without a bound oracle
- **WHEN** candidate landed totals use different currencies and no approved current FX conversion is bound
- **THEN** they occupy incomparable surfaces or the non-settlement-currency candidate is rejected
- **AND** the router does not rank raw numeric amounts across currencies

### Requirement: Economic routing begins only after an explicit fulfillment mandate
The system SHALL present free queue, requester-owned/BYOC, and paid-market fulfillment as distinct choices and SHALL NOT silently move a request between them. After the requester selects an authorized paid or BYOC path, the economic router SHALL filter hard capability, artifact, license, privacy, locality, authority, budget, and expiry constraints before ranking eligible candidates by the versioned all-in objective. It SHALL return the selected executable quote, deterministic tie-break facts, and material rejection reasons, and SHALL require a separate explicit reservation or purchase transition before execution.

#### Scenario: no silent paid fallback
- **WHEN** free or BYOC fulfillment is unavailable and the requester has not authorized a paid market purchase
- **THEN** the work remains pending or reports no authorized route
- **AND** no market escrow, reservation, provider call, or maintainer quota is used

#### Scenario: hard constraint beats lower price
- **WHEN** the cheapest candidate violates a hard privacy, region, artifact, model, topology, deadline, or acceptance constraint
- **THEN** it is rejected with the corresponding reason
- **AND** only eligible candidates participate in deterministic ranking

#### Scenario: price and spend caps reject without substitution
- **WHEN** the selected paid quote exceeds the capability price cap or tenant-period market spend cap
- **THEN** purchase is rejected before any lock
- **AND** the response names the cap and required total without changing instrument, provider, or envelope

#### Scenario: owned capacity is outside market spend accounting
- **WHEN** the requester uses owned compute, their own API key, or their own subscription without buying a market instrument
- **THEN** market-tier spend caps and fees do not classify that owned usage as a market settlement
- **AND** its separate quota/budget authority remains explicit

### Requirement: External hosted-provider adapters are reference-only
External hosted-provider adapters SHALL be credential-blind, read-only price sources in this phase. They SHALL publish exact source, terms, resource envelope, settlement currency, component coverage/missing fields, region, discounts/minimum assumptions, mode, and freshness and SHALL NOT execute, reserve, claim, settle, accept an upstream credential, or return an executable route. A complete comparable price may appear only as an external reference ceiling alongside native executable supply; incomplete prices remain partial references. Requester-owned upstream execution and seller-bundled resale SHALL require separate approved authority and legal contracts.

#### Scenario: external price can inform but not execute
- **WHEN** a fresh external hosted-provider price is lower than every native executable ask
- **THEN** the surface shows that reference and its caveats
- **AND** the router does not buy, resell, credential, or execute that external service

#### Scenario: reference-adapter failure is isolated
- **WHEN** one external reference adapter times out, returns malformed units, or exceeds its freshness bound
- **THEN** that source becomes stale or unavailable without changing fresh native fields
- **AND** no fabricated ceiling or fallback execution is created

### Requirement: Economic discovery is separate from provider and domain execution routing
The economic router SHALL NOT modify provider role/health fallback chains, resolve credentials, treat provider health as payment authority, create/fence domain capacity, lock money, or replace domain-native execution protocols. It MAY consume a later provider attempt receipt identity and credential class as evidence. Discovery SHALL evaluate and revalidate a quote; the domain owner SHALL create and fence the capacity grant/lease/work order; `paid-market-economy` SHALL record logical budget reservation/accounting intent; and the required §18.6 successor SHALL remain the sole wallet/chain-effect authority. Interactive inference SHALL retain streaming/cancellation/metering semantics, repo/source work SHALL retain fenced B2 leases, training SHALL retain checkpoint/evaluation acceptance, bounties SHALL retain first verified machine gates, and fabrication SHALL retain work-order/inspection/delivery/cure/rejection semantics.

#### Scenario: quote selection cannot authorize provider credentials
- **WHEN** a quote ranks first but no requester-owned credential or accepted market execution lease is bound
- **THEN** execution remains held for missing authority
- **AND** no ambient platform or maintainer credential is used

#### Scenario: market-selected source job keeps its fence
- **WHEN** a paid route selects an eligible repo/source execution offer
- **THEN** the job enters the existing lease protocol and settlement remains bound to `job_id:lease_fence:accepted_result_sha256`
- **AND** quote selection does not create a second worker protocol

#### Scenario: discovery cannot reserve capacity or money
- **WHEN** a quote wins deterministic evaluation
- **THEN** discovery returns a selection receipt to the domain capacity owner and market transaction owner
- **AND** no capacity fence, budget lock, or money movement exists until those owners independently authorize and commit it

### Requirement: Discovery decisions produce reproducible privacy-minimal receipts
Every tenant-private route evaluation SHALL record opaque tenant-scoped commitments for descriptor and requester policy, objective version/weights, candidate quote identities and versions, field freshness, eligibility or rejection reason codes, selected quote if any, deterministic monetary total breakdown, service-attribute result, and evaluation time. Equality commitments SHALL use tenant-keyed opaque/HMAC forms rather than public low-entropy raw hashes. The receipt SHALL exclude prompts, datasets, CAD, credentials, private endpoints, and private demand details; SHALL be non-enumerable and readable only by the owning tenant's authorized owner/admin/auditor roles; SHALL declare retention, legal-hold, deletion, and export policy; and SHALL state that ranking is not proof of reservation, execution, acceptance, invoice, or settlement. Public surfaces SHALL expose only aggregate fields explicitly classified public.

#### Scenario: ranking can be replayed without private payload
- **WHEN** an authorized owner/admin/auditor replays a route evaluation from its immutable quote snapshot and tenant-scoped policy/descriptor commitments
- **THEN** the same eligible set, rejection reasons, totals, and winner are reproduced
- **AND** no private workload payload or credential is required

#### Scenario: another tenant cannot enumerate demand
- **WHEN** a principal from another tenant guesses a descriptor, policy, quote, receipt, or capacity identifier
- **THEN** it cannot discover the receipt, candidate set, demand, policy, quote, or capacity lock
- **AND** public aggregate output reveals no tenant-private correlation

#### Scenario: retention and deletion preserve only required evidence
- **WHEN** the owning tenant's declared retention expires or an authorized deletion runs without a legal hold
- **THEN** tenant-private evaluation material is deleted or cryptographically made inaccessible according to policy
- **AND** any legally required aggregate/financial evidence retains no private demand payload

### Requirement: Quote, lock, and receipt authority is tenant-isolated
Every private quote, evaluation receipt, capacity grant, reservation, idempotency key, cache key, and settlement handoff SHALL include tenant and universe identity derived from verified request authority. Public offers SHALL be explicitly classified public; absence of a private ACL SHALL fail closed rather than publish. Unique constraints and lookups SHALL use composite tenant keys, mixed-tenant candidate sets or posting handoffs SHALL be rejected, and membership/authority revocation SHALL invalidate cached eligibility so stale state can only deny.

#### Scenario: cross-tenant quote reuse is rejected
- **WHEN** a tenant attempts to rank, reserve, or settle another tenant's private quote or capacity grant
- **THEN** composite tenant authority rejects the operation before a lock
- **AND** no quote, candidate, policy, capacity, or spend information leaks

#### Scenario: stale membership cannot preserve eligibility
- **WHEN** tenant membership or delegated authority is revoked while a private quote or cache entry remains
- **THEN** revalidation denies access and execution
- **AND** stale cached authority cannot create a reservation or receipt

### Requirement: Public quote reads are bounded, cached, and connector-safe
The system SHALL expose unauthenticated CDN-cacheable public aggregate reads equivalent to `GET /v1/price/{capability_id}`, `GET /v1/prices?model=<llm_model>`, and `GET /v1/curve/{capability_id}` with a 60-second TTL and bounded pagination/result limits, plus an approved MCP quote read without adding an unreviewed public handle. Public output SHALL include units, landed monetary total/currency, priced-component coverage, authority class, executability, freshness, source type, confidence, and caveats in primary protocol text and SHALL contain no tenant-private receipt, demand, policy, candidate, or capacity identity. A public MCP/HTTP surface SHALL pass security review, concurrency/load proof, live canary, and rendered-chatbot acceptance before advertisement. Firm-quote eligibility SHALL be revalidated against current authority, expiry, offer version, and capacity grant rather than trusted from a cache.

#### Scenario: cached indicative quote cannot bypass firm revalidation
- **WHEN** a cached public surface names a formerly executable native ask
- **THEN** a later reservation revalidates the live offer version, expiry, and capacity lock
- **AND** stale cache state cannot double-sell capacity

#### Scenario: chatbot sees the full caveat
- **WHEN** a real chatbot reads the public quote through the live connector
- **THEN** price, units, total, executability, freshness, origin class, and caveats appear in rendered text
- **AND** critical authority facts are not hidden only in structured content

### Requirement: Manipulation controls aggregate by authenticated economic principal
The live index SHALL use dispute-cleared settlements and verified native asks and aggregate volume by a canonical economic-principal root backed by verified payout/funding, legal-entity, or common operator linkage rather than account identity alone. It SHALL apply a configurable per-principal influence cap, retain direction-insensitive pair analysis, conservatively exclude or downweight volume when linkage is unknown, and publish root-based distinct-owner and concentration/confidence facts. One principal SHALL NOT evade controls by splitting volume across offers, counterparties, workforce/OAuth accounts, seller accounts, or reversed pair direction. Discovery SHALL consume, not decide, the transaction owner's self-host classification: an accepted observation whose verified requester and host owner are identical SHALL carry `self_hosted_zero_fee` and remain excluded from paid-market volume, executable public ranking, and trusted VWAP. Broader linked-party paid-market volume SHALL be excluded or downweighted from trusted VWAP and SHALL retain its recorded ordinary canonical fee unless the transaction owner applied that exact same-owner exemption. External references SHALL remain separate and may bound only the named canonical composite-index field under its complete/current/valid all-in-ceiling rule; they SHALL NOT clamp raw native VWAP or enter native executable ranking.

#### Scenario: split-counterparty wash volume cannot dominate
- **WHEN** one authenticated principal trades through multiple counterparties or offer identities inside the index window
- **THEN** its aggregate capped influence remains within the configured principal limit
- **AND** the price surface discloses the resulting breadth and concentration state

#### Scenario: self-hosted work is not market volume
- **WHEN** the index receives an accepted observation whose verified requester identity equals verified host-owner identity
- **THEN** the observation must carry the transaction owner's `self_hosted_zero_fee` classification or ingestion fails loud
- **AND** a valid self-hosted observation creates no paid-market price, breadth, or executable-ranking evidence

#### Scenario: unknown linkage lowers confidence
- **WHEN** accounts cannot be linked to a verified economic-principal root with sufficient evidence
- **THEN** their volume is excluded or conservatively downweighted according to the versioned index policy
- **AND** account count is not reported as independent owner diversity

### Requirement: Capacity forwards remain physically delivered and fully collateralized
Forward instruments SHALL bind an immutable order id, capability descriptor version, one standard 8-hour UTC bucket or calendar-day/calendar-week roll-up no more than 28 days ahead, one supported 1M/10M/100M output-token size, unit price, authenticated seller, collateral terms, and an authenticated monotone posting/purchase/delivery/expiry/cancellation/settlement lifecycle. The initial forward class SHALL be batch-only with no secondary transfer. An order SHALL remain non-executable until canonical collateral is durably locked through the single transaction transport. Its published price SHALL be the deterministic lowest executable open ask for that exact bucket/class/size with source time. Settlement SHALL pass normalized exercised demand and caller-supplied delivered count to the canonical demand-relative oracle, reduce seller payment exactly pro-rata by unserved exercised demand, use the delivery threshold only to gate collateral slashing, compensate the buyer from any slash, persist exact inputs/outputs/version/conservation, and release or slash only from the immutable lock. Spot offers SHALL remain collateral-free unless a separately approved abuse-driven change says otherwise.

#### Scenario: uncollateralized forward cannot execute
- **WHEN** a seller posts a capacity forward without its matching durable collateral lock
- **THEN** the order is rejected or remains non-executable
- **AND** no buyer can reserve it

#### Scenario: buyer no-show does not slash the seller
- **WHEN** a buyer exercises no demand during a valid reserved window
- **THEN** the seller receives the canonical reservation settlement and collateral release
- **AND** no failure is invented

#### Scenario: delivery shortfall uses the canonical oracle
- **WHEN** delivered exercised demand falls below the configured threshold
- **THEN** seller payment is reduced exactly pro-rata by unserved exercised demand and the threshold gates slashing only
- **AND** any slash compensates the buyer rather than the treasury

#### Scenario: spot remains collateral-free
- **WHEN** an immediate supported spot offer is published under the existing cooperative-trust/dispute posture
- **THEN** no forward collateral lock is required
- **AND** the forward rule does not silently change the spot instrument

### Requirement: Demand forecasting is private and disabled by default
The demand-forecast signal SHALL remain `TINYASSETS_DEMAND_SIGNAL=off` by default pending privacy review. When deliberately enabled, it SHALL publish only a coarse daily per-capability signal containing bucketed, k-anonymized `n_universes_holding` and `est_tokens_declared`, with no identifiable universe, organization, goal, prompt, dataset, or private workload facts.

#### Scenario: demand signal remains dark by default
- **WHEN** the deployment flag is unset or the privacy gate is incomplete
- **THEN** no public or seller-visible demand forecast is emitted

### Requirement: Unsupported financial and upstream instruments are refused
The initial transport SHALL support only physically delivered native capacity under the declared spot/forward lifecycle and SHALL reject cash- or index-settled derivatives, secondary transfer, cross-margining, portfolio netting, leverage, options, proprietary-model instruments, seller-bundled upstream resale, and F3 swarm execution. External proprietary prices SHALL remain reference-only.

#### Scenario: cash-settled or resold instrument is refused
- **WHEN** a caller requests cash settlement, secondary transfer, or seller-bundled upstream service
- **THEN** the system returns the exact unsupported-instrument reason
- **AND** creates no order, credential grant, capacity lock, or settlement
