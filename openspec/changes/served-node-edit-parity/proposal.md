## Why

The app agent can create a node but cannot revise ordinary settings such as its output names or timeout. Rebuilding the workflow to repair its configuration is a platform limitation, not user work that an operator should do.

## What Changes

- Extend existing served `write_graph` branch `patch` / `update_node` to ordinary node configuration through the canonical staged updater.
- Assess metadata, model preferences, input/output keys, timeout, retry policy and enabled state together; keep grants, ownership, approval, publication and sub-branch invocation outside this edit contract.
- Keep malformed batches atomic, admitted run snapshots immutable and runtime authorization independent of declarations.
- Publish accurate discoverable guidance and prove same-branch editing through the ordinary app agent.

## Capabilities

### New Capabilities

None; no new tool or action.

### Modified Capabilities

- `live-mcp-connector-surface`: owner-scoped served editing of ordinary node settings.

## Impact

Served edit adapter and descriptions, canonical validation only where needed for safe malformed-input refusal, focused regression tests and generated plugin mirror. No storage migration, authority expansion, provider dependency, private-workflow edits or host execution. Owner: Codex; branch: `codex/node-edit-parity`; one implementation PR, assigned when opened. Previously deployed workflow-control and effects-edit slices stay closed; this change repairs the separately recorded editable-field gap.
