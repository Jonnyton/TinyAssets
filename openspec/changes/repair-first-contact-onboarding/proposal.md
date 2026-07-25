## Why

A newly connected chatbot can inspect a branch only after it somehow learns an opaque branch ID, and the canonical write router can patch that branch but cannot create the user's first complete branch. The registered onboarding prompts and several live wiki guides compound the gap by teaching hidden legacy tools that are being retired, so the rendered first-contact path is not honestly usable through the exact seven-handle surface.

## What Changes

- Keep the advertised MCP surface at exactly seven handles and add a bounded, commons-only `read_graph(target="branches")` catalog target.
- Extend `write_graph(target="branch")` with a closed create-patch-publish discriminator: a complete `definition_json` creates one atomically validated branch, `branch_id` plus `changes_json` preserves transactional patching, and explicit `publish=true` deliberately mints a catalog-published version.
- Backfill the currently unspecced branch catalog and composite authoring contract, including verified-principal authorship/publication, V1 public-commons-only storage, atomic validation failure, versioned cryptographic keying, bounded results, and closed nested request/response shapes.
- Replace registered prompt instructions that name hidden legacy tools with compositions over the canonical handles.
- Produce an exact-path, lower-bound repository/live-wiki planning manifest; prove exhaustiveness before apply, and do not treat the existing race-prone SHA precondition as atomic compare-and-swap.
- Add no default branch, eighth tool, compatibility alias, provider/compute authority, or runtime implementation in this review lane.

## Capabilities

### New Capabilities

- `branch-authoring-and-catalog`: Visibility-safe branch catalog, exact branch inspection boundary, atomic complete-definition creation, and transactional patch discrimination.

### Modified Capabilities

- `live-mcp-connector-surface`: Add the canonical branch catalog/create routes and make all registered onboarding prompts truthful for the exact seven-handle surface.

## Impact

- Future runtime integration will touch the canonical MCP router and its packaging mirror, the existing branch list/build adapters, focused first-contact tests, and public MCP acceptance probes.
- The active `universe-creation`, `universe-visibility`, newborn-BYOC, and `control_station` prompt-truth owners remain read-only dependencies. Retire-legacy caller inventory v4 landed in #1772; this packet now records the missing `publish_version` and `approve_source_code` replacement-first decisions directly in retire-legacy tasks 2.3a and 4.0 plus the pending STATUS row. Any future retirement owner must satisfy them before removing `extensions`. No current `broad-test` owner/lane exists.
- This lane changes only OpenSpec artifacts, the evidence manifest, and coordination metadata. Claude Opus 5 opposite-provider review gates a draft spec PR and all runtime work.
