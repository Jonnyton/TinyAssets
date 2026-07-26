## ADDED Requirements

### Requirement: Activated transactional domains have one PostgreSQL authority
The system SHALL use Supabase-hosted PostgreSQL at launch as the sole mutation authority for the activated catalog, ledger, inbox, and market transactional domains. Within this capability, `inbox` SHALL mean durable request/admission records and domain-owned transition/outbox state only; it SHALL NOT include scheduler policy, task ownership, work claiming, execution leases, provider selection, or work-coordination authority. Claim integration SHALL remain blocked until the file-lock versus epoch-2 claim-model contradiction is resolved in PLAN and the owning capability. This capability SHALL NOT authorize another domain to adopt the substrate; any expansion requires a host-approved PLAN amendment and that domain's own separately accepted OpenSpec change. Host-local SQLite/files SHALL remain execution, checkpoint, or rebuildable cache state; separately specified OKF/artifact and private-custody stores SHALL retain their domain authority; GitHub SHALL remain an export/contribution transport; none SHALL become a second mutation authority for the same domain.

#### Scenario: Shared mutation commits once
- **WHEN** an activated shared control-plane command succeeds
- **THEN** its authoritative state transition commits in PostgreSQL
- **AND** any local cache, GitHub export, Realtime message, or artifact projection is derived from that committed version

#### Scenario: Local execution stores remain local
- **WHEN** a daemon checkpoints a run or persists host-local execution/cache state
- **THEN** that state remains outside the shared PostgreSQL authority unless a separately approved domain contract explicitly promotes a public/shared projection

#### Scenario: A durable inbox record is mistaken for a work claim
- **WHEN** PostgreSQL stores a request, admission decision, transition, outbox event, queue-shaped row, lock, or lease
- **THEN** that record grants no scheduler, task-owner, provider-selection, execution-claim, or work-coordination authority
- **AND** claim integration remains disabled until its PLAN and capability owners accept the exact model

### Requirement: Persistence evidence never escalates authority
The system SHALL treat PostgreSQL rows, locks, claims, leases, cursors, receipts, RLS results, and transaction outcomes only as durability evidence for fields already authorized by their owning domain. They SHALL NOT mint, replace, satisfy, or attest provider authority, accepted-market B2/B13 authority, execution admission or isolation evidence, branch/read authority, credential or egress grants, private-custody permission, external-effect authority, compute capacity, payment authority, wallet funding, custody, chain settlement, or chain finality. Provider work SHALL still consume its owner-native authority carrier; execution SHALL still pass trusted pre-launch admission and post-launch actual-execution evidence validation; branch-linked projections SHALL preserve authenticated-subject authority and unreadable-private indistinguishability; and market rows SHALL preserve the paid-market owners' state-machine, descriptor/class identity, fee-version, settlement-identity, and price-evidence invariants.

#### Scenario: A stored provider or execution decision lacks owner authority
- **WHEN** a row, lock, lease, receipt, or transition says that a provider, compute host, model execution, or accepted-market path was selected
- **THEN** no provider call or execution starts unless the provider/B2/B13 and execution-admission owners independently authorize it
- **AND** the persistence record is not accepted as sandbox, launch, capacity, payment, or completion evidence

#### Scenario: A persisted market result lacks payment or price authority
- **WHEN** PostgreSQL stores a request, quote, bid, match, logical reservation, delivery, settlement, or price observation
- **THEN** the owning paid-market command and evidence contracts still determine validity
- **AND** the row alone proves no fee correctness, funding, custody, payout, chain finality, compute availability, or executable capacity

