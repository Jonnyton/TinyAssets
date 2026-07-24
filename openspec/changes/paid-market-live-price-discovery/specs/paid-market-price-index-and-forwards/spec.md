## ADDED Requirements

### Requirement: Capability descriptors define substitutability without defining execution
The market SHALL bind every demand intent, native offer, and quote to a public versioned capability descriptor that classifies one atomic correlated supply tuple without granting price, execution, or settlement authority. The derived `capability_id` SHALL be exact validated supply-content identity and SHALL NOT be treated as price-index equivalence or demand identity. V1 SHALL NOT contain caller-supplied `profile_id`, `capability_id`, or `profiles[]`. An offer supporting multiple capability combinations SHALL reference multiple independently validated and hashed descriptors; matching SHALL NOT combine fields from different descriptors. Every point and cross-field combination admitted by one descriptor's ranges and sets SHALL be independently supportable at the same time; otherwise those combinations SHALL be separate descriptors.

The trusted library SHALL build an envelope containing exactly `domain="tinyassets.capability-descriptor"`, `schema_version="capability-descriptor/v1"`, and `descriptor`. `descriptor` SHALL contain exactly `lane`, `profile_schema_revision`, `unit_semantics`, `region`, `privacy_class`, `reliability_class`, and one `profile`. `lane` SHALL be exactly `inference`, `training`, `task`, or `fabrication`; `unit_semantics` SHALL contain exactly `delivered_unit` and integer `scale >= 1`.

The exact required inference-profile keys SHALL be `model_revision`, `runtime_revision`, `quantization`, `context_tokens`, `latency_ms`, `throughput_tokens_per_second`, `modalities`, `structured_output_classes`, `tool_classes`, and `token_categories`. Training SHALL require exactly `resource_revision`, `accelerator_memory_bytes`, `topology_classes`, `interconnect_revisions`, `runtime_revisions`, `container_formats`, `interruption_classes`, and `attestation_classes`. Generic task SHALL require exactly `task_protocol_revision`, `sandbox_revision`, `environment_revision`, `input_media_types`, `output_media_types`, `machine_gate_classes`, `cancellation_classes`, and `retry_classes`. Fabrication SHALL require exactly `process_revision`, `material_spec_revisions`, `build_x`, `build_y`, `build_z`, `tolerance`, `inspection_classes`, `certification_classes`, and `service_regions`. No other V1 profile key SHALL be accepted. Generic task describes bounded artifact-in/artifact-out and machine-verification capability and SHALL NOT create another execution protocol.

Every numeric profile field SHALL use exactly `{"min":Integer,"max":Integer,"unit":Identifier}` with `min <= max`; the interval SHALL be closed and inclusive. Every set field SHALL use exactly `{"unit":Identifier,"values":[Identifier,...]}` with non-empty, sorted, duplicate-free same-domain values. A required set with no supported member SHALL use explicit same-domain `none`, not an empty array.

Comparison direction SHALL be fixed by the lane field schema and SHALL NOT be caller data. An exact demand for `context_tokens`, `accelerator_memory_bytes`, `build_x`, `build_y`, or `build_z` SHALL lie inclusively inside the offered range. Offered `throughput_tokens_per_second.min` SHALL be greater than or equal to the demand minimum. Offered `latency_ms.max` and fabrication `tolerance.max` SHALL be less than or equal to the demand maximum. For every V1 set field, the canonical non-empty demand `required_values` SHALL be a subset of the offer's `values`; scalar selection SHALL use a singleton required subset. Units SHALL match the field schema before comparison. V1 SHALL reject any `direction`, `min_inclusive`, or `max_inclusive` member.

`region`, `privacy_class`, and `reliability_class` SHALL be exact schema-owned descriptor fields, SHALL participate in the capability id, and SHALL require exact equality for substitutability. The trusted constructor SHALL materialize absent inputs as `region="unspecified"`, `privacy_class="public_only"`, and `reliability_class="best_effort_unverified"`. `unspecified` matches only explicitly permitted `unspecified`; `public_only` permits public-data workloads only; and `best_effort_unverified` asserts no availability, durability, or verified-reliability floor. Omission SHALL NOT mean “any”.

