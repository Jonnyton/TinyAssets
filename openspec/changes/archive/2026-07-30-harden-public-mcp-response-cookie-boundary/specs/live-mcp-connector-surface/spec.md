## MODIFIED Requirements

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
