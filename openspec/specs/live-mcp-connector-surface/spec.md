# Live MCP Connector Surface

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

The public MCP entry point: the canonical handle set served at https://tinyassets.io/mcp as thin routers over `tinyassets.api.*` handlers, MCP prompts that teach connecting chatbots, legacy fat-tool deprecation, the Cloudflare Worker front door, and the public canaries that guard the surface.
## Requirements
### Requirement: Remote Streamable-HTTP MCP Endpoint

The platform SHALL expose a single remote MCP server over Streamable-HTTP transport (`tinyassets/universe_server.py`, built on FastMCP) that any MCP-compatible chatbot can connect to by URL with no local installation. The server SHALL register exactly the following prompt catalog so a connecting chatbot receives behavioral instructions on how to act as the user's control interface:

| Prompt name | Title | Tags |
|---|---|---|
| `control_station` | `Control Station Guide` | `control`, `daemon`, `multiplayer`, `operations` |
| `meet_universe` | `Meet Your Universe` | `first-contact`, `onboarding`, `persona`, `tinyassets` |
| `extension_guide` | `Extension Authoring Guide` | `extensions`, `nodes`, `plugins`, `tinyassets` |
| `branch_design_guide` | `Branch Design Guide` | `branches`, `customization`, `extensions`, `graph` |

Each prompt SHALL return its registered behavioral guide and SHALL expose its function docstring as discoverability text.

#### Scenario: Chatbot completes an MCP handshake and lists tools

- **WHEN** an MCP client sends `initialize`, then `notifications/initialized`, then `tools/list` to the server
- **THEN** the server responds with a valid MCP `serverInfo` + `protocolVersion` and returns a non-empty advertised tool list
- **AND** the response is delivered as either JSON or an SSE `event: message` frame, both of which are valid Streamable-HTTP responses

#### Scenario: Prompt listing returns the exact catalog
- **WHEN** an MCP client lists prompts on the live server
- **THEN** the response contains the four names, titles, and tag sets above with no additional registered prompt

#### Scenario: Prompt invocation returns the owned guide
- **WHEN** an MCP client invokes any catalogued prompt
- **THEN** the server returns that prompt's registered control, first-contact, extension-authoring, or branch-design guide

### Requirement: Canonical Advertised Handle Set