`profile_schema_revision` SHALL be a globally immutable content-addressed identifier of the closed profile grammar, allowed units, comparison rules, market-class threshold/projection rules, and validator contract. The injected validator SHALL attest that exact revision and SHALL fail closed on any revision mismatch.

The trusted structured constructor SHALL accept a typed descriptor body, validate it, sort semantic set values, reject duplicates, build the exact envelope, and compute canonical bytes as `json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")`. It SHALL derive `capability_id` exactly as `"sha256:" + hashlib.sha256(canonical_bytes).hexdigest()`, where the suffix is 64 lowercase hexadecimal characters.

A separate canonical-byte decoder/verifier SHALL reject untrusted input longer than 65,536 bytes and any non-ASCII byte before parsing or materializing an object. It SHALL then use a guarded JSON parser that enforces the depth, member, array, and scalar-node limits while parsing, detects duplicate keys, and maps parser recursion/depth/node exhaustion to `limit_exceeded`. Only after those gates SHALL it perform exact domain/version checks, invoke the structured constructor on the parsed descriptor, regenerate canonical bytes, and byte-compare them to the input. Only this decoder/verifier SHALL emit `not_canonical`; the structured constructor SHALL NOT. No alternate serializer, caller-provided canonical bytes/id, Unicode normalization, numeric coercion, or unknown envelope field SHALL be accepted.

V1 SHALL be ASCII-only. Canonical bytes SHALL not exceed 65,536 bytes; nesting depth 8; 64 members per object; 64 values per set/array; or 1,024 scalar leaves. Keys SHALL be fixed schema keys and semantic identifiers SHALL match `[a-z0-9][a-z0-9._:/+-]{0,127}`. Free text and non-ASCII strings SHALL be rejected. Numbers SHALL be JSON integers in `0..9007199254740991`; V1 has no Boolean fields. Fractions, exponents, negative zero, integer-valued floats, infinities/NaN, duplicate keys, `null`, unknown keys/facets, empty required values, `min > max`, and out-of-bound structures SHALL fail before hashing.

After common validation and before hashing, every validation or match call SHALL receive an explicitly injected owning-domain validator selected by exact `(schema_version, lane, profile_schema_revision)`, never a process-global or mutable registry. The validator SHALL be synchronous, pure, deterministic, bounded, non-rewriting, perform no I/O, consult no clock, randomness, prices, credentials, or mutable execution state, and attest the exact content-addressed revision. Missing validator SHALL return `domain_validator_unavailable`; unknown revision SHALL return `unsupported_profile_schema_revision`; attested-revision mismatch SHALL return `domain_validator_revision_mismatch`; exception or semantic refusal SHALL return `domain_validation_failed`. Every failure SHALL return no capability id or quote, and the price index SHALL provide no fallback.

Validation SHALL return exactly `{"status":"valid","capability_id":...}` or `{"status":"invalid","code":Code,"path":JsonPointer}`. Matching SHALL return exactly `{"status":"compatible","capability_id":...}` or `{"status":"incompatible","code":Code,"path":JsonPointer}`. V1 `Code` SHALL be `malformed_descriptor`, `not_canonical`, `unsupported_schema_version`, `unsupported_profile_schema_revision`, `unknown_field`, `missing_field`, `invalid_type`, `invalid_identifier`, `duplicate_value`, `invalid_range`, `limit_exceeded`, `domain_validator_unavailable`, `domain_validator_revision_mismatch`, `domain_validation_failed`, `unit_mismatch`, `facet_missing`, `facet_not_in_set`, `range_below_min`, `range_above_max`, `region_mismatch`, `privacy_mismatch`, or `reliability_mismatch`. Decoder precedence SHALL be: raw byte-length bound; ASCII encoding; guarded JSON parsing with in-parser depth/member/array/scalar limits and duplicate-key detection; root; exact domain then schema version; missing fields in declared schema order; unknown fields in ASCII-sorted order; types, identifiers, numbers, ranges, and sets in schema depth-first order; remaining structural bounds; canonical byte comparison; validator availability/revision/semantics; compatibility in lane-field order; and public market-class projection last. Structured-constructor precedence SHALL begin at its typed-root/schema checks and otherwise follow the same order without decoder-only steps. Messages SHALL be fixed by code. JSON Pointers SHALL contain only known schema keys and bounded numeric indices; unknown caller keys SHALL be represented by their known parent plus `<?>`. Results and logs SHALL NOT echo caller values, canonical bytes, private commitments, or exception text.

