# Paid Market Economy

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

The built token/market/settlement subset: a pure, I/O-free market microstructure library, the flag-gated escrow money path with integer MicroTokens, file-backed node bids with atomic claim and write-once settlement, and conserved basis-point treasury math.

## Requirements

### Requirement: The money path is flag-gated off and pre-launch
Every value-moving paid-market action SHALL be inert unless `TINYASSETS_PAID_MARKET` is truthy (`on`/`1`/`true`/`yes`), and the flag SHALL default off. Under flag-off, the escrow money actions (`escrow_lock`, `escrow_release`, `escrow_refund`, `escrow_fund`, `escrow_set_wallet`, `escrow_withdraw` in the paid-market API) SHALL return a `not_available` status instead of touching funds, and the `NodeBidProducer` SHALL NOT register, so the dispatcher never sees bid tasks. Read-only surfaces (escrow inspect/balance, treasury status) SHALL remain available regardless of the flag, because a read cannot move money. On-chain withdrawal defaults to a testnet chain (Base Sepolia), confirming the path is pre-launch.

#### Scenario: mutating escrow action is inert under flag-off
- **WHEN** `TINYASSETS_PAID_MARKET` is unset or off and a caller invokes `escrow_lock`, `escrow_fund`, or `escrow_withdraw`
- **THEN** the action returns `{"status": "not_available"}` with a message naming `TINYASSETS_PAID_MARKET=on`
- **AND** no escrow, settlement, or wallet record is written

#### Scenario: bid producer does not register under flag-off
- **WHEN** `register_if_enabled` runs while the flag is off
- **THEN** the `NodeBidProducer` is not registered
- **AND** the dispatcher produces no bid-backed `BranchTask`s

#### Scenario: reads stay available regardless of the flag
- **WHEN** the flag is off and a caller invokes `escrow_inspect`, `escrow_balance`, or treasury status
- **THEN** the read returns its summary without a `not_available` gate

### Requirement: Money actions operate only on the authenticated actor
Value-moving actions (fund, set-wallet, withdraw, lock) SHALL act on the authenticated actor resolved from auth context, never on a caller-supplied identity. A caller-supplied `staker_id` SHALL be honored only when it equals the authenticated actor, or when the authenticated actor is the configured host (`UNIVERSE_SERVER_HOST_USER`) acting explicitly on another's behalf; any other cross-actor attempt SHALL be rejected with an error and no state change. A lock SHALL reserve the caller's own funded budget, and release/refund SHALL be authorized against the lock's own staker (or host), so a write-scoped caller cannot fund, withdraw, redirect, or cancel another actor's escrow by id. As-built limitation (security concern, STATUS.md 2026-07-19): the "authenticated actor" is resolved by the ledger-attribution helper `_current_actor()` (`tinyassets/api/engine_helpers.py`), which falls back to the `UNIVERSE_SERVER_USER` environment variable on authless paths — escrow authorization then derives identity from daemon environment rather than a verified subject, and an env identity equal to `UNIVERSE_SERVER_HOST_USER` would carry host on-behalf rights. The hardened no-env-fallback resolver (`tinyassets/api/permissions.py`) is not yet the money-path authority; the default-off money flag is the operative mitigation.

#### Scenario: cross-actor escrow attempt is rejected
- **WHEN** an authenticated actor supplies a `staker_id` that is neither themselves nor (when they are host) an on-behalf target, for `escrow_fund`, `escrow_set_wallet`, or `escrow_withdraw`
- **THEN** the action returns a `rejected` status stating money actions operate on your own escrow only
- **AND** no funds, wallet address, or withdrawal are recorded

#### Scenario: host may act on behalf of another actor
- **WHEN** the authenticated actor equals `UNIVERSE_SERVER_HOST_USER` and supplies another actor's `staker_id`
- **THEN** the action proceeds against that actor's escrow