### Requirement: Private-content custody is explicit and secret authority remains outside the control plane
The system SHALL require every private-content field and every private or restricted artifact reference to bind to a separately accepted, per-situation custody policy before persistence. Public immutable artifact references require their accepted artifact authority but SHALL NOT require a private-custody decision. A private custody policy MAY select a host, private universe brain, user vault, or approved platform-held store; this generic substrate SHALL NOT choose among them. The shared PostgreSQL control plane SHALL NOT store requester or host provider credentials, API keys, OAuth tokens, secret-bearing provider subscription authentication/account material, local client authentication files, wallet signing keys, database signing secrets, or other secret authority. Platform-resident domain tables SHALL carry only fields and opaque references allowed by the owning domain's accepted custody, retention, visibility, and access policy; RLS, a service role, or platform-side encryption SHALL NOT create permission by itself.

#### Scenario: Private content has no accepted custody binding
- **WHEN** a command attempts to persist private universe or branch content without an accepted domain custody policy and instance binding
- **THEN** the command is rejected before mutation
- **AND** no platform row, Storage object, log payload, export, ranking input, analytics input, or training input is created from that content

#### Scenario: An accepted policy selects platform-held custody
- **WHEN** an owning domain and user-selected instance policy explicitly allow a private field or artifact to use an approved platform-held store
- **THEN** PostgreSQL records only the allowed data or opaque reference under that policy's visibility, access, retention, residency, deletion, export, and audit controls
- **AND** the generic control-plane contract does not broaden that permission to another field, artifact, tenant, or purpose

#### Scenario: BYOC credentials stay with their owner
- **WHEN** a requester or compute host uses a provider credential to execute work
- **THEN** the credential remains in the requester/host credential boundary
- **AND** PostgreSQL may record only bounded non-secret routing, authority, and receipt metadata approved by the owning domain
- **AND** operational database credentials remain separate from all user BYOC credentials

### Requirement: Production schema starts from an approved observed baseline
The system SHALL require a dated, sanitized, read-only structural inventory of the deployed Supabase project's schemas, tables, columns, constraints, extensions, authentication integration, grants, policies, functions, triggers, roles, indexes, pooling configuration, migration history, untracked/prototype state, and deployment mechanism before production SQL is authored or applied. The inventory SHALL exclude row content, password hashes, secret-valued role settings, DSNs, tokens, and secret literals embedded in function or configuration bodies; it SHALL record secret dependencies only as identifiers, custody locations, rotation/reprovision status, and verification results. After a fresh current-main Claude Opus 5 review and host acceptance of every adaptation, the host SHALL approve that inventory as the production baseline and `db/postgres/migrations/` as the production migration home for TinyAssets-owned application schemas; `prototype/full-platform-v0/migrations/` SHALL remain fixture-only and SHALL NOT be copied, renumbered, or recorded as production history. Supabase-managed Auth, Storage, Realtime, extension, and system schemas SHALL retain separately inventoried and version-pinned vendor history owned by their accepted adapters and SHALL NOT be recorded as TinyAssets migration history. The runner SHALL verify live structure against the approved baseline and abort on unexplained mismatch.

#### Scenario: Missing baseline blocks SQL
- **WHEN** the deployed inventory, host-approved baseline, or production migration home is absent
- **THEN** no production migration identifier is allocated or applied

#### Scenario: Prototype SQL is presented for production
- **WHEN** a production change copies, renumbers, or attempts to baseline a prototype migration
- **THEN** validation fails before database mutation

#### Scenario: Live database differs from the baseline
- **WHEN** the runner observes an unapproved schema, role, policy, function, extension, or migration-history difference from the accepted production baseline
- **THEN** it aborts before applying feature SQL and reports the unexplained mismatch

#### Scenario: Inventory encounters secret-bearing metadata
- **WHEN** the inventory encounters a password hash, secret-valued role setting, DSN, token, row value, or secret literal in a function or configuration body
- **THEN** it omits the value and records only the allowed dependency identifier and verification status
- **AND** the inventory artifact contains no reusable credential or private row content