Exact quantity, prompt, dataset, CAD/work-order payload, requested-item dimensions, destination, requested window, gang size/count/topology, deadline, lead time, checkpoint cadence, restart terms, acceptance payload, budget, and requester policy/weights SHALL remain exclusively in demand intent. A descriptor SHALL contain no tenant/user/universe identity, private demand commitment, prompt/artifact digest, offer/seller/capacity identity, endpoint, credential/secret reference, price/fee/currency, reservation/lease/fence, execution state, quote authority, or settlement fact. Stable public ranges/sets SHALL live in its one hashed profile. Offers SHALL carry commercial, availability, seller, and capacity terms separately. Private/low-entropy demand equality SHALL use a separate tenant-keyed purpose-separated HMAC. The descriptor SHALL NOT replace domain execution, acceptance, or settlement protocols.

After one validated descriptor is compatible with demand, a trusted pure lane projection owned by `profile_schema_revision` SHALL derive a separate public `market_class_id`; capability identity SHALL NOT be reused as aggregation identity. Its trusted library-built envelope SHALL contain exactly `domain="tinyassets.market-class"`, `schema_version="market-class/v1"`, and `descriptor`. That descriptor SHALL contain exactly `descriptor_schema_version`, `lane`, `profile_schema_revision`, `unit_semantics`, `region_class`, `privacy_class`, `reliability_class`, and `public_requirements`.

`public_requirements` SHALL be a sorted canonical array with unique fields whose members are exactly one of: `{"field":Identifier,"kind":"exact","value":Identifier}`, `{"bucket":Identifier,"field":Identifier,"kind":"threshold","unit":Identifier}`, or `{"field":Identifier,"kind":"required_subset","unit":Identifier,"values":[Identifier,...]}`. Numeric demand SHALL map through explicit immutable threshold buckets defined by `profile_schema_revision`, never raw values or dynamic/statistical buckets. Set demand SHALL contribute only its canonical sorted required subset; scalar set selection SHALL be a singleton. Extra supply values, wider ranges, and range headroom SHALL NOT enter the projection. Region, privacy, and reliability SHALL map only through the revision's coarse privacy-safe public class tables. A public ask or reference without private requester demand SHALL match an explicit revision-owned public demand-class template and SHALL NOT infer its market class from supply headroom.

The market-class library SHALL apply the same ASCII bounds and exact `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")` plus `"sha256:" + hashlib.sha256(canonical_bytes).hexdigest()` derivation. It SHALL return exactly `{"status":"classified","market_class_id":...}` or `{"status":"unclassified","code":"market_class_unavailable"}`. If projection is not deterministic, total for supported input, or privacy-safe, it SHALL emit no public class, quote, ask, external reference, or settlement observation. Firm quotes and accepted settlement evidence SHALL bind both exact `capability_id` and derived `market_class_id`.

#### Scenario: incompatible supply is not substituted
- **WHEN** an offer differs from a hard descriptor facet such as model revision, topology, region, privacy class, material, or tolerance
- **THEN** the offer is ineligible for that demand intent
- **AND** the router records the stable mismatch code and JSON Pointer without echoing a private demand value or treating a lower price as substitutable

#### Scenario: unsupported descriptor version fails loud
- **WHEN** a reader cannot validate the descriptor schema version or required lane facets
- **THEN** it returns the stable invalid result and exact `unsupported_schema_version`, `unsupported_profile_schema_revision`, or domain-validation code
- **AND** it publishes no executable quote or route for that descriptor

#### Scenario: demand terms resolve against supply ranges
- **WHEN** an exact requested public region, topology, quantity, window, or lead time satisfies its descriptor or offer-term constraint
- **THEN** compatibility is evaluated without creating a new capability identity for every request
- **AND** the resolved terms are bound into the firm quote and tenant-keyed demand commitment

