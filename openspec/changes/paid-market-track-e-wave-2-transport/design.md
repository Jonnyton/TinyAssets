## Context

PR #1440 landed the pure `tinyassets.paid_market` package and prototype migrations 006–008. The pure package already supplies exact settlement objects, posting adapters, `Ledger.assert_drained`, and deterministic `match.best_execution`, but production code does not call them. Current money actions instead use the older SQLite payment path, and founder decision D2 forbids a dual-write bridge: `public.ledger` stays frozen as v1 history while new logical market accounting eventually uses the double-entry `market.*` ledger. Real wallet/chain effects remain a separate authority domain.

The prototype is not a live migration system. It mounts every SQL file into `docker-entrypoint-initdb.d`, applies only on an empty volume, has duplicate active `003` identifiers, and records no migration history. It also contains deliberately non-production substitutes such as GUC-based auth, `TO PUBLIC` policies, and 16-dimensional vectors. Migration 008 exposes a `SECURITY DEFINER` function without revoking default function execution from `PUBLIC`, does not bind idempotency keys to request bodies, and separates posting from drain assertion. None of this prototype SQL is production migration authority.

The transport crosses security, money, migration, distributed-execution, and uptime boundaries. It therefore remains dark until distributed-execution S14/B36 binds settlement to the current lease fence, accepted-result hash, claim ownership, verified actor/payment facts, and independent verification. User-owned wallets remain the source of real-fund authority; PostgreSQL is only a logical reservation/accounting-intent system and never holds signing keys. Wave 2 adds no smart-contract escrow.

## Goals / Non-Goals

**Goals:**

- Preserve `tinyassets.paid_market` as the I/O-free executable oracle.
- Define one adapter path for atomic claim and settlement persistence.
- Make idempotency body-bound, actor-bound, and safe under concurrency and response loss.
- Make ledger RPCs fail closed by role, search path, payload size, and account authority.
- Make the v0 fixture replayable, then require a read-only inventory and host-approved production-native Supabase baseline before paid-market migrations can run live.
- Require §14 concurrency/load and zero-host evidence before activation.

**Non-Goals:**

- Enabling `TINYASSETS_PAID_MARKET`, applying migrations live, or moving real funds.
- Implementing chain signing, a wallet custodian, a smart-contract escrow, or an on-chain payout dispatcher.
- Implementing Wave 3 quote/index endpoints, Wave 4 forward UX, demand signals, pooled/training/fabrication public endpoints, or a new MCP action.
- Replacing the repo-file node-bid claim domain or rewriting v1 settlement YAML/`public.ledger`.
- Reopening accepted founder decisions or choosing still-open forward defaults.

## Decisions

### 1. Pure core plus one effect adapter

I/O remains outside `tinyassets/paid_market`. A future `tinyassets/payments/market_transport.py` consumes pure settlement results, ledger posting adapters, and `BookOffer`/`best_execution`; it exposes no balance-write method. Its database dependency is an injected `MarketLedgerRpc` protocol, not a new psycopg import in application core. The protocol accepts immutable `SettlementCommand` and `ClaimCommand` values carrying verified request-authority identity, business reference/state version, postings, and drain accounts, and returns typed `applied`, `replayed`, `conflict`, or contention results. Tenant and actor are derived from the verified authority rather than trusted as caller-selected strings; any advisory body hash is ignored and recomputed inside the trusted wrapper. A psycopg implementation exists only in fixture/integration-test scope until the production Supabase boundary is audited. `tinyassets/paid_market/ledger.py` gains only the missing pure spot-settlement posting adapter. API wrappers delegate to the transport and contain no posting construction.

Alternative considered: put PostgreSQL calls in `tinyassets.paid_market`. Rejected because it destroys the pure oracle and makes differential verification circular.

### 2. Matching and claiming share a concurrency contract

For a single paid request, the transport performs a narrow row claim; it never poll-scans the whole inbox. Every offer row carries a monotonic `version`. For a multi-offer purchase, the transport reads an eligible versioned snapshot, calls `best_execution`, locks only the selected offer IDs in canonical order, verifies their state/version, and atomically transitions them. A stale selected offer aborts the transaction and permits at most three jittered recomputations; exhaustion returns an honest contention result and waits for the next capability-channel event.

Alternative considered: `ORDER BY unit_price LIMIT ...` or greedy matching in SQL. Rejected because it violates the proven covering-knapsack contract. Full-book `SKIP LOCKED` polling is also rejected by the §14 contention analysis.

### 3. Settlement is one server-side transaction

One internal stored procedure owns the boundary:

