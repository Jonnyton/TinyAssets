## 1. Review And Authority Gates

- [x] 1.1 Record the host's 2026-07-23 Option 1 selection and preserve the current domain-bounded PostgreSQL, GitHub-export, local-state, OKF/artifact, custody-neutral private-content, BYOC, and stock-PostgreSQL-exit boundaries in this change.
- [x] 1.2 Map canonical and active OpenSpec ownership; keep `postgres-control-plane` limited to the generic persistence substrate and record collisions with identity, visibility, uptime, moderation, paid-market, handoff, operator-request, brain/OKF, and local SQLite owners, including #1800's merged handoff/outcome integration, still-unchecked task 5.4, canonical external-effect receipt/dedup ownership, and fixture-only migration.
- [ ] 1.3 Obtain independent current-main Codex architecture/security reviews of the planning artifacts and fold in auth-ownership, claim-model, non-escalation, privacy-conflict, tenant-context, baseline, privileged-role, zero-host, and first-write corrections.
- [ ] 1.4 Obtain a fresh current-main Claude Opus 5 source/deployment re-check with an explicit APPROVE, ADAPT, or REJECT verdict and exact current evidence; the historical packet approval does not approve this successor.
- [ ] 1.5 Obtain explicit host acceptance of every Claude adaptation or stop this change if the host rejects the resulting boundary.
- [x] 1.6 Verify this restack against current PLAN ancestry: PostgreSQL owns catalog/ledger/inbox/market transactions, GitHub is their export sink, and private custody remains deliberately per-situation; no PLAN edit is authorized or required by this lane.
- [ ] 1.7 Re-run OpenSpec/STATUS/idea/provider-context collision checks and update downstream dependencies before claiming any runtime, deployment, database, production-inventory, or sibling OpenSpec change directory. Treat PR #1792 as open and unsatisfied until its implementation/schema actually lands; treat #1800 as the merged handoff owner without promoting its prototype migration.

## 2. Read-Only Production Inventory And Baseline

- [ ] 2.1 Define a sanitized, read-only structural inventory procedure that records schemas, tables/columns/constraints, indexes, extensions, auth integration, roles/grants, RLS policies, functions/triggers, pooling, migration history, untracked state, and deployment path while excluding rows, password hashes, secret-valued role settings, DSNs/tokens, and secret literals in function/configuration bodies. Record secret dependencies only by identifier, custody location, rotation/reprovision status, and verification result.
- [ ] 2.2 Execute the procedure against the actual Supabase project without mutation and store the dated evidence at a host-approved artifact path outside production migration history.
- [ ] 2.3 Compare observed production state with repository configuration and prototype fixtures; classify every difference without assuming the prototype is a baseline.
- [ ] 2.4 Obtain host approval of the observed production baseline, `db/postgres/migrations/` home, role matrix, and first permissible migration identifier. Generic runner tests may use synthetic tenants. A domain may proceed only when its owning identity/visibility/custody contracts define its accepted mapping; a missing organization mapping blocks organization-scoped activation, not an otherwise accepted personal-domain slice.

## 3. Provider-Neutral Migration Substrate

