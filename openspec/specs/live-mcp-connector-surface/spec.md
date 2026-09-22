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

### Requirement: Authenticated identity is stable across MCP hosts

The account identity resolved from OAuth SHALL be independent of the MCP host
and OAuth client registration. A user authenticating the same account through
ChatGPT, Claude, a local agent, or another MCP host SHALL resolve to the same
principal and home universe. A cached registration that predates OAuth SHALL
not receive tool data; the host MUST reconnect through the current OAuth
metadata.

#### Scenario: one account connects from ChatGPT and Claude
- **WHEN** the same account completes OAuth in ChatGPT and Claude
- **THEN** authenticated status from both hosts reports the same principal fingerprint and home universe

#### Scenario: a cached host credential cannot refresh
- **WHEN** a host presents no valid bearer because its cached registration or refresh credential is stale
- **THEN** the request receives the OAuth linking challenge before any tool handler runs or returns tool data

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

### Requirement: Converse relays bounded turn input provenance
The founder-only `converse` handle SHALL accept one optional `input_method` field with the closed values `typed`, `spoken`, `app_action`, and `unknown`, default it to `unknown` when omitted, and relay it to the universe writer as a fact about the specific current turn that cannot expand authority or alter the canonical founder message. The handle SHALL NOT expose or accept the replaced `voice_active` field.

#### Scenario: Reported input method reaches the universe writer
- **WHEN** an authorized founder calls `converse` with an allowed reported `input_method`
- **THEN** the writer receives plainly labeled context identifying how that specific turn entered the calling client
- **AND** the context is distinct from founder-authored message text

#### Scenario: Client cannot report input provenance
- **WHEN** an authorized caller omits `input_method`
- **THEN** the writer receives explicit `unknown` input-method context
- **AND** the system does not guess from the message wording or Voice-session state

#### Scenario: Replaced Voice-state field is rejected
- **WHEN** a caller supplies the removed `voice_active` field
- **THEN** the public tool boundary rejects it rather than translating or accepting it as an alias

#### Scenario: Input provenance cannot grant authority
- **WHEN** any caller supplies an allowed `input_method`
- **THEN** founder authentication, universe access, interlocutor tier, and effect consent remain unchanged
- **AND** conversation storage and learning extraction preserve only the original founder message and canonical reply

### Requirement: A conversational answer can identify its own answering model
Successful `converse` JSON SHALL support an optional `execution` object containing
bounded printable `provider`, `model`, and `model_status` labels. The receipt
SHALL belong to that request's first successful conversational writer response,
not to a shared last-provider slot or later learning extraction. `model_status`
SHALL be `reported` only with validated answering-model evidence, otherwise
`unknown` with an empty model. Requested aliases, configured defaults and speech
voices SHALL NOT substitute for answering-model evidence. Held/error replies
SHALL omit execution receipts. Public inputs, direct JSON-string return type,
and authentication/authority checks SHALL remain unchanged.

#### Scenario: A reply is followed by learning or another conversation
- **WHEN** a writer completes and subsequent inference uses another provider
- **THEN** the successful reply retains only its own request-local receipt
- **AND** receipt-observer failure does not discard or retry the earned answer

#### Scenario: Provider does not report the resolved model
- **WHEN** the writer succeeds without validated resolved-model metadata
- **THEN** the receipt marks the model unknown rather than presenting its requested alias as fact

#### Scenario: Typed or spoken app reply includes optional telemetry
- **WHEN** the app renders a newly delivered canonical reply
- **THEN** it displays that reply's provider/model evidence as inert text or explicitly reports missing metadata
- **AND** the text spoken aloud remains the canonical reply without the metadata footer
- **AND** receipt rendering does not activate selection controls or change model routing
- **AND** historical replies without persisted receipts are not assigned inferred model labels

### Requirement: Authorized status explains platform resource observations
Existing authenticated status SHALL offer existing ACL admins universe-scoped resource
observations with timestamp, actual activity scope and limits, workspace
allocation/transport/storage distinctions, and explicit availability. Reads
SHALL NOT create databases, migrate schemas, reconcile usage or mutate records.
SQLite's normal coordination sidecars MAY be created by read-only connections;
reads SHALL preserve locking and visibility of committed WAL transactions.
No new handle or authority SHALL be introduced.
Activity SHALL retain observed engine-mutation counts, but its limits SHALL name
only the enforced total (900) and write-run (300) admission ceilings per rolling
3600 seconds, without the retired `engine_mutations` category ceiling.

