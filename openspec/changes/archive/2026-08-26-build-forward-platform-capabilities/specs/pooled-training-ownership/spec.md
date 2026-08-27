## ADDED Requirements

### Requirement: Pool funding persists consensus order and exact allocation
A pooled training instrument SHALL durably assign each accepted contribution an arrival sequence before settlement and SHALL run the canonical ordered funding and exact apportionment oracles over that immutable sequence. A crossing contribution SHALL split exactly, late contributions SHALL refund whole, a pool that fails to reach funding SHALL refund every contribution, and each contributor SHALL always satisfy `accepted + refunded == paid`. All results SHALL reproduce from the persisted event log. Largest-remainder payouts SHALL sum exactly, leave every owner within one micro of exact pro-rata, and break equal remainders by key ascending.

#### Scenario: persisted arrival order reproduces settlement
- **WHEN** concurrent contributions are admitted around the funding target
- **THEN** their durable sequence determines the crossing split, and replay yields identical accepted and refunded amounts

#### Scenario: integer apportionment cannot leak value
- **WHEN** funded value or a refund is divided among contributors
- **THEN** deterministic integer shares sum exactly to the distributable amount

### Requirement: Revenue pays frozen lineage before contributor ownership
At capability mint, the system SHALL freeze the base-lineage obligations and contributor ownership table for that version. Every realized revenue event SHALL first satisfy the frozen lineage share, then distribute the remaining owner share through canonical exact apportionment, with both legs and the total conserving. A derived chain SHALL compose through each model's own frozen table in separate bounded events so one revenue event never recurses unboundedly through ancestry.

#### Scenario: a derived capability pays its base on every revenue event
- **WHEN** a pooled derivative records realized paid revenue
- **THEN** the event applies its frozen base-lineage share before owner distribution and records exact balanced postings

### Requirement: V1 ownership is revenue-bearing and non-transferable
V1 shares SHALL be the accepted-contribution integers, immutable at capability mint. They SHALL confer attributable revenue, provenance credit, and governance-lite votes to relicense or open-weight through existing gate/consultation machinery; they SHALL NOT be sellable, assignable, collateralizable, or transferable. Every attempted transfer surface SHALL return a stable refusal and move no ownership or value.

#### Scenario: a share-transfer request is refused
- **WHEN** an owner attempts to transfer or sell a pooled share
- **THEN** the system returns the v1 non-transferable reason and leaves the ownership table unchanged

### Requirement: Pool terms expose risk and terminal refund semantics before funding
Before accepting funds, a pool SHALL display schedule, checkpoints, verification, fees, loss risk, cancellation, failure, unspent-refund, ownership, lineage, and non-transferability terms bound to the instrument version. Pools SHALL fund cost, not worth: the platform quotes input cost from market indices and SHALL NOT promise investment return or model value. Shares SHALL remain proportional to accepted money, so splitting one contribution across wallets produces the same aggregate payout and confers no sybil advantage. A terminal failed run SHALL refund only durably unspent escrow under exact contributor apportionment; already earned execution payment SHALL not be clawed back silently.

#### Scenario: terminal failure refunds only unspent escrow
- **WHEN** a funded run reaches a terminal failure after some verified work has settled
- **THEN** the remaining escrow is apportioned exactly to eligible contributors and prior valid payments remain auditable