The advertised `tools/list` surface SHALL be exactly seven handles: `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, and `get_status`. Each is a thin shape/target router that delegates to an existing `tinyassets.api.*` handler without changing that handler's behavior. The public drift-guard canary (`scripts/mcp_public_canary.py --assert-handles`) SHALL require that exact set; a missing `get_status` or any extra advertised handle is drift.

#### Scenario: Live surface advertises exactly the seven handles

- **WHEN** a client reads `tools/list` from the running server with middleware applied
- **THEN** the advertised set equals `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}` and nothing else
- **AND** `converse` is present as a user-facing handle (verified by `tests/test_universe_server_five_handles.py`)

#### Scenario: A canonical handle routes to its existing API handler

- **WHEN** a client calls `write_graph(target="goal", ...)` and later `read_graph(target="goals", ...)`
- **THEN** the write routes to the same goals handler the read queries, so the goal proposed by the write is returned by the read

#### Scenario: An unknown router target is reported, not silently accepted

- **WHEN** a client calls `read_graph(target="bogus")`
- **THEN** the result is a JSON error with `error="unknown_target"`, `handle="read_graph"`, and the list of allowed targets

### Requirement: Legacy Fat Tools Registered But Hidden

The server SHALL keep the six legacy fat tools (`universe`, `community_change_context`,
`extensions`, `goals`, `gates`, `wiki`) registered and
dispatchable for one migration release while being hidden from `tools/list`
by the `_DeprecatedToolVisibility` middleware. Every call to a hidden legacy
tool SHALL be logged as deprecated. Like every handle they require a valid
bearer: the transport SHALL challenge an unauthenticated call before it can
reach them.

#### Scenario: Legacy tool is absent from the advertised list but still callable

- **WHEN** an authenticated client reads `tools/list` and then calls the legacy `universe` tool by name
- **THEN** `universe` does not appear in the advertised list, the call still dispatches and returns a result, and a `deprecated-tool-call name=universe` warning is logged

#### Scenario: Unauthenticated caller is refused before a legacy tool

- **WHEN** an unauthenticated client calls a deprecated fat tool
- **THEN** the transport returns an authentication challenge and the legacy tool is not dispatched

### Requirement: Connector-Safe Handle Names

Every advertised handle name SHALL match `^[a-zA-Z0-9_-]{1,64}$` and MUST NOT contain a dot. The canonical handles therefore use underscore names (`read_graph`, `write_graph`, and so on), because the Anthropic connector API rejects any tool name containing a dot and a single rejected name rejects the whole connector. This constraint is documented and honored at the registration boundary in `tinyassets/universe_server.py`.

#### Scenario: Advertised handle names are connector-safe

- **WHEN** the advertised handle set is inspected
- **THEN** every handle name matches `^[a-zA-Z0-9_-]{1,64}$` with no dots

### Requirement: Faithful Structured And Text Result Envelope

Every handle result SHALL be wrapped so the MCP response carries both a `structuredContent` typed object and a text `content` block that reflects the real payload. The text block SHALL be capped at 6000 characters. When the payload fits, the text block SHALL carry the full payload as JSON; when it exceeds the cap, the text block SHALL carry as much real, readable data as fits plus an explicit truncation pointer to `structuredContent`, and SHALL NOT be replaced by a lossy placeholder stub.

#### Scenario: Under-budget result carries the full payload in text

- **WHEN** a handle returns a payload whose JSON is at or under 6000 characters
- **THEN** the text `content` block contains the full payload as JSON and `structuredContent` contains the same typed object

#### Scenario: Over-budget result stays faithful and bounded

- **WHEN** a handle returns a payload whose JSON exceeds 6000 characters
- **THEN** the text `content` block contains real payload data truncated to the cap with an explicit `[truncated: ... full payload in structuredContent]` pointer, never a placeholder that reads as empty

### Requirement: Cloudflare Worker Public Front Door

`https://tinyassets.io/mcp` SHALL be the only public user-facing MCP URL. A
Cloudflare Worker on the `tinyassets.io/mcp*` route SHALL proxy only canonical
`/mcp` traffic to the Access-gated tunnel origin `mcp.tinyassets.io`, injecting
the CF Access service-token headers (`CF-Access-Client-Id` /
`CF-Access-Client-Secret`) from Worker environment secrets. The Worker SHALL
stream SSE bodies straight through without buffering, SHALL preserve request
headers and method, SHALL preserve non-hop-by-hop upstream response headers
except that it MUST strip every `Set-Cookie` response header, and SHALL map any
tunnel `5xx` (or an unreachable tunnel) to an explicit `502` JSON body rather
than falling through to the GoDaddy origin. It SHALL NOT route, redirect, proxy,
alias, translate, or return a compatibility response for `/mcp-directory*`;
those paths receive the ordinary edge 404. `mcp.tinyassets.io` is an internal
Access-gated origin and MUST NOT be presented as user-facing.

#### Scenario: Worker proxies canonical MCP only

- **WHEN** a client request arrives at `tinyassets.io/mcp`
- **THEN** the Worker rewrites `Host` to `mcp.tinyassets.io`, adds the CF Access service-token headers from env secrets, and forwards method, body stream, and non-hop-by-hop headers
- **AND** the broad Worker binding terminates `/mcp-directory*` as an ordinary edge 404 without proxy, redirect, alias, or translation

#### Scenario: Upstream response cookies never cross the public boundary

- **WHEN** the tunnel origin returns one or more `Set-Cookie` headers, including an Access `CF_Authorization` cookie or an application cookie
- **THEN** the public Worker response contains no `Set-Cookie` header
- **AND** allowed non-cookie response headers, status, status text, and body stream are preserved

