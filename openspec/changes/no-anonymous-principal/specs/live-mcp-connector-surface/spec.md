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

#### Scenario: hosted connector has a cached tool catalog but no bearer
- **WHEN** it calls any canonical tool without a valid bearer
- **THEN** no tool handler runs
- **AND** the MCP error result carries `_meta["mcp/www_authenticate"]` with the routed protected-resource URL, an OAuth error code and an error description

### Requirement: Canonical tools advertise OAuth-only security

Every canonical tool descriptor SHALL advertise `securitySchemes` containing
only OAuth2 with `openid`, `profile`, `email` and `offline_access`. It SHALL NOT
advertise `noauth`. The compatibility `_meta.securitySchemes` mirror SHALL carry
the identical value.

#### Scenario: hosted connector lists tools
- **WHEN** the authenticated connector lists the canonical tool catalog
- **THEN** every returned tool carries identical top-level and compatibility OAuth-only security schemes

#### Scenario: a browser opens the endpoint
- **WHEN** a browser GETs `/mcp` with `Accept: text/html`, or any client HEADs it
- **THEN** the response is the same 401 challenge, not the discovery page
- **AND** the discovery documents at `/mcp/.well-known/*` stay public, so a client can still find the authorization server

### Requirement: Release reads use the named canary principal

`GET /mcp/pulse` SHALL require a valid user bearer or the canary bearer and SHALL return exactly
`git_sha`, `image_tag`, `deployed_at` and `uptime_seconds` from the release
receipt, with empty strings when no receipt is present. It SHALL name no
universe, no user and no run. The deploy gate (`scripts/deployed_sha.py`) reads
it with the canary bearer. Public website clients SHALL NOT call it without a
signed-in user's bearer.

#### Scenario: the deploy gate reads production's sha
- **WHEN** `GET /mcp/pulse` is requested with the canary bearer
- **THEN** the response is HTTP 200 carrying the four release fields and nothing a user authored

#### Scenario: an unsigned browser requests pulse
- **WHEN** `GET /mcp/pulse` is requested without a bearer
- **THEN** the response is the OAuth 401 challenge and no release fields are returned

#### Scenario: a deeper path is not exempt
- **WHEN** `GET /mcp/pulse/extra` is requested with no bearer
- **THEN** the response is the 401 challenge

### Requirement: Probes are the canary service principal

The bearer `TINYASSETS_WIKI_CANARY_TOKEN` SHALL resolve to the service
principal `canary`, which holds no capabilities. Before dispatch, every item
of a single or batch JSON-RPC body under that bearer SHALL be one of:
`initialize`, `notifications/initialized`, `tools/list`, `tools/call
get_status` with no arguments, `tools/call read_graph` with exactly
`{"target": "status"}`, and the reserved wiki canary's exact `write_page` /
`read_page` shapes. Anything else, and any use of the bearer off `POST /mcp`,
except exact `GET /mcp/pulse`, SHALL be refused with HTTP 403 before dispatch. The bearer SHALL NOT be
downgraded to any other identity.

#### Scenario: the canary probes liveness
- **WHEN** the canary bearer accompanies `tools/call get_status` with no arguments
- **THEN** the call is dispatched as the `canary` principal

#### Scenario: a leaked canary bearer tries to read a universe
- **WHEN** the canary bearer accompanies `tools/call read_graph target=graph`
- **THEN** the response is HTTP 403 and no handler runs

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
