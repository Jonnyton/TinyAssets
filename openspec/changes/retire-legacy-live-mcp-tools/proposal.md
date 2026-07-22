## Why

The live connector still registers six hidden legacy fat tools even though the migration contract bounded that compatibility window to one release. Once external manifests are reconciled and telemetry plus host migration evidence show that callers use the canonical surface, those hidden entry points must leave the live server so the registered contract, public canary, and executable proof all agree on exactly seven handles.

## What Changes

- **BREAKING:** after explicit migration gates pass, unregister exactly `universe`, `community_change_context`, `extensions`, `goals`, `gates`, and `wiki` from the live `tinyassets/universe_server.py` MCP server and remove `_DeprecatedToolVisibility`.
- Preserve non-MCP Python wrappers or migrate every import caller explicitly; unregistering an MCP tool does not silently delete internal behavior.
- Require the public `--assert-handles` canary to accept exactly the seven canonical live handles, including `get_status` as required rather than optional.
- Add a genuine live-server `run_graph` dispatch/round-trip proof rather than treating presence in `tools/list` as execution evidence.
- Keep `tinyassets/directory_server.py` as the intentional narrower reviewed-directory surface.
- Keep the legacy stdio-server fence in PR #1561 and the directory `run_graph` authorization work in PR #1553 as separate concerns.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `live-mcp-connector-surface`: end the hidden-fat-tool migration window, make the public canary enforce exactly seven live handles, and require executable proof that live `run_graph` reaches the canonical run path while preserving the directory surface.

## Impact

- Future implementation: `tinyassets/universe_server.py` and its packaged runtime mirror; `scripts/mcp_public_canary.py`; focused live-surface and canary tests.
- External consumers: removal is gated on the `reconcile-external-connector-manifests` change plus telemetry and host migration proof.
- Coordination: implementation must reconcile active PR ownership before touching shared runtime or test files; this proposal changes no runtime behavior.