#### Scenario: SSE bodies stream without buffering

- **WHEN** the tunnel origin returns a `text/event-stream` response
- **THEN** the Worker returns the upstream `ReadableStream` body directly without calling `.text()`/`.json()`/`.arrayBuffer()`

#### Scenario: Tunnel failure surfaces as an explicit 502

- **WHEN** the tunnel origin returns a `5xx` status or is unreachable
- **THEN** the Worker responds `502` with a `bad_gateway` JSON body, never a GoDaddy `404` fallthrough

### Requirement: Public Canary And Canonical Review Surface

The platform SHALL expose `https://tinyassets.io/mcp` as its sole remote
user-facing MCP endpoint. Its advertised set SHALL be exactly
`{read_graph, write_graph, run_graph, read_page, write_page, converse,
get_status}`. Registry and hosted-chatbot review metadata SHALL bind to this
endpoint rather than an alternate directory product.

The platform SHALL preserve the stdlib-only public canary
(`scripts/mcp_public_canary.py`) whose `--assert-handles` mode performs a full
handshake, reads `tools/list`, and fails (exit 4) unless the live surface
advertises the exact seven handles, plus the lightweight
`scripts/uptime_canary.py`.

`/mcp-directory` and every versioned `/mcp-directory*` catalog route SHALL be
unmounted. The platform SHALL NOT redirect, proxy, alias, silently translate,
return 410, or serve a compatibility response at the retired path.

#### Scenario: Canary fails on advertised-handle drift

- **WHEN** the live `tools/list` is missing a required canonical handle or advertises a handle outside the allowed set (for example a leaked legacy fat tool)
- **THEN** `mcp_public_canary.py --assert-handles` exits with code 4 and reports the missing/extra handle sets

#### Scenario: Retired directory route is absent

- **WHEN** a client calls `/mcp-directory` or a versioned descendant after the cutover
- **THEN** no MCP transport or catalog is mounted at that path
- **AND** the response is the ordinary absent-route 404
- **AND** it has no `Location` redirect, proxy, alias, translation to `/mcp`, 410 status, or compatibility body

### Requirement: Published registry metadata follows canonical MCP

The checked-in MCP Registry manifest SHALL advertise
`https://tinyassets.io/mcp`. Repository tests plus packaging CI SHALL fail when
`packaging/registry/server.json` differs from deterministic canonical runtime
metadata. The generator SHALL run directly from a clean repository checkout.

#### Scenario: Canonical registry metadata change makes stale metadata fail

- **WHEN** the canonical Registry endpoint or manifest version changes without regenerating `packaging/registry/server.json`
- **THEN** the focused artifact-equality test fails
- **AND** the packaging workflow's generator `--check` step fails

#### Scenario: Clean checkout generation uses canonical metadata

- **WHEN** a contributor runs `python packaging/registry/generate_server_json.py --check` from repository root
- **THEN** the command compares the checked-in manifest with deterministic canonical endpoint metadata without importing a retired directory catalog

#### Scenario: Published registry remote is canonical and reachable

- **WHEN** the generated manifest is proposed for external-directory publication
- **THEN** its remote URL is exactly `https://tinyassets.io/mcp`
- **AND** a read-only Streamable-HTTP MCP handshake lists the canonical exact-seven handles

### Requirement: Registered tools publish exact discoverability and behavior metadata
The system SHALL attach the following title, tag set, and four MCP behavior hints to every currently registered tool. In the hint columns, `T` means true and `F` means false, ordered as read-only, destructive, idempotent, and open-world:

