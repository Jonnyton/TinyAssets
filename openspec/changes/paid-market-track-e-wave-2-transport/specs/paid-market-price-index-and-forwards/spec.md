## MODIFIED Requirements

### Requirement: Money movement goes through market.apply_tx() and nothing else (HARD RULE)

The market SHALL enforce the following ledger-transport HARD RULE verbatim (founder sign-off 2026-07-13):

Every money movement in the market goes through market.apply_tx() and NOTHING ELSE. Application code never computes a balance and writes it. The pure ledger.py stays the validation oracle and the executable spec; this RPC is its one transport.

The system SHALL route every settlement, escrow lock/release, refund, slash, and fee posting through internal `market.apply_tx()`; no other code path SHALL write a balance or ledger row. Application transport SHALL use the named pure `tinyassets.paid_market.ledger` adapter without recomputing postings. A trusted server-side settlement wrapper SHALL combine business-state compare-and-set, actor/account authorization, adapter postings, `market.apply_tx`, and all `market.assert_drained` checks in one database transaction. `market.apply_tx` SHALL store a SHA-256 hash of the canonical request body with its deterministic idempotency key: same key plus identical body returns the original transaction, while same key plus any changed memo, account, amount, or posting order SHALL raise an idempotency conflict. Raw ledger functions and table/sequence DML SHALL be unavailable to public and user-facing roles. The persisted result SHALL be differential-tested against the pure `ledger.py` oracle and any divergence SHALL roll back and fail loud. (Ledger-transport law adopted by founder sign-off 2026-07-13; concurrency proof-of-need: unlocked writers created value through lost updates, while serialized transactions preserved conservation.)

#### Scenario: a settlement posts through one atomic transport
- **WHEN** any market path moves money
- **THEN** the named pure adapter supplies postings to one trusted settlement wrapper
- **AND** state CAS, `market.apply_tx`, drain assertions, and audit state commit or roll back together

#### Scenario: identical replay is exactly once
- **WHEN** 100 concurrent callers submit the same deterministic idempotency key and identical canonical body
- **THEN** they observe one transaction identity and one applied effect
- **AND** no balance or posting is duplicated

#### Scenario: changed-body replay conflicts
- **WHEN** a caller reuses an idempotency key with any changed canonical body field
- **THEN** the transport returns an idempotency conflict
- **AND** the original transaction remains unchanged

#### Scenario: transport is validated against the pure oracle
- **WHEN** randomized adapter transactions are applied to both the persistent transport and pure `Ledger`
- **THEN** balances, conservation, overdraft decisions, and drain outcomes match
- **AND** any divergence fails loud rather than persisting

#### Scenario: direct ledger write is denied
- **WHEN** a public, anonymous, authenticated, or ordinary application role attempts table DML or raw `market.apply_tx` execution
- **THEN** PostgreSQL denies the operation
- **AND** no ledger state changes

## ADDED Requirements

### Requirement: Paid-market migration prerequisites are tracked and production-native
The v0 fixture PostgreSQL chain SHALL have one unique, gap-free, strictly increasing identifier per active migration and SHALL be applied by an advisory-lock-protected local fixture runner. The runner SHALL maintain `schema_migrations(version, name, sha256, applied_at)`, checksum exact migration bytes, and commit a migration plus its history row in the same transaction. Fixture order SHALL be `001_core_tables`, `002_flags`, `003_rls`, `004_indexes`, `005_seed`, `006_discover_nodes`, `007_token_normalization`, `008_forwards`, `009_market_ledger`; discovery SHALL establish/check pgvector first, and forwards SHALL add a monotonic offer version. Duplicate identifiers, gaps, out-of-order files, checksum drift, unverifiable fixture schema, or inability to establish the advisory lock within a bounded timeout SHALL fail closed before unsafe mutation. Concurrent runners SHALL serialize. `schema_migrations` DML SHALL be denied to public/application roles and granted only to a migration-only role.

Before live paid-market migration authoring, a read-only inventory SHALL record the actually deployed Supabase schemas, extensions, auth model, policies, functions, roles, vector dimensions/indexes, migration history, and deployment mechanism. Production SQL SHALL be authored natively from that host-approved baseline and migration home; prototype SQL SHALL NOT be promoted, copied as production authority, or used to assert a live legacy baseline.

#### Scenario: fresh fixture database applies its chain once
- **WHEN** the migration runner targets an empty supported PostgreSQL database
- **THEN** every fixture migration applies exactly once in identifier order
- **AND** every committed migration has one matching immutable history row