### Requirement: Payment-core conversions produce integers while legacy bids permit non-integer scalars
The payments core SHALL construct `MicroToken` through Python's `int` boundary
after rejecting values that compare below zero, and subtraction below zero
SHALL raise. Current money-action transports SHALL also call `int(...)`; a
fractional JSON number can therefore be truncated and `True` becomes `1`, while
`False` becomes `0` and mutating payment actions subsequently reject converted
amounts less than or equal to zero. A fractional string that `int(...)` cannot
parse SHALL be rejected. `NodeBid.bid` SHALL preserve the caller/YAML scalar
type without runtime coercion, so float bids are permitted, while v1 settlement
serialization SHALL coerce `bid_amount` to float.

#### Scenario: negative payment-core money is rejected
- **WHEN** code constructs `MicroToken(-1)` or subtracts past zero
- **THEN** a `ValueError` is raised

#### Scenario: current transport conversion can truncate a numeric fraction
- **WHEN** a money action receives a positive fractional JSON number such as `1.5`
- **THEN** current `int(...)` conversion passes `1` to the action rather than rejecting the fraction at transport
- **AND** a converted amount less than or equal to zero is rejected by the mutating payment action
- **AND** a fractional string such as `"1.5"` is rejected because `int(...)` cannot parse it

#### Scenario: legacy bid storage permits float amounts
- **WHEN** a `NodeBid` receives and serializes a fractional float bid
- **THEN** its runtime/YAML representation preserves that supplied scalar type
- **AND** a v1 settlement derived from it serializes `bid_amount` as a float

### Requirement: Paid-market computation library is pure and I/O-free
The `tinyassets/paid_market/` package (spot index, buckets, forwards, ceiling, training, pools, fund, licenses, shuttles, fabrication, matching, ledger) SHALL contain no I/O: it reads no files, opens no database, and reads no environment — transport layers sit on top of it. Every money-path computation SHALL be integer or `Fraction` exact with conservation invariants asserted internally, so a rounding residue can never silently create or destroy value. As-built, this library is a complete, tested subset with no live money-moving MCP transport wired to it; its only importers are the package's own modules and the test suite.

#### Scenario: library performs no I/O
- **WHEN** the paid-market computation modules are imported and exercised
- **THEN** no file, database, or environment access occurs within the package

#### Scenario: exact-arithmetic conservation holds
- **WHEN** a paid-market computation apportions or splits an amount
- **THEN** the parts sum exactly to the input with no float residue

### Requirement: Node bids are file-backed with atomic single-claim
A node bid SHALL be a cross-universe, single-node execution request persisted as `bids/<node_bid_id>.yaml` under the repo root. Claiming a bid SHALL be atomic: under a per-bid file lock the claimer SHALL assert the bid is `open`, rename it to a `claimed_by_<daemon>` record with status `claimed:<daemon_id>`, then (when a git remote exists) commit and push; a failed push SHALL revert the working tree and delete any partial bid outputs, returning no claim so two daemons cannot both win the same bid. Reads SHALL treat the filename stem as the authoritative id (defeating rename-in-place tampering) and SHALL skip malformed YAML with a warning rather than raising.

#### Scenario: only one daemon wins a contested bid
- **WHEN** a bid is `open` and one claimer completes the rename-and-push while another loses the remote race
- **THEN** the losing claim reverts its working tree, removes partial outputs, and returns no bid
- **AND** exactly one `claimed_by_<daemon>` record exists

#### Scenario: malformed bid file is skipped, not fatal
- **WHEN** the bids directory contains an unparseable or non-mapping YAML file
- **THEN** it is logged and skipped
- **AND** the remaining valid bids are still read

### Requirement: Settlement recording rejects pre-existing paths sequentially but is not race-atomic
`record_settlement_event` SHALL validate `outcome_status`, derive the v1
repo-root settlement path, reject a path that already exists, and then write the
YAML record with ordinary `Path.write_text`. This check-then-write boundary
SHALL protect sequential calls but SHALL NOT provide an atomic single-winner
guarantee for concurrent writers that both observe the path as absent.

#### Scenario: sequential double-settle is refused
- **WHEN** a settlement path already exists and recording is attempted again
- **THEN** `SettlementExistsError` is raised
- **AND** the existing record is left unchanged

