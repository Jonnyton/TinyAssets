# Live MCP Connector Surface

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

The public MCP entry point: the canonical handle set served at https://tinyassets.io/mcp as thin routers over `tinyassets.api.*` handlers, MCP prompts that teach connecting chatbots, legacy fat-tool deprecation, the Cloudflare Worker front door, and the public canaries that guard the surface.
## Requirements
### Requirement: Remote Streamable-HTTP MCP Endpoint

The platform SHALL expose a single remote MCP server over Streamable-HTTP transport (`tinyassets/universe_server.py`, built on FastMCP) that any MCP-compatible chatbot can connect to by URL with no local installation. The server SHALL register MCP prompts (control-station and meet-universe prompts in `tinyassets/api/prompts.py`) so a connecting chatbot receives behavioral instructions on how to act as the user's control interface.

#### Scenario: Chatbot completes an MCP handshake and lists tools

- **WHEN** an MCP client sends `initialize`, then `notifications/initialized`, then `tools/list` to the server
- **THEN** the server responds with a valid MCP `serverInfo` + `protocolVersion` and returns a non-empty advertised tool list
- **AND** the response is delivered as either JSON or an SSE `event: message` frame, both of which are valid Streamable-HTTP responses

#### Scenario: Connecting chatbot receives behavioral prompts

- **WHEN** a chatbot enumerates the server's MCP prompts
- **THEN** the control-station and meet-universe prompts are available, teaching the chatbot how to operate the universe and how consent-gated universe embodiment works

### Requirement: Canonical Advertised Handle Set