### Requirement: Migration history is locked and checksum verified
The production migration runner SHALL be the only migration-history executor for TinyAssets-owned application schemas. Supabase Branching, `supabase db push`, dashboard SQL, ORM auto-create, and any other schema tool SHALL be disabled or demonstrably subordinate to it for those schemas; vendor-managed Supabase schemas SHALL remain outside its history. Committed migration identifiers, rows, and checksums SHALL NOT be updated, deleted, or replaced. Repairs SHALL use additive forward migrations. Exceptional baseline reconciliation SHALL require quiescence, a preserved snapshot, explicit dual approval, and an immutable audit record. The runner SHALL use a dedicated direct-connection migration role and DSN, hold one bounded PostgreSQL advisory lock for the run, enforce unique gap-free ordered identifiers, verify exact-byte SHA-256 checksums against immutable `schema_migrations` history, and commit each migration with its history row in one transaction. Duplicate, missing, reordered, drifted, wrong-baseline, partially applied, unverifiable, or lock-timeout states SHALL fail closed.

#### Scenario: Concurrent runners serialize exactly once
- **WHEN** two deploys attempt to apply the same pending migration set concurrently
- **THEN** the advisory lock allows exactly one runner to apply each migration and history row
- **AND** the other runner either observes the completed history or exits with a bounded lock result without duplicate effects

#### Scenario: A second schema tool attempts production mutation
- **WHEN** Supabase Branching, `supabase db push`, dashboard SQL, ORM auto-create, or another non-runner path attempts to change production schema or history
- **THEN** deployment policy or database privilege denies the mutation
- **AND** only the provider-neutral runner can advance the verified migration history

#### Scenario: Applied migration bytes drift
- **WHEN** a migration file's exact bytes no longer match its recorded SHA-256
- **THEN** the runner refuses the run before applying later migrations

#### Scenario: An operator attempts to repair committed history
- **WHEN** an operator attempts to update, delete, replace, or re-checksum a committed migration row
- **THEN** database privilege and runner validation deny the mutation
- **AND** correction requires an additive forward migration or an explicitly dual-approved, quiesced baseline reconciliation with preserved snapshot and immutable audit

#### Scenario: Migration fails mid-transaction
- **WHEN** a migration statement fails before its transaction commits
- **THEN** its schema effects and history row are both absent
- **AND** a later corrected run can retry from the last committed version

#### Scenario: Database begins in a supported non-empty state
- **WHEN** the runner is exercised against fresh, partially applied, populated-upgrade, and structurally pre-existing database fixtures
- **THEN** it accepts only the fixture matching an explicitly supported and verified baseline state
- **AND** every unexplained or partially applied state fails closed

### Requirement: Application and migration authority are separated
The system SHALL keep migration and service-role credentials unavailable to ordinary long-running application request handlers and SHALL deny public, anonymous, authenticated, and ordinary application roles raw table/sequence access to activated domains. Public, anonymous, authenticated, read-only, and ordinary application roles SHALL be unable to run schema DDL, bypass forced RLS, mutate migration history, directly insert/update/delete activated domain tables or sequences, or update/delete immutable audit and accounting history. Reads and mutations SHALL pass through narrowly granted authenticated query/command functions or an equivalent trusted boundary, except for separately approved operational read-only access. Migrations, dumps, restores, persistent sessions, LISTEN/NOTIFY consumers, and advisory-lock owners SHALL use a compatible direct or session connection and SHALL never use transaction pooling; transient application requests MAY use an explicitly tested pool mode whose prepared-statement and connection-reuse behavior matches the driver configuration. Each privileged `SECURITY DEFINER` function SHALL have a non-login owner, fixed safe `search_path`, explicit grants/revokes, and tenant-isolation tests. Deployment SHALL apply approved migrations before activating the new application image, and migration failure SHALL prevent activation.

#### Scenario: Application role attempts migration DML
- **WHEN** an ordinary application role inserts, updates, or deletes a `schema_migrations` row
- **THEN** PostgreSQL denies the operation