#### Scenario: Owner asks about usage
- **WHEN** the app's pinned agent reads status with its owner's existing admin authority for the universe
- **THEN** it receives observed usage and actual policy scope without needing operator database access

#### Scenario: Meter is missing or unreadable
- **WHEN** a trustworthy observation cannot be obtained
- **THEN** the field is unknown or unavailable, not a fabricated zero, and independent status still works

#### Scenario: Canary or unrelated user reads status
- **WHEN** a caller is not authorized for private universe usage
- **THEN** no private counts, paths, run identifiers or holder identities are disclosed

#### Scenario: The oldest charge is about to expire
- **WHEN** status reports a rolling-window expiration
- **THEN** it gives a UTC next-charge-expiration instant and does not guarantee enough capacity for an unspecified future request

#### Scenario: Engine usage is observed without a separate allowance
- **WHEN** authorized status reports engine mutations
- **THEN** activity contains their count and includes them in total, but `activity.limits` contains only `total` and `write_runs`

### Requirement: Legacy storage telemetry labels freshness and accounting scope
The existing storage-utilization status SHALL preserve prior response keys while
reporting scan-start UTC observation time, elapsed observation age, cache reuse
TTL, filesystem denominator and partial enumerated daemon accounting scope.
It SHALL NOT represent the largest listed subsystem as the largest host consumer
or as complete owner-attributed or billable storage.

#### Scenario: Cached status follows a storage change
- **WHEN** storage status reuses a cached measurement
- **THEN** its original observation time remains unchanged and elapsed age is refreshed
- **AND** declared cache TTL means reuse after scan completion, not atomicity or a hard maximum observation age

#### Scenario: Subsystems do not cover the filesystem
- **WHEN** status returns filesystem pressure beside enumerated subsystem bytes
- **THEN** it declares the filesystem-containing-data-root scope and formula `1 - volume_bytes_free / volume_bytes_total`
- **AND** caveats identify partial coverage, excluded Docker images/unlisted paths, mixed universe/root scope and no ownership attribution without exposing additional paths or identities

#### Scenario: Filesystem pressure cannot be measured
- **WHEN** the disk probe fails or reports zero total capacity
- **THEN** additive availability is unavailable and prior numeric keys remain compatible rather than constituting healthy evidence

### Requirement: Storage observations distinguish measurable footprint from complete attribution
Existing admin-only resource status SHALL report bounded metadata-only logical
file-footprint observations separately from unavailable complete attributed
storage. It SHALL preserve existing authority, policy and accounting without
new databases, record mutations, quota changes or file-content reads.

#### Scenario: Authorized owner reads a footprint
- **WHEN** the current universe admin reads status and safe traversal succeeds
- **THEN** the response reports capture time, logical regular-file bytes and categories for permanent workspace, provider runtime, other universe files and lease-attributed scratch
- **AND** it discloses no paths, file names, lease identities or other owners' usage

#### Scenario: Attribution is incomplete
- **WHEN** local footprint is observed but shared-root records and unowned scratch cannot be attributed
- **THEN** those exclusions remain explicit and complete attributed storage remains unavailable rather than equaling the measured footprint

#### Scenario: Walk cannot cover its scope
- **WHEN** traversal meets a link, unsafe path, inaccessible or changing file, unsupported host or work bound
- **THEN** coverage is partial or unavailable with a sanitized reason, not fabricated complete zero

#### Scenario: Cached measurement does not cache authority
- **WHEN** a cached snapshot exists but the caller no longer has current admin authority
- **THEN** it is not returned
- **AND** authorized cache hits retain the original measurement time and declared staleness bound

#### Scenario: Measurements do not create a scan stampede
- **WHEN** simultaneous status requests arrive
- **THEN** same-scope work shares one bounded scan and distinct-scope concurrency is bounded without changing user-work quotas

