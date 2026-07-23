## MODIFIED Requirements

### Requirement: Money actions operate only on the authenticated actor
Value-moving actions (fund, set-wallet, withdraw, lock, claim, settle, refund, release, slash) SHALL act only under an authenticated subject and tenant/universe derived from verified request authority, never from caller-supplied identity/tenant fields or `UNIVERSE_SERVER_USER` / `UNIVERSE_SERVER_HOST_USER` environment fallback. Every business, offer, claim, account, escrow, collateral, idempotency, posting, and receipt lookup SHALL use composite tenant keys, and mixed-tenant commands or posting sets SHALL fail before mutation. A caller-supplied `staker_id` SHALL be honored only when it equals the authenticated actor, or when an authenticated configured host presents an immutable signed on-behalf grant that binds grant id, host, target tenant/actor/account, allowed action set, maximum amount, issue/expiry, and revocation generation. The transport SHALL derive buyer, seller, escrow, and collateral accounts from tenant-scoped locked business rows and SHALL accept the treasury account only from fixed server configuration. Wave 2 SHALL reject caller-supplied treasury accounts and all `external:*` or `pool:*` accounts; external funding requires a separately reviewed receipt-verified ingress. Release/refund SHALL also be authorized against the lock's persisted tenant and owner, so a write-scoped caller cannot fund, withdraw, redirect, claim, or cancel another actor's money by id.

#### Scenario: cross-actor escrow attempt is rejected
- **WHEN** an authenticated actor supplies a `staker_id` or account owner that is neither themselves nor an explicitly authorized on-behalf target
- **THEN** the action returns a rejected status stating money actions operate only within the actor's authority
- **AND** no funds, wallet address, claim, posting, or withdrawal is recorded

#### Scenario: environment identity grants no money authority
- **WHEN** an unauthenticated request runs while `UNIVERSE_SERVER_USER` or `UNIVERSE_SERVER_HOST_USER` names a privileged actor
- **THEN** every value-moving action is rejected
- **AND** the environment value is not used as the ledger actor

#### Scenario: authenticated host acts only under an explicit grant
- **WHEN** the authenticated actor is the configured host and presents a current signed on-behalf grant whose target, action, account, amount, tenant, and time bounds cover the request
- **THEN** the action proceeds against that target's escrow
- **AND** the audit record identifies the grant id, host actor, target actor, target tenant, action, and amount

#### Scenario: caller-selected or mixed tenant is rejected
- **WHEN** a command names a tenant different from verified request authority or any locked row/account belongs to another tenant
- **THEN** the trusted wrapper rejects the command before a business or ledger mutation
- **AND** the privileged service role does not act as a cross-tenant deputy

#### Scenario: revoked or overbroad host grant is rejected
- **WHEN** an on-behalf grant is expired, revoked, exceeds its amount, or omits the requested action/account/target
- **THEN** the action is rejected before any lock or posting
- **AND** no environment or host identity broadens the grant

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
Every market value movement SHALL use the named pure adapter and the single internal `market.apply_tx` transport; application code SHALL NOT compute and write balances or ledger rows directly. Wave 2 transport SHALL combine tenant-scoped business-state compare-and-set, actor/account authority, body-bound idempotency, adapter-derived postings, `market.apply_tx`, and every required escrow/collateral drain assertion in one server-side database transaction. The trusted wrapper SHALL ignore any caller-computed hash, recompute SHA-256 over a versioned domain-separated canonical encoding of the complete command, and bind the deterministic tenant-scoped idempotency key to that digest; an identical replay returns the original result, while a supplied-hash mismatch or changed canonical body conflicts. It SHALL coalesce duplicate accounts and acquire every touched row in one reviewed global order: tenant-scoped business rows by type/id, escrow/collateral rows by type/id, idempotency transaction row, then balance accounts lexicographically; postings/audit rows are inserted only after required locks. Any authorization, oracle, overdraft, residual, state, deadlock-order, or transport failure SHALL roll back the entire transaction, and persistent results SHALL be differential-tested against the pure `Ledger` oracle. A completion-dependent settlement SHALL NOT move value until the domain owner validates every normalized delivery field required for that completion; missing or implausible required evidence SHALL reject the completion or enter its domain dispute path before transport invocation. The platform SHALL remain non-custodial: real escrow and payout authority stay in Base contracts, PostgreSQL stores only bounded accounting/intent and observed receipt state, and the platform stores no user signing keys. The transport SHALL remain unreachable from live claim/settle paths while `TINYASSETS_PAID_MARKET` is off and until distributed-execution S14/B36, independent review, and host-approved cutover are complete.

