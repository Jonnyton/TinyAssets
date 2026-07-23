## MODIFIED Requirements

### Requirement: Canonical Advertised Handle Set

The live MCP server SHALL register and advertise exactly seven handles: `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, and `get_status`. Each handle SHALL remain a thin shape/target router that delegates to an existing `tinyassets.api.*` handler without changing that handler's behavior. The public drift-guard canary (`scripts/mcp_public_canary.py --assert-handles`) SHALL require exact equality with all seven names; `get_status` SHALL NOT be optional.

#### Scenario: Live surface advertises exactly the seven handles

- **WHEN** a client reads `tools/list` from the running server
- **THEN** the advertised set equals `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}` and nothing else

#### Scenario: Middleware-bypassed registry contains exactly the seven handles

- **WHEN** a contract test inspects every tool registered on the live server without applying listing middleware
- **THEN** the registered set equals the same exact seven-handle set
- **AND** no hidden or deprecated tool registration exists

#### Scenario: A canonical handle routes to its existing API handler

- **WHEN** a client calls `write_graph(target="goal", ...)` and later `read_graph(target="goals", ...)`
- **THEN** the write routes to the same goals handler the read queries, so the goal proposed by the write is returned by the read

#### Scenario: run_graph completes a live MCP-to-storage round trip

- **WHEN** an authenticated in-process MCP client calls `run_graph` for a deterministic no-provider branch in isolated storage
- **THEN** the registered live tool dispatches through the current `run_branch` handler and returns a durable run identifier
- **AND** a subsequent MCP call to `read_graph(target="run", run_id=<returned identifier>)` returns that same persisted run
- **AND** the proof does not replace MCP registration, run creation, or run read-back with a direct wrapper call, AST check, schema check, or handler stub

#### Scenario: An unknown router target is reported, not silently accepted

- **WHEN** a client calls `read_graph(target="bogus")`
- **THEN** the result is a JSON error with `error="unknown_target"`, `handle="read_graph"`, and the list of allowed targets

### Requirement: Registered tools publish exact discoverability and behavior metadata

The system SHALL attach the following title, tag set, and four MCP behavior
hints to every registered tool after retirement. In the hint columns, `T`
means true and `F` means false, ordered as read-only, destructive, idempotent,
and open-world:

| Tool | Title | Tags | R | D | I | O |
|---|---|---|---:|---:|---:|---:|
| `read_graph` | `Read Graph` | `graph`, `read`, `tinyassets` | T | F | T | F |
| `write_graph` | `Write Graph` | `graph`, `tinyassets`, `write` | F | F | F | F |
| `run_graph` | `Run Graph` | `graph`, `run`, `tinyassets` | F | F | F | F |
| `read_page` | `Read Page` | `page`, `read`, `tinyassets`, `wiki` | T | F | T | F |
| `write_page` | `Write Page` | `page`, `tinyassets`, `wiki`, `write` | F | F | F | T |
| `converse` | `Talk With Your Universe` | `relay`, `tinyassets`, `universe` | F | F | F | F |
| `get_status` | `Daemon Status + Routing Evidence` | `confidential-tier`, `privacy`, `routing`, `status`, `tinyassets`, `verification` | T | F | T | F |

These hints SHALL remain descriptive MCP metadata rather than authorization
enforcement; the tool implementations and permission middleware retain
authority over whether an invocation can mutate or access state. No retired
tool SHALL retain a registry metadata row after its registration is removed.

#### Scenario: Retired registrations leave no metadata residue

- **WHEN** the registry is listed after the six legacy tools are retired
- **THEN** its metadata table contains exactly the seven rows above
- **AND** no metadata row remains for `universe`, `community_change_context`, `extensions`, `goals`, `gates`, or `wiki`

#### Scenario: Behavior hints do not grant authority

- **WHEN** a remaining tool's metadata marks it non-destructive or open-world
- **THEN** that metadata alone does not bypass the tool's write gate, authentication, ownership, or action-specific validation

### Requirement: Public Canary And Directory Review Surface

The platform SHALL provide a stdlib-only public canary (`scripts/mcp_public_canary.py`) whose `--assert-handles` mode performs a full handshake, reads `tools/list`, and fails (exit 4) unless the live surface advertises exactly `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}`. The platform SHALL continue to expose a separate narrower directory surface (`tinyassets/directory_server.py`, served at `/mcp-directory`) intended for reviewed host directories such as Claude's Connectors Directory and ChatGPT Apps; it advertises no catch-all `action` inputs and returns a redacted `get_status` that strips operator diagnostics and injects a `directory_privacy_note`.

#### Scenario: Canary fails on an extra handle

- **WHEN** the live `tools/list` advertises a handle outside the exact seven-name set, including a reintroduced legacy fat tool
- **THEN** `mcp_public_canary.py --assert-handles` exits with code 4 and reports the extra handle set

#### Scenario: Canary fails when get_status is missing

- **WHEN** the live `tools/list` advertises the other six canonical handles but omits `get_status`
- **THEN** `mcp_public_canary.py --assert-handles` exits with code 4 and reports `get_status` as missing

#### Scenario: Directory status redacts operator diagnostics

- **WHEN** a directory client reads status through the `/mcp-directory` surface
- **THEN** raw activity logs and internal diagnostics are stripped and the payload carries a `directory_privacy_note`, whereas the live `/mcp` `read_graph target=status` returns the full unredacted status

## ADDED Requirements

### Requirement: Legacy Fat Tools Are Absent From The Live MCP Registry

After the manifest, telemetry, rendered-client, and host-approval migration gates pass, the live MCP server SHALL NOT register `universe`, `community_change_context`, `extensions`, `goals`, `gates`, or `wiki`, and SHALL NOT retain `_DeprecatedToolVisibility` or any equivalent hide-but-dispatch compatibility layer. Removing their MCP registrations SHALL NOT silently remove primitive behavior still reached by canonical handles or repository Python callers.

#### Scenario: Direct legacy tools/call is unknown

- **WHEN** a client sends `tools/call` for any of the six retired names after deployment
- **THEN** the MCP server reports that the tool is unknown rather than dispatching it through a hidden path

#### Scenario: Existing primitive behavior remains reachable canonically

- **WHEN** a supported operation formerly reachable through a fat tool has a documented canonical-handle route
- **THEN** that operation remains reachable through the canonical route with unchanged handler semantics and authorization

#### Scenario: Python callers are preserved or explicitly migrated

- **WHEN** implementation removes the MCP registrations
- **THEN** every repository import or direct Python caller of the underlying wrapper functions is inventoried
- **AND** each wrapper is either preserved as non-MCP Python behavior with focused coverage or all of its callers are explicitly migrated and tested before deletion
- **AND** no compatibility alias is added

#### Scenario: Removal waits for accepted migration proof

- **WHEN** manifest reconciliation, the predeclared telemetry window, rendered-client proof, or explicit host approval is absent
- **THEN** the six registrations remain unchanged and implementation is held rather than guessing that migration is complete

## REMOVED Requirements

### Requirement: Legacy Fat Tools Registered But Hidden

**Reason**: The one-release migration window ends after accepted manifest, telemetry, rendered-client, and host evidence. Keeping callable tools hidden forever contradicts the exact seven-handle registration contract and preserves an unauditable compatibility surface.

**Migration**: Supported external clients SHALL use the canonical seven-handle live surface. Repository Python callers SHALL either keep using preserved non-MCP wrappers or be explicitly migrated to owning APIs/canonical routes before a wrapper is deleted. The separate stdio and directory-server lanes are not migrated by this change.