### Requirement: Owned workflow lifecycle is reachable through graph handles
The graph handles SHALL expose owned workflow editing, exact persisted output
inspection, accurate node failure status, and cancellation without new top-level
tools or extra provider authority. Served selection SHALL remain pinned to its
universe and enforce the existing record ACL before content or mutation.

#### Scenario: Agent follows workflow edit guidance
- **WHEN** an authorized agent uses the operation and payload taught by the edit guidance
- **THEN** a valid owned-node content edit succeeds and reads back without rebuilding the workflow
- **AND** invalid or unauthorized edits refuse without changing the definition

#### Scenario: Agent repairs an existing node model preference
- **WHEN** an authorized served agent updates an owned node's llm_policy through update_node
- **THEN** a valid replacement or explicit null clear SHALL persist without rebuilding the workflow, and omission SHALL preserve the existing policy
- **AND** malformed policy SHALL refuse atomically using canonical validation
- **AND** the edit SHALL NOT grant provider authority, alter ownership, publish a version or modify an admitted run
- **AND** protected execution fields and foreign-owner edits SHALL remain refused

#### Scenario: Code produces ordinary values
- **WHEN** an owned run produces Unicode text, numbers or structured state output
- **THEN** the agent can discover the output fields and retrieve their exact values through read_graph
- **AND** bounded responses explicitly provide continuation rather than silently dropping data

#### Scenario: Another universe's run identifier is supplied
- **WHEN** a pinned served agent selects a run outside its universe for run inspection, output or cancellation
- **THEN** it refuses without disclosing run content or mutating the run, even if broader public read access exists

#### Scenario: Code fails in a parallel workflow
- **WHEN** one code node raises while a sibling is active or complete
- **THEN** the failing node is recorded as failed with its own graph identity and original failure reason
- **AND** no sibling is falsely labeled as the failing node

#### Scenario: Owner cancels queued or running work
- **WHEN** the agent requests cancellation of its queued or running run through run_graph
- **THEN** the existing runner receives the request without another run admission or provider launch
- **AND** request acknowledgement remains distinct from observed terminal cancellation

#### Scenario: Cancel is repeated after completion
- **WHEN** the selected run is already terminal
- **THEN** the actual terminal status is returned without a new cancellation record or false cancelled claim

#### Scenario: Cancel stops an executing code node
- **WHEN** the sandbox reports that an executing code node was cancelled
- **THEN** its graph-instance node event and status are terminal cancelled, not running or failed
- **AND** completed siblings remain completed and nodes that never started are not falsely reported as executed or cancelled
- **AND** initial execution, resumed execution and status diagrams preserve that observed terminal state

#### Scenario: Cancellation is an owner control
- **WHEN** a caller with write capability cancels a run in a universe where it has write access
- **THEN** cancellation does not require platform-admin or costly capability
- **AND** a read-only caller is refused
- **AND** legacy runs without a universe binding require their recorded owner or, when no owner is recorded, their actual actor

#### Scenario: Workspace cleanup follows a real ancestor
- **WHEN** discard names this run's held workspace created by a graph ancestor with no HTTP result
- **THEN** absence from the HTTP response map does not refuse the authorized discard
- **AND** a parallel non-ancestor workspace remains inaccessible and actual cleanup settlement is preserved

### Requirement: Shared unpowered model catalogue
The read_graph handle SHALL accept target=model_options without changing its
arguments or direct string/structured-adapter return contract. The read SHALL
require the authenticated owner's complete current home and explicit admin ACL.
It SHALL NOT create a home, agent, assignment, preference or inference grant.

#### Scenario: Unpowered current home
- **WHEN** the owner has a complete home but no serving agent or working model
- **THEN** the read returns available registered inventory or an empty catalogue
- **AND** unavailable sources and missing saved model references remain distinguishable

#### Scenario: Unknown or foreign scope
- **WHEN** an explicit graph is not the current owned home or lacks admin access
- **THEN** the read refuses without disclosing that graph's model inventory
- **AND** omitted scope never resolves to a designated public universe

#### Scenario: Complete choices, not a first-page sample
- **WHEN** approved discovery returns more models than the default read limit
- **THEN** all protocol-bounded choices survive in structured content
- **AND** limit does not silently hide models from this catalogue target

