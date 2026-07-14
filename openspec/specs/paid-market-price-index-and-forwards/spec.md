# Paid Market: Live Price Index & Capacity Forwards

## Purpose

Provide a live spot token price and a live forward token price for every
open-source LLM traded on the paid market — quotable from day one at zero
volume and hardening into real market prices as flow arrives — plus the
standardized capacity-forward instrument that makes future compute priceable and
collateral-backed. This capability is the FOUNDATION for token-normalized
settlement and index computation, and it owns the market's single
money-movement transport.

Historical source of record (untouched): `docs/exec-plans/active/2026-07-08-track-e-price-index-and-capacity-forwards.md`.
Adversarial review: `docs/design-notes/2026-07-08-paid-market-adversarial-review.md`.
Pure core (implemented + 20k-case conservation sweep): `tinyassets/paid_market/{index.py,buckets.py,forwards.py}`.
Ledger transport (founder-gated migration): `prototype/full-platform-v0/migrations/008_market_ledger.sql`.

## Requirements

### Requirement: Money movement goes through market.apply_tx() and nothing else (HARD RULE)

The market SHALL enforce the following ledger-transport HARD RULE verbatim (founder sign-off 2026-07-13):

Every money movement in the market goes through market.apply_tx() and NOTHING ELSE. Application code never computes a balance and writes it. The pure ledger.py stays the validation oracle and the executable spec; this RPC is its one transport.

The system SHALL route every settlement, escrow lock/release, refund, slash, and
fee posting through `market.apply_tx()`; no other code path SHALL write a balance
or a ledger row. `tinyassets/paid_market/ledger.py` SHALL remain the pure
validation oracle and executable spec, and the transport SHALL be verified
against it. (Ledger-transport law adopted by founder sign-off 2026-07-13; source:
`prototype/full-platform-v0/migrations/008_market_ledger.sql` header. The
concurrency proof-of-need: 8 unlocked threads against the pure ledger created 278
units from nothing via lost updates, while single-writer did 1M tx with zero
drift — serialization is not optional.)

#### Scenario: a settlement posts through the single transport
- **WHEN** any market path (spot settle, forward settle, escrow lock/release, slash, fee) moves money
- **THEN** the movement is applied via `market.apply_tx()`
- **AND** no application code computes a balance and writes it directly

#### Scenario: transport is validated against the pure oracle
- **WHEN** the ledger transport applies a transaction
- **THEN** the resulting state matches what pure `ledger.py` computes for the same inputs
- **AND** any divergence fails loud rather than persisting

### Requirement: Token-normalized settlement (Wave 3a)

The system SHALL record `tokens_in` and `tokens_out` on every completed request
and derive a per-capability `unit_price_micros_per_mtok` at settlement using
integer micros (never float). Normalization key SHALL be `capability_id`.
`complete_request` SHALL require token counts for `state='completed'`; missing
counts SHALL fail loud (completion rejected, no silent nulls). Existing v1
settlement records SHALL remain byte-for-byte untouched (schema_version bump
only).

#### Scenario: completion without token counts is rejected
- **WHEN** a daemon calls `complete_request` with `state='completed'` but no `tokens_in`/`tokens_out`
- **THEN** the completion is rejected with a loud error
- **AND** no null-count settlement row is written

#### Scenario: egregious count inflation is a dispute ground
- **WHEN** reported token counts diverge implausibly from deliverable-size heuristics
- **THEN** the mismatch is a dispute ground within the existing dispute window
- **AND** no new infrastructure is required beyond the moderation backstop

### Requirement: Composite spot quote never fabricates liveness

Per capability, the system SHALL publish a three-number spot quote
`{last_vwap_micros, best_ask_micros, ceiling_micros}` with per-field `as_of`
timestamps and `n_trades`. The cheapest hosted-API `ceiling_micros` SHALL make
the quote non-null at zero volume; a rational buyer never pays above `ceiling`.
The system SHALL NOT fabricate liveness — stale fields are flagged, never
invented.

#### Scenario: quote is live at zero volume via the ceiling
- **WHEN** a capability has zero settled trades in the window
- **THEN** the spot quote is still non-null because `ceiling_micros` is present
- **AND** the payload carries `as_of` timestamps and `n_trades` so consumers can judge staleness

#### Scenario: ceiling fetch failure degrades honestly
- **WHEN** the external ceiling feed fails
- **THEN** the last value is served stale-but-flagged
- **AND** liveness is never fabricated

### Requirement: Spot/forward quote surface is unauthenticated, cached, and MCP text-block safe

The system SHALL expose `GET /v1/price/{capability_id}`,
`GET /v1/prices?model=<llm_model>`, and `GET /v1/curve/{capability_id}` as
unauthenticated, CDN-cacheable (60s TTL) reads, and SHALL also expose the quote
as an MCP tool. The MCP result MUST be in the text content block, not
`structuredContent`-only — text-only clients are a known dark-payload failure
mode on this connector.

#### Scenario: MCP quote lands in the text content block
- **WHEN** a chatbot-hosted universe calls the market price MCP tool
- **THEN** the price appears in the text content block of the result
- **AND** a text-only client can read it (no structuredContent-only payload)

### Requirement: Thin-market manipulation posture on the index

The system SHALL compute VWAP over settled trades only (money moved and dispute
window passed), SHALL apply a per-user trade-weight cap in the VWAP so a single
account's self-dealt volume cannot dominate the window, and SHALL never publish a
VWAP above the ceiling (flagging instead).