- [ ] 3.1 Add `db/postgres/migrations/` documentation and the approved baseline marker/verification data without copying, renaming, renumbering, or promoting prototype SQL.
- [ ] 3.2 Select and pin a supported PostgreSQL driver, then implement `tinyassets/storage/postgres_migrations.py` as a bounded library with no import-time connection or application-start mutation.
- [ ] 3.3 Implement `scripts/postgres_migrate.py` as the sole migration-history executor for TinyAssets-owned application schemas with a separate direct-connection migration DSN/role, bounded advisory locking, strict ordered identifiers, exact-byte SHA-256 verification, and transactional migration-plus-history commits. Disable or demonstrably subordinate Supabase Branching, `supabase db push`, dashboard SQL, ORM auto-create, and every other path for those schemas. Inventory/version-pin vendor-managed Supabase schemas through their adapter owners. Forbid update/delete/checksum replacement of committed history; use additive forward migrations, with exceptional baseline reconciliation requiring quiescence, preserved snapshot, explicit dual approval, and immutable audit.
- [ ] 3.4 Add dedicated migration, application, read-only, and operational role setup with forced-RLS-compatible least privilege; keep migration/service credentials out of ordinary request handlers.
- [ ] 3.5 Add tests for duplicate/gap/reorder/checksum drift, wrong baseline, lock timeout, failed/partial migration, retry, and immutable migration history.
- [ ] 3.6 Add real-PostgreSQL tests for fresh, populated-upgrade, partially applied, structurally pre-existing, and unexplained-drift databases; required CI tests fail rather than skip when PostgreSQL is unavailable.
- [ ] 3.7 Add privileged-function, role, and pooled-connection tests covering non-login object ownership, fixed safe `search_path`, explicit grants/revokes, revoked raw table/sequence reads and DML, narrowly granted authenticated query/command functions, `FORCE ROW LEVEL SECURITY`, `rolbypassrls=false`, `SET ROLE` denial, forged `SET LOCAL`/`set_config` and direct context-setter denial, absence of migration/service credentials from request handlers, transaction-local actor/tenant context, exception/cancel cleanup, pooled reuse, composite tenant keys, cross-tenant denial, and driver/prepared-statement behavior under every accepted application pool mode. Prove migrations, dumps, restores, persistent sessions, LISTEN/NOTIFY consumers, and advisory locks never use transaction pooling.

## 4. Deployment, Recovery, And Stock-PostgreSQL Exit

- [ ] 4.1 Create, accept, and keep active a separate dependent OpenSpec change with a modified `uptime-and-alarms` delta for PostgreSQL backup/DR/release-state ownership before backup testing or any first-write approval; do not silently supersede its current SQLite/full-volume contract. Depend on the landed `implement-production-load-harness` implementation and accepted evidence-schema version while keeping PostgreSQL workload populations and thresholds capability-local.
- [ ] 4.2 Add deployment configuration with separate application/migration DSNs and a migrate-before-candidate-activation gate; leave serving-image rollback, alarms, schedules, system DR, and RPO/RTO under the accepted `uptime-and-alarms` change.
- [ ] 4.3 Add PostgreSQL backup and restore verification that defaults to synthetic data, preserves schema history, canonical IDs, tenant boundaries, checksums/counts, and immutable audit/accounting ordering, and separately covers Storage object bodies, custom-role secrets excluded from dumps, subscriptions, publication state, replication slots, expected downtime, and accepted RPO/RTO. Any production snapshot requires explicit custody/residency approval, encryption, least-privilege access, a retention deadline, cleanup proof, and replacement rather than restoration of reusable credentials.
- [ ] 4.4 Consume and verify only separately accepted Supabase-specific Auth, Realtime, Storage, pooling, backup, or observability adapters from their owning capabilities; require a dependent OpenSpec change for any missing adapter rather than implementing it in this lane.
- [ ] 4.5 Run an isolated export/restore rehearsal into supported stock PostgreSQL and pass representative canonical read/write, role-denial, tenant-isolation, and migration-verification tests without a Supabase service-role-only path.
- [ ] 4.6 Add prior-application-image compatibility tests for every additive schema step and document the forward-fix recovery path after the first authoritative write.
- [ ] 4.7 Make preview branches data-less by default and populate them only with a versioned privacy-safe production-shaped synthetic seed whose access-classified row counts, content hashes, and size characteristics are recorded; prove the seed contains no production value, digest, sensitive low-cardinality distribution, private row, Storage object body, credential, or secret authority.

## 5. First Dark Downstream Transaction

