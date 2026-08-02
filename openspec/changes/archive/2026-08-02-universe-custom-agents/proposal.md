## Why

TinyAssets users need to assemble agents that range from common presets to
OpenClaw-like personal operators, Hermes-like assistants, coding agents, and
component-level remixes without leaving the platform when their needs become
advanced. The durable foundation is a portable public definition plus a
private universe binding, so collaboration and remix stay open while
credentials, authority, conversations, and runtime state remain private.

## What Changes

- Add versioned, public agent definitions whose independently replaceable
  components can reference existing branches, evaluators, skills, adapters,
  memory policies, and provider policies.
- Add component-level, multi-parent remix lineage so a definition can combine
  pieces from several public agents without losing attribution.
- Add private universe bindings that connect a public definition to a
  universe-specific role, goals, authority, resources, provider preferences,
  channel addresses, and runtime state without copying secrets into the public
  artifact.
- Add create, remix, inspect, list, bind, update, export, and import operations
  as targets under the existing `read_graph` and `write_graph` handles.
- Keep arbitrary managed-cloud code execution dependent on the Engine OS
  sandbox and keep live Slack/other outbound effects dependent on the outbound
  boundary layer; this change stores portable component and channel intent but
  does not bypass either security boundary.
- Preserve the daemon as the runtime instance of an agent binding rather than
  adding another top-level execution primitive.

## Capabilities

### New Capabilities

- `universe-custom-agents`: Public composable agent definitions, private
  universe bindings, component provenance, portable interchange, and their
  authorization and validation rules.

### Modified Capabilities

- `live-mcp-connector-surface`: Extend the canonical graph handles with
  discoverable custom-agent read and write targets without adding a new MCP
  handle.
- `evaluation-outcomes-and-attribution`: Extend remix provenance from a single
  parent edge to bounded component-level, multi-parent attribution.

## Impact

The change affects the graph-facing MCP router, a new agent domain/storage API,
SQLite schema initialization, attribution records, and focused tests. It
reuses existing universe ownership, provider routing, credential/resource
binding, branch definitions, and daemon runtime concepts. No credentials are
stored in agent definitions or bindings, no new public MCP handle is added,
and no Slack effect or arbitrary managed-cloud user code is executed by this
slice.
