## Why

TinyAssets' shared multi-user surfaces need one production authority that stays
available with zero daemon hosts online, but the deployed service still uses a
single-host SQLite bridge and the repository has no approved production
PostgreSQL baseline, migration home, or runner. The host selected
Supabase-hosted PostgreSQL with a stock-PostgreSQL exit path on 2026-07-23;
this change preserves that boundary as a review-blocked executable contract
without treating the selection as implementation authority before the required
Claude source re-check and host acceptance of any adaptation.

## What Changes

- Add a target-only contract for PostgreSQL authority over shared multi-user
  control-plane state while preserving host-only private content,
  domain-authoritative OKF/artifact stores, and host-local execution/cache
  state.
- Establish `db/postgres/migrations/` as the only future production SQL home,
  gated by a read-only inventory and host-approved baseline of the deployed
  Supabase project.
- Require a provider-neutral, advisory-lock and checksum-verified migration
  runner with separate migration/application roles and fail-closed drift
  handling.
- Require a tested stock-PostgreSQL export/restore exit, zero-host availability,
  tenant isolation, and complete-system concurrency/load evidence before
  activation.
- Keep GitHub as an export/contribution transport and
  `prototype/full-platform-v0/migrations/` as fixture-only provenance.
- Forbid dual-authority writes, SQLite fallback mutation, and storage of
  requester provider credentials or private universe/branch content in the
  shared control plane.
- Treat the first canonical PostgreSQL production write as a separately
  recorded, host-approved one-way boundary after the baseline and exit drills
  pass.
- Keep all implementation, PLAN reconciliation, production inventory, and
  migration application blocked until the required opposite-provider review
  returns and the host accepts any resulting adaptation.

## Capabilities

### New Capabilities

- `postgres-control-plane`: Shared multi-user PostgreSQL authority, production
  baseline and migration integrity, role/tenant isolation, privacy and BYOC
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

Downstream moderation, paid-market, operator-request admission,
collaboration/catalog, authoring, and handoff persistence must wait for the
accepted baseline and migration substrate. Existing daemon-local SQLite,
SqliteSaver, knowledge/memory stores, OKF bundles, and artifact stores are not
migrated or reclassified by this proposal.
