## ADDED Requirements

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
Value-moving actions (fund, set-wallet, withdraw, lock) SHALL act on the authenticated actor resolved from auth context, never on a caller-supplied identity. A caller-supplied `staker_id` SHALL be honored only when it equals the authenticated actor, or when the authenticated actor is the configured host (`UNIVERSE_SERVER_HOST_USER`) acting explicitly on another's behalf; any other cross-actor attempt SHALL be rejected with an error and no state change. A lock SHALL reserve the caller's own funded budget, and release/refund SHALL be authorized against the lock's own staker (or host), so a write-scoped caller cannot fund, withdraw, redirect, or cancel another actor's escrow by id.

#### Scenario: cross-actor escrow attempt is rejected
- **WHEN** an authenticated actor supplies a `staker_id` that is neither themselves nor (when they are host) an on-behalf target, for `escrow_fund`, `escrow_set_wallet`, or `escrow_withdraw`
- **THEN** the action returns a `rejected` status stating money actions operate on your own escrow only
- **AND** no funds, wallet address, or withdrawal are recorded

#### Scenario: host may act on behalf of another actor
- **WHEN** the authenticated actor equals `UNIVERSE_SERVER_HOST_USER` and supplies another actor's `staker_id`
- **THEN** the action proceeds against that actor's escrow

### Requirement: All money amounts are integer MicroTokens, never floats
The payments subsystem SHALL represent every currency amount as `MicroToken`, an immutable non-negative `int` subclass (1 Token = 1,000,000 MicroTokens), so no settlement value is ever a float. Constructing a negative `MicroToken` SHALL raise, and a subtraction that would go negative SHALL raise rather than wrap. Money-action transports SHALL coerce a supplied `amount` to `int` and reject a non-integer amount with an error rather than silently rounding.

#### Scenario: negative money is impossible
- **WHEN** code constructs `MicroToken(-1)` or subtracts past zero
- **THEN** a `ValueError` is raised

#### Scenario: non-integer amount is rejected at the transport
- **WHEN** an escrow money action receives an `amount` that does not parse as an integer
- **THEN** the action returns a `rejected` status naming the bad amount
- **AND** performs no money movement

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

### Requirement: Settlement records are immutable and write-once
Bid settlement SHALL append a repo-root-level record at `settlements/<bid_id>__<daemon_id>.yaml` carrying `schema_version: "1"`, the requester/owner/daemon identities, bid amount, evidence URL, completion timestamp, an `outcome_status` of exactly `succeeded` or `failed`, and `settled: false`. Recording SHALL be write-once: a second record for the same `(bid_id, daemon_id)` pair SHALL raise `SettlementExistsError` rather than overwrite, and an `outcome_status` outside the allowed set SHALL raise. v1 records SHALL never be rewritten, so the audit trail survives a future token-launch migration byte-for-byte.

#### Scenario: double-settle is refused
- **WHEN** a settlement already exists for a `(bid_id, daemon_id)` pair and recording is attempted again
- **THEN** `SettlementExistsError` is raised
- **AND** the existing record is left unchanged

#### Scenario: invalid outcome status is rejected
- **WHEN** a settlement is recorded with an `outcome_status` other than `succeeded` or `failed`
- **THEN** a `ValueError` is raised and no file is written

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
