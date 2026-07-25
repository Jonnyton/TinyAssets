## Why

A newly connected chatbot can inspect a branch only after it somehow learns an opaque branch ID, and the canonical write router can patch that branch but cannot create the user's first complete branch. The registered onboarding prompts and several live wiki guides compound the gap by teaching hidden legacy tools that are being retired, so the rendered first-contact path is not honestly usable through the exact seven-handle surface.

## What Changes

- Keep the advertised MCP surface at exactly seven handles and add a bounded, commons-only `read_graph(target="branches")` catalog target.
- Extend `write_graph(target="branch")` with a closed create-patch-publish discriminator: a complete `definition_json` creates one atomically validated branch, `branch_id` plus `changes_json` preserves transactional patching, and explicit `publish=true` deliberately mints a catalog-published version.
- Backfill the currently unspecced branch catalog and composite authoring contract, including Postgres-canonical hosted authority, downstream-only SQLite execution projection, verified-principal authorship/publication, V1 public-commons-only storage, atomic validation failure, versioned cryptographic keying, bounded results, and closed nested request/response shapes.
- Replace registered prompt instructions that name hidden legacy tools with compositions over the canonical handles.
- Produce an exact-path, lower-bound repository/live-wiki planning manifest; prove exhaustiveness before apply, and do not treat the existing race-prone SHA precondition as atomic compare-and-swap.
- Add no default branch, eighth tool, compatibility alias, provider/compute authority, or runtime implementation in this review lane.

## Capabilities

### New Capabilities

- `branch-authoring-and-catalog`: Visibility-safe branch catalog, exact branch inspection boundary, atomic complete-definition creation, and transactional patch discrimination.

### Modified Capabilities

- `live-mcp-connector-surface`: Add the canonical branch catalog/create routes and make all registered onboarding prompts truthful for the exact seven-handle surface.

## Impact

- Future runtime integration will touch the canonical MCP router and packaging mirror, an approved production Postgres migration/adapter, existing branch adapters as one-way import/downstream execution projections, focused Postgres/first-contact tests, and public MCP acceptance probes.
- The active `universe-creation`, `universe-visibility`, shared-Goals, `control_station`, Postgres-baseline, and `scope=commons` owners remain read-only dependencies and require landed SHAs or explicit file releases. Newborn BYOC behavior is a landed read-only base from #1759, but executable run guidance remains blocked on the full requester-authority/isolation gates. Retire-legacy caller inventory v4 landed in #1772; this packet records replacement-first gates for `publish_version`, source approval, and remix/lineage as retire tasks 2.3a/2.3b/4.0. No current `broad-test` owner/lane exists.
- This lane changes only OpenSpec artifacts, the evidence manifest, and coordination metadata. Claude Opus 5 opposite-provider review gates a draft spec PR and all runtime work.