The advertised `tools/list` surface SHALL be exactly seven handles: `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, and `get_status`. Each is a thin shape/target router that delegates to an existing `tinyassets.api.*` handler without changing that handler's behavior. The public drift-guard canary (`scripts/mcp_public_canary.py --assert-handles`) SHALL require the six core handles (`CANONICAL_HANDLES`, which includes `converse`) and permit `get_status` as an optional read affordance — the server advertises all seven; the canary treats `get_status` as allowed-but-not-required so a status-less deploy is not drift. As-built note: legacy "five handles" naming survives only in identifiers (e.g. `assert_five_handles_with_retry`, `test_universe_server_five_handles.py`) as historical naming; the enforced contract is the set above.

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

The six legacy fat tools (`universe`, `community_change_context`, `extensions`, `goals`, `gates`, `wiki`) SHALL remain registered and dispatchable for one migration release while being hidden from `tools/list` by the `_DeprecatedToolVisibility` middleware. Every call to a hidden legacy tool SHALL be logged as deprecated. In gating auth modes an anonymous caller SHALL NOT be able to invoke a legacy fat tool.

#### Scenario: Legacy tool is absent from the advertised list but still callable

- **WHEN** a client reads `tools/list` and then calls the legacy `universe` tool by name
- **THEN** `universe` does not appear in the advertised list, the call still dispatches and returns a result, and a `deprecated-tool-call name=universe` warning is logged

#### Scenario: Anonymous caller is refused a legacy tool in gating auth mode

- **WHEN** an unauthenticated client calls a deprecated fat tool while the server is in a write-gating auth mode
- **THEN** the call is rejected with a `ToolError` directing the caller to the canonical handles instead

### Requirement: Connector-Safe Handle Names

Every advertised handle name SHALL match `^[a-zA-Z0-9_-]{1,64}$` and MUST NOT contain a dot. The canonical handles therefore use underscore names (`read_graph`, `write_graph`, and so on), because the Anthropic connector API rejects any tool name containing a dot and a single rejected name rejects the whole connector. This constraint is documented and honored at the registration boundary in `tinyassets/universe_server.py`.

#### Scenario: Advertised handle names are connector-safe

- **WHEN** the advertised handle set is inspected
- **THEN** every handle name matches `^[a-zA-Z0-9_-]{1,64}$` with no dots

### Requirement: Read-Open, Write-Challenged Authentication Boundary

Pure-read handles (`read_graph`, `read_page`, and the `read_graph target=status` alias) SHALL remain callable anonymously. Pure-write / costly-effect handles (`write_graph`, `run_graph`, `write_page`, `converse`) SHALL answer an anonymous `tools/call` with an HTTP 401 + `WWW-Authenticate` challenge pre-dispatch so the MCP client launches OAuth, since a tool-JSON rejection would not prompt sign-in. `converse` is the connector's opening call: it is founder-only, relays the founder's turn to the universe's own intelligence, and for an authenticated founder with no home universe it resolves-or-creates and binds that home as a one-time onboarding side effect. `get_status` and the `read_graph target=status` alias are both pure reads (`readOnlyHint=True`) and never provision. Per the 2026-07-22 host directive (`docs/design-notes/2026-07-22-first-contact-birth-moves-to-converse.md`) birth moved off `get_status`, because a mutating *opening* call proved refusable in production — the assistant declined to call it, citing the side effect its own tool description advertised, which contradicted the shipped instruction to call it first.

#### Scenario: Anonymous write handle triggers an OAuth challenge

- **WHEN** an unauthenticated client calls `write_graph`, `run_graph`, `write_page`, or `converse`
- **THEN** the server answers HTTP 401 with a `WWW-Authenticate` header pre-dispatch, launching the OAuth sign-in flow

#### Scenario: Anonymous read handle stays open

- **WHEN** an unauthenticated client calls `read_graph` or `read_page`
- **THEN** the read is served without an auth challenge

#### Scenario: First-contact provisioning via converse

- **WHEN** an authenticated founder with no home universe issues their opening `converse` with no `graph_id`
- **THEN** a home universe is created and bound, and the reply is the universe speaking in first person
- **AND** a later `converse` for the same founder reaches the same home with no further creation

#### Scenario: get_status never provisions

- **WHEN** an authenticated founder with no home universe calls `get_status`
- **THEN** no universe is created and the call is a pure read (`readOnlyHint=True`)

#### Scenario: The read alias never provisions

- **WHEN** any caller invokes `read_graph(target="status")`
- **THEN** no universe is created

#### Scenario: Non-founder is refused converse

- **WHEN** an anonymous or non-owner caller reaches `converse` for a universe they do not own
- **THEN** the reply is an auth error and no message is relayed to the universe intelligence

### Requirement: Faithful Structured And Text Result Envelope

Every handle result SHALL be wrapped so the MCP response carries both a `structuredContent` typed object and a text `content` block that reflects the real payload. The text block SHALL be capped at 6000 characters. When the payload fits, the text block SHALL carry the full payload as JSON; when it exceeds the cap, the text block SHALL carry as much real, readable data as fits plus an explicit truncation pointer to `structuredContent`, and SHALL NOT be replaced by a lossy placeholder stub.

#### Scenario: Under-budget result carries the full payload in text

- **WHEN** a handle returns a payload whose JSON is at or under 6000 characters
- **THEN** the text `content` block contains the full payload as JSON and `structuredContent` contains the same typed object

#### Scenario: Over-budget result stays faithful and bounded

- **WHEN** a handle returns a payload whose JSON exceeds 6000 characters
- **THEN** the text `content` block contains real payload data truncated to the cap with an explicit `[truncated: ... full payload in structuredContent]` pointer, never a placeholder that reads as empty

### Requirement: Cloudflare Worker Public Front Door

`https://tinyassets.io/mcp` SHALL be the only public user-facing MCP URL. A Cloudflare Worker on the `tinyassets.io/mcp*` route SHALL proxy `/mcp` and `/mcp-directory` requests to the Access-gated tunnel origin `mcp.tinyassets.io`, injecting the CF Access service-token headers (`CF-Access-Client-Id` / `CF-Access-Client-Secret`) from Worker environment secrets. The Worker SHALL stream SSE bodies straight through without buffering, SHALL preserve request headers and method, and SHALL map any tunnel `5xx` (or an unreachable tunnel) to an explicit `502` JSON body rather than falling through to the GoDaddy origin. `mcp.tinyassets.io` is an internal Access-gated origin and MUST NOT be presented as user-facing.

