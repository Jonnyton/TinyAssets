## ADDED Requirements

### Requirement: Live connector exposes exactly the five canonical handles
The live MCP server `workflow/universe_server.py` (served at `https://tinyassets.io/mcp`) SHALL register exactly five user-facing tools — `read.graph`, `write.graph`, `run.graph`, `read.page`, `write.page` — as the canonical user surface. `get_status` MAY remain as a read affordance and registered MCP prompts MAY remain, but no other user-facing data/compute tool SHALL be advertised as canonical.

#### Scenario: tools/list advertises the five handles
- **WHEN** an MCP client calls `tools/list` against the live `/mcp` endpoint
- **THEN** the canonical user-facing tool set is exactly `{read.graph, write.graph, run.graph, read.page, write.page}` (plus `get_status` and any prompts)
- **AND** no enumerated legacy action (e.g. `build_branch`, `submit_request`) is exposed as a top-level tool

### Requirement: Handles dispatch to existing primitive handlers via shape, with no behavior change
Each handle SHALL act as a thin router that maps a `shape=` parameter and payload onto the EXISTING `workflow/api/*` action handlers. `run.graph` SHALL be the only verb that produces a Run. The collapse SHALL NOT alter primitive behavior, run semantics, scoping, or storage; it changes only the surface shape.

#### Scenario: write.graph creates a node via the existing handler
- **WHEN** a client calls `write.graph` with `shape=node` and a node payload
- **THEN** the request is routed to the same handler that previously served `extensions action=add_node`
- **AND** the resulting graph state is identical to the pre-collapse behavior

#### Scenario: run.graph is the sole run-producing verb
- **WHEN** a client wants to execute a branch
- **THEN** it calls `run.graph` (mapping to the existing `run_branch` handler)
- **AND** no other handle produces a Run

#### Scenario: read.page / write.page cover the brain surface
- **WHEN** a client reads or writes durable wiki/brain knowledge
- **THEN** it uses `read.page` / `write.page` routed to the existing `wiki` read/write handlers

### Requirement: Legacy fat surface is deprecated during a bounded migration window
For one release the legacy tools (`universe`, `extensions`, `goals`, `gates`, `wiki` as enumerated-action tools) MAY remain registered but SHALL be marked deprecated, and deprecated-action invocations SHALL be logged so remaining external consumers can be identified. A subsequent change SHALL remove the legacy tools after the window.

#### Scenario: deprecated action still works but is flagged
- **WHEN** a client calls a legacy enumerated action during the migration window
- **THEN** the call still succeeds (back-compat)
- **AND** a deprecation signal is logged identifying the caller/action

### Requirement: Public canary asserts the live handle set
`scripts/mcp_public_canary.py` SHALL assert that the deployed public `/mcp` advertises exactly the five canonical handles, and this assertion SHALL run as part of the post-change public canary mandated after any DNS/tunnel/Worker/connector change.

#### Scenario: canary fails on drift
- **WHEN** the live `/mcp` advertises a tool set that does not match the five canonical handles
- **THEN** the public canary fails
- **AND** the deploy is treated as not-green until corrected
