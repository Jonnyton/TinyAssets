## ADDED Requirements

### Requirement: Shared control-plane state has one PostgreSQL authority
The system SHALL use Supabase-hosted PostgreSQL at launch as the sole mutation authority for shared multi-user control-plane state whose domain has been activated on the new substrate. Host-local SQLite/files SHALL remain execution, checkpoint, private-content, or rebuildable cache state; separately specified OKF/artifact stores SHALL retain their domain authority; GitHub SHALL remain an export/contribution transport; none SHALL become a second shared-state mutation authority.

#### Scenario: Shared mutation commits once
- **WHEN** an activated shared control-plane command succeeds
- **THEN** its authoritative state transition commits in PostgreSQL
- **AND** any local cache, GitHub export, Realtime message, or artifact projection is derived from that committed version

#### Scenario: Local execution stores remain local
- **WHEN** a daemon checkpoints a run or persists host-local execution/cache state
- **THEN** that state remains outside the shared PostgreSQL authority unless a separately approved domain contract explicitly promotes a public/shared projection

### Requirement: Private content and BYOC secrets remain outside the control plane
The system SHALL NOT store, upload, index, replicate, export, log, rank from, analyze, or train on private universe/branch content, private canon source files, host paths, private tool inputs/outputs, private instance values, host-local knowledge/vector stores or notes artifacts, requester or host provider credentials, API keys, OAuth tokens, secret-bearing provider subscription authentication/account material, local model endpoints, local client authentication files, wallet signing keys, user-owned model weights, or host execution artifacts through the shared PostgreSQL control plane, Supabase Storage/Realtime, audit payloads, or public exports. Platform-resident domain tables SHALL carry only reviewed shared/public control-plane fields, and RLS, a service role, or platform-side encryption SHALL NOT be treated as permission to upload host-only content.

#### Scenario: Private branch content is refused
- **WHEN** a command attempts to persist private universe or branch content in a shared control-plane table
- **THEN** the command is rejected before mutation
- **AND** no encrypted or soft-private platform row is created

#### Scenario: BYOC credentials stay with their owner
- **WHEN** a requester or compute host uses a provider credential to execute work
- **THEN** the credential remains in the requester/host credential boundary
- **AND** PostgreSQL may record only bounded non-secret routing, authority, and receipt metadata approved by the owning domain
- **AND** operational database credentials remain separate from all user BYOC credentials

### Requirement: Production schema starts from an approved observed baseline
The system SHALL require a dated read-only inventory of the deployed Supabase project's schemas, tables, columns, constraints, extensions, authentication integration, grants, policies, functions, triggers, roles, indexes, pooling configuration, migration history, untracked/prototype state, and deployment mechanism before production SQL is authored or applied. After the required Claude re-check, the host SHALL approve that inventory as the production baseline and `db/postgres/migrations/` as the production migration home; `prototype/full-platform-v0/migrations/` SHALL remain fixture-only and SHALL NOT be copied, renumbered, or recorded as production history. The runner SHALL verify live structure against the approved baseline and abort on unexplained mismatch.

#### Scenario: Missing baseline blocks SQL
- **WHEN** the deployed inventory, host-approved baseline, or production migration home is absent
- **THEN** no production migration identifier is allocated or applied

#### Scenario: Prototype SQL is presented for production
- **WHEN** a production change copies, renumbers, or attempts to baseline a prototype migration
- **THEN** validation fails before database mutation

#### Scenario: Live database differs from the baseline
- **WHEN** the runner observes an unapproved schema, role, policy, function, extension, or migration-history difference from the accepted production baseline
- **THEN** it aborts before applying feature SQL and reports the unexplained mismatch

### Requirement: Migration history is locked and checksum verified
The production migration runner SHALL use a dedicated migration role and DSN, hold one bounded PostgreSQL advisory lock for the run, enforce unique gap-free ordered identifiers, verify exact-byte SHA-256 checksums against immutable `schema_migrations` history, and commit each migration with its history row in one transaction. Duplicate, missing, reordered, drifted, wrong-baseline, partially applied, unverifiable, or lock-timeout states SHALL fail closed.