#### Scenario: invalid outcome status is rejected
- **WHEN** a settlement is recorded with an `outcome_status` other than `succeeded` or `failed`
- **THEN** a `ValueError` is raised and no file is written

#### Scenario: concurrent creation has no single-winner guard
- **WHEN** two writers both pass the path-existence check before either ordinary write completes
- **THEN** the current recorder does not guarantee a single winner
- **AND** a later write may replace the earlier record

### Requirement: Treasury take is conserved basis-point math with a read-only status surface
The treasury SHALL compute its take as pure integer basis-point math: a 1% platform take (100 bp) split 50/50 between a bounty pool and treasury retention, using floor division so `net_to_claimer + bounty_pool + treasury_retained` equals the settlement amount exactly. The treasury/cost-ledger status surface SHALL be strictly read-only — it SHALL NOT run migrations, create the database, or lock/release/refund/batch/spend — reporting `autonomous_spend_allowed: false` and treating a missing database or table as zeroed sections so a status check can never become an implicit payment write. It is exposed as an economy read on the universe MCP tool.

#### Scenario: the split conserves the settlement amount
- **WHEN** `split_take` runs on a settlement amount
- **THEN** it returns `(net_to_claimer, bounty_pool, treasury_retained)` summing exactly to the amount
- **AND** each part is a non-negative integer computed by floor division

#### Scenario: status never writes
- **WHEN** treasury status runs against a missing or empty database
- **THEN** it returns zeroed sections with `read_only: true` and `autonomous_spend_allowed: false`
- **AND** creates no database, table, or ledger entry

### Requirement: The pure spot oracle uses settled-trade windows and pair-capped weights
The I/O-free spot oracle SHALL validate one capability's positive integer settled trades, select a trailing 24-hour window or widen to seven days when fewer than `min_trades` exist, and return no VWAP when the widened window remains thin. It SHALL compute exact direction-insensitive counterparty-pair weights, equal-weight an infeasibly thin market, floor the resulting VWAP, and clamp a present above-market VWAP to the caller-supplied ceiling while retaining the raw value. The cap is per pair, not per user; best ask and ceiling are caller inputs, and the oracle has no feed, cache, persistence, or publication behavior.

#### Scenario: a thin market does not invent a VWAP
- **WHEN** fewer than `min_trades` exist across the trailing seven-day window
- **THEN** `compute_spot_quote` returns `vwap_micros: null`, no VWAP window, and the caller-supplied best ask and ceiling unchanged

#### Scenario: one pair cannot buy volume influence in an infeasible cap market
- **WHEN** the number of counterparty pairs multiplied by the configured pair-share cap is at most one
- **THEN** `capped_pair_weights` assigns equal weight to every pair regardless of raw pair volume

#### Scenario: an above-ceiling VWAP is flagged and clamped
- **WHEN** the exact raw VWAP exceeds a non-null caller-supplied ceiling
- **THEN** the quote retains the raw VWAP, publishes the ceiling as its VWAP, and sets `above_ceiling: true`

### Requirement: Bucket and hosted-price helpers fail loud without performing transport
The pure bucket helpers SHALL reject naive datetimes, normalize any timezone-aware datetime to UTC, enforce the supported 8-, 24-, and 168-hour widths and their UTC alignment, reject starts outside the configured horizon, and enumerate deterministic starts. The hosted-price helper SHALL parse supported model-price payloads and convert decimal USD-per-token strings into floored integer micros-per-million-tokens without fetching or caching the payload itself.

#### Scenario: aware timestamps normalize while naive timestamps fail
- **WHEN** bucket validation receives a timezone-aware non-UTC datetime
- **THEN** it converts the instant to UTC before checking alignment and horizon
- **AND** a naive datetime raises `BucketError`

#### Scenario: hosted price conversion is deterministic integer arithmetic
- **WHEN** a valid decimal USD-per-token value is converted
- **THEN** the result is a floored integer micros-per-million-tokens value with no floating-point money arithmetic

