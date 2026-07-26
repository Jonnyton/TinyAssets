## Context

The final architecture names Supabase/PostgreSQL as the canonical
transactional store for the catalog, ledger, inbox, and market domains and
GitHub as their export sink, while production still runs on one host-mounted
SQLite volume. The only PostgreSQL migrations in the repository live under
`prototype/full-platform-v0/`, whose README and schema mark them as throwaway
fixtures.

This creates a shared dependency for catalog, ledger, inbox, and market work:
none can safely invent a numbered production migration or a temporary SQLite
authority before the platform establishes its production baseline and
migration substrate. Another domain may adopt it only after a host-approved
PLAN amendment and its own separately accepted capability contract.

The host selected Option 1 on 2026-07-23: Supabase-hosted PostgreSQL is the sole
launch authority for those transactional domains, with provider-neutral
migrations and a tested stock-PostgreSQL self-host exit. Current PLAN truth
also leaves private-data custody deliberately situational: an accepted owning
policy and user-selected instance may choose a host, private universe brain,
vault, or approved platform-held store. This substrate remains custody-neutral
and never stores provider credentials, signing keys, or secret authority.

This design is planning/scaffolding only. A fresh review against current main
by Claude Opus 5 and renewed host acceptance of every adaptation are required
before publication, PLAN edits, runtime, migrations, inventory, or production
changes.

## Goals / Non-Goals

**Goals:**

- Give the catalog, ledger, inbox, and market domains one authoritative
  transactional home that remains available with zero daemon hosts online.
- Remain neutral about private-content custody while requiring every persisted
  private field or reference to have an accepted domain policy and per-instance
  binding.
- Preserve BYOC: requester/host provider credentials, signing keys, and
  execution authority never become control-plane secrets.
- Establish a production-native migration home, baseline, locked runner, role
  model, and fail-closed drift contract before any domain migration.
- Keep domain authority explicit: OKF bundles and other separately specified
  artifact stores remain authoritative for their own content; local SQLite and
  files remain execution, checkpoint, or rebuildable cache state unless an
  owning capability explicitly assigns another authority.
- Make Supabase replaceable by proving export/restore and operation on stock
  PostgreSQL without application-domain rewrites.
- Require tenant/security, concurrency/load, backup/recovery, and zero-host
  evidence before activation.

**Non-Goals:**

- Implement the runner, schema, domain stores, APIs, deployment, or Supabase
  changes in this review-blocked lane.
- Select which legacy local records migrate or assign field-level
  public/private classifications.
- Decide where private content or user-owned model weights live; those
  per-situation custody choices belong to accepted owning policies.
- Store model/provider credentials, wallet signing keys, database signing
  secrets, or host execution authority in PostgreSQL.
- Replace LangGraph `SqliteSaver`, daemon-local SQLite stores, the OKF brain
  contract, or other domain-authoritative artifact stores.
- Decide retention, deletion, export, legal hold, residency, analytics, or
  training-use policy.
- Authorize analytics, telemetry reuse, training access, private-content
  backup/legal access, or multi-cloud federation.
- Promote or renumber prototype migrations.
- Make Realtime, GitHub, caches, replicas, or local projections mutation
  authorities.

## Decisions

### Shared control-plane authority is domain-bounded

PostgreSQL owns the catalog, ledger, inbox, and market transactional state once
each domain lands. It does not become a universal blob store or implicitly own
identity, moderation, host registry, authoring, handoff, or private-content
custody. OKF, artifact, vault, and host-local stores retain authority assigned
by their owning capabilities.

`Inbox` has the narrowest safe meaning under current PLAN truth: durable
request/admission records plus domain-owned transition and outbox state. It
does not include scheduler policy, task ownership, work claiming, execution
leases, provider selection, or work-coordination authority. PLAN still says
one file-locked claimer while the live coordination board records epoch-2
transactional claiming; this change does not resolve that contradiction.
Claim integration and rollout remain blocked until a host-approved PLAN
reconciliation and the owning capability delta define the model.

Alternatives considered:

- **Dual PostgreSQL/SQLite authority:** rejected because conflict recovery,
  replay, and money/moderation correctness would require permanent
  reconciliation and violate one-mutation-authority.
- **Two mutation authorities inside one domain:** rejected because cross-store
  transactions and reconciliation multiply failure modes. The canonical
  cross-domain split remains: PostgreSQL for catalog/ledger/inbox/market, OKF
  for commons/default brain organization, and GitHub as export/contribution
  transport.
- **Keep the deployed SQLite bridge:** rejected because it cannot provide the
  target multi-user concurrency or zero-host independence.

