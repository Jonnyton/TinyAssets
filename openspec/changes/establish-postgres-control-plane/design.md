## Context

The final architecture already names Supabase/PostgreSQL as the target shared
control plane and GitHub as an export sink, but production still runs on one
host-mounted SQLite volume. The only PostgreSQL migrations in the repository
live under `prototype/full-platform-v0/`, whose README and schema mark them as
throwaway fixtures. PLAN also retains one stale open tension that calls the
already-selected PostgreSQL/GitHub boundary unresolved.

This creates a shared dependency for moderation, paid-market transport,
catalog/collaboration, authoring, and handoff/outcome work: none can safely
invent a numbered production migration or a temporary SQLite authority before
the platform establishes its production baseline and migration substrate.

The host selected Option 1 on 2026-07-23: Supabase-hosted PostgreSQL is the sole
launch authority for shared multi-user control-plane state, with provider-
neutral migrations and a tested stock-PostgreSQL self-host exit. This design is
planning/scaffolding only. The source decision packet still requires an
independent Claude re-check after provider capacity resets; any adaptation
requires renewed host acceptance before PLAN, runtime, migrations, or
production are changed.

That re-check must also reconcile a privacy contradiction: PLAN's commons-first
rule says the platform never stores private content, while passages in the
integrated architecture note permit private drafts or instance blobs in
Supabase Storage. This change carries the host-selected host-only boundary as a
review-blocked requirement and does not treat the older storage passages as
accepted authority.

## Goals / Non-Goals

**Goals:**

- Give shared multi-user control-plane state one authoritative transactional
  home that remains available with zero daemon hosts online.
- Preserve the commons-first boundary: public/shared control-plane data may be
  platform-resident; private universe/branch content remains host-only.
- Preserve BYOC: requester/host provider credentials, model weights, and
  execution authority never become control-plane secrets.
- Establish a production-native migration home, baseline, locked runner, role
  model, and fail-closed drift contract before any domain migration.
- Keep domain authority explicit: OKF bundles and other separately specified
  artifact stores remain authoritative for their own content; local SQLite and
  files remain execution, checkpoint, private-content, or rebuildable cache
  state.
- Make Supabase replaceable by proving export/restore and operation on stock
  PostgreSQL without application-domain rewrites.
- Require tenant/security, concurrency/load, backup/recovery, and zero-host
  evidence before activation.

**Non-Goals:**

- Implement the runner, schema, domain stores, APIs, deployment, or Supabase
  changes in this review-blocked lane.
- Select which legacy local records migrate or assign field-level
  public/private classifications.
- Store private content, model/provider credentials, wallet signing keys,
  user-owned model weights, or host execution artifacts in PostgreSQL.
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

PostgreSQL owns shared identity-bound catalog/collaboration state, moderation
and audit history, host registry, shared inbox/bid lifecycle, and logical
market-accounting state once each domain lands. It does not become a universal
blob store. Private instance content remains absent from the platform, OKF and
artifact stores retain their separate authority, and daemon-local state stays
local.

Alternatives considered:

- **Dual PostgreSQL/SQLite authority:** rejected because conflict recovery,
  replay, and money/moderation correctness would require permanent
  reconciliation and violate one-mutation-authority.
- **Git/OKF plus PostgreSQL split for shared control-plane mutation:** rejected
  for launch because cross-store transactions and outboxes multiply failure
  modes; GitHub remains export/contribution transport.
- **Keep the deployed SQLite bridge:** rejected because it cannot provide the
  target multi-user concurrency or zero-host independence.

### Supabase hosts launch, while PostgreSQL remains the application contract

Launch uses Supabase-managed PostgreSQL, but this selection does not replace or
redefine the canonical identity/auth contract. Tables, constraints, migrations,
and core domain transactions use stock PostgreSQL semantics. Supabase Auth,
Realtime, Storage, pooling, and other managed services remain unresolved
adapter options at replaceable edges until their owning capabilities accept
them. A tested export/restore path into supported stock PostgreSQL is an
activation gate, not future documentation.

Running a TinyAssets-operated PostgreSQL stack at launch was rejected because
it adds independent auth, realtime, backup, upgrade, and incident-response
surfaces before the zero-host product path is restored.

### Production begins from observed reality, not prototype numbering

Before SQL is authored, a read-only inventory records the deployed Supabase
project's schemas, extensions, functions, policies, roles, indexes, migration
history, and deployment mechanism. The host approves that inventory as the
baseline. Only then can a migration identifier be allocated under
`db/postgres/migrations/`.

`prototype/full-platform-v0/migrations/` remains fixture provenance. Copying,
renumbering, or baselining those files into production is forbidden because
their init-on-empty assumptions, duplicate numbering, broad prototype roles,
and bearer/user-id shim are not production authority.

### One provider-neutral runner owns schema history