1. derive authenticated subject plus tenant/universe from verified request authority and verify every tenant-scoped business-state/version and, after S14 exists, lease fence plus accepted-result identity;
2. verify the actor/account binding, any bounded signed on-behalf grant, and the server-recomputed versioned/domain-separated canonical request hash;
3. derive/receive only the unchanged posting list produced by the named pure adapter;
4. coalesce duplicate accounts and lock tenant-scoped business, logical reservation/collateral, idempotency, and balance rows in the single global order before invoking internal `market.apply_tx` once;
5. invoke internal drain checks for every temporary logical reservation/collateral account; and
6. commit business state, transaction, postings, balances, and drain success together.

Any error rolls back every step. `market.apply_tx` is not a public PostgREST surface. Its transaction row stores the server-recomputed `request_sha256` plus encoding/domain version; same tenant-scoped key plus same canonical body returns the original transaction, while a caller-hash mismatch or changed body conflicts.

Alternative considered: call `apply_tx`, then `assert_drained` through two client RPCs. Rejected because a committed residual cannot be rolled back.

### 4. The SQL privilege boundary is deny-by-default

Ledger functions use a non-login owner and fixed `search_path` containing only trusted schemas. The migration explicitly revokes function execution and table/sequence DML from `PUBLIC`, anonymous, authenticated, and ordinary application roles, then grants only the settlement wrapper to a dedicated internal service role. Raw `market.apply_tx` and drain helpers remain callable only inside the trusted boundary. The wrapper independently compares verified request authority with tenant-scoped locked rows, derives buyer, seller, logical reservation (`escrow:*`), and collateral accounting accounts from those rows, and accepts the treasury account only from fixed server configuration. Caller-supplied tenants, treasury accounts, and every `external:*` or `pool:*` account are rejected in Wave 2. Host on-behalf action requires an immutable signed grant bounded by target, tenant, action, account, amount, expiry, and revocation generation and records both principals plus grant id. A future external-funding entry needs a separately reviewed, receipt-verified ingress. `UNIVERSE_SERVER_USER` or `UNIVERSE_SERVER_HOST_USER` environment values confer no money authority.

Wave 2 payloads are bounded: at most 16 postings, 128 UTF-8 bytes for an idempotency key, 512 bytes for a memo, 256 bytes per account name, and 16 KiB for canonical posting JSON. Larger future settlement families need a separately reviewed bulk contract.

Alternative considered: rely on revoked table writes while granting `apply_tx` broadly. Rejected because caller-chosen `external:*` contra accounts can mint arbitrary user balances.

### 5. Dark, non-custodial settlement posture

This apply lane may build adapters, SQL, tests, and shadow comparison, but it may not expose a live claim/settle route. It proves only database idempotency, including response loss after commit; it does not invent a chain saga, resubmission policy, signer, payout dispatcher, or smart-contract escrow. The required later §18.6 chain-settlement successor must bind each effect to exactly `job_id:lease_fence:accepted_result_sha256`, implement the locked hybrid batched/immediate posture, and define durable reconciliation, reorg, retry, worker, alarm, wallet authority, receipt verification, and custody posture before a signer exists. PostgreSQL may record bounded logical reservation/accounting intent; it never stores user signing keys or treats an accounting row as proof of funding or payout.

Live activation depends on distributed-execution S14/B36, the reviewed and implemented §18.6 chain-settlement successor, opposite-provider approval, host-approved dual verification, and explicit cutover. Dual verification may compare results, but dual money movement is forbidden.

Alternative considered: platform-controlled off-chain custody, a Wave 2 smart-contract escrow, or an independent Wave 2 payout path. Rejected from this lane because the cooperative launch posture specifies no escrow, Wave 2 has no chain-effect authority, and the approved §18.6 settlement target requires its own reviewed successor.

### 6. Prototype replay and production baselining are separate

Wave 2 first makes the throwaway v0 fixture deterministic in place; it does not promote the prototype into production. The fixture gains a local runner and history table solely for clean clone/test replay. Its dependency-correct order is:

1. `001_core_tables`
2. `002_flags`
3. `003_rls`
4. `004_indexes`
5. `005_seed`
6. `006_discover_nodes`
7. `007_token_normalization`
8. `008_forwards`
9. `009_market_ledger`

The fixture runner bootstraps `schema_migrations(version, name, sha256, applied_at)`, takes a PostgreSQL advisory lock, rejects duplicate/gapped/out-of-order identifiers, computes the checksum from exact bytes, and applies each pending migration plus its history row in one transaction. A failed migration is not recorded. Concurrent runners serialize; failure to establish the lock within a bounded timeout fails closed. Migration-history DML is revoked from public/application roles and granted only to a migration-only role. `006_discover_nodes` explicitly establishes/checks its pgvector dependency, and `008_forwards` adds the monotonic offer version used by claim CAS.