#### Scenario: Application role attempts raw domain access
- **WHEN** a public, anonymous, authenticated, or ordinary application role directly selects, inserts, updates, or deletes an activated domain table or sequence
- **THEN** PostgreSQL denies the operation
- **AND** accepted access can proceed only through the narrowly granted authenticated query or command boundary

#### Scenario: Migration fails during deployment
- **WHEN** the migration runner returns a non-success result
- **THEN** the deployment does not activate the candidate application image
- **AND** serving-image recovery remains governed by `uptime-and-alarms`

#### Scenario: A role uses an incompatible pool mode
- **WHEN** a migration, dump, restore, persistent session, LISTEN/NOTIFY consumer, or advisory-lock owner is configured through transaction pooling
- **THEN** configuration validation fails before the operation starts
- **AND** no schema, history, backup, restore, subscription, or lock action runs through that connection

### Requirement: Tenant and actor context is verified and transaction local
Every shared control-plane command SHALL consume actor, tenant, visibility, grant, and ownership decisions from their accepted identity/visibility/domain authorities rather than define a second identity model, trust caller payload, ordinary SQL, or ambient host configuration. A narrowly granted authenticated wrapper or equivalent trusted command boundary SHALL establish database actor/tenant context transaction-locally and independently verify the supplied authoritative context, current object version, and state transition. Public, anonymous, authenticated, and ordinary application roles SHALL NOT call context setters directly or forge context with `SET LOCAL` or `set_config`. Every tenant-owned canonical row SHALL carry the canonical tenant/owner identity, and tenant scope SHALL participate in relevant foreign keys, uniqueness constraints, and indexes. Forced RLS SHALL provide defense in depth and SHALL NOT be the source of positive mutation authority.
For catalog or branch-linked projections, the command and query boundaries SHALL preserve unreadable-private indistinguishability: row presence, absence, counts, conflict or foreign-key errors, timing classes, and RLS behavior SHALL NOT reveal an unreadable private branch or version, and caller-supplied branch identifiers SHALL NOT create readability.

#### Scenario: Payload identity conflicts with authentication
- **WHEN** a request payload supplies an actor or tenant different from the verified request context
- **THEN** the command rejects without mutation

#### Scenario: Ordinary SQL attempts to forge tenant context
- **WHEN** an ordinary role calls a context setter or uses `SET LOCAL` or `set_config` to claim another actor or tenant
- **THEN** privilege or command validation denies the attempt without mutation
- **AND** exception, cancellation, and pooled-connection cleanup leave no forged or prior context

#### Scenario: Pooled connection is reused across tenants
- **WHEN** a connection that completed a tenant-A transaction is reused for tenant B
- **THEN** no tenant-A transaction-local context remains
- **AND** tenant B cannot read or mutate tenant-A rows

#### Scenario: RLS-visible row lacks command authority
- **WHEN** an actor can read a row through a permitted projection but lacks the current grant or state-transition authority
- **THEN** the command rejects without mutation

#### Scenario: A private branch is not readable
- **WHEN** an actor addresses a catalog or inbox projection linked to an unreadable private branch or version
- **THEN** the result is indistinguishable from an absent target under the owning branch-authority contract
- **AND** PostgreSQL row existence, RLS behavior, conflicts, or foreign-key errors reveal no private metadata

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
The system SHALL keep schema, constraints, migration history, and core domain transactions runnable on a supported stock PostgreSQL deployment without application-domain rewrites. Before activation it SHALL prove a documented export, restore, migration verification, and representative domain read/write path outside Supabase; any Supabase-specific Auth, Realtime, Storage, pooling, or operational behavior SHALL remain behind replaceable adapters. Recovery and exit drills SHALL default to synthetic data. Any production snapshot SHALL require explicit custody and residency approval, encryption, least-privilege access, a retention deadline, cleanup proof, and replacement rather than restoration of reusable credentials. The recovery and exit plan SHALL explicitly account for Storage object bodies, custom-role secrets that database dumps exclude, subscriptions, publication state, replication slots, expected downtime, and accepted RPO/RTO instead of treating a SQL dump as complete recovery.

