## Why

TinyAssets' shared multi-user surfaces need one production authority that stays
available with zero daemon hosts online, but the deployed service still uses a
single-host SQLite bridge and the repository has no approved production
PostgreSQL baseline, migration home, or runner. The host selected
Supabase-hosted PostgreSQL with a stock-PostgreSQL exit path on 2026-07-23.
Current PLAN truth scopes that authority to the catalog, ledger, inbox, and
market transactional domains. This change preserves that boundary as a
review-blocked executable contract without treating the selection as
implementation authority before a fresh current-main Claude Opus 5 review and
host acceptance of any adaptation.

## What Changes

- Add a target-only contract for PostgreSQL authority over the catalog,
  ledger, inbox, and market transactional domains while preserving
  custody-neutral private content, domain-authoritative OKF/artifact stores,
  and host-local execution/cache state.
- Establish `db/postgres/migrations/` as the only future production SQL home
  for TinyAssets-owned application schemas, gated by a sanitized read-only
  inventory and host-approved baseline of the deployed Supabase project.
- Require a provider-neutral, advisory-lock and checksum-verified migration
  runner with separate migration/application roles and fail-closed drift
  handling.
- Require a tested stock-PostgreSQL export/restore exit, zero-host availability,
  tenant isolation, and complete-system concurrency/load evidence before
  activation.
- Keep GitHub as an export/contribution transport and
  `prototype/full-platform-v0/migrations/` as fixture-only provenance.
- Forbid dual-authority writes, SQLite fallback mutation, and storage of
  requester provider credentials, signing keys, or other secret authority in
  the shared control plane. Private-content custody remains a per-situation
  choice owned by its accepted domain policy.
- Treat the first canonical PostgreSQL production write as a separately
  recorded, host-approved one-way boundary after the baseline and exit drills
  pass.
- Keep all implementation, production inventory, migration application, and
  publication blocked until the required opposite-provider review returns and
  the host accepts any resulting adaptation.

## Capabilities

### New Capabilities

- `postgres-control-plane`: Domain-bounded PostgreSQL authority, production
  baseline and migration integrity, role/tenant isolation, custody and BYOC
  boundaries, stock-PostgreSQL exit, cutover, and scale/availability proof.

### Modified Capabilities

None. Domain capabilities continue to own their business invariants and consume
this substrate after it is accepted and implemented. The active paid-market
change must eventually depend on this capability rather than becoming a second
owner of the generic production migration runner.

## Impact

Planning names the future production surfaces
`db/postgres/migrations/`, `tinyassets/storage/postgres_migrations.py`,
`scripts/postgres_migrate.py`, deployment configuration/workflows, and focused
PostgreSQL integration/load tests. No runtime, API, canonical spec, PLAN,
Supabase project, or production data changes in this review-blocked lane.

The catalog, ledger, inbox, and market owners must wait for the accepted
baseline and migration substrate before production SQL, cutover, or activation;
pure domain implementation does not depend on the database substrate.
Moderation, operator-request admission, collaboration, authoring, handoff, or
another domain may opt in only after a host-approved PLAN amendment and its own
separately accepted capability contract. Existing daemon-local SQLite,
SqliteSaver, knowledge/memory stores, OKF bundles, artifact stores, and
private-content custody choices are not migrated or reclassified here.