### Requirement: Forward validation and settlement are pure, monotone, and conservation-exact
The forward oracle SHALL allow only `open→sold→delivering→settled` or `open→expired`, restrict contract sizes to 1, 10, or 100 million tokens, validate collateral percentages from 5 through 100, and compute demand-relative settlement using exact integer arithmetic. Seller payment SHALL be reduced pro-rata by unserved exercised demand, a buyer no-show SHALL pay the seller for reserved capacity, the delivery threshold SHALL gate collateral slashing only, slash proceeds SHALL compensate the buyer, and buyer funds plus collateral SHALL each conserve exactly. The oracle performs no posting, locking, persistence, or money movement.

#### Scenario: buyer no-show cannot grief reserved capacity
- **WHEN** a buyer requests zero tokens during a valid sold capacity window
- **THEN** the seller receives the full gross price less the floor-rounded treasury fee, the buyer receives no price refund, and no collateral is slashed

#### Scenario: a missed obligation refunds and slashes pro-rata
- **WHEN** the caller-supplied delivered count serves less exercised demand than the configured threshold
- **THEN** payment is reduced by the unserved share, the buyer receives the exact residual refund plus the floor-rounded collateral slash, and both conservation checks pass

### Requirement: Training checkpoint settlement is a pure trusted-count oracle
The training oracle SHALL settle a positive total price across contracted, scheduled, and caller-verified checkpoint counts, cap scheduled counts at contracted counts and verified counts at scheduled counts, and preserve the forward oracle's demand-relative payment, threshold-only slashing, buyer compensation, and exact conservation. It trusts the supplied verified count and performs no attestation, checkpoint release, persistence, gate evaluation, or minting.

#### Scenario: early cancellation with every reached checkpoint verified pays in full
- **WHEN** a run schedules fewer checkpoints than contracted and every scheduled checkpoint is supplied as verified
- **THEN** the seller earns the full gross reservation price, subject only to the treasury fee, with no refund or slash

#### Scenario: a missed scheduled checkpoint is settled exactly
- **WHEN** verified checkpoints are fewer than scheduled checkpoints
- **THEN** `settle_training_window` produces pro-rata payment, refund, and slash values whose buyer-fund and collateral invariants both conserve

### Requirement: Declared license terms compose fail-closed as a pure lattice
The license helper SHALL resolve only non-empty identifiers present in its curated in-process registry, reject an empty input set, reject any unrecognized or no-derivatives input, and compose accepted inputs by unioning all restriction flags. It SHALL return deterministic composed terms but does not authenticate declarations or enforce them at a training-run or mint boundary.

#### Scenario: unknown or no-derivatives input is rejected
- **WHEN** `check_trainable` receives an unregistered license or a registered no-derivatives license
- **THEN** it raises `LicenseError` before returning composed terms

#### Scenario: restrictions can only accumulate
- **WHEN** permissive and share-alike or named-redistribution inputs are composed
- **THEN** every restriction present on any input remains present on the composed terms

### Requirement: Pool funding and revenue apportionment conserve caller-supplied order and shares
The pool helpers SHALL process contributions in caller-supplied order, split only the contribution that crosses a funding target, refund late and unused amounts, and satisfy `accepted + refunded == paid` for every contribution. Exact apportionment SHALL use deterministic largest-remainder allocation with stable tie-breaking, and a caller-supplied single-event lineage/contributor split SHALL conserve the revenue amount. The helpers do not persist arrival order, ownership, lineage tables, or revenue events.

#### Scenario: a crossing contribution is split exactly
- **WHEN** an ordered contribution crosses the remaining pool target
- **THEN** only the amount needed is accepted, its remainder and all later contributions are refunded, and the pool totals conserve

#### Scenario: largest-remainder allocation leaks no units
- **WHEN** an integer amount is apportioned across positive weights
- **THEN** deterministic shares sum exactly to the input amount