#### Scenario: Worker proxies to the Access-gated origin with service tokens

- **WHEN** a client request arrives at `tinyassets.io/mcp`
- **THEN** the Worker rewrites `Host` to `mcp.tinyassets.io`, adds the CF Access service-token headers from env secrets, and forwards method, body stream, and non-hop-by-hop headers

#### Scenario: SSE bodies stream without buffering

- **WHEN** the tunnel origin returns a `text/event-stream` response
- **THEN** the Worker returns the upstream `ReadableStream` body directly without calling `.text()`/`.json()`/`.arrayBuffer()`

#### Scenario: Tunnel failure surfaces as an explicit 502

- **WHEN** the tunnel origin returns a `5xx` status or is unreachable
- **THEN** the Worker responds `502` with a `bad_gateway` JSON body, never a GoDaddy `404` fallthrough

### Requirement: Public Canary And Directory Review Surface

The platform SHALL provide a stdlib-only public canary (`scripts/mcp_public_canary.py`) whose `--assert-handles` mode performs a full handshake, reads `tools/list`, and fails (exit 4) unless the live surface advertises the required canonical handles and nothing beyond the allowed advertised set, plus a lightweight uptime canary (`scripts/uptime_canary.py`). The platform SHALL also expose a narrower directory surface (`tinyassets/directory_server.py`, served at `/mcp-directory`) intended for reviewed host directories such as Claude's Connectors Directory and ChatGPT Apps: it advertises no catch-all `action` inputs and returns a redacted `get_status` that strips operator diagnostics and injects a `directory_privacy_note`.

#### Scenario: Canary fails on advertised-handle drift

- **WHEN** the live `tools/list` is missing a required canonical handle or advertises a handle outside the allowed set (for example a leaked legacy fat tool)
- **THEN** `mcp_public_canary.py --assert-handles` exits with code 4 and reports the missing/extra handle sets

#### Scenario: Directory status redacts operator diagnostics

- **WHEN** a directory client reads status through the `/mcp-directory` surface
- **THEN** raw activity logs and internal diagnostics are stripped and the payload carries a `directory_privacy_note`, whereas the live `/mcp` `read_graph target=status` returns the full unredacted status

### Requirement: Published registry metadata follows the current versioned directory catalog
The checked-in MCP Registry manifest SHALL advertise the versioned remote URL derived from `tinyassets.connector_catalog.directory_mcp_remote_url()`, and repository tests plus packaging CI SHALL fail when `packaging/registry/server.json` differs from the deterministic generator output. The generator SHALL run directly from a clean repository checkout. Before repaired metadata is accepted for publication, the generated versioned URL SHALL serve the current directory catalog successfully.

#### Scenario: a connector catalog version change makes stale metadata fail
- **WHEN** `DIRECTORY_TOOL_CATALOG_VERSION` changes without regenerating `packaging/registry/server.json`
- **THEN** the focused artifact-equality test fails
- **AND** the packaging workflow's generator `--check` step fails

#### Scenario: clean checkout generation uses the current catalog source
- **WHEN** a contributor runs `python packaging/registry/generate_server_json.py --check` from repository root
- **THEN** the command imports the repository's real `tinyassets.connector_catalog` module
- **AND** it compares the checked-in manifest with the document containing `directory_mcp_remote_url()`

#### Scenario: repaired registry remote is reachable
- **WHEN** the generated manifest is proposed for external-directory publication
- **THEN** a read-only Streamable-HTTP MCP handshake to its remote URL succeeds and lists the current versioned directory catalog handles