| Tool | Title | Tags | R | D | I | O |
|---|---|---|---:|---:|---:|---:|
| `read_graph` | `Read Graph` | `graph`, `read`, `tinyassets` | T | F | T | F |
| `write_graph` | `Write Graph` | `graph`, `tinyassets`, `write` | F | F | F | F |
| `run_graph` | `Run Graph` | `graph`, `run`, `tinyassets` | F | F | F | F |
| `read_page` | `Read Page` | `page`, `read`, `tinyassets`, `wiki` | T | F | T | F |
| `write_page` | `Write Page` | `page`, `tinyassets`, `wiki`, `write` | F | F | F | T |
| `converse` | `Talk With Your Universe` | `relay`, `tinyassets`, `universe` | F | F | F | F |
| `universe` | `Universe Operations` | `agent-workflow`, `ai-builder`, `collaboration`, `custom-ai`, `daemon`, `general-purpose`, `tinyassets`, `universe`, `universe-builder`, `workflow-builder` | F | F | F | T |
| `community_change_context` | `Community Change Context` | `change-loop`, `community`, `github`, `plan`, `pull-request`, `review`, `tinyassets` | T | F | T | T |
| `extensions` | `Graph Extensions` | `customization`, `extensions`, `nodes`, `plugins` | F | F | F | T |
| `goals` | `Goals` | `community`, `discovery`, `goals`, `intent` | F | F | F | T |
| `gates` | `Outcome Gates` | `community`, `gates`, `impact`, `leaderboard`, `outcomes` | F | F | F | T |
| `wiki` | `Wiki Knowledge Base` | `drafts`, `knowledge`, `pages`, `research`, `wiki` | F | T | F | T |
| `get_status` | `Daemon Status + Routing Evidence` | `confidential-tier`, `privacy`, `routing`, `status`, `tinyassets`, `verification` | T | F | T | F |

These hints SHALL remain descriptive MCP metadata rather than authorization enforcement; the tool implementations and permission middleware retain authority over whether an invocation can mutate or access state.

#### Scenario: Raw registry listing carries exact metadata
- **WHEN** the server registry is listed without deprecated-tool visibility filtering
- **THEN** every registered tool has the exact title, tag set, and four behavior-hint values in the table

#### Scenario: Behavior hints do not grant authority
- **WHEN** a tool's metadata marks it non-destructive or open-world
- **THEN** that metadata alone does not bypass the tool's write gate, authentication, ownership, or action-specific validation

### Requirement: Full get_status responses expose cached sandbox readiness without making the read fail

Full live `get_status` responses SHALL include cached sandbox readiness. When
the path reaches full daemon-status assembly, the response includes
`sandbox_status` from the production
`tinyassets.providers.base.get_sandbox_status` cache. Its ordinary shape SHALL
include boolean `bwrap_available` and nullable or explanatory `reason`. If
obtaining the cached result raises, the sandbox lookup failure SHALL be caught
and substituted with `{"bwrap_available": false, "reason": "probe_error:
<exception>"}` without itself aborting the remaining assembly.

This evidence is a best-effort, process-cached readiness observation. Reading
status SHALL not refresh the probe, provision a universe, gate execution, or
assert OS confinement. Early no-home, access-denied, or configuration-load
responses return before full status assembly and do not include this field.

#### Scenario: Full status returns the cached readiness dictionary

- **WHEN** `get_status` passes its early gates and obtains a cached unavailable or available sandbox result
- **THEN** its response includes that dictionary under `sandbox_status`

#### Scenario: A probe error does not break status

- **WHEN** obtaining sandbox status raises an exception
- **THEN** the lookup failure is caught and does not itself abort full daemon-status assembly
- **AND** `sandbox_status.bwrap_available` is false with a `probe_error` reason

#### Scenario: Early status responses omit sandbox evidence

- **WHEN** `get_status` returns early for no bound home, denied access, or configuration-load failure
- **THEN** that early response does not include `sandbox_status`

### Requirement: Custom agents route through canonical graph handles

Custom agents SHALL be read through `read_graph` (`agents`, `agent`,
`agent_bindings`, `agent_binding`) and written through `write_graph`; the
public agent commons SHALL be browsable by any authenticated caller, and
private bindings by their universe's ACL only.