#### Scenario: Registration is not execution authority
- **WHEN** an owned registered HTTP source has approved discovery but is not accepted for inference
- **THEN** its models remain visible with source_not_accepted and no execution candidates
- **AND** server-derived bind keys and complete existing model_access constraints are provided separately

#### Scenario: Freshness and source-level reasons
- **WHEN** a source is revoked or expires during refresh
- **THEN** that source loses its model rows without concealing independent sources
- **AND** a changed home, admin scope, serving binding or assignment refuses the whole snapshot
- **AND** source failures are a separate channel, not invented empty model identifiers

#### Scenario: Existing native default
- **WHEN** the owner has a current legacy native serving chain
- **THEN** its provider default is visible as legacy_single_provider
- **AND** the read neither invents an actual model name nor grants expanded model selection

#### Scenario: Existing legacy HTTP configuration
- **WHEN** the current legacy serving chain survives the read's final authority fence
- **THEN** legacy_source identifies its provider, bind key and configured fixed model
- **AND** these fields are not actual answering-model receipts or newly admitted candidates
- **AND** revocation during refresh clears the legacy-source projection

### Requirement: Served model setup preserves the person-only access boundary
The served agent SHALL be able to read pinned model options and its universe's
private agent bindings, save current-home model preferences by expected
generation, and configure discovery metadata on existing owned connections.
These operations SHALL NOT grant inference, widen endpoints, change spending
ceilings or silently enroll a provider. Shared connector preference saving SHALL
use the same parser, actor/current-home checks and generation store.

#### Scenario: Catalogue admission and isolation
- **WHEN** the served agent requests model options or an exact private binding
- **THEN** the graph is server-pinned and foreign binding ids are not disclosed
- **AND** catalogue refresh requires admission and envelopes remote strings as untrusted

#### Scenario: Preference and discovery setup are not grants
- **WHEN** a model preference or discovery descriptor is saved
- **THEN** inference membership and connection grants remain unchanged
- **AND** stale generation, changed home and outside-grant URLs refuse without overwrite

#### Scenario: Explicit owner model-access approval
- **WHEN** the agent raises a bind_model_access pending request
- **THEN** the server validates current home, creator, revision and each owned source before showing it
- **AND** captures the baseline assignment and exact model-access proposal server-side
- **AND** the person sees deterministic before/after scope, unchanged spending ceilings and reconnect warning
- **AND** other accepted providers and their scopes are preserved; new sources are free-only
- **AND** the request has no answer fields and the served agent cannot answer it

#### Scenario: Reconnection failure can be retried safely
- **WHEN** publication or reconnect fails during the person's confirmation
- **THEN** the request remains pending and the UI shows the actionable error without claiming delivery to an offline agent
- **AND** replay distinguishes untouched, failed-publication, bound and serving states using revision, exact membership and assignment fences
- **AND** repeated failed publication generations are recoverable without blindly overwriting a superseding assignment
- **AND** reconnect rechecks the exact assignment digest and current home inside its transaction
- **AND** success is reported only after serving and request resolution are confirmed

### Requirement: Converse accepts non-authoritative current model choice
The authenticated converse handle SHALL accept optional model_choice using the
existing versioned preferences document. Omission SHALL use supported saved
preferences or preserve absent-policy legacy behavior. A current override SHALL
replace the entire current order without modifying saved defaults or authority.

#### Scenario: One-turn explicit choice
- **WHEN** an authorized owner supplies valid explicit model_choice
- **THEN** this turn captures that primary and exact fallback tail
- **AND** the saved row and generation remain unchanged

#### Scenario: One-turn automatic choice
- **WHEN** model_choice requests automatic mode
- **THEN** this turn clears the saved primary and uses eligible automatic ordering
- **AND** it does not append the old default as an explicit fallback

#### Scenario: Invalid or unauthorized choice
- **WHEN** the document is malformed, unsupported, outside supported owner scope or accepted authority
- **THEN** the runtime refuses before launch without widening access

#### Scenario: Cross-client compatibility
- **WHEN** the changed tool is tested through ChatGPT and Claude
- **THEN** both render structured results and final narration without wedging
- **AND** protected canary --assert-handles and deployed-SHA gates remain required