#### Scenario: successful dark settlement conserves and drains
- **WHEN** an authorized dark-path settlement uses a pure adapter and valid current business state
- **THEN** integer-micro postings commit exactly once and sum to zero
- **AND** every temporary escrow/collateral account is zero in the same committed transaction

#### Scenario: inference completion without normalized counts moves no value
- **WHEN** an inference completion omits required normalized input, output, or applicable cached-token evidence
- **THEN** the inference domain rejects completion or opens its dispute path before invoking the transaction transport
- **AND** no completion-dependent funds movement or null-count settlement observation is recorded

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

#### Scenario: concurrent identical replay applies once
- **WHEN** 100 callers concurrently submit the same tenant-scoped idempotency key and identical canonical command
- **THEN** they observe one transaction identity and one applied effect
- **AND** no balance or posting is duplicated

#### Scenario: changed-body replay conflicts
- **WHEN** a caller reuses an idempotency key with a changed memo, account, amount, posting order, or other canonical body field
- **THEN** the transport returns an idempotency conflict
- **AND** the original transaction remains unchanged

#### Scenario: caller hash cannot bless a changed command
- **WHEN** a caller supplies a digest that does not equal the server-recomputed versioned canonical command digest
- **THEN** the wrapper rejects the command before row locks or mutation
- **AND** stores neither the caller digest nor a transaction result

#### Scenario: global lock order avoids cross-family deadlock
- **WHEN** concurrent commands touch overlapping business, escrow, collateral, idempotency, and account rows in different input orders
- **THEN** the wrapper coalesces and locks them in the single canonical order
- **AND** commits or returns clean contention without a deadlock or partial effect

#### Scenario: persistent settlement matches the pure oracle
- **WHEN** randomized adapter transactions run through both the persistent transport and pure `Ledger`
- **THEN** balances, conservation, overdraft decisions, and drain outcomes match
- **AND** any divergence rolls back and fails loud

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

#### Scenario: privileged wrapper independently rechecks row authority
- **WHEN** an internal caller submits command authority that does not match the tenant, actor, amount, accounts, or state on locked business rows
- **THEN** the wrapper rejects before `market.apply_tx`
- **AND** possession of the internal service role does not grant positive market authority

#### Scenario: hostile search path cannot redirect the ledger function
- **WHEN** a caller creates lookalike objects in a writable schema and invokes the settlement wrapper
- **THEN** the fixed trusted search path resolves only the intended ledger objects
- **AND** no attacker-controlled object is executed

#### Scenario: oversized settlement is rejected before mutation
- **WHEN** any posting-count or byte-size bound is exceeded
- **THEN** the wrapper rejects the request with a bounded validation error
- **AND** creates no transaction or posting row

### Requirement: Paid-market migrations are replay-safe and production-native
The v0 fixture PostgreSQL chain SHALL use unique, gap-free, strictly increasing identifiers in dependency order: `001_core_tables`, `002_flags`, `003_rls`, `004_indexes`, `005_seed`, `006_discover_nodes`, `007_token_normalization`, `008_forwards`, and `009_market_ledger`. An advisory-lock-protected runner SHALL store `schema_migrations(version, name, sha256, applied_at)`, check exact-byte hashes, establish/check the discovery vector dependency before use, and commit each migration with its history row in one transaction. Duplicate, missing, reordered, drifted, unverifiable, or lock-contended fixture migrations SHALL fail closed. Public and application roles SHALL NOT alter migration history. Before any live paid-market SQL is authored, a read-only inventory SHALL record the deployed Supabase schemas, extensions, auth, policies, functions, roles, indexes, migration history, and deployment mechanism; production SQL SHALL be authored from the host-approved production baseline and migration home, never copied from the prototype.