Production follows a different lane. A read-only inventory first records the actually deployed Supabase schemas, extensions, auth model, policies, functions, roles, dimensions/indexes, migration history, and deployment mechanism. The host then approves a production baseline and migration home. New production-native SQL is authored and security-reviewed against that inventory; prototype SQL is never copied or treated as a legacy production baseline. The former paid-market 006–008 migrations remain unapplied until that lane exists. This proposal therefore specifies only the migration prerequisites needed by paid market, not a global platform migration contract.

Alternative considered: add only a tracking table while retaining Docker's empty-volume init behavior. Rejected because it cannot upgrade, resume, detect drift, or serialize concurrent deploys.

### 7. V1 is frozen; shadow comparison is not dual write

Existing YAML settlement records and `public.ledger` stay byte-for-byte unchanged. New dark-path tests may compare computed outcomes against v1 fixtures, but no request writes money to both ledgers. Old application versions continue to ignore the new `market` schema while the feature remains off.

### 8. Activation is evidence-gated

The apply lane must leave executable evidence for role isolation, actor binding, body-bound replay, database crash points, migration resume/drift, pure-oracle differential behavior, matcher/claim contention, ledger conservation, logical-reservation drain contention, and zero-host honesty. Database load runs on an isolated Supabase test project matching the intended launch region and compute plan, recording PostgreSQL version, pool settings, CPU, connections, and exact commands. The ledger target is at least 5,000 committed transactions/second aggregate, p99 below 250 ms, zero deadlocks/timeouts, and sustained database CPU and pool occupancy below 80%. The §14 scenario routes 500 synthetic daemons and 1,000 requests through the real production-shaped Realtime capability push, not a mock, with claim p99 below three seconds. The dark-lane zero-host proof covers available reads/durable state and honest pending/unavailable settlement; hosted retry workers and alarms are deferred to S14/B36 rollout proof.

## Risks / Trade-offs

- **[Risk] The prototype is mistaken for deploy authority.** → It remains an isolated fixture; production SQL is authored only from the audited live Supabase baseline after host approval.
- **[Risk] A body-changing idempotent retry is mistaken for success.** → Store and compare the canonical request hash; mismatch is a conflict.
- **[Risk] Selected offers change between match and claim.** → Versioned snapshot, selected-ID locks, atomic state transition, and bounded recomputation.
- **[Risk] `SECURITY DEFINER` expands privileges or resolves hostile objects.** → Non-login owner, fixed trusted search path, explicit revokes, dedicated internal role, and malicious-search-path tests.
- **[Risk] PostgreSQL accounting is mistaken for custody or chain finality.** → Dark adapter, no provisional chain saga, no keys, and an explicit S14/B36/host cutover gate.
- **[Risk] Load proof is expensive.** → It is activation evidence, not optional polish; the Forever Rule requires it for the paid-market uptime surface.
- **[Trade-off] Sixteen postings excludes large pool closes.** → Wave 2 spot/forward transactions stay small and auditable; bulk settlement needs a separately reviewed atomic contract.

## Migration Plan

1. Land this OpenSpec package after opposite-provider review; do not implement or deploy from an unreviewed money/concurrency design.
2. In a later apply lane, add the pure spot adapter and dark transport with unit/differential tests.
3. Renumber and dependency-correct only the v0 fixture, add its local runner, and prove fresh install, populated fixture baseline, checksum drift, concurrent serialization, failure resume, and prior-app rollback compatibility.
4. Inventory the deployed Supabase schema read-only. Stop for host approval of the production baseline and migration home, then author new production-native paid-market migrations; never promote the v0 SQL.
5. Harden the fixture ledger migration and future production-native equivalent so the wrapper owns CAS + postings + drains atomically and raw ledger functions are not publicly executable.
6. Run PostgreSQL integration, fault-injection, concurrency, and §14 load suites in the specified isolated test project; record dated environment and latency evidence.
7. Obtain opposite-provider implementation review. Keep the flag off and the route dark.
8. After distributed-execution S14/B36 lands, perform host-approved shadow/dual verification with no dual money movement.
9. Only after the required §18.6 chain-settlement successor is reviewed and implemented may a separate host-approved rollout apply production-native migrations, enable settlement, connect that chain-effect boundary, run canary/rendered-chatbot proof if a public surface changes, and leave a clean-use watch until real-user evidence exists.

Rollback before activation is code/config rollback with the flag off; additive schemas remain unused and v1 stays authoritative. A populated upgrade must pass a prior-application-version compatibility test before cutover. After any future live migration, schema rollback is forward-fix only unless the reviewed rollout artifact proves a reversible data migration; settlement effects are never “rolled back” by deleting accounting history.

## Open Questions

- The actual deployed Supabase baseline, production migration home, live migration, market enablement, S14/B36 cutover, and deployment of the required §18.6 chain-settlement successor each remain explicit host decisions.
- Forward collateral/threshold/bucket defaults remain open downstream decisions and do not block the dark Wave 2 spot transport.