### Requirement: Graph handles expose structured cross-user delivery controls
Canonical top-level handles SHALL retain their signatures. Validated graph
dispatch SHALL expose receiver create/update/revoke, output-link connect/disconnect,
explicit deliver_output sends, and receiver/output_links/delivery inspection.
The served read_graph wrapper SHALL accept optional query for those reads;
served management and sends SHALL remain graph-pinned and operation-authorized.
These controls SHALL NOT claim file transfer, in-node delivery RPC or receiver
execution retry, which remain outside this shipped structured MVP.

#### Scenario: Each party manages only its authorized side
- **WHEN** authenticated users manage their receiving contracts and outgoing links
- **THEN** each action enforces current owner and universe authority
- **AND** the shared served wrappers use the same validated dispatch as connector callers

#### Scenario: Contract inspection remains narrow
- **WHEN** a permitted sender inspects a receiver contract
- **THEN** it receives the advertised description, contract and generation
- **AND** not the private receiver graph, credentials, other senders or unrelated deliveries

#### Scenario: Receipt read requires party authority
- **WHEN** an unrelated or anonymous caller supplies a delivery identifier
- **THEN** no delivery record is revealed
- **AND** sender-side inspection never reveals private receiver run evidence

#### Scenario: Delivery does not add another top-level tool
- **WHEN** the public tool inventory is inspected after deployment
- **THEN** the canonical handle set is unchanged and collaboration uses existing graph handles

### Requirement: Served owners can edit existing effect and workspace declarations

The served write_graph branch patch surface SHALL allow an authorized author to
add effect-bearing nodes and replace or clear an existing node's effects and
workspace declarations using the same admitted effect grammar as served creation.
Omitted declarations SHALL remain unchanged. The edit SHALL grant no connection,
consent, provider, filesystem or execution authority and SHALL dispatch no effect.
Source-review provenance SHALL retain its existing source-bound semantics, never
become an execution gate or be accepted from caller-supplied approval metadata.
Existing ownership, runtime consent, resource, sandbox and workspace ancestor/lease
checks SHALL remain effective. There SHALL be no per-branch effect-node count cap.

#### Scenario: Owner revises an existing effect without rebuilding

- **WHEN** an authorized author patches an existing node to use an admitted sink
- **THEN** the original branch identity is retained and readback shows the declaration
- **AND** clearing effects with an empty array or null removes the declaration
- **AND** an unrelated edit leaves the declaration unchanged

#### Scenario: Owner adds an effect-bearing node

- **WHEN** an author adds a node with a declaration accepted by served creation
- **THEN** the existing branch gains the node without a graph-size refusal
- **AND** caller-supplied approval and author fields are stripped as on creation

#### Scenario: Workspace declaration is an ancestor reference not a grant

- **WHEN** the owner changes or clears the workspace declaration
- **THEN** canonical string/null semantics apply and the result persists on the same node
- **AND** execution still refuses a missing or non-ancestor workspace or invalid lease

#### Scenario: Invalid batch or foreign edit persists nothing

- **WHEN** a patch contains a malformed declaration, unadmitted sink, repeated sink,
  forbidden authority field, or targets another author's branch
- **THEN** it refuses without changing the persisted branch or firing an effect

#### Scenario: Declaration does not bypass consent

- **WHEN** a successfully edited node later tries an external operation without its required consent
- **THEN** the runtime refuses under the same authority rules as a newly created node
- **AND** the edit has neither minted a grant nor made the operation authorized

### Requirement: Run reads expose honest stored node activity
Authorized run inspection SHALL include compact typed node-activity evidence
derived from existing run events without new execution, credentials, storage,
top-level tools or raw event-detail disclosure. Existing run status, output
retrieval, authorization, pinned universe selection and client envelopes SHALL
remain intact. Missing evidence SHALL remain explicitly unknown.

#### Scenario: A later node fails after a provider returned
- **WHEN** existing events record a completed provider response for one node and a later node fails
- **THEN** the run read includes the earlier node's stored returned-call evidence even without a success-only run aggregate
- **AND** normalized actual-model evidence is distinguished from an unreported model or configuration hint
- **AND** `model_status` describes only model-identifier provenance (`reported` or `unknown`), not request receipt, provider admission or output validation