#### Scenario: fixture chain applies and resumes exactly once
- **WHEN** the fixture runner applies a fresh, partially applied, or previously verified fixture chain
- **THEN** each pending version and its immutable history row commit exactly once in order
- **AND** a failed version leaves no history row or partial schema mutation

#### Scenario: untracked existing fixture is baselined only after exact verification
- **WHEN** a pre-existing fixture schema has no `schema_migrations` rows
- **THEN** the runner verifies the exact expected tables, columns, functions, policies, constraints, and migration bytes before recording any baseline
- **AND** any mismatch aborts before a later version can apply

#### Scenario: drift or concurrent application fails closed
- **WHEN** migration identifiers have a gap, duplicate, or ordering error, applied bytes change, or concurrent runners contend
- **THEN** no unsafe pending SQL executes
- **AND** the advisory lock serializes one valid runner or returns a bounded failure

#### Scenario: application roles cannot rewrite migration truth
- **WHEN** a public, anonymous, authenticated, or ordinary application role attempts migration-history DML
- **THEN** PostgreSQL denies the operation
- **AND** only the migration role can append a committed history row

#### Scenario: prototype SQL cannot become live authority
- **WHEN** the deployed Supabase inventory, approved production baseline, or deliberate live-apply approval is absent
- **THEN** no production database applies the paid-market migrations
- **AND** the market remains default-off

#### Scenario: populated fixture upgrade remains compatible
- **WHEN** the runner upgrades a populated supported fixture database
- **THEN** both the upgraded application and the prior application version pass their read/write compatibility suites while the market flag remains off
- **AND** rollback to the prior application requires no destructive schema reversal

### Requirement: Wave 2 activation requires concurrency, recovery, and zero-host proof
The Wave 2 transport SHALL remain dark until a production-shaped isolated environment records dated evidence for role isolation, actor binding, body-bound replay, response-loss recovery, matcher/claim contention, ledger conservation, terminal escrow contention, migration recovery, and zero-host behavior. Evidence SHALL include environment, exact commands, load, latency distributions, resource occupancy, and raw failure counts and SHALL receive independent review before host-approved activation.

#### Scenario: capability-sharded claim storm stays correct and bounded
- **WHEN** 500 synthetic daemons receive 1,000 paid requests over five minutes through the production-shaped capability push and narrow claim boundary without mocked delivery
- **THEN** no request is lost or claimed twice and claim latency p99 remains below three seconds
- **AND** the system creates no poll-all retry storm

#### Scenario: offer-book contention never double-sells
- **WHEN** 100 buyers concurrently match and claim from one versioned offer book
- **THEN** no offer is sold twice
- **AND** every committed selection equals `best_execution` for its valid snapshot

#### Scenario: overlapping writers preserve conservation
- **WHEN** at least 64 writers apply at least one million overlapping transfers in the production-shaped test environment
- **THEN** aggregate throughput is at least 5,000 committed transactions per second, p99 is below 250 milliseconds, and balances and postings remain zero-sum with no negative internal balance, deadlock, timeout, or duplicate effect
- **AND** sustained CPU and pool occupancy remain below 80%, with p50, p95, and p99 recorded

#### Scenario: one escrow has one terminal result
- **WHEN** 500 callers concurrently attempt to settle and drain the same escrow
- **THEN** exactly one terminal settlement succeeds
- **AND** every other caller receives the prior result or a clean state/idempotency conflict

#### Scenario: fault injection never applies twice
- **WHEN** execution stops before or after claim CAS, ledger apply, drain assertion, commit, or response delivery
- **THEN** recovery yields zero or one committed effect
- **AND** no retry creates a duplicate transaction or posting

#### Scenario: zero hosts remains honest
- **WHEN** every tray and daemon host is offline
- **THEN** market reads and durable state remain available while unfulfilled work stays pending
- **AND** no settlement is fabricated or attributed to platform/maintainer compute
