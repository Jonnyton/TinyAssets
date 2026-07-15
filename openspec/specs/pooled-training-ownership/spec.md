# Pooled Training & Fractional Model Ownership

## Purpose

Democratize the CAPITAL behind pretraining: many users fund one training goal,
the run pays from the pool, and the minted model is owned fractionally by its
funders — with revenue flowing back automatically when the model earns on the
inference market. Track H is pure composition of owned primitives (goal pools,
attribution provenance, outcome gates, and a compute market adjacent to each
other).

Historical source of record (untouched): `docs/exec-plans/active/2026-07-08-track-h-pooled-training-ownership.md`.
Exactness-critical math (implemented + conservation sweeps): `tinyassets/paid_market/pool.py`.
Composes: Track E (escrow, price index), Track F (training instruments, checkpoint settlement, capability minting), plus `goal_pool/` and the attribution chain (`record_remix` / `get_provenance` in `api/market.py`).

## Requirements

### Requirement: The math that must not drift (implemented)

The system SHALL enforce the following exact computations, each conservation-swept
in code. Funding close (`settle_pool_funding`): contributions processed in
arrival order (order is consensus-critical and SHALL be persisted); the crossing
contribution splits exactly (accepted part + refunded overshoot); late
contributions refunded whole; a failed pool refunds everything; per-contributor
`accepted + refunded == paid`, always. Revenue apportionment (`apportion_exact`):
largest-remainder apportionment SHALL guarantee `sum(payouts) == revenue`
exactly, every owner within 1 micro of exact pro-rata, with a deterministic
tie-break (remainder desc, key asc) so every node computes identical payouts.

#### Scenario: naive floor pro-rata leakage is impossible
- **WHEN** revenue is split across owners
- **THEN** largest-remainder apportionment makes `sum(payouts) == revenue` exactly
- **AND** no dust leaks to compound into unbalanceable ledgers

#### Scenario: arrival order is consensus-critical and persisted
- **WHEN** contributions accrue toward a pool target
- **THEN** they are processed in persisted arrival order
- **AND** the crossing contribution splits exactly into accepted plus refunded overshoot

### Requirement: Attribution splits pay the lineage first and jointly conserve

`distribute_revenue` SHALL send `attribution_ppm` of each revenue event to the
lineage owners FIRST, remainder to the model's owners; both legs SHALL apportion
exactly and jointly conserve. The rate SHALL be frozen at mint from remix
records, so derived models pay their base forever. Chains SHALL compose via each
model's own frozen table, so no single revenue event recurses unboundedly.

#### Scenario: a derived model pays its base on every revenue event
- **WHEN** a derived model earns revenue
- **THEN** `attribution_ppm` flows up the lineage first, remainder to owners
- **AND** both legs conserve jointly with no unbounded recursion

### Requirement: Ownership is deliberately minimal in v1 — no secondary share transfer

Shares SHALL be the accepted-contribution integers, immutable at mint. There
SHALL be no secondary transfer of shares in v1 — transferable fractional model
shares walk straight into securities-law territory; that is a legal-review gate,
not an engineering task. v1 owners SHALL receive revenue distribution,
governance-lite (owners vote to re-license or open-weight via existing
gate/consultation machinery), and provenance credit.

#### Scenario: a share-transfer request is refused in v1
- **WHEN** an owner attempts to transfer or sell their shares
- **THEN** the operation is refused (non-transferable in v1)
- **AND** the restriction stands until counsel clears the securities-law gate

### Requirement: Risk is stated on the tin

Pool terms SHALL state that funders bear run risk: if a run fails terminally,
unspent escrow refunds pro-rata to accepted contributions via `apportion_exact`
and the spent portion is gone. Pools SHALL fund cost, not worth — the platform
quotes costs (Track E index), never returns. Shares SHALL be proportional to
money in, so splitting a contribution across wallets splits the payout identically
(sybil-neutral).

#### Scenario: terminal run failure refunds only the unspent portion
- **WHEN** a funded run fails terminally
- **THEN** unspent escrow refunds pro-rata to accepted contributions
- **AND** the spent portion is gone, as the pool terms stated up front

## Open founder decisions

- **Share transfer / secondary market** (Track H §3, §5, §7): revenue-bearing
  fractional ownership is the closest thing in the stack to a security; v1's
  non-transferability is the conservative posture pending counsel. Enabling any
  secondary transfer is a legal-review gate, stacked with the token-architecture
  legal gate — a founder/counsel decision, not an engineering one.