#### Scenario: offer capabilities cannot be cross-combined
- **WHEN** no one descriptor satisfies every requested facet but individual facets could be collected from two or more descriptors on the same offer
- **THEN** each descriptor is independently incompatible
- **AND** matching does not manufacture a synthetic capability id or compatible tuple

#### Scenario: one descriptor cannot imply unsupported Cartesian combinations
- **WHEN** an offer can support each advertised range endpoint or set member separately but cannot support every admitted cross-field combination simultaneously
- **THEN** the combined descriptor is invalid
- **AND** the offer must publish separately supportable combinations as separate capability descriptors

#### Scenario: omitted policy defaults deny broader use
- **WHEN** descriptor-constructor input omits region, privacy, and reliability and a demand requires a named region, private-data handling, or a verified reliability floor
- **THEN** the trusted constructor materializes exact `unspecified`, `public_only`, and `best_effort_unverified` fields before hashing
- **AND** matching returns the applicable region, privacy, or reliability mismatch

#### Scenario: private demand does not enter the public capability id
- **WHEN** two tenants request the same public capability with different quantities, prompts, destinations, budgets, or policy weights
- **THEN** the public capability id remains the same for the same validated descriptor metadata
- **AND** each private demand is bound only by its own tenant-keyed purpose-separated commitment and firm-quote resolved terms

#### Scenario: unavailable domain validator fails closed
- **WHEN** the exact lane/profile-schema-revision validator is not injected, throws, or refuses the profile
- **THEN** validation returns `domain_validator_unavailable` or `domain_validation_failed` with no usable capability id
- **AND** no public or executable quote is emitted through a fallback validator

#### Scenario: caller direction and capability identity are refused
- **WHEN** input contains `profile_id`, `capability_id`, `profiles`, `direction`, or range-inclusivity fields
- **THEN** validation returns `unknown_field` with a non-echoing safe path
- **AND** the library derives no capability id from the caller-controlled shape

#### Scenario: set requirements use subset compatibility
- **WHEN** a demand requires two modalities, artifact types, topology classes, or other V1 set values
- **THEN** the descriptor is compatible only when both required values are members of the offer's same-unit set
- **AND** a scalar requirement is represented as a one-value required subset

#### Scenario: canonical bytes are verified separately from construction
- **WHEN** untrusted descriptor bytes decode to valid structured content but differ from bytes regenerated by the trusted constructor
- **THEN** only the byte decoder/verifier returns `not_canonical`
- **AND** structured construction continues to emit canonical bytes without accepting caller serialization

#### Scenario: validation failures have deterministic precedence
- **WHEN** one descriptor violates multiple structural, bound, validator, and compatibility rules
- **THEN** the first result follows the specified validation order and ASCII/schema field ordering
- **AND** validator or compatibility results cannot mask an earlier structural failure

#### Scenario: validator must attest the immutable profile revision
- **WHEN** an injected validator claims a different profile-schema digest than the descriptor
- **THEN** validation returns `domain_validator_revision_mismatch`
- **AND** no capability or market class id is emitted

#### Scenario: supply headroom does not fragment a market class
- **WHEN** two different capability ids both satisfy the same normalized public demand requirements but expose different extra set members or range headroom
- **THEN** the trusted projection derives the same market class id
- **AND** neither extra supply support nor private demand detail enters the public class

#### Scenario: unsafe demand cannot create a public class
- **WHEN** the active lane revision cannot map compatible demand to a deterministic privacy-safe public class
- **THEN** projection returns `market_class_unavailable`
- **AND** no public quote, ask, reference, or settlement observation is emitted

