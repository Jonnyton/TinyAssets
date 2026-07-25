## Why

A newly connected chatbot can inspect a branch only after it somehow learns an opaque branch ID, and the canonical write router can patch that branch but cannot create the user's first complete branch. The registered onboarding prompts and several live wiki guides compound the gap by teaching hidden legacy tools that are being retired, so the rendered first-contact path is not honestly usable through the exact seven-handle surface.

## What Changes

- Keep the advertised MCP surface at exactly seven handles and add a bounded, visibility-filtered `read_graph(target="branches")` catalog target.
- Extend `write_graph(target="branch")` with a closed create-or-patch discriminator: a complete `definition_json` creates one atomically validated branch, while `branch_id` plus `changes_json` preserves transactional patching.
- Backfill the currently unspecced branch catalog and composite authoring contract, including caller-bound authorship, explicit visibility, non-enumeration of private branches, atomic validation failure, bounded results, and closed response shapes.
- Replace registered prompt instructions that name hidden legacy tools with compositions over the canonical handles.
- Produce an exact repository/live-wiki correction manifest; any later live wiki mutation must use the existing dry-run and compare-and-swap path.
- Add no default branch, eighth tool, compatibility alias, provider/compute authority, or runtime implementation in this review lane.

## Capabilities

### New Capabilities

- `branch-authoring-and-catalog`: Visibility-safe branch catalog, exact branch inspection boundary, atomic complete-definition creation, and transactional patch discrimination.

### Modified Capabilities

- `live-mcp-connector-surface`: Add the canonical branch catalog/create routes and make all registered onboarding prompts truthful for the exact seven-handle surface.

## Impact

- Future runtime integration will touch the canonical MCP router and its packaging mirror, the existing branch list/build adapters, focused first-contact tests, and public MCP acceptance probes.
- The active `universe-creation`, `universe-visibility`, broad-test, and legacy-tool-retirement owners remain read-only dependencies. Their work must land or explicitly adapt this contract before runtime implementation is claimed.
- This lane changes only OpenSpec artifacts, the evidence manifest, and coordination metadata. Claude Opus 5 opposite-provider review gates a draft spec PR and all runtime work.