#### Scenario: A node starts locally but has no returned provider evidence
- **WHEN** an event records local node start and no subsequent returned-call receipt
- **THEN** the read identifies local start and leaves provider acknowledgment and response evidence unknown
- **AND** it does not infer provider silence, non-start, upstream load or stopped execution from an outer timeout

#### Scenario: Timestamps and repeated starts are interpreted honestly
- **WHEN** a node has repeated starts or a return followed by output validation failure
- **THEN** returned-call evidence retains its observation step and time independently of latest node status
- **AND** local elapsed time uses an observed ordered start/terminal pair, not the near-zero span of a terminal record
- **AND** missing, invalid or nonfinite timing is unknown rather than fabricated

#### Scenario: Event details contain generated content or sensitive payloads
- **WHEN** stored details contain prompts, previews, responses, code, arbitrary errors, credentials or nested provider objects
- **THEN** the new activity projection excludes those raw fields and exposes only bounded typed metadata and strict normalized execution receipts
- **AND** exact authorized output remains available through the existing output read rather than being copied into diagnostic metadata

#### Scenario: A caller supplies an unauthorized or foreign-scope run
- **WHEN** a caller lacks run-read authority or a served run identifier is outside the pinned universe
- **THEN** the existing refusal occurs before activity is returned
- **AND** public visibility does not widen a served agent's pinned selector

#### Scenario: Large or legacy workflows are inspected
- **WHEN** a run has many nodes or legacy events with incomplete metadata
- **THEN** no new workflow-size restriction is imposed and no node is silently omitted merely for exceeding a diagnostic count
- **AND** per-node metadata remains bounded, existing result envelopes remain faithful and bounded, and unavailable facts are marked unknown
- **AND** existing recovery guidance precedes activity caveats, which precede the node-activity list in bounded text presentation

### Requirement: A bounded conversation preview names its own full size
`get_status` with `include_conversation` SHALL, for each turn it returns, carry the
turn's stable store identifier, its full length in Unicode code points, and whether
the returned text was bounded. The returned text SHALL remain bounded and the
identifier SHALL be the key accepted by the lossless read below, so a client never
pairs a preview to a stored message by text or timestamp.

#### Scenario: A bounded turn is identifiable
- **WHEN** a retained turn is longer than the per-turn preview bound
- **THEN** the turn reports `truncated: true`, its full `total_chars`, and an `id`
  that the lossless read accepts
- **AND** the preview text itself is unchanged in length or content.

#### Scenario: A short turn claims no loss
- **WHEN** a retained turn fits inside the preview bound
- **THEN** it reports `truncated: false` and a `total_chars` equal to its own length.

#### Scenario: The identifier grants nothing
- **WHEN** a caller holds a turn identifier from another account's thread
- **THEN** the lossless read resolves its own principal and home and returns no
  bytes of that thread.

### Requirement: The connector serves the rest of a bounded message losslessly
The public connector SHALL expose a read-only retrieval of one retained message of
the authenticated caller's own conversation, selected by the identifier above and
returned in exact Unicode-code-point chunks with a server-supplied continuation
offset. The read SHALL derive its principal and universe home from the verified
caller at call time, SHALL NOT accept a caller-supplied session, principal or
store path, SHALL NOT create or migrate a store, and SHALL NOT change any state.
Execution or delivery receipt metadata SHALL NOT be treated as authorization.

#### Scenario: A long reply is recovered whole
- **WHEN** the caller reads a bounded turn by its identifier and follows each
  returned continuation offset until none is returned
- **THEN** the concatenated chunks equal the stored message exactly, including
  characters outside the Basic Multilingual Plane.

#### Scenario: An unauthenticated or foreign caller reads nothing
- **WHEN** the call carries no verified principal, or carries a different account's
- **THEN** it is refused, or resolves to that caller's own thread, and in neither
  case returns another account's content.

#### Scenario: Retention is stated, never fabricated
- **WHEN** the identified message is not retained
- **THEN** the read says so and returns no reconstructed or approximated text.