### Persistence records never mint cross-domain authority

PostgreSQL proves only that an accepted command durably committed the fields
owned by its domain. A row, lock, claim, lease, outbox event, cursor, receipt,
RLS result, or transaction outcome cannot create, replace, or attest authority
owned elsewhere.

In particular:

- provider work continues to require #1784's owner-native
  `ProviderInvocation`/`ProviderExecutor` authority or accepted-market B2/B13
  authority before ordinary routing;
- execution continues to require #1573's trusted requirement, sealed binding,
  and two-phase admission/evidence validation; a queue row or database lease
  is not sandbox or execution-admission evidence;
- branch/catalog projections consume #1797's authenticated-subject and
  readable-version authority, including indistinguishability of unreadable
  private state, rather than inferring permission from row presence or RLS
  visibility;
- paid-market state machines and accounting remain owned by #1786, while
  descriptor/market-class identity, fee-schedule/version, settlement identity,
  and price evidence remain owned by #1798; a stored request, quote, match,
  reservation, or settlement row creates no compute capacity, payment, wallet,
  custody, chain-finality, or execution authority; and
- real-world handoff lifecycle, receipts, and outcome-registry extensions
  remain owned by #1800; a handoff-shaped row or receipt grants no handoff
  authority, and prototype migration `014_real_world_handoffs.sql` remains
  fixture provenance rather than production migration history; and
- credential, egress, private-custody, and external-effect owners remain the
  only sources of their grants and evidence.

This is an enforcement boundary, not a new public MCP primitive or a second
identity/authority system.

### Supabase hosts launch, while PostgreSQL remains the application contract

Launch uses Supabase-managed PostgreSQL, but this selection does not replace or
redefine the canonical identity/auth contract. Tables, constraints, migrations,
and core domain transactions use stock PostgreSQL semantics. Supabase Auth,
Realtime, Storage, pooling, and other managed services remain unresolved
adapter options at replaceable edges until their owning capabilities accept
them. A tested export/restore path into supported stock PostgreSQL is an
activation gate, not future documentation.

The exit and recovery inventory includes what a database dump does not:
Supabase Storage object bodies, custom-role secrets, subscriptions,
publication state, replication slots, expected downtime, and accepted RPO/RTO.
Preview branches are data-less until populated by a versioned, privacy-safe
synthetic generator whose row counts, hashes, and size characteristics are
recorded. Privacy-safe means it uses no production values, digests, or
sensitive low-cardinality distributions; its aggregate counts and hashes are
access-classified. Private production data never seeds a preview.

Recovery and exit drills default to synthetic data. A production snapshot may
be used only with explicit custody and residency approval, encryption,
least-privilege access, a retention deadline, cleanup proof, and replacement
of reusable credentials before the restored environment is exercised.

Running a TinyAssets-operated PostgreSQL stack at launch was rejected because
it adds independent auth, realtime, backup, upgrade, and incident-response
surfaces before the zero-host product path is restored.

### Production begins from observed reality, not prototype numbering

Before SQL is authored, a sanitized read-only inventory records structural
metadata for the deployed Supabase project's schemas, extensions, functions,
policies, roles, indexes, migration history, and deployment mechanism. It
never records rows, password hashes, secret-valued role settings, DSNs/tokens,
or secret literals from function/configuration bodies. Secret dependencies are
represented only by identifiers, custody locations, rotation/reprovision
status, and verification results. The host approves that inventory as the
baseline. Only then can a TinyAssets-owned application-schema migration
identifier be allocated under `db/postgres/migrations/`.

Supabase-managed Auth, Storage, Realtime, extension, and system schemas retain
their vendor-managed history. Their adapter owners inventory and pin compatible
versions and map required stock-PostgreSQL replacements; the TinyAssets runner
does not import or rewrite vendor history.

`prototype/full-platform-v0/migrations/` remains fixture provenance. Copying,
renumbering, or baselining those files into production is forbidden because
their init-on-empty assumptions, duplicate numbering, broad prototype roles,
and bearer/user-id shim are not production authority.
That includes #1800's `014_real_world_handoffs.sql`: its merged runtime owner
does not expand the four PostgreSQL domains or authorize promotion of its
prototype SQL.

### One provider-neutral runner owns schema history