#### Scenario: signed-in caller browses the public agent commons
- **WHEN** an authenticated caller uses `read_graph` with target `agents`
- **THEN** public agent definitions are listed

### Requirement: An owner can delete their own branch through write_graph

`write_graph target=branch` SHALL accept `operation=delete` with `branch_id` on
both the universe surface and the served build surface, as an operation under the
existing `write_graph` handle and not as a new advertised tool. The operation SHALL
delete only a branch authored by the caller; for any other branch, including a
public one, it SHALL answer with the same not-found envelope a private read gives.
A public branch is a shape others copy or remix into their own universe and runs
nothing for anyone else, so it SHALL delete like any other. It SHALL refuse with
`branch_has_dependents`, naming each dependent it found, when any of these
readers still references the branch: an active automation (any universe), an
active webhook, an active schedule or event subscription, a canonical goal
binding (default, personal or legacy) on any of the branch's versions, another
branch of the same author — by current definition or by an active published
snapshot — that invokes it through `invoke_branch_spec` or
`invoke_branch_version_spec`, or a universe whose soul declares it as its loop
branch. A foreign snapshot that invoked the branch while it was public SHALL NOT
count: it was cut off when the branch went private and is not the owner's to
edit. Version ids SHALL be read uncapped. The branch's own patch snapshots in `branch_versions` SHALL NOT
count as a dependency. The tool text on both surfaces SHALL name the operation
and the refusal.

#### Scenario: An own private branch nothing depends on is deleted

- **WHEN** the author calls `write_graph target=branch operation=delete branch_id=<own private branch>`
- **THEN** the result is `{"branch_def_id": ..., "status": "deleted"}`
- **AND** `read_graph target=branches` no longer lists it

#### Scenario: A branch that was patched still deletes

- **WHEN** the author has patched the branch (which minted version snapshots) and then calls delete
- **THEN** it is deleted

#### Scenario: A public branch deletes like any other

- **WHEN** the author calls delete on their public branch that nothing of theirs depends on
- **THEN** it is deleted

#### Scenario: Dependents are named, not broken

- **WHEN** any listed reader references the branch
- **THEN** delete answers `branch_has_dependents` with the ids under `automations`, `webhooks`, `schedules`, `subscriptions`, `goals`, `branches`, `universes`
- **AND** nothing is deleted

#### Scenario: A non-author cannot probe

- **WHEN** a caller who is not the author calls delete on a public branch
- **THEN** the result is the not-found envelope

### Requirement: Owned conversation UI shows viewer-local message instants

The daemon-served conversation app at `/mcp/app` SHALL show message timestamps.
The same renderer SHALL show a date and time on every founder, universe, and system-notice
message across the desktop and mobile shells. A known message instant SHALL be
formatted by the browser in the viewing user's locale and local timezone with a
visible timezone abbreviation or offset, while an HTML `time` element retains
the same instant as a UTC ISO 8601 `datetime` value. Durable history SHALL use
each turn's stored epoch timestamp; optimistic, queued, received, and generated
notice messages SHALL use the corresponding client event time. An unstamped or
malformed legacy turn SHALL say that its date and time are unavailable and
SHALL NOT receive a fabricated `datetime` value.

#### Scenario: One instant crosses a viewer date boundary

- **WHEN** two viewers in Los Angeles and Tokyo render the same stored instant near midnight UTC
- **THEN** each sees the date and time appropriate to their own timezone, including timezone context
- **AND** both semantic `datetime` values identify the same UTC instant

#### Scenario: Every message role carries time context

- **WHEN** the app renders founder text, a universe reply, or a system notice
- **THEN** the message metadata includes its role and its viewer-local date, time, and timezone context

#### Scenario: Legacy missing time remains unknown

- **WHEN** a durable legacy turn has no usable timestamp
- **THEN** the app displays `Date and time unavailable`
- **AND** it does not substitute page-load time or emit a machine-readable instant for that turn

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
