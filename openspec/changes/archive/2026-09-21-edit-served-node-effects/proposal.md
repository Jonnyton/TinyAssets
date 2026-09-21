## Why

The live app agent can create effect-bearing workflows but cannot add or change
the same declarations in an existing workflow. It has to rebuild the branch.
The served adapter still cites a removed graph-size ceiling and obsolete
execution-approval semantics; the actual boundaries are ownership, sandboxing,
connection authority and runtime consent.

## What Changes

- Allow served owners to add effect-bearing nodes and update or clear existing
  node effects/workspace declarations through the existing patch operation.
- Reuse creation validation; retain runtime authority, sandbox and consent gates.
- Preserve source-approval provenance semantics and atomic malformed-batch refusal.
- Explain these editable declarations through the existing tool description.

## Capabilities

### New Capabilities

None. No new tool, operation, sink, grant or runtime path.

### Modified Capabilities

- `live-mcp-connector-surface`: served creation/edit parity for existing effect
  and workspace declarations, without credential or execution-authority grants.

## Impact

Served branch sanitizer, its guidance, and focused real-store regressions.
Canonical branch updating is reused; change it only if evidence exposes a
necessary validation inconsistency. No storage migration or private workflow edit.
Owner: root Codex; Claude subscription peer review/build; branch
`codex/served-effect-edit-parity`; one PR. Live acceptance belongs to the app agent.