The runner is the sole migration-history executor for TinyAssets-owned
application schemas. Supabase Branching, `supabase db push`, dashboard SQL,
ORM auto-create, and other tools are disabled or demonstrably subordinate for
those schemas; vendor-managed Supabase schemas remain outside its history.
Committed migration rows, identifiers, and checksums are never updated or
deleted. Repairs use additive forward migrations. Exceptional baseline
reconciliation requires quiescence, a preserved snapshot, explicit dual
approval, and an immutable audit record. The runner uses a dedicated
direct-connection
migration DSN and non-application role, a bounded PostgreSQL advisory lock,
exact-byte SHA-256 checksums, ordered gap-free history, and one transaction per
migration plus history row. Duplicate, missing, reordered, drifted,
wrong-baseline, partially applied, or lock-timeout states fail closed.

The application role cannot bypass RLS, run DDL, mutate migration history, or
rewrite immutable audit/accounting history. Production deployment runs the
approved migrations before activating a candidate image; schema failure blocks
candidate activation. `uptime-and-alarms` retains ownership of serving-image
rollback, system DR, alarms, and RPO/RTO behavior.

Connection mode is role-specific: migrations, dumps, restores, persistent
sessions, LISTEN/NOTIFY consumers, and advisory locks never use transaction
pooling. Transient application paths may use an explicitly tested pool mode
only when its prepared-statement and connection-reuse behavior matches the
driver configuration.

Alternatives such as ORM auto-create, app-start migrations, and a Supabase-only
CLI history were rejected because long-running application credentials must
not carry schema authority and the exit path must reproduce the same history.

### RLS is defense in depth, not positive mutation authority

Every request derives actor and tenant from verified authentication context;
payload-supplied identity and ordinary SQL are never authoritative. Activated
domain tables and sequences revoke raw access from public, anonymous,
authenticated, and ordinary application roles. Narrowly granted authenticated
query/command wrappers or an equivalent trusted boundary establish
transaction-local actor and tenant context, lock and verify current object
version, grant, and state transition, and access the rows. Ordinary roles
cannot gain protected-row access by calling a context setter or forging
`SET LOCAL`/`set_config`.
Connection-pool reuse, exceptions, and cancellation must not leak prior
transaction context.

The exact canonical personal/org tenant mapping remains a per-domain
pre-implementation dependency owned by `identity-auth-and-access-control`,
`universe-visibility`, and each domain command contract. This substrate
consumes their accepted mappings and grants; it does not define them. A missing
organization mapping blocks only organization-scoped activation, not an
otherwise accepted personal-domain slice. No schema can invent a second
identity model merely to unblock a domain.

Catalog and branch-linked projections additionally consume the landed branch
authority helpers and SHALL preserve unreadable-private indistinguishability:
row existence, foreign-key failure shape, count, timing, conflict text, or RLS
behavior cannot reveal an unreadable private branch or version. PostgreSQL
does not make a caller-selected branch readable.

Tenant identity must participate in every tenant-owned foreign-key, unique, and
lookup boundary where an unscoped identifier could otherwise cross tenants.
Any privileged database function has a non-login owner, fixed safe
`search_path`, explicit grants/revokes, and focused cross-tenant tests.

### Realtime and exports carry invalidations or projections, never truth

The authoritative transaction appends any required outbox event in the same
commit. Realtime delivery is at-least-once notification; clients recover from
disconnects by reading versioned PostgreSQL state. GitHub exports are
periodic/public projections, and imported contributions pass through the same
validated command boundary before becoming authoritative.

### Cutover has one reversible boundary

Before the first PostgreSQL-only production write, the application path can be
disabled and the additive schema left unused. Any accepted legacy shared state
is moved through a quiesced one-time import with counts, hashes, and a
preserved source snapshot. Shadow reads may compare projections; dual mutation
is forbidden.

After the first authoritative write, rollback means disabling new writes where
necessary and forward-fixing while preserving audit/accounting history. It
never means down-migrating, resuming SQLite mutation, or replaying into a
second authority.

The first write is not an incidental deploy event: it requires a recorded,
host-approved boundary after the baseline, migration, recovery, exit, and
capability-specific evidence gates pass.

### Activation evidence covers the complete dependency, not only SQL syntax

The isolated production-shaped proof uses the landed shared
`production-load-evidence` protocol implementation and its accepted schema
version. It covers concurrent migration runners, role/RLS isolation,
pooled-connection context, domain transaction contention, backup/restore,
stock-PostgreSQL exit, prior-image compatibility, zero-host operation, and
capability-owned workload/SLO thresholds. Every enabled accepted notification
adapter also proves duplicate/reorder/disconnect/catch-up behavior; a disabled
or unaccepted adapter is recorded as `unavailable` or inapplicable while
durable version/outbox recovery remains unconditional. Tests that skip when
PostgreSQL is unavailable do not satisfy the CI gate.

## Risks / Trade-offs

