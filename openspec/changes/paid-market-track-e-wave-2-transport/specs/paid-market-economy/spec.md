## MODIFIED Requirements

### Requirement: Money actions operate only on the authenticated actor
Value-moving actions (fund, set-wallet, withdraw, lock, claim, settle, refund, release, slash) SHALL act only under an authenticated actor resolved from the hardened request-auth context, never from a caller-supplied identity or `UNIVERSE_SERVER_USER` / `UNIVERSE_SERVER_HOST_USER` environment fallback. A caller-supplied `staker_id` SHALL be honored only when it equals the authenticated actor, or when an authenticated configured host with an explicit on-behalf capability targets another actor; any other cross-actor attempt SHALL be rejected with no state change. The transport SHALL derive buyer, seller, escrow, and collateral accounts from locked business rows and SHALL accept the treasury account only from fixed server configuration. Wave 2 SHALL reject caller-supplied treasury accounts and all `external:*` or `pool:*` accounts; external funding requires a separately reviewed receipt-verified ingress. Release/refund SHALL also be authorized against the lock's persisted owner (or the explicitly authorized host), so a write-scoped caller cannot fund, withdraw, redirect, claim, or cancel another actor's money by id.

#### Scenario: cross-actor escrow attempt is rejected
- **WHEN** an authenticated actor supplies a `staker_id` or account owner that is neither themselves nor an explicitly authorized on-behalf target
- **THEN** the action returns a rejected status stating money actions operate only within the actor's authority
- **AND** no funds, wallet address, claim, posting, or withdrawal is recorded

#### Scenario: environment identity grants no money authority
- **WHEN** an unauthenticated request runs while `UNIVERSE_SERVER_USER` or `UNIVERSE_SERVER_HOST_USER` names a privileged actor
- **THEN** every value-moving action is rejected
- **AND** the environment value is not used as the ledger actor

#### Scenario: authenticated host acts only under an explicit grant
- **WHEN** the authenticated actor is the configured host and holds the explicit on-behalf capability for the target actor
- **THEN** the action proceeds against that target's escrow
- **AND** the audit record identifies both host actor and target actor

### Requirement: Paid-market computation library is pure and I/O-free
The `tinyassets/paid_market/` package (spot index, buckets, forwards, ceiling, training, pools, fund, licenses, shuttles, fabrication, matching, ledger) SHALL contain no I/O: it reads no files, opens no database, and reads no environment. Transport code SHALL sit outside the package, call its matcher and named posting adapters, and persist their outputs without recomputing settlement math. Every money-path computation SHALL be integer or `Fraction` exact with conservation invariants asserted internally, so a rounding residue can never silently create or destroy value. Persisted results SHALL be differential-checked against the pure `Ledger` oracle in tests and SHALL fail loud on divergence.

#### Scenario: transport consumes a pure adapter without adding I/O
- **WHEN** a transport settlement is computed and persisted
- **THEN** the named `tinyassets.paid_market.ledger` adapter produces the posting list
- **AND** no file, database, environment, or network access occurs within `tinyassets.paid_market`

#### Scenario: library modules perform no I/O
- **WHEN** the `tinyassets.paid_market` modules are imported and exercised
- **THEN** they read no file, database, environment variable, or network resource

#### Scenario: exact-arithmetic conservation holds
- **WHEN** a paid-market computation apportions or splits an amount
- **THEN** the parts sum exactly to the input with no float residue

#### Scenario: matching uses the executable oracle
- **WHEN** persisted offers must cover a requested standard-size amount
- **THEN** the transport calls `match.best_execution` with the eligible snapshot
- **AND** it does not substitute greedy, partial, or hand-written SQL matching

### Requirement: Settlement records are immutable and write-once
Legacy repo-file node-bid settlement SHALL remain a repo-root-level record at `settlements/<bid_id>__<daemon_id>.yaml` with `schema_version: "1"`, the requester/owner/daemon identities, bid amount, evidence URL, completion timestamp, an `outcome_status` of exactly `succeeded` or `failed`, and `settled: false`. Recording SHALL remain write-once: a second record for the same `(bid_id, daemon_id)` pair SHALL raise `SettlementExistsError` rather than overwrite, and an invalid `outcome_status` SHALL raise. v1 YAML and `public.ledger` SHALL remain byte-for-byte historical and SHALL receive no new Wave 2 money writes. New dark-path accounting SHALL write only through the double-entry `market.*` transport, with no shim or dual-write path.

#### Scenario: v1 settlement history stays frozen
- **WHEN** Wave 2 transport artifacts are installed or exercised in dark mode
- **THEN** existing settlement YAML and `public.ledger` rows remain unchanged
- **AND** no new `public.ledger` row is written by the Wave 2 path

#### Scenario: double-settle is refused
- **WHEN** a v1 settlement already exists for a `(bid_id, daemon_id)` pair and recording is attempted again
- **THEN** `SettlementExistsError` is raised
- **AND** the existing record is left unchanged

