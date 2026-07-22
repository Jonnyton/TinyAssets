## ADDED Requirements

### Requirement: Settlement records normalized delivered-token evidence
Every completed inference request SHALL record integer `tokens_in` and `tokens_out`, derive integer `unit_price_micros_per_mtok`, and key normalization by `capability_id`. `complete_request(state='completed')` SHALL reject missing counts loudly and SHALL write no null-count settlement. Existing v1 settlement records SHALL remain byte-for-byte unchanged; any new shape SHALL use a schema-version bump. Implausible counts relative to deliverable-size heuristics SHALL be a ground in the standard dispute window without silently changing payment.

#### Scenario: completion without counts is rejected
- **WHEN** an inference completion omits required normalized token evidence
- **THEN** completion is rejected, no null-count settlement row is written, and no final funds move

### Requirement: Published spot quotes preserve field-level freshness
For each capability, the live quote service SHALL source dispute-cleared settled trades, open asks, and hosted-price ceilings; compute the canonical oracle; and publish `{last_vwap_micros, best_ask_micros, ceiling_micros}` with per-field `as_of` timestamps and `n_trades`. The ceiling SHALL keep the composite quote non-null at zero settled volume. Thin volume SHALL not invent a VWAP, and a failed ceiling fetch SHALL serve the bounded last-known value explicitly marked stale rather than fabricating freshness.

#### Scenario: zero-volume quote stays honest
- **WHEN** no sufficient settled-trade window exists but a fresh ceiling exists
- **THEN** the composite quote remains non-null through `ceiling_micros`, publishes per-field timestamps and `n_trades`, and leaves VWAP null

#### Scenario: ceiling failure is visible
- **WHEN** the ceiling source fails beyond its freshness bound
- **THEN** the quote serves the bounded last value marked stale rather than presenting it as current

### Requirement: Quote surfaces are public-read, cached, and connector-safe
The system SHALL expose unauthenticated CDN-cacheable reads equivalent to `GET /v1/price/{capability_id}`, `GET /v1/prices?model=<llm_model>`, and `GET /v1/curve/{capability_id}` with a 60-second TTL, plus an approved MCP quote read. MCP results SHALL place the complete human-readable quote in the protocol text content block, not only `structuredContent`, and any new public handle SHALL pass connector review and rendered-chatbot acceptance before advertisement.

#### Scenario: MCP quote is visible to a chatbot
- **WHEN** a real chatbot calls the approved quote read through the live connector
- **THEN** the price, units, freshness, and caveats appear in the rendered text response without requiring hidden structured-content access

### Requirement: Manipulation controls aggregate by authenticated principal
The live index SHALL use settled, dispute-window-cleared trades only and aggregate economically linked volume by authenticated principal before applying a configurable per-user influence cap, while retaining direction-insensitive pair analysis and fee/dispute signals. It SHALL not allow one principal to evade the cap by splitting trades across counterparties, accounts, or reversed pair direction, SHALL charge the standard 1% fee on both sides of self-dealt volume, and SHALL never publish a VWAP above the ceiling without clamping and flagging it.

#### Scenario: split-counterparty wash volume cannot dominate
- **WHEN** one authenticated principal trades through multiple counterparties inside the index window
- **THEN** their aggregate capped influence remains within the configured principal limit and the diversity fields disclose the resulting market breadth

### Requirement: Capacity forwards have standardized buckets and an explicit order lifecycle
Forward instruments SHALL bind a capability version, UTC bucket, supported size, unit price, seller, collateral terms, and immutable order id. Standard buckets SHALL be 8-hour UTC blocks plus calendar-day and calendar-week roll-ups, sellable no more than 28 days ahead; standard sizes SHALL be 1M, 10M, and 100M output tokens; Wave 4 SHALL be batch class only. Posting, purchase, delivery, expiry, cancellation, and settlement transitions SHALL be authenticated and monotone; the published forward price for a bucket SHALL be its lowest executable open ask with a source timestamp, and Wave 4 SHALL have no secondary transfer.

#### Scenario: best ask per bucket is reproducible
- **WHEN** multiple valid open asks exist for the same capability, bucket, and size
- **THEN** the quote publishes the deterministic lowest executable ask and identifies the snapshot time

### Requirement: Forward settlement uses the canonical demand-relative oracle
Live forward settlement SHALL pass normalized exercised demand and the caller-supplied delivered count into the canonical pure oracle, reduce seller payment pro-rata by unserved exercised demand, gate collateral slashing only on the delivery threshold, compensate the buyer from any slash rather than the treasury, and persist exact oracle inputs, outputs, version, and conservation results in the transaction receipt.

#### Scenario: buyer no-show does not slash the seller
- **WHEN** a buyer exercises no demand during a valid reserved window
- **THEN** the seller receives the canonical full reservation settlement and collateral release

#### Scenario: a threshold gates slashing only
- **WHEN** delivered exercised demand falls below the configured threshold
- **THEN** seller payment is reduced pro-rata by unserved exercised demand, collateral is slashed pro-rata, and the slash compensates the buyer rather than rounding payment up

### Requirement: Buyer price and spend caps reject without substitution
Every spot request and forward purchase SHALL enforce a per-capability `price_cap`, and every escrow lock SHALL enforce a per-user-per-period `spend_cap` across the market tier only. Owned compute, the user's own API keys, and subscriptions SHALL remain outside market-tier spend accounting. A cap violation SHALL return a machine-readable reason and current quote; it SHALL NOT silently substitute another instrument, size, provider, or higher price.

#### Scenario: spend cap is binding
- **WHEN** a market-tier escrow would exceed the buyer's current-period spend cap
- **THEN** purchase is rejected without a lock and the response names the cap and required amount

### Requirement: Forward collateral is locked before an order is executable
A forward post SHALL remain non-executable until the canonical collateral amount is durably locked through the single transaction transport. Cancellation, expiry, and settlement SHALL release or slash only from that immutable lock and SHALL conserve it exactly. Spot delivery SHALL remain collateral-free under the existing cooperative-trust posture because it is immediate, low-stakes, and already covered by the dispute window.

#### Scenario: an uncollateralized forward cannot be bought
- **WHEN** a seller attempts to publish an order without a matching durable collateral lock
- **THEN** the order is rejected or remains non-executable
- **AND** spot offers remain collateral-free unless a separate abuse-driven behavior change is approved

### Requirement: Demand forecasting is private and disabled by default
The demand-forecast signal SHALL remain `TINYASSETS_DEMAND_SIGNAL=off` by default pending privacy review. When deliberately enabled, it MAY publish only a coarse daily per-capability signal containing bucketed, k-anonymized `n_universes_holding` and `est_tokens_declared`, with no identifiable universe or goal data.

#### Scenario: demand signal remains dark by default
- **WHEN** the deployment flag is unset or the privacy gate is incomplete
- **THEN** no public or seller-visible demand forecast is emitted

### Requirement: Cash-settled and secondary instruments are explicitly refused
The v1 transport SHALL support only physically delivered batch capacity for open-source model capability keys under the declared forward lifecycle. It SHALL reject cash- or index-settled derivatives, secondary transfer, interactive low-latency forward SLAs, cross-margining, portfolio collateral or netting, capability-key widening, proprietary-model instruments, options, and leverage. Hosted proprietary prices MAY enter only as ceiling references.

#### Scenario: a cash-settled derivative is refused
- **WHEN** a caller requests cash settlement instead of delivered capacity
- **THEN** the transport returns the unsupported-instrument reason and creates no order or lock