### Requirement: Settlement records normalized delivery evidence
The price index SHALL consume immutable accepted settlement observations emitted jointly by the `paid-market-economy` logical-accounting owner, the required wallet/chain-effect successor from `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6, and the domain execution owners; it SHALL NOT create or mutate settlement truth. A paid settlement SHALL NOT become an accepted price observation until its logical-accounting result, domain acceptance evidence, and independently verified wallet/chain receipt from that successor agree on the same tenant/universe-scoped settlement identity, `job_id:lease_fence:accepted_result_sha256`, parties, currency/token/chain, gross/net/fee amounts, exact `capability_id`, derived `market_class_id`, `market_scope_revision`, and canonical `public_scope_dimensions`, with the receipt accepted under that successor's finality and reorg policy. Scope SHALL be derived before execution from resolved quote/domain terms and re-derived against accepted settlement evidence; an aggregator SHALL NOT post-hoc bucket an observation. A new-version inference observation SHALL carry integer `tokens_in`, integer `tokens_out`, applicable integer cached-token counts, integer `unit_price_micros_per_mtok`, both capability and market-class ids, scope revision/dimensions, accepted evidence digest, verified chain-receipt digest, and canonical fee schedule/version. Existing v1 settlement records SHALL remain byte-for-byte unchanged, and any new observation shape SHALL use a schema-version bump. Training, task, and fabrication observations SHALL retain their domain-native delivered units and accepted evidence digest rather than translating them into tokens. Missing, mismatched, or implausible delivery evidence SHALL fail loud or enter the domain dispute path. Missing, mismatched, invalid, non-final, or reorg-affected wallet/chain evidence SHALL remain rejected and route only through that successor's reconciliation/finality process. Neither failure class SHALL silently produce a final paid price observation.

#### Scenario: inference completion without counts is rejected
- **WHEN** an inference completion omits required normalized token evidence
- **THEN** the price index rejects ingestion and publishes no null-count settlement observation or derived price
- **AND** the domain owner alone produces the semantic completion-acceptance verdict, `paid-market-economy` may record the bound request-lifecycle acceptance transition and logical accounting intent but cannot invent that verdict, and the `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6 successor alone controls wallet/chain effects

#### Scenario: non-inference work keeps its native units
- **WHEN** accepted training, task, or fabrication work becomes a market observation
- **THEN** the observation retains the domain-native units, descriptor, and acceptance evidence
- **AND** it is not converted to a fictitious token price

#### Scenario: price index cannot rewrite settlement truth
- **WHEN** an index calculation or adapter disagrees with an immutable accepted settlement observation
- **THEN** the observation remains unchanged and the index computation fails or flags divergence
- **AND** no price-discovery component writes a replacement settlement

#### Scenario: logical accounting without a verified chain receipt is not a paid observation
- **WHEN** domain acceptance and a logical `market.apply_tx` result exist but the matching wallet/chain receipt required by `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6 is absent, invalid, or mismatched
- **THEN** the index rejects paid-settlement ingestion
- **AND** no paid-market price, volume, breadth, or confidence evidence is created

#### Scenario: settlement scope mismatch cannot be rebucketed
- **WHEN** accepted settlement evidence does not revalidate the quote-bound market class or scope revision/dimensions
- **THEN** the index rejects observation ingestion
- **AND** no aggregator may replace them with a post-hoc public key

### Requirement: Quote provenance distinguishes indicative references from executable firm offers
Every quote SHALL identify its quote id, exact `capability_id`, derived `market_class_id`, descriptor schema version, resolved demand digest, `market_scope_revision`, canonical `public_scope_dimensions`, authority class, issuer, origin adapter, unit semantics, settlement currency, every priced component, component-coverage/missing-fields state, canonical fee schedule/version, landed monetary total, verified eligibility-fact digest, region/policy result, terms digest, issued/observed time, and expiry. The scope revision/dimensions SHALL be derived before execution from resolved quote/domain terms. An indicative quote SHALL be explicitly nonbinding. A native firm quote SHALL additionally bind authenticated issuer and tenant, nonce, signature domain, offer version, exact quantity, and an immutable capacity grant containing tenant, demand, quote, descriptor, offer version, quantity, expiry, and fence. A versioned domain-separated canonical encoding SHALL reject unknown/unclassified fields and SHALL be signed by an enrolled revocable issuer key whose algorithm, key id, validity, rotation, and revocation are verified through the shared record-verifier pattern. The server SHALL recompute all derived totals and canonical bytes. Mutable database state MAY narrow or prove current non-consumption but SHALL NOT grant positive authority. Only a verified, unexpired native firm quote whose aggregate capacity is conserved and whose capacity grant is unconsumed for the requested quantity SHALL be marked executable.

#### Scenario: catalog listing cannot become executable
- **WHEN** a listing or indicative observation has no verified native issuer signature and capacity lock
- **THEN** it remains nonbinding
- **AND** ranking cannot promote it to an executable route

#### Scenario: stale firm quote loses eligibility
- **WHEN** a firm quote is expired or its offer version or capacity lock is no longer current
- **THEN** it is excluded before route selection
- **AND** no reservation, claim, or settlement is attempted from it

#### Scenario: signature covers every authority-bearing field
- **WHEN** any quote identity, capability id, market class id, scope revision/dimensions, descriptor, demand, unit, price, fee, total, currency, eligibility, terms, quantity, tenant, issue/expiry, offer-version, or capacity field changes after signing
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
The live price service SHALL key every public aggregate by `(market_class_id, market_scope_revision, public_scope_dimensions)`, never exact supply `capability_id`. `market_scope_revision` SHALL be a globally immutable content-addressed projection contract that derives one bounded canonical ASCII object of allowlisted coarse public dimensions from resolved quote/domain terms before execution, such as an execution-region/SLO bucket or approved fabrication origin/destination/shipping-service bucket. The trusted scope projector SHALL sort semantic sets and construct the dimensions using the same bounded `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")` method; those canonical object bytes are what records bind. Every quote, native ask, external reference, and settlement observation SHALL bind the revision and canonical dimensions before publication or execution; settlement ingestion SHALL re-derive and revalidate them against accepted evidence. The aggregator SHALL only group identical bound keys and SHALL NOT create or rewrite a post-hoc bucket.