#### Scenario: invalid outcome status is rejected
- **WHEN** a v1 settlement is recorded with an `outcome_status` other than `succeeded` or `failed`
- **THEN** a `ValueError` is raised and no file is written

## ADDED Requirements

### Requirement: Paid-market claims are narrow, exact, and atomic
The Postgres paid-request claim transport SHALL claim only eligible offered work in one transaction. Every offer row SHALL carry a monotonic `version` used by compare-and-set. A single-request claim SHALL lock only the addressed request/bid rows. A multi-offer purchase SHALL call `match.best_execution` on a versioned eligible snapshot, lock the selected IDs in canonical order, verify state and version, and transition all selected rows atomically. A stale selected row SHALL roll back and permit at most three jittered recomputations; exhaustion SHALL return an honest contention result rather than a partial fill or retry storm. This claim domain SHALL NOT replace the separate repo-file node-bid claim path.

#### Scenario: exactly one claimer wins a paid request
- **WHEN** multiple eligible actors concurrently claim the same offered paid request
- **THEN** exactly one atomic state transition succeeds
- **AND** every loser receives a clean contention result with no partial state

#### Scenario: selected offer changes before claim
- **WHEN** `best_execution` selects multiple offers and any selected version is stale at lock time
- **THEN** no selected offer is claimed in that transaction
- **AND** the transport either recomputes within the bounded retry budget or reports contention

#### Scenario: insufficient supply stays honest
- **WHEN** `best_execution` returns no covering set
- **THEN** the transport records no claim
- **AND** it does not silently accept a partial fill

### Requirement: Wave 2 settlement is atomic, non-custodial, and dark by default
Wave 2 transport SHALL combine business-state compare-and-set, body-bound idempotency, adapter-derived postings, `market.apply_tx`, and every required escrow/collateral drain assertion in one server-side database transaction. Any authorization, oracle, overdraft, residual, state, or transport failure SHALL roll back the entire transaction. The platform SHALL remain non-custodial: real escrow and payout authority stay in Base smart contracts, PostgreSQL stores only bounded accounting/intent and observed receipt state, and the platform stores no user signing keys. The transport SHALL remain unreachable from live claim/settle paths while `TINYASSETS_PAID_MARKET` is off and until distributed-execution S14/B36, independent review, and host-approved cutover are complete.

#### Scenario: successful dark settlement conserves and drains
- **WHEN** an authorized dark-path settlement uses a pure adapter and valid current business state
- **THEN** integer-micro postings commit exactly once and sum to zero
- **AND** every temporary escrow/collateral account is zero in the same committed transaction

#### Scenario: residual escrow aborts everything
- **WHEN** a settlement posting set would leave any required escrow or collateral account non-zero
- **THEN** the drain assertion fails loud
- **AND** no business-state change, transaction, posting, or balance update commits

#### Scenario: live payout remains unavailable before authority cutover
- **WHEN** distributed-execution S14/B36 or host-approved cutover is incomplete
- **THEN** no public/API path can activate a market claim, settlement, or on-chain payout
- **AND** read-only market state remains available only with an explicit dark/unavailable status

#### Scenario: database response loss cannot apply twice
- **WHEN** a caller loses the response after a settlement attempt
- **THEN** a retry with the same body-bound idempotency key returns the prior database transaction
- **AND** the system creates no second database effect

### Requirement: The ledger boundary is least-privilege and bounded
Ledger tables, sequences, raw apply functions, and drain helpers SHALL deny access to `PUBLIC`, anonymous, authenticated, and ordinary application roles. A fixed-search-path `SECURITY DEFINER` wrapper owned by a non-login role SHALL be callable only by a dedicated internal settlement role after actor/account binding. The wrapper SHALL derive business accounts from locked rows, use only the configured treasury account, and reject `external:*` and `pool:*` accounts. Wave 2 SHALL reject more than 16 postings, idempotency keys over 128 UTF-8 bytes, memos over 512 bytes, account names over 256 bytes, or canonical posting payloads over 16 KiB before mutation.

#### Scenario: account provenance cannot be forged
- **WHEN** a caller supplies a treasury, external, pool, or business account that differs from the trusted configuration or locked business rows
- **THEN** the wrapper rejects the request before ledger execution
- **AND** no transaction, posting, or balance changes

#### Scenario: public and user roles cannot invoke ledger writers
- **WHEN** public, anonymous, authenticated, or ordinary application roles attempt direct table DML or raw ledger RPC execution
- **THEN** PostgreSQL denies the operation
- **AND** only the dedicated internal settlement role can invoke the bounded wrapper

#### Scenario: hostile search path cannot redirect the ledger function
- **WHEN** a caller creates lookalike objects in a writable schema and invokes the settlement wrapper
- **THEN** the fixed trusted search path resolves only the intended ledger objects
- **AND** no attacker-controlled object is executed

#### Scenario: oversized settlement is rejected before mutation
- **WHEN** any posting-count or byte-size bound is exceeded
- **THEN** the wrapper rejects the request with a bounded validation error
- **AND** creates no transaction or posting row
