# live-mcp-connector-surface (delta)

## REMOVED Requirements

### Requirement: Read-Open, Write-Challenged Authentication Boundary

Removed. No handle is callable without a valid bearer (founder, 2026-09-02:
"anonymous should not be a possibility anywhere in the codebase"). Replaced by
*Every handle requires a named principal* below.

## ADDED Requirements

### Requirement: Every handle requires a named principal

`initialize`, `tools/list` and every `tools/call` on the live connector SHALL
require a valid bearer. A request without one SHALL answer HTTP 401 with a
`WWW-Authenticate: Bearer` challenge carrying the resource-metadata URL, so an
MCP client starts OAuth before it lists tools. `converse` SHALL require an
authenticated actor with write or admin on the target universe. `get_status`
and `read_graph target=status` remain pure reads for any authenticated caller
and never provision.

#### Scenario: unauthenticated initialize
- **WHEN** a client POSTs `initialize` with no bearer
- **THEN** the response is HTTP 401 with the `WWW-Authenticate` challenge and no session is created

#### Scenario: authenticated read
- **WHEN** an authenticated caller calls `read_graph target=status`
- **THEN** the read succeeds and no universe is created

## MODIFIED Requirements

### Requirement: Legacy Fat Tools Registered But Hidden

The six legacy fat tools (`universe`, `community_change_context`,
`extensions`, `goals`, `gates`, `wiki`) SHALL remain registered and
dispatchable for one migration release while being hidden from `tools/list`
by the `_DeprecatedToolVisibility` middleware. Every call to a hidden legacy
tool SHALL be logged as deprecated. Like every handle they require a valid
bearer; an unauthenticated call never reaches them.

#### Scenario: hidden legacy tool is still dispatchable
- **WHEN** an authenticated caller invokes a hidden legacy tool
- **THEN** it dispatches and the call is logged as deprecated

### Requirement: Custom agents route through canonical graph handles

Custom agents SHALL be read through `read_graph` (`agents`, `agent`,
`agent_bindings`, `agent_binding`) and written through `write_graph`; the
public agent commons SHALL be browsable by any authenticated caller, and
private bindings by their universe's ACL only.

#### Scenario: signed-in caller browses the public agent commons
- **WHEN** an authenticated caller uses `read_graph` with target `agents`
- **THEN** public agent definitions are listed