The runner uses a dedicated migration DSN and non-application role, a bounded
PostgreSQL advisory lock, exact-byte SHA-256 checksums, ordered gap-free
history, and one transaction per migration plus history row. Duplicate,
missing, reordered, drifted, wrong-baseline, partially applied, or lock-timeout
states fail closed.

The application role cannot bypass RLS, run DDL, mutate migration history, or
rewrite immutable audit/accounting history. Production deployment runs the
approved migrations before activating a candidate image; schema failure blocks
candidate activation. `uptime-and-alarms` retains ownership of serving-image
rollback, system DR, alarms, and RPO/RTO behavior.

Alternatives such as ORM auto-create, app-start migrations, and a Supabase-only
CLI history were rejected because long-running application credentials must
not carry schema authority and the exit path must reproduce the same history.

### RLS is defense in depth, not positive mutation authority

Every request derives actor and tenant from verified authentication context;
payload-supplied identity is never authoritative. Transaction-local tenant and
actor context plus forced RLS constrain reads/writes, while domain command
boundaries independently lock and verify current object version, actor,
tenant, grant, and state transition. Connection-pool reuse must not leak prior
transaction context.

The exact canonical personal/org tenant mapping remains a pre-implementation
design dependency owned by `identity-auth-and-access-control`,
`universe-visibility`, and each domain command contract. This substrate
consumes their accepted mappings and grants; it does not define them. No schema
can invent a second identity model merely to unblock a domain.

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

The isolated production-shaped proof must cover concurrent migration runners,
role/RLS isolation, pooled-connection context, domain transaction contention,
Realtime disconnect/replay, backup/restore, stock-PostgreSQL exit, prior-image
compatibility, zero-host operation, and §14 load/resource measurements. Tests
that skip when PostgreSQL is unavailable do not satisfy the CI gate.

## Risks / Trade-offs

- **[PLAN and source review diverge]** → Keep this lane draft/review-blocked;
  reconcile PLAN and adapt the change only after Claude re-check plus host
  acceptance.
- **[Supabase features leak into domain code]** → Put provider-specific Auth,
  Realtime, Storage, and operations behind adapters; test the same migrations
  and domain transactions on stock PostgreSQL.
- **[RLS is mistaken for authorization]** → Require authenticated command
  boundaries and transaction-local context in addition to forced RLS.
- **[A domain becomes a second migration owner]** → Allocate all production
  identifiers from the approved platform history; domain changes own only
  their later domain migrations.
- **[Private content enters the commons database]** → Define an explicit data
  classification/ownership review before every table; reject private instance
  content rather than encrypting it platform-side.
- **[Cutover loses or duplicates state]** → Quiesce, export once, verify
  counts/hashes, retain the source snapshot, and never dual-mutate.
- **[Managed-service outage becomes platform outage]** → Exercise backup,
  restore, regional/provider recovery, and stock-PostgreSQL exit; publish
  honest degraded-state evidence.
- **[Migration rollback corrupts immutable history]** → Additive migrations
  plus prior-image compatibility before cutover; forward-fix after first
  authoritative write.

## Migration Plan

0. Obtain the required Claude source re-check; host accepts or rejects every
   adaptation. Reconcile PLAN's stale open tension only after acceptance.
1. Inventory the deployed Supabase project read-only and obtain host approval
   of the production baseline, migration home, tenant mapping, and role model.
2. Land the provider-neutral migration runner, dedicated roles, checksum
   history, baseline verification, and real-PostgreSQL CI without any domain
   table.
3. Prove backup/restore, stock-PostgreSQL exit, concurrent runner behavior,
   connection-pool isolation, and deploy-before-activate failure semantics.
4. Add one dark, additive downstream transaction slice—moderation flag intake
   is the candidate—using the approved identity/artifact authorities.
5. Run security, concurrency/load, prior-image compatibility, Realtime
   recovery, zero-host, and rendered user-surface acceptance where applicable.
6. Quiesce and import any separately approved shared legacy state, verify
   counts/hashes, preserve the source snapshot, then obtain explicit host
   approval for the recorded first-write boundary and enable exactly one
   PostgreSQL mutation authority.
7. Fold generic migration requirements out of dependent domain changes, sync
   the implemented `postgres-control-plane` capability, and archive this
   change only after production evidence and independent review.

The pending `complete-plan-gated-platform-targets` lane remains the owner of
catalog/collaboration topology and the still-separate private-data,
portability/deletion, succession, and feedback decisions. This change depends
on those decisions where they affect a table; it does not absorb them.

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
- Which canonical artifact/catalog record supplies identity and ownership to
  the first moderation transaction without creating a copied authority?
- Which Supabase Auth, Realtime, Storage, pooling, backup, and observability
  features are accepted at launch, and what are their stock-PostgreSQL
  replacements?
- What RPO/RTO, region/residency, deletion/export, retention, and legal-hold
  contracts will later govern shared control-plane data?
- Which downstream domain becomes the first dark transaction after the
  substrate passes its own gates?