#### Scenario: Concurrent runners serialize exactly once
- **WHEN** two deploys attempt to apply the same pending migration set concurrently
- **THEN** the advisory lock allows exactly one runner to apply each migration and history row
- **AND** the other runner either observes the completed history or exits with a bounded lock result without duplicate effects

#### Scenario: Applied migration bytes drift
- **WHEN** a migration file's exact bytes no longer match its recorded SHA-256
- **THEN** the runner refuses the run before applying later migrations

#### Scenario: Migration fails mid-transaction
- **WHEN** a migration statement fails before its transaction commits
- **THEN** its schema effects and history row are both absent
- **AND** a later corrected run can retry from the last committed version

#### Scenario: Database begins in a supported non-empty state
- **WHEN** the runner is exercised against fresh, partially applied, populated-upgrade, and structurally pre-existing database fixtures
- **THEN** it accepts only the fixture matching an explicitly supported and verified baseline state
- **AND** every unexplained or partially applied state fails closed

### Requirement: Application and migration authority are separated
The system SHALL keep migration and service-role credentials unavailable to ordinary long-running application request handlers and SHALL deny public, anonymous, authenticated, read-only, and ordinary application roles the ability to run schema DDL, bypass forced RLS, mutate migration history, or update/delete immutable audit and accounting history. Each privileged `SECURITY DEFINER` function SHALL have a non-login owner, fixed safe `search_path`, explicit grants/revokes, and tenant-isolation tests. Deployment SHALL apply approved migrations before activating the new application image, and migration failure SHALL prevent activation.

#### Scenario: Application role attempts migration DML
- **WHEN** an ordinary application role inserts, updates, or deletes a `schema_migrations` row
- **THEN** PostgreSQL denies the operation

#### Scenario: Migration fails during deployment
- **WHEN** the migration runner returns a non-success result
- **THEN** the deployment does not activate the candidate application image
- **AND** serving-image recovery remains governed by `uptime-and-alarms`

### Requirement: Tenant and actor context is verified and transaction local
Every shared control-plane command SHALL consume actor, tenant, visibility, grant, and ownership decisions from their accepted identity/visibility/domain authorities rather than define a second identity model, trust caller payload, or trust ambient host configuration; it SHALL set database actor/tenant context transaction-locally and independently verify the supplied authoritative context, current object version, and state transition inside the domain command boundary. Every tenant-owned canonical row SHALL carry the canonical tenant/owner identity, and tenant scope SHALL participate in relevant foreign keys, uniqueness constraints, and indexes. Forced RLS SHALL provide defense in depth and SHALL NOT be the source of positive mutation authority.

#### Scenario: Payload identity conflicts with authentication
- **WHEN** a request payload supplies an actor or tenant different from the verified request context
- **THEN** the command rejects without mutation

#### Scenario: Pooled connection is reused across tenants
- **WHEN** a connection that completed a tenant-A transaction is reused for tenant B
- **THEN** no tenant-A transaction-local context remains
- **AND** tenant B cannot read or mutate tenant-A rows

#### Scenario: RLS-visible row lacks command authority
- **WHEN** an actor can read a row through a permitted projection but lacks the current grant or state-transition authority
- **THEN** the command rejects without mutation

### Requirement: Realtime and exports are recoverable projections
The system SHALL treat Realtime messages as at-least-once invalidations and GitHub records as public export/contribution projections, never as queue or mutation truth. Any required notification SHALL be represented by a durable version/cursor or transactional outbox record committed with the authoritative PostgreSQL change, and a disconnected consumer SHALL recover by reading versioned PostgreSQL state.

#### Scenario: Realtime message is duplicated
- **WHEN** a consumer receives the same invalidation more than once
- **THEN** it converges on the single authoritative PostgreSQL version without duplicating a state transition