#### Scenario: existing fixture database is baselined only after verification
- **WHEN** a fixture database has pre-run historical schema but no `schema_migrations` rows
- **THEN** the runner verifies the expected tables, columns, functions, policies, and constraints for each claimed fixture version before recording a baseline
- **AND** any mismatch aborts before applying a later migration

#### Scenario: checksum drift or ordering error aborts
- **WHEN** an applied migration's bytes change, two active files share an identifier, an identifier is missing, or files are out of order
- **THEN** the runner fails before executing pending SQL
- **AND** existing data and migration history remain unchanged

#### Scenario: failed migration resumes safely
- **WHEN** a migration fails after earlier versions committed
- **THEN** the failed version has no applied history row and its transaction leaves no partial schema mutation
- **AND** a corrected rerun resumes from the first unapplied version

#### Scenario: concurrent runners serialize
- **WHEN** multiple deploy jobs start the migration runner simultaneously
- **THEN** the PostgreSQL advisory lock admits one runner at a time
- **AND** the chain records no duplicate or interleaved application

#### Scenario: application roles cannot alter migration history
- **WHEN** public, anonymous, authenticated, or ordinary application roles attempt `schema_migrations` DML
- **THEN** PostgreSQL denies the operation
- **AND** only the migration-only role can append a committed history row

#### Scenario: market migrations cannot go live from the prototype
- **WHEN** paid-market migrations exist only under the throwaway prototype or the audited production baseline and deliberate live-apply approval are absent
- **THEN** no production database applies them
- **AND** the paid market remains default-off

#### Scenario: populated upgrade remains compatible with the prior app
- **WHEN** the fixture runner upgrades a populated supported database
- **THEN** both the upgraded application and the prior application version pass their read/write compatibility suite while the paid-market flag remains off
- **AND** rollback to the prior application requires no destructive schema reversal

### Requirement: Wave 2 activation requires concurrency, recovery, and zero-host proof
The Wave 2 transport SHALL remain dark until an isolated Supabase test project matching the intended launch region and compute plan records dated evidence for role isolation, actor binding, idempotent database response-loss recovery, matcher/claim contention, ledger conservation, escrow-drain contention, migration recovery, and operation with zero daemon hosts. Evidence SHALL record PostgreSQL version, pool configuration, compute plan, region, CPU, connections, exact commands, latency distributions, and raw failure counts, not only a pass label, and SHALL be independently reviewed before host-approved activation.

#### Scenario: capability-sharded claim storm stays correct and bounded
- **WHEN** 500 synthetic daemons receive 1,000 paid requests over five minutes through the production-shaped Supabase Realtime capability push and narrow claim RPCs without mocked delivery
- **THEN** no request is lost or claimed twice
- **AND** claim latency p99 is below three seconds without a poll-all retry storm

#### Scenario: buyers contend on one offer book
- **WHEN** 100 buyers concurrently match and claim from the same versioned offer book
- **THEN** no offer is sold twice
- **AND** each successful selection equals `best_execution` for the valid snapshot it committed

#### Scenario: overlapping ledger writers preserve conservation
- **WHEN** at least 64 writers apply at least one million overlapping transfers, including reverse-order first-touch account sets
- **THEN** aggregate throughput is at least 5,000 committed transactions per second, p99 is below 250 milliseconds, and total postings and balances remain zero-sum with no negative internal balance, deadlock, or timeout
- **AND** sustained database CPU and pool occupancy stay below 80%, with p50, p95, and p99 recorded

#### Scenario: one escrow has one terminal drain
- **WHEN** 500 callers concurrently attempt to settle and drain the same escrow
- **THEN** exactly one terminal settlement succeeds
- **AND** every other caller receives the prior result or a clean state/idempotency conflict without a second effect

#### Scenario: database fault injection never applies twice
- **WHEN** execution is interrupted before or after claim CAS, ledger apply, drain assertion, database commit, or response delivery
- **THEN** recovery yields zero or one committed database effect
- **AND** no retry creates a duplicate transaction or posting

#### Scenario: zero hosts leaves the control plane honest and available
- **WHEN** every tray and daemon host is stopped
- **THEN** market reads and durable state remain available, unfulfilled work remains honestly pending, and no settlement is fabricated
- **AND** the UI/API reports settlement unavailable rather than claiming hosted retry or alarm coverage before S14/B36 supplies it
