## ADDED Requirements

### Requirement: One authenticated transaction transport owns all market money movement
Every market debit, credit, escrow transition, fee, refund, and collateral movement SHALL execute through one versioned authenticated double-entry transaction boundary owned by `paid-market-economy`. Direct SQLite side paths SHALL be removed before launch, schema history SHALL precede prototype migrations 006-008, and each operation SHALL be idempotent and differential-tested against the canonical pure ledger and settlement oracles.

#### Scenario: a settlement posts through the single transport
- **WHEN** an authorized spot, forward, training, data, pool, or fabrication settlement is committed
- **THEN** one idempotent transaction balances every posting and no alternate payment helper mutates the same funds

#### Scenario: transport agrees with the pure oracle
- **WHEN** generated valid and invalid transaction cases are evaluated by the transport and canonical pure oracle
- **THEN** accepted state, rejection boundaries, rounding, and conservation match exactly

### Requirement: Future market transports remain differential-tested against canonical pure oracles
Every transport introduced by this change SHALL consume the canonical `tinyassets.paid_market` input/output contracts or prove behavioral equivalence through generated differential tests covering valid inputs, rejection boundaries, rounding, state transitions, and conservation. A transport SHALL NOT silently fork a formula into SQL, HTTP, MCP, or workflow code; any intentional rule change MUST first modify the canonical oracle requirement and tests through its own OpenSpec change.

#### Scenario: transport and oracle cannot drift silently
- **WHEN** a transport implementation changes a price, settlement, apportionment, fee, refund, collateral, or NAV result for the same inputs
- **THEN** the differential gate fails until an explicit reviewed behavior change updates both canonical contract and implementation