### Requirement: Shuttle allocation and break-even arithmetic are total-first and deterministic
The shuttle helper SHALL validate positive die area and design areas, reject overcommit or fill below the configured minimum, floor the used-area share of full-die cost, apportion that integer cost exactly by design area with deterministic largest-remainder rounding, and report the operator-fee share within the used cost. Removing a design recomputes the floored used cost and apportionment, so another design's integer allocation may change by rounding. The break-even helper SHALL return the ceiling-rounded number of units needed to recover non-recurring cost from positive per-unit margin, or `None` when the margin is non-positive. It accepts numeric design data only and enforces no FPGA or fabrication gate.

#### Scenario: shuttle allocation conserves the floored used-area cost
- **WHEN** a viable set of positive design areas is allocated on a die
- **THEN** deterministic design costs sum exactly to `floor(total_cost × used_area / die_area)`

#### Scenario: non-positive margin has no break-even
- **WHEN** unit price is less than or equal to unit variable cost
- **THEN** `break_even_units` returns `None`

### Requirement: Fabrication quotation, ranking, and settlement fail closed at their pure boundaries
The fabrication helpers SHALL compute total-first integer quotes, calculate distance only as a pure numeric helper, exclude offers that match no declared shipping band rather than extrapolating, rank eligible sellers deterministically, and settle accepted units, rejected units, shipping disposition, treasury fee, seller net, and buyer refund with exact conservation. They perform no artifact admission, seller discovery, shipping lookup, QA gate, persistence, or payment.

#### Scenario: an uncovered shipping distance excludes the seller
- **WHEN** a buyer distance falls outside every shipping band declared by an offer
- **THEN** seller ranking excludes that offer rather than estimating a price

#### Scenario: partial physical acceptance conserves payment
- **WHEN** fewer units are accepted than delivered
- **THEN** the pure settlement assigns seller net, treasury fee, shipping disposition, and buyer refund that sum exactly to the paid total

### Requirement: Treasury-internal fund arithmetic refuses ambiguous bootstrap state
The fund helpers SHALL calculate floor-rounded NAV, mint and redeem with rounding in the fund's favor, retain explicit entry/exit fees in AUM, compute reserve-bound redemption capacity, and support exact final wind-down. An empty fund SHALL bootstrap at one-to-one; a fund with AUM but zero supply SHALL reject minting rather than pricing a pre-seeded treasury implicitly. The helpers accept caller-computed AUM and perform no valuation, custody, public minting, governance, or settlement integration.

#### Scenario: a pre-seeded zero-supply fund refuses minting
- **WHEN** fund AUM is positive while token supply is zero
- **THEN** `mint_at_nav` raises `FundError` rather than granting the first minter ownership of pre-existing assets

#### Scenario: a mint-redeem round trip cannot extract value
- **WHEN** an actor mints and immediately redeems against unchanged fund state
- **THEN** floor rounding and configured fees prevent the actor from receiving more base value than supplied

### Requirement: Pure matching and ledger-entry builders fail loud and balance
The matching helper SHALL solve the discrete 0/1 covering problem over validated 1-, 10-, and 100-million-token offers, returning the minimum-total-cost subset that covers the requested size with ties broken by total size and lexicographic offer ids; insufficient aggregate supply SHALL return `None`. The in-memory ledger SHALL require a non-empty list of `(non-empty account, integer delta)` entries whose signed deltas zero-sum, allow negative and zero deltas, and reject an internal-account overdraft atomically while permitting negative `external:` contra balances. Entry builders SHALL validate their positive source amounts and construct balanced postings for escrow locks, forward sales and settlements, training settlements, physical settlements, and pool closure. They do not provide durable transaction serialization or live money movement.

#### Scenario: insufficient executable supply returns no fill
- **WHEN** eligible book offers cannot fill the requested quantity under the caller's constraints
- **THEN** `best_execution` returns `None` rather than returning an underfilled execution

#### Scenario: an invalid or overdrawing posting is rejected atomically
- **WHEN** entries do not zero-sum, contain a non-integer delta or empty account, or would overdraw an internal account
- **THEN** the pure ledger raises `LedgerError` and changes no balance