- **[Review evidence is stale]** → Keep this lane local and review-blocked
  until a fresh current-main Claude Opus 5 review plus host acceptance.
- **[Supabase features leak into domain code]** → Put provider-specific Auth,
  Realtime, Storage, and operations behind adapters; test the same migrations
  and domain transactions on stock PostgreSQL.
- **[RLS is mistaken for authorization]** → Require authenticated command
  boundaries and transaction-local context in addition to forced RLS.
- **[A domain becomes a second migration owner]** → Allocate all production
  identifiers from the approved platform history; domain changes own only
  their later domain migrations.
- **[Custody permission is inferred]** → Require an accepted owning-domain
  policy and per-instance custody binding before any private field or artifact
  reference is persisted; encryption or RLS alone does not grant permission.
- **[Cutover loses or duplicates state]** → Quiesce, export once, verify
  counts/hashes, retain the source snapshot, and never dual-mutate.
- **[Managed-service outage becomes platform outage]** → Exercise backup,
  restore, regional/provider recovery, and stock-PostgreSQL exit; publish
  honest degraded-state evidence.
- **[Migration rollback corrupts immutable history]** → Additive migrations
  plus prior-image compatibility before cutover; forward-fix after first
  authoritative write.
- **[Backup is mistaken for complete recovery]** → Inventory Storage object
  bodies, excluded role secrets, subscriptions/publications/replication slots,
  downtime, RPO, and RTO in every restore and exit rehearsal.
- **[Preview data leaks production content]** → Preview branches are data-less
  until populated by versioned privacy-safe synthetic seeds with recorded
  hashes, counts, and size characteristics.

## Migration Plan

0. Obtain a fresh current-main Claude Opus 5 review; the host accepts or
   rejects every adaptation before this local lane is published or used as
   build authority.
1. Inventory the deployed Supabase project through the sanitized structural
   procedure and obtain host approval of the production baseline, migration
   home, tenant mapping, and role model.
2. Land the provider-neutral migration runner, dedicated roles, checksum
   history, baseline verification, and real-PostgreSQL CI without any domain
   table.
3. Prove complete backup/restore and stock-PostgreSQL exit, concurrent runner
   behavior, role-specific connection modes, preview-data isolation, and
   deploy-before-activate failure semantics.
4. Select the shortest ready catalog, ledger, inbox, or market transaction
   slice whose applicable identity, artifact, custody, and domain contracts
   are accepted; do not require an irrelevant artifact or custody dependency
   and do not hard-code a moderation dependency.
5. Run security, the shared production-load-evidence protocol with
   capability-owned thresholds, prior-image compatibility, Realtime recovery,
   zero-host, and rendered user-surface acceptance where applicable.
6. Quiesce and import any separately approved shared legacy state, verify
   counts/hashes, preserve the source snapshot, then obtain explicit host
   approval for the recorded first-write boundary and enable exactly one
   PostgreSQL mutation authority.
7. Fold generic migration requirements out of dependent domain changes, sync
   the implemented `postgres-control-plane` capability, and archive this
   change only after production evidence and independent review.

Current identity, universe visibility, branch authority, provider authority,
execution admission, paid-market Wave 2, live-price discovery,
operator-request, outbound-boundary, moderation, and custody owners retain
their domain decisions. `harden-production-load-evidence` owns the shared
evidence protocol. Its dependent implementation successor is still open as
draft PR #1792 and is not main authority; it must land an accepted schema and
implementation before this capability executes load proof. This change owns
only its population, SLO, and adapter, and consumes accepted decisions only
where a catalog, ledger, inbox, or market table needs them.

Before step 6's first authoritative write, rollback disables the new path and
leaves additive schema unused. After it, rollback is forward-fix only for data
and schema; code rollback requires proven compatibility with the current
schema.

## Open Questions

- What schemas, extensions, roles, RLS policies, functions, and migration
  history actually exist in the deployed Supabase project?
- What is the canonical tenant mapping for a personal account versus an
  organization: authenticated subject, WorkOS organization, or another
  accepted identity owner?
- Which accepted catalog, ledger, inbox, or market transaction is the shortest
  ready first dark slice without creating a copied identity or custody
  authority?
- Which Supabase Auth, Realtime, Storage, pooling, backup, and observability
  features are accepted at launch, and what are their stock-PostgreSQL
  replacements?
- What RPO/RTO, region/residency, deletion/export, retention, and legal-hold
  contracts will later govern shared control-plane data?
- Which downstream domain becomes the first dark transaction after the
  substrate passes its own gates?
- Which private fields or artifact references, if any, does that domain's
  accepted per-situation custody policy allow the platform to hold?
