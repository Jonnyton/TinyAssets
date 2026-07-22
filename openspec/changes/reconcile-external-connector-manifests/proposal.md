## Why

TinyAssets publishes three intentionally different connector products, but one
checked-in artifact still describes a fourth, obsolete shape: the MCPB manifest
declares only the hidden legacy `universe` and `extensions` tools even though
the bundled `tinyassets.universe_server` advertises seven canonical handles.
This makes a package capable of passing schema validation while its declared
tool catalog disagrees with the runtime users install.

## What Changes

- Make the MCPB manifest declare exactly the seven handles advertised by its
  bundled `universe_server` runtime:
  `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`,
  `converse`, and `get_status`.
- Add an executable parity check that stages/imports the bundle runtime,
  enumerates its middleware-applied advertised tools, and compares that set
  with the staged MCPB manifest. Packaging validation SHALL fail on drift.
- Preserve the MCP Registry remote and ChatGPT submission packet as the
  intentional five-handle directory product backed by `directory_server`;
  reconciliation SHALL NOT expand those directory-review surfaces to seven.
- Fold or supersede PR #1522 rather than treating its naming-only rename as the
  content refresh: after the runtime/manifest truth is established, rename the
  recovered Polsia handoff to TinyAssets and replace its stale pre-cutover,
  pre-WorkOS integration guidance with the current live-seven versus
  directory-five split.
- Keep legacy-tool retirement out of this change. It belongs to the dependent
  `retire-legacy-live-mcp-tools` change after manifest migration and external
  consumer evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `live-mcp-connector-surface`: Require each distributed connector artifact to
  declare the tool catalog of the runtime/surface it actually delivers, while
  preserving the deliberate live/bundle-seven and directory-five split.

## Impact

- Packaging: `packaging/mcpb/manifest.json`, `packaging/mcpb/build_bundle.py`,
  and packaging parity tests.
- Directory metadata: `packaging/registry/server.json`, its deterministic
  generator, and `chatgpt-app-submission.json` remain directory-five and gain
  regression coverage only where existing coverage is insufficient.
- Documentation: the recovered Polsia handoff is renamed and substantively
  refreshed in the implementation lane; PR #1522 overlaps that file and the
  obsolete change being archived, so it must be folded, rebased to the new
  scope, or closed before implementation lands.
- Dependency: `retire-legacy-live-mcp-tools` must wait for this reconciliation
  and its external-consumer migration evidence.