A scope revision SHALL NOT duplicate, override, or reclassify descriptor or market-class facets unless that revision defines a single canonical projection from the already-bound facet. Exact destination, tenant policy, private demand, seller identity, and identifying or low-entropy terms SHALL NOT enter the public key. Firm quotes SHALL remain authoritative for exact resolved terms.

For each exact public key, the live price service SHALL publish separate raw dispute-cleared settled VWAP, lowest executable native ask, external hosted-provider reference/ceiling, and canonical composite-index fields. Every field SHALL carry its own source set, `observed_at`, `valid_until`, sample count, distinct verified economic-principal count, component coverage, and confidence/manipulation state. An external field SHALL be called an all-in ceiling only when every mandatory component for the demand envelope is covered; otherwise it SHALL be labeled partial/incomparable with missing components. Missing, unsupported, zero-volume, and stale values SHALL remain explicit null or stale states; freshness of one field SHALL NOT refresh another. External references SHALL NOT mutate raw native settlement truth or enter executable ranking. When and only when a complete, current, valid all-in ceiling exists, the canonical composite-index price SHALL equal the lesser of raw native VWAP and that ceiling and SHALL identify the clamp; an incomplete, stale, or invalid reference SHALL NOT clamp any field. The system SHALL NOT publish one global compute scalar or a midpoint that is not executable.

#### Scenario: unlike landed terms do not share one public aggregate
- **WHEN** two observations have the same market class id but differ in a public scope dimension under the active market-scope revision
- **THEN** they are published in separate aggregate keys
- **AND** neither exact private demand nor exact destination is exposed to create that separation

#### Scenario: compatible supply headroom shares one demand class
- **WHEN** different exact capability ids satisfy the same market class and bind the same scope revision/dimensions
- **THEN** their eligible observations may contribute to the same public aggregate
- **AND** the aggregate still retains each source's exact capability id as evidence

#### Scenario: aggregator cannot invent scope after settlement
- **WHEN** a quote or accepted settlement lacks bound scope revision/dimensions or settlement evidence does not revalidate them
- **THEN** public observation ingestion fails
- **AND** the aggregator cannot choose a convenient bucket after seeing price or delivery

