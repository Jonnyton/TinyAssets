# Token Architecture: Stablecoin × TINY

## Purpose

Define the two-token architecture and the wall between them: a regulated
stablecoin as the unit of account and settlement rail for every market
(E/F/G/H/I), and TINY as a claim on the platform's productive asset pool that
appears in no settlement path. The wall is the design — a volatile settlement
token would poison forward prices, break cap semantics, and taint the index;
keeping TINY out of payments keeps day-to-day platform use free of securities
questions.

Historical source of record (untouched): `docs/exec-plans/active/2026-07-08-token-architecture.md`.
Implemented fund math (5,000-case adversarial sweep): `tinyassets/paid_market/fund.py`.
**LEGAL GATE: nothing in this capability ships to public availability without counsel sign-off — see Open founder decisions.**

## Requirements

### Requirement: The wall — TINY never appears in any settlement path

The stablecoin SHALL be the unit of account and settlement rail, appearing in
every price, cap, escrow, collateral, refund, and payout across all markets. TINY
SHALL appear nowhere in any settlement path — `fund.py` SHALL be imported by no
market module, by design. The platform SHALL NOT self-issue the settlement
stablecoin (use an existing regulated stablecoin, USDC native on Base);
self-issuing a payment stablecoin is licensed, reserve-audited activity.

#### Scenario: no market module imports the fund
- **WHEN** a market settlement path executes
- **THEN** it prices and settles in stablecoin micros
- **AND** `fund.py` (TINY) is not imported anywhere in the settlement path

### Requirement: Fund discipline — mint/redeem at NAV only, rounding favors the fund (implemented)

TINY SHALL mint at NAV only (floored, contributor never receives above-NAV value;
genesis bootstraps 1:1 and prices any pre-seeded treasury into the first mint)
and redeem at NAV only (floored; full wind-down pays exact AUM, no stranded
assets). Rounding SHALL always favor the fund — a mint→redeem cycle SHALL never
extract value (proven by a 5,000-case adversarial sweep; dust-skimming is
arithmetically impossible). The only non-mint AUM increase SHALL be fee inflow;
there SHALL be no code path for printing.

#### Scenario: a mint-then-redeem round trip cannot extract value
- **WHEN** a holder mints TINY and immediately redeems
- **THEN** the round trip is strictly non-profitable (rounding favors the fund)
- **AND** no discretionary mint path exists in code

### Requirement: Conservative valuation — realized cash flow only, never mark-to-model

The system SHALL value stable reserves at face and productive positions by realized trailing cash flow only — because most fund positions (e.g. non-transferable Track H shares) have no market price, and marking them to model would let NAV be inflated by optimism. Every input SHALL be auditable from the settlement ledger. Conservative NAV SHALL understate; it SHALL never lie. Valuation SHALL be a ledger/reporting job; `fund.py` takes AUM as input and never guesses.

#### Scenario: illiquid positions are not marked to optimism
- **WHEN** NAV is computed and a position has no market price
- **THEN** it is valued by realized trailing cash flow, auditable from the ledger
- **AND** NAV is never inflated by mark-to-model optimism

### Requirement: Mixed-asset current-state binding rules

The following SHALL hold given the current mixed-asset backing. Fund assets SHALL
never provide liquidity for TINY (AUM in a TINY pair bleeds backing to arbitrage).
Mixed-asset NAV SHALL require live pricing plus an entry/exit fee that ACCRUES TO
AUM (never leaves the fund) — a round trip is strictly unprofitable and full
wind-down is fee-exempt and pays exact AUM (`mint_at_nav_with_fee` /
`redeem_at_nav_with_fee`; suggested band 0.3–1%). The liquidity pool SHALL be
personal and seeded AT NAV; remaining founder tokens are stake, not inventory,
and stay out of the pool.

#### Scenario: entry/exit fee accrues to AUM and pins arbitrage
- **WHEN** a holder mints or redeems against mixed backing
- **THEN** the fee accrues to AUM (never leaves the fund) making a round trip unprofitable
- **AND** a full wind-down is fee-exempt and pays exact AUM

## Open founder decisions

- **Token items** (token-architecture §6): redemption gating (open vs. windowed),
  whether TINY carries governance weight, treasury position policy (what % of fee
  inflow buys model/dataset positions vs. stays in reserves), the genesis treasury
  contents, and redemptions-from-mixed-assets posture (liquid sleeve vs. in-kind,
  §7.3) are all pending founder decisions.
- **Legal gates** (§5, stacking with Track H §3): TINY is very plausibly a
  security/fund interest. Public mint/redeem availability, marketing language, and
  jurisdictional availability are counsel decisions. Until sign-off:
  treasury-internal accounting only. This gate stacks with Track H's share
  non-transferability — the same counsel engagement should cover both.