- [ ] 5.1 Select the shortest ready catalog, ledger, inbox, or market pilot only after its applicable identity, artifact, custody, and domain OpenSpec dependencies are accepted; do not block a transaction on an irrelevant artifact/custody owner and do not hard-code moderation or another non-canonical domain.
- [ ] 5.2 Give the selected domain only its later domain migration and transaction boundary; do not copy domain tables, grants, state machines, or load claims into `postgres-control-plane`.
- [ ] 5.3 Prove the pilot remains dark and boundedly refuses when PostgreSQL, any applicable accepted identity/artifact/custody authority, or a required version is unavailable; never fall back to SQLite or dual mutation.
- [ ] 5.4 Reconcile the generic production inventory/runner clauses in `paid-market-track-e-wave-2-transport` so paid market retains fixture and market-specific ownership while depending on this substrate.
- [ ] 5.5 Update `operator-request-trigger-contract` to depend on the approved platform migration substrate for its future request-inbox schema while retaining ownership of admission, aggregate, and row-lock behavior.

## 6. Security, Concurrency, And Zero-Host Evidence

- [ ] 6.1 Before load execution, require the shared production-load implementation successor (draft PR #1792 at this review) and accepted evidence-schema version to have landed, then record this capability's approved launch workload/SLO envelope: dataset size, tenant mix, reader/writer concurrency, burst and sustained duration, failure injection, and numerical latency/error/deadlock/saturation/recovery pass-fail thresholds. Until then record `not_run` with the protocol dependency code; do not create a local substitute.
- [ ] 6.2 Run the foundation security matrix for tenant/actor binding, role denial, privileged functions, pool reuse/exhaustion, and cross-tenant keys; add sentinel/taint evidence for every enabled ingress, persistence, log/error, audit/outbox, notification, Storage, export, ranking, analytics, and training boundary, recording disabled channels as unavailable rather than omitting them.
- [ ] 6.3 Run concurrent migration-runner, transaction-contention, database-failure, and backup/restore fault-injection tests with raw failure and recovery evidence. For every enabled accepted notification adapter, also run duplicate/reorder/disconnect/catch-up tests; record disabled or unaccepted adapters as `unavailable` or inapplicable while always proving durable version/outbox recovery.
- [ ] 6.4 After the shared implementation and evidence schema land, run the production-shaped workload under that versioned protocol against the pre-approved capability-owned launch envelope with PostgreSQL/Supabase versions, topology/region, pool configuration, commands, latency distributions, catch-up lag, deadlocks, occupancy/saturation, lost/duplicate writes, and recovery timings.
- [ ] 6.5 Prove activated catalog/ledger/inbox/market commands remain within accepted bounds with zero daemon hosts online while host-local execution remains honestly unavailable and private content follows its selected custody mode.
- [ ] 6.6 Obtain independent security, migration, and code-to-requirement review; keep every downstream capability's stricter concurrency/failure/user-surface proof separate.

## 7. Import And First-Write Boundary

- [ ] 7.1 For any separately approved legacy shared state, build an idempotent quiesced export/import with a preserved source snapshot, record counts, content hashes, and reconciliation evidence.
- [ ] 7.2 Run shadow reads only; resolve every divergence while the old source remains sole authority and prove no dual mutation path exists.
- [ ] 7.3 Record host approval of the exact first canonical PostgreSQL production write after all applicable review, baseline, migration, accepted PostgreSQL `uptime-and-alarms` ownership, recovery, exit, workload/SLO, and domain gates pass.
- [ ] 7.4 Activate exactly one PostgreSQL mutation authority for the selected domain and record the irreversible boundary; after it, disable writes and forward-fix on faults rather than restoring SQLite/Git/OKF mutation or destructively down-migrating history.

## 8. Foldback

- [ ] 8.1 Re-run strict OpenSpec validation, focused and real-PostgreSQL tests, security/load suites, stock-exit drill, zero-host proof, and independent diff review against the exact landing SHA.
- [ ] 8.2 Sync `postgres-control-plane` into canonical specs only after implementation and production-shaped acceptance are complete; leave unfinished downstream domain changes and the separately owned uptime change active until each is complete.
- [ ] 8.3 Archive this change, remove its STATUS/worktree claim, and publish the final evidence/rollback/first-write record in the landing lane.