#### Scenario: scope cannot silently reclassify a market facet
- **WHEN** a scope rule tries to duplicate or alter descriptor or market-class region, privacy, reliability, unit, or public-requirement semantics without its declared canonical projection
- **THEN** scope derivation fails
- **AND** the observation cannot enter a second equivalence class by scope alone

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
The system SHALL present free queue, requester-owned/BYOC, and paid-market fulfillment as distinct choices and SHALL NOT silently move a request between them. After the requester selects an authorized paid or BYOC path, the economic router SHALL filter hard capability, artifact, license, privacy, locality, authority, budget, and expiry constraints before ranking eligible candidates by the versioned all-in objective. It SHALL return the selected executable quote, deterministic tie-break facts, and material rejection reasons, and SHALL require a separate explicit reservation or purchase transition before execution. This discovery decision SHALL compare fulfillment lanes and capability-compatible quote envelopes only; it SHALL NOT allocate hosts or fan-out slots. When it selects a native paid path, the Wave 2 `paid-market-economy` workflow SHALL separately revalidate and bind each selected firm quote to a request-scoped bid, then run `best_execution` only across admitted bids within that request/path. Both receipts SHALL preserve the quote-to-bid identity/version/digest link.

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

#### Scenario: discovery selection is not bidder allocation
- **WHEN** the economic router selects a native paid quote/path
- **THEN** its receipt authorizes no host, fan-out slot, claim, execution lease, or money effect
- **AND** the Wave 2 workflow records a separate request-bound bid/match receipt before any atomic claim

### Requirement: External hosted-provider adapters are reference-only
External hosted-provider adapters SHALL be credential-blind, read-only price sources in this phase. They SHALL publish exact source, terms, resource envelope, settlement currency, component coverage/missing fields, region, discounts/minimum assumptions, mode, freshness, `market_class_id`, `market_scope_revision`, and canonical `public_scope_dimensions`, all derived before publication under the same trusted projection rules as native asks. They SHALL NOT post-hoc bucket, execute, reserve, claim, settle, accept an upstream credential, or return an executable route. A complete comparable price may appear only as an external reference ceiling beside native supply under the identical public aggregate key; a classifiable but price-component-incomplete value remains a partial reference in that key. An unclassifiable value SHALL NOT become a public reference. Requester-owned upstream execution and seller-bundled resale SHALL require separate approved authority and legal contracts.

#### Scenario: external price can inform but not execute
- **WHEN** a fresh external hosted-provider price is lower than every native executable ask
- **THEN** the surface shows that reference and its caveats
- **AND** the router does not buy, resell, credential, or execute that external service

#### Scenario: reference-adapter failure is isolated
- **WHEN** one external reference adapter times out, returns malformed units, or exceeds its freshness bound
- **THEN** that source becomes stale or unavailable without changing fresh native fields
- **AND** no fabricated ceiling or fallback execution is created

