## 1. Review And Authority Gates

- [x] 1.1 Record the host's 2026-07-23 Option 1 selection and preserve the exact PostgreSQL, GitHub-export, local-state, OKF/artifact, private-content, BYOC, and stock-PostgreSQL-exit boundaries in the decision packet and this change.
- [x] 1.2 Map canonical and active OpenSpec ownership; keep `postgres-control-plane` limited to the generic persistence substrate and record collisions with identity, visibility, uptime, moderation, paid-market, operator-request, brain/OKF, and local SQLite owners.
- [x] 1.3 Obtain independent Codex architecture/security reviews of the planning artifacts and fold in auth-ownership, privacy-conflict, tenant-context, baseline, privileged-role, zero-host, and first-write corrections.
- [ ] 1.4 After Claude capacity resets, obtain the required opposite-provider source/deployment re-check with an explicit APPROVE, ADAPT, or REJECT verdict and exact current evidence.
- [ ] 1.5 Obtain explicit host acceptance of every Claude adaptation or stop this change if the host rejects the resulting boundary.
- [ ] 1.6 Reconcile PLAN's stale PostgreSQL/GitHub open tension, the private-storage contradiction, and the accepted identity/visibility/tenant dependencies in a separately reviewed PLAN edit.
- [ ] 1.7 Re-run OpenSpec/STATUS/idea/provider-context collision checks and update downstream dependencies before claiming any runtime, deployment, database, or production-inventory file.

## 2. Read-Only Production Inventory And Baseline

- [ ] 2.1 Define a sanitized, read-only inventory procedure that cannot expose credentials or private content and records schemas, tables/columns/constraints, indexes, extensions, auth integration, roles/grants, RLS policies, functions/triggers, pooling, migration history, untracked state, and deployment path.
- [ ] 2.2 Execute the procedure against the actual Supabase project without mutation and store the dated evidence at a host-approved artifact path outside production migration history.
- [ ] 2.3 Compare observed production state with repository configuration and prototype fixtures; classify every difference without assuming the prototype is a baseline.
- [ ] 2.4 Obtain host approval of the observed production baseline, `db/postgres/migrations/` home, role matrix, and first permissible migration identifier. Generic runner tests may use synthetic tenants, but no production tenant schema or downstream pilot may proceed until the owning identity/visibility/domain contracts contain an accepted personal-and-organization tenant mapping.

## 3. Provider-Neutral Migration Substrate

- [ ] 3.1 Add `db/postgres/migrations/` documentation and the approved baseline marker/verification data without copying, renaming, renumbering, or promoting prototype SQL.
- [ ] 3.2 Select and pin a supported PostgreSQL driver, then implement `tinyassets/storage/postgres_migrations.py` as a bounded library with no import-time connection or application-start mutation.
- [ ] 3.3 Implement `scripts/postgres_migrate.py` with separate migration DSN/role, bounded advisory locking, strict ordered identifiers, exact-byte SHA-256 verification, and transactional migration-plus-history commits.
- [ ] 3.4 Add dedicated migration, application, read-only, and operational role setup with forced-RLS-compatible least privilege; keep migration/service credentials out of ordinary request handlers.
- [ ] 3.5 Add tests for duplicate/gap/reorder/checksum drift, wrong baseline, lock timeout, failed/partial migration, retry, and immutable migration history.
- [ ] 3.6 Add real-PostgreSQL tests for fresh, populated-upgrade, partially applied, structurally pre-existing, and unexplained-drift databases; required CI tests fail rather than skip when PostgreSQL is unavailable.
- [ ] 3.7 Add privileged-function, role, and pooled-connection tests covering non-login object ownership, fixed safe `search_path`, explicit grants/revokes, `FORCE ROW LEVEL SECURITY`, `rolbypassrls=false`, `SET ROLE` denial, absence of migration/service credentials from request handlers, transaction-local actor/tenant context, composite tenant keys, and cross-tenant denial.

## 4. Deployment, Recovery, And Stock-PostgreSQL Exit

- [ ] 4.1 Create, accept, and keep active a separate dependent OpenSpec change with a modified `uptime-and-alarms` delta for PostgreSQL backup/DR/release-state ownership before backup testing or any first-write approval; do not silently supersede its current SQLite/full-volume contract.
- [ ] 4.2 Add deployment configuration with separate application/migration DSNs and a migrate-before-candidate-activation gate; leave serving-image rollback, alarms, schedules, system DR, and RPO/RTO under the accepted `uptime-and-alarms` change.
- [ ] 4.3 Add PostgreSQL backup and restore verification that preserves schema history, canonical IDs, tenant boundaries, checksums/counts, and immutable audit/accounting ordering.
- [ ] 4.4 Consume and verify only separately accepted Supabase-specific Auth, Realtime, Storage, pooling, backup, or observability adapters from their owning capabilities; require a dependent OpenSpec change for any missing adapter rather than implementing it in this lane.
- [ ] 4.5 Run an isolated export/restore rehearsal into supported stock PostgreSQL and pass representative canonical read/write, role-denial, tenant-isolation, and migration-verification tests without a Supabase service-role-only path.
- [ ] 4.6 Add prior-application-image compatibility tests for every additive schema step and document the forward-fix recovery path after the first authoritative write.

## 5. First Dark Downstream Transaction

- [ ] 5.1 Select one downstream pilot only after its own identity, artifact, privacy, and domain OpenSpec dependencies are accepted; moderation flag intake is the current candidate.
- [ ] 5.2 Give the selected domain only its later domain migration and transaction boundary; do not copy domain tables, grants, state machines, or load claims into `postgres-control-plane`.
- [ ] 5.3 Prove the pilot remains dark and boundedly refuses when PostgreSQL, the accepted identity/artifact authority, or a required version is unavailable; never fall back to SQLite or dual mutation.
- [ ] 5.4 Reconcile the generic production inventory/runner clauses in `paid-market-track-e-wave-2-transport` so paid market retains fixture and market-specific ownership while depending on this substrate.
- [ ] 5.5 Update moderation's “next numbered migration” task and other dependent domains to wait for the approved platform history rather than inventing identifiers.
- [ ] 5.6 Update `operator-request-trigger-contract` to depend on the approved platform migration substrate for its future request-inbox schema while retaining ownership of admission, aggregate, and row-lock behavior.

## 6. Security, Concurrency, And Zero-Host Evidence

- [ ] 6.1 Before load execution, record and obtain approval of the launch workload/SLO envelope: dataset size, tenant mix, reader/writer concurrency, burst and sustained duration, failure injection, and numerical latency/error/deadlock/saturation/recovery pass-fail thresholds.
- [ ] 6.2 Run the foundation security matrix for tenant/actor binding, role denial, privileged functions, pool reuse/exhaustion, and cross-tenant keys; add sentinel/taint evidence for every enabled ingress, persistence, log/error, audit/outbox, notification, Storage, export, ranking, analytics, and training boundary, recording disabled channels as unavailable rather than omitting them.
- [ ] 6.3 Run concurrent migration-runner, transaction-contention, database-failure, Realtime duplicate/reorder/disconnect/catch-up, and backup/restore fault-injection tests with raw failure and recovery evidence.
- [ ] 6.4 Run the §14 production-shaped workload against the pre-approved launch envelope with PostgreSQL/Supabase versions, topology/region, pool configuration, commands, latency distributions, catch-up lag, deadlocks, occupancy/saturation, lost/duplicate writes, and recovery timings.
- [ ] 6.5 Prove activated shared control-plane commands remain within accepted bounds with zero daemon hosts online while host-local execution and private content remain honestly unavailable.
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