#### Scenario: self-dealt volume cannot dominate the index
- **WHEN** one account settles a large share of the window's volume against itself
- **THEN** the per-user weight cap limits its contribution to the VWAP
- **AND** the wash trades still cost the 1% fee both ways

### Requirement: Standardized capacity forwards

The system SHALL sell forwards as seller-posted, collateralized promises of
inference capacity in standard time buckets (8-hour UTC blocks plus calendar-day
and calendar-week roll-ups, sellable up to 28 days ahead) and standard sizes
(1M / 10M / 100M output tokens), batch class only in Wave 4. Standardization is
the whole point: the best ask per bucket IS the live forward price. There SHALL
be no secondary trading of forwards in Wave 4.

#### Scenario: best ask per bucket is the forward price
- **WHEN** multiple sellers post forwards for the same capability and bucket
- **THEN** the offers compete directly on a standard instrument
- **AND** the lowest open ask per bucket is published as the live forward price

### Requirement: Forward settlement is demand-relative, pro-rata, and conservation-exact

Forward settlement SHALL be pro-rata: the buyer is refunded only for unserved
demand (buyer no-show -> seller paid in full, use-it-or-lose-it). The seller's
obligation SHALL be `demand = min(requested, size)`, a capacity reservation and
not unilateral token emission (finding B-1: measuring against raw size made
buyer no-show griefing profitable). The >=95%-of-demand threshold SHALL gate
collateral slashing ONLY and SHALL never round payment up (finding A-1). Slash
proceeds SHALL compensate the buyer, not the treasury (finding B-3). Conservation
invariants SHALL be asserted at every settlement using exact integer math.

#### Scenario: buyer no-show does not grief the seller
- **WHEN** the buyer submits no demand during a purchased forward window
- **THEN** the seller is paid in full (use-it-or-lose-it capacity reservation)
- **AND** the seller's collateral is not slashed

#### Scenario: threshold gates slashing only, never payment
- **WHEN** a seller delivers below the 95%-of-demand threshold
- **THEN** collateral is slashed pro-rata to unserved demand
- **AND** the slash proceeds pay the buyer, not the treasury
- **AND** payment is never rounded up by the threshold

### Requirement: Uniform buyer caps with machine-readable rejection

The system SHALL enforce a per-capability `price_cap` (max unit price, checked at
spot request submission and forward purchase) and a per-user-per-period
`spend_cap` across the market tier only (owned compute, own API keys, and
subscriptions are outside market accounting), checked as a ledger check at escrow
time. On a cap hit the market SHALL reject with a machine-readable reason and
SHALL NOT perform substitution — adaptation (queue, redesign, wait) lives in the
universe, not the market.

#### Scenario: spend cap hit returns a reason, not a substitution
- **WHEN** an escrow would exceed the user's period `spend_cap`
- **THEN** the market rejects with a machine-readable reason
- **AND** the market performs no substitution; the universe decides what to do

### Requirement: Forwards require collateral by construction; spot posture unchanged

Collateral SHALL be table stakes for forwards from day one — not a response to
abuse but the thing that makes the promise meaningful — overriding the
cooperative-trust memory for forwards only. The spot posture SHALL remain
cooperative-trust (instant delivery, small stakes, dispute window suffices), with
no escrow/reputation infrastructure required until abuse appears.

#### Scenario: a forward cannot be posted without collateral
- **WHEN** a seller posts a forward offer
- **THEN** collateral is locked at post
- **AND** spot offers remain collateral-free under the unchanged cooperative-trust posture

### Requirement: Demand-forecast signal is privacy-gated off by default

The demand-forecast signal SHALL be flag-gated `TINYASSETS_DEMAND_SIGNAL=off` by default pending a privacy pass. When enabled, the system MAY publish a coarse daily signal per capability (`n_universes_holding`, `est_tokens_declared`, bucketed and k-anonymized so no universe is identifiable).

#### Scenario: demand signal stays dark until the privacy pass
- **WHEN** the demand-forecast flag is unset
- **THEN** no demand signal is published
- **AND** enabling it requires the deliberate flag flip after a privacy pass

### Requirement: Cash-settled and secondary instruments are out of scope

The system SHALL NOT ship cash-settled futures / index-settled derivatives,
secondary trading or transfer of forwards, interactive-class (low-latency SLA)
forwards, cross-margining/portfolio-collateral/netting, capability-key widening
(Wave 5 candidate, tracked separately), or proprietary-model instruments (the
market covers open-source models only; hosted prices enter only as the ceiling
reference).

#### Scenario: a cash-settled derivative request is refused
- **WHEN** a caller asks for a cash-settled or index-settled forward
- **THEN** the market declines — only physically-settled forwards exist
- **AND** the out-of-scope boundary is preserved

## Open founder decisions

- **Forward collateral / threshold / bucket defaults** (Track E §3 forwards, §6
  trust-memory override): the default `collateral_pct` (currently 20), the
  >=95%-of-demand slashing threshold, and the standard bucket/size set are pending
  founder confirmation. The trust-memory override for forwards is decided; the
  numeric defaults are not.
- **Capability-key granularity** (§2 note, §7): widening the capability key to
  encode quantization / context / latency class is a Wave 5 candidate, tracked
  separately. Do not block the index on it.

*Note: the 2026-07-13 founder sign-offs adopted the serialization HARD RULE above
and the double-entry `market.apply_tx` transport (freezing `public.ledger` as v1
historical), but did not resolve the per-track defaults listed here. See
`docs/decisions/2026-07-13-paid-market-founder-signoffs.md`.*