### Requirement: Economic discovery is separate from provider and domain execution routing
The economic router SHALL NOT modify provider role/health fallback chains, resolve credentials, treat provider health as payment authority, create/fence domain capacity, lock money, or replace domain-native execution protocols. It MAY consume a later provider attempt receipt identity and credential class as evidence. Discovery SHALL evaluate and revalidate a quote; the domain owner SHALL create and fence the capacity grant/lease/work order; `paid-market-economy` SHALL record logical budget reservation/accounting intent; and the successor defined by `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6 SHALL remain the sole wallet/chain-effect authority. Interactive inference SHALL retain streaming/cancellation/metering semantics, repo/source work SHALL retain fenced B2 leases, training SHALL retain checkpoint/evaluation acceptance, bounties SHALL retain first verified machine gates, and fabrication SHALL retain work-order/inspection/delivery/cure/rejection semantics.

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
The system SHALL expose unauthenticated CDN-cacheable public aggregate reads equivalent to `GET /v1/price/{market_class_id}`, `GET /v1/prices?model=<llm_model>`, and `GET /v1/curve/{market_class_id}` with required bounded scope-revision/dimension selection, a 60-second TTL, and bounded pagination/result limits, plus an approved MCP quote read without adding an unreviewed public handle. Cache identity SHALL be the complete `(market_class_id, market_scope_revision, public_scope_dimensions)` key. Public output SHALL include units, landed monetary total/currency, priced-component coverage, authority class, executability, freshness, source type, confidence, and caveats in primary protocol text and SHALL contain no tenant-private receipt, demand, policy, candidate, or capacity identity. A public MCP/HTTP surface SHALL pass security review, concurrency/load proof, live canary, and rendered-chatbot acceptance before advertisement. Firm-quote eligibility SHALL be revalidated against current authority, expiry, offer version, and capacity grant rather than trusted from a cache.

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
Forward instruments SHALL bind an immutable order id, capability descriptor version, one standard 8-hour UTC bucket or calendar-day/calendar-week roll-up no more than 28 days ahead, one supported 1M/10M/100M output-token size, unit price, authenticated seller, collateral terms, and an authenticated monotone posting/purchase/delivery/expiry/cancellation/settlement lifecycle. The initial forward class SHALL be batch-only with no secondary transfer. An order SHALL remain non-executable until canonical collateral is durably locked through the single transaction transport. Its published price SHALL be the deterministic lowest executable open ask for that exact bucket/class/size with source time. Settlement SHALL pass normalized exercised demand and caller-supplied delivered count to the canonical demand-relative oracle, reduce seller payment exactly pro-rata by unserved exercised demand, use the delivery threshold only to gate collateral slashing, compensate the buyer from any slash, persist exact inputs/outputs/version/conservation, and release or slash only from the immutable lock. Spot offers SHALL remain collateral-free unless a separately approved abuse-driven change says otherwise. These product constraints SHALL NOT be represented as a regulatory safe harbor. Every jurisdiction SHALL remain dark until specialist counsel records the applicable CFTC facts-and-circumstances forward-contract-exclusion analysis—actual delivery, commercial intent, non-severable optionality, and the purpose of volume variation—plus applicable commodities, derivatives, securities, consumer, money-transmission, sanctions, and export-control conclusions and an approved jurisdiction policy version.

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

#### Scenario: forwards remain dark without jurisdiction-specific legal review
- **WHEN** the current jurisdiction lacks an approved specialist legal analysis and policy version for the proposed capacity-forward product
- **THEN** forward publication, purchase, transfer, exercise, and settlement remain unavailable in that jurisdiction
- **AND** physical delivery, collateral, or refusal of cash settlement is not advertised as legal approval or a categorical safe harbor

### Requirement: Demand forecasting is private and disabled by default
The demand-forecast signal SHALL remain `TINYASSETS_DEMAND_SIGNAL=off` by default pending privacy review. When deliberately enabled, it SHALL publish only a coarse daily per-capability signal containing bucketed, k-anonymized `n_universes_holding` and `est_tokens_declared`, with no identifiable universe, organization, goal, prompt, dataset, or private workload facts.

#### Scenario: demand signal remains dark by default
- **WHEN** the deployment flag is unset or the privacy gate is incomplete
- **THEN** no public or seller-visible demand forecast is emitted

### Requirement: Unsupported financial and upstream instruments are refused
The initial transport SHALL support only legally approved physically delivered native capacity under the declared spot/forward lifecycle and SHALL reject cash- or index-settled derivatives, secondary transfer, cross-margining, portfolio netting, leverage, options, proprietary-model instruments, seller-bundled upstream resale, and F3 swarm execution. External proprietary prices SHALL remain reference-only. Training/hardware eligibility SHALL consume verified policy facts and fail closed, but it SHALL NOT claim that a seller label or automated policy result constitutes BIS/export-control legal approval; jurisdictions and routes requiring such review SHALL remain dark until current specialist analysis is bound.

#### Scenario: cash-settled or resold instrument is refused
- **WHEN** a caller requests cash settlement, secondary transfer, or seller-bundled upstream service
- **THEN** the system returns the exact unsupported-instrument reason
- **AND** creates no order, credential grant, capacity lock, or settlement

#### Scenario: automated eligibility cannot certify export legality
- **WHEN** a training or hardware route has only seller-supplied compliance labels or automated policy facts without the current required specialist export-control review
- **THEN** the route remains ineligible for executable publication or purchase
- **AND** the platform reports missing legal authority rather than certifying compliance