#### Scenario: Exit rehearsal restores to stock PostgreSQL
- **WHEN** the approved production-shaped dataset and migration history are exported from the Supabase-shaped environment and restored to supported stock PostgreSQL
- **THEN** checksums, row counts, constraints, and migration history verify
- **AND** representative authenticated domain transactions pass through the same application-domain contracts
- **AND** every Storage body, subscription, publication, replication slot, or replacement needed by an accepted domain or custody mode is restored or regenerated through its approved path and verified
- **AND** every required role or database secret is newly generated or rotated, rebound, and verified without restoring any reusable credential value from the backup
- **AND** an optional Supabase-only adapter may remain disabled only when no canonical data or secret authority is lost and the stock-PostgreSQL deployment still meets the accepted service, downtime, RPO, and RTO bounds
- **AND** any missing required dependency fails the rehearsal and blocks activation

#### Scenario: Supabase adapter is unavailable
- **WHEN** a Supabase-specific notification or operational adapter is unavailable but PostgreSQL remains reachable
- **THEN** canonical transaction truth remains intact
- **AND** the system reports the degraded adapter honestly instead of accepting mutation through an alternate authority

#### Scenario: A preview database is requested
- **WHEN** a branch or preview environment needs production-shaped data
- **THEN** it receives a privacy-safe synthetic dataset with recorded generator version, access-classified row counts, content hashes, and size characteristics
- **AND** the seed contains no production value, digest, sensitive low-cardinality distribution, private row, object body, credential, or secret authority

#### Scenario: A preview database is created
- **WHEN** a new branch or preview database is provisioned
- **THEN** it contains no production row, Storage object body, credential, or secret authority
- **AND** it remains data-less until an explicit versioned privacy-safe synthetic seed is applied
- **AND** an empty preview is not accepted as production-shaped launch or load evidence

### Requirement: Activation requires zero-host, security, recovery, and load proof
The PostgreSQL control plane SHALL remain dark until the shared `production-load-evidence` implementation and an accepted evidence-schema version have landed and a production-shaped isolated environment records dated evidence under that protocol for zero-daemon-host shared operation, tenant/role isolation, actor binding, connection-pool context safety and exhaustion, concurrent runner serialization/recovery, transaction contention and database failure, backup/restore, stock-PostgreSQL exit, prior-application compatibility, and bounded behavior at a capability-owned, explicitly accepted launch workload and SLO. Every enabled accepted notification adapter SHALL additionally prove duplicate/reorder/disconnect/catch-up behavior; a disabled or unaccepted adapter SHALL be recorded as `unavailable` or inapplicable while durable version/outbox recovery remains unconditional. Evidence SHALL name the protocol schema version, PostgreSQL/Supabase versions, region/topology, pool configuration, commands, workload, latency distributions, catch-up lag, errors, deadlocks, saturation/resource occupancy, lost/duplicate write counts, recovery timings/results, and independent review; PostgreSQL integration tests required by the gate SHALL fail rather than skip when their database is unavailable. Until the shared implementation lands, the PostgreSQL load packet SHALL remain `not_run` with the protocol dependency code and SHALL NOT use a capability-local substitute. This foundation proof SHALL NOT replace any downstream capability's stricter security, concurrency, failure, or user-surface acceptance proof.

#### Scenario: Load evidence is incomplete
- **WHEN** concurrency tests omit resource saturation, raw failures, deadlocks, recovery timing, or the exact environment
- **THEN** activation remains blocked

#### Scenario: No daemon hosts are online
- **WHEN** all user/daemon hosts are offline during the zero-host acceptance run
- **THEN** activated shared control-plane commands that do not require private host content remain available within the accepted service bounds

#### Scenario: Required PostgreSQL CI service is unavailable
- **WHEN** a required PostgreSQL integration job cannot start or reach its database
- **THEN** the job fails visibly instead of reporting a skipped or passing result
