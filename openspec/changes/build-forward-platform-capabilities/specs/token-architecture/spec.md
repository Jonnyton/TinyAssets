## ADDED Requirements

### Requirement: Settlement value and public TINY remain separate ledgers
Market settlement SHALL use an existing approved regulated stablecoin rail and SHALL never require public TINY ownership, minting, redemption, or price exposure. The platform SHALL NOT self-issue its settlement stablecoin. TINY fund accounting SHALL live behind a separate interface, storage boundary, feature flag, and authorization policy; market settlement modules SHALL NOT import the public TINY fund module, and invoking settlement SHALL not initialize or mutate the fund.

#### Scenario: a market payment does not touch TINY
- **WHEN** an ordinary paid-market transaction settles
- **THEN** only the stable-value settlement ledger changes and no TINY supply, NAV, or holder record is read or written

### Requirement: Public mint and redemption use explicit NAV state and refuse ambiguous bootstrap
If counsel authorizes public TINY, mint and redemption SHALL use audited realized AUM and supply, canonical floor-rounded arithmetic, explicit entry/exit fees, reserve capacity, and exact fee-exempt final wind-down. An empty fund MAY bootstrap one-to-one, but positive AUM with zero supply SHALL block public minting until a separately approved genesis allocation explicitly accounts for those assets. Fee inflow SHALL be the only non-mint AUM increase exposed by the fund contract, and no discretionary supply-printing path SHALL exist.

#### Scenario: ambiguous pre-seeded treasury blocks minting
- **WHEN** audited AUM is positive while public supply is zero and no approved genesis allocation exists
- **THEN** minting is unavailable rather than granting the first minter implicit ownership

#### Scenario: a round trip cannot extract fund value
- **WHEN** an actor mints and redeems against unchanged NAV inputs
- **THEN** rounding and fees ensure the actor receives no more stable value than supplied

### Requirement: Valuation uses auditable realized cash-flow policy
NAV input SHALL be produced by a versioned valuation job over immutable settlement-ledger evidence. Stable reserves SHALL value at face; illiquid models, datasets, ownership interests, and hardware positions without an approved market price SHALL value only by conservative realized trailing cash flow and SHALL never be marked to optimistic internal estimates. The report SHALL disclose its window and inputs so conservative NAV may understate but cannot silently inflate.

#### Scenario: an illiquid position is not marked to model
- **WHEN** the treasury holds an asset without an approved realizable price source
- **THEN** the NAV report excludes its speculative value and discloses the excluded position

### Requirement: Mixed-asset liquidity and fee rules are explicit
The fund SHALL separate liquid redemption reserves from illiquid positions, retain entry/exit and market fee inflows under frozen policy, enforce reserve-bound redemption capacity, and define windowed, in-kind, or unavailable redemption behavior before accepting a mint. Fund assets SHALL never provide liquidity for a TINY trading pair because doing so transfers backing through arbitrage. Any permitted TINY liquidity SHALL be personal, seeded at audited NAV, and SHALL exclude remaining founder tokens, which remain stake rather than inventory. Treasury allocations, founder holdings, governance rights, and personal liquidity arrangements SHALL be disclosed and policy-gated.

#### Scenario: redemption cannot exceed liquid capacity
- **WHEN** a requested redemption exceeds the policy-approved liquid sleeve
- **THEN** the request is capped, queued, or rejected according to the published rule without forcing an unpriced illiquid sale

### Requirement: Public token behavior is dark until counsel and launch gates pass
Public minting, redemption, marketing, governance, jurisdictional access, and any pooled-share secondary transfer SHALL default unavailable until written counsel approval, security review, economic simulation, abuse controls, and jurisdiction-specific launch configuration are recorded. Treasury-internal test accounting SHALL not be represented as a public token launch.

#### Scenario: missing counsel approval keeps public surfaces dark
- **WHEN** any required legal or launch approval is absent or expired
- **THEN** public TINY actions and promotional claims remain unavailable while internal non-public arithmetic may continue