#### Scenario: Contribution arrives through GitHub
- **WHEN** a public export is modified through an accepted GitHub contribution
- **THEN** the contribution passes through the authenticated domain command boundary before PostgreSQL changes
- **AND** merging the Git commit alone does not mutate canonical state

### Requirement: Cutover never creates dual mutation authority
The system SHALL allow shadow reads and verified one-time idempotent import before cutover but SHALL NOT enable simultaneous PostgreSQL and SQLite/Git/OKF mutation authority for the same shared domain. An accepted import SHALL run under quiescence with counts, content hashes, reconciliation evidence, and a preserved source snapshot. The first PostgreSQL-only authoritative production write SHALL be an explicit recorded one-way boundary requiring host approval after the applicable review, baseline, migration, recovery, exit, and capability-specific gates pass; after it, recovery SHALL preserve committed history and use forward fixes rather than down migration or fallback mutation.

#### Scenario: Pre-cutover comparison finds divergence
- **WHEN** a shadow read differs from the existing source before the first authoritative PostgreSQL write
- **THEN** activation stops and the existing source remains authoritative

#### Scenario: First authoritative write has occurred
- **WHEN** a fault is found after PostgreSQL has accepted the domain's first authoritative production write
- **THEN** operators may disable new writes and deploy a compatible forward fix
- **AND** they do not resume mutation in the former source or erase committed audit/accounting history

### Requirement: Supabase has a tested stock-PostgreSQL exit
The system SHALL keep schema, constraints, migration history, and core domain transactions runnable on a supported stock PostgreSQL deployment without application-domain rewrites. Before activation it SHALL prove a documented export, restore, migration verification, and representative domain read/write path outside Supabase; any Supabase-specific Auth, Realtime, Storage, pooling, or operational behavior SHALL remain behind replaceable adapters.

#### Scenario: Exit rehearsal restores to stock PostgreSQL
- **WHEN** the approved production-shaped dataset and migration history are exported from the Supabase-shaped environment and restored to supported stock PostgreSQL
- **THEN** checksums, row counts, constraints, and migration history verify
- **AND** representative authenticated domain transactions pass through the same application-domain contracts

#### Scenario: Supabase adapter is unavailable
- **WHEN** a Supabase-specific notification or operational adapter is unavailable but PostgreSQL remains reachable
- **THEN** canonical transaction truth remains intact
- **AND** the system reports the degraded adapter honestly instead of accepting mutation through an alternate authority

### Requirement: Activation requires zero-host, security, recovery, and load proof
The PostgreSQL control plane SHALL remain dark until a production-shaped isolated environment records dated §14 evidence for zero-daemon-host shared operation, tenant/role isolation, actor binding, connection-pool context safety and exhaustion, concurrent runner serialization/recovery, transaction contention and database failure, Realtime disconnect/recovery, backup/restore, stock-PostgreSQL exit, prior-application compatibility, and bounded behavior at an explicitly accepted launch workload and SLO. Evidence SHALL name the PostgreSQL/Supabase versions, region/topology, pool configuration, commands, workload, latency distributions, catch-up lag, errors, deadlocks, saturation/resource occupancy, lost/duplicate write counts, recovery timings/results, and independent review; PostgreSQL integration tests required by the gate SHALL fail rather than skip when their database is unavailable. This foundation proof SHALL NOT replace any downstream capability's stricter security, concurrency, failure, or user-surface acceptance proof.

#### Scenario: Load evidence is incomplete
- **WHEN** concurrency tests omit resource saturation, raw failures, deadlocks, recovery timing, or the exact environment
- **THEN** activation remains blocked

#### Scenario: No daemon hosts are online
- **WHEN** all user/daemon hosts are offline during the zero-host acceptance run
- **THEN** activated shared control-plane commands that do not require private host content remain available within the accepted service bounds

#### Scenario: Required PostgreSQL CI service is unavailable
- **WHEN** a required PostgreSQL integration job cannot start or reach its database
- **THEN** the job fails visibly instead of reporting a skipped or passing result
