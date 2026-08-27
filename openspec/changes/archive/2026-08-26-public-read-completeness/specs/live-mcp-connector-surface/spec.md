## ADDED Requirements

### Requirement: Canonical public reads advertise continuation and completeness contracts
The live MCP connector SHALL keep the exact canonical seven-handle set while advertising `category`, `scope`, `cursor`, `offset`, `max_chars`, and `expected_sha256` on `read_page` and advertising `cursor` on `read_graph`. Canonical exact-page reads SHALL default to 4,000 characters and cap public `max_chars` at 32,000. Public wiki enumeration `max_results` and Goal catalog `limit` SHALL reject values outside 1 through 100 with no rows and `invalid_window_limit`. Parameters SHALL route only to their defined modes: `query` to ranked wiki search and the exact-read ambient feed; `scope` to ranked wiki search, wiki changed-since enumeration, and the exact-read ambient feed; `category` to wiki changed-since enumeration and the exact-read ambient feed; `read_page.cursor` to wiki changed-since enumeration; `offset`, `max_chars`, and `expected_sha256` to exact page reads; and `read_graph.cursor` to `target=goals` catalog enumeration. With an exact `page`, the shipped `changed_since` input plus `query` SHALL remain ambient-feed filters, slice 1A SHALL newly forward `category`, and slice 1B SHALL newly forward `scope`; without an exact `page`, `changed_since` SHALL select wiki enumeration. A non-empty no-page `query` SHALL select ranked search only when neither `changed_since` nor an enumeration cursor is supplied; combining that query with either enumeration discriminator SHALL return zero results and a structured parameter/mode conflict rather than silently dropping `changed_since` or `cursor`. A `read_page.cursor` supplied without `changed_since` SHALL itself select wiki changed-since enumeration and recover the bound bootstrap/poll boundary from retained cursor state; if `changed_since` is also supplied, both SHALL decode to the same normalized inclusive boundary or fail with zero results regardless of raw string representation. Wiki enumeration `changed_since` SHALL accept an explicit ISO bootstrap boundary or the opaque actor/visibility-partition-bound `next_changed_since` token returned by a terminal prior poll. A `read_page` call without an exact `page` and with `changed_since` SHALL remain enumeration even when `scope` or `category` is also supplied; the wrapper SHALL forward both filters to the changed-since handler rather than misrouting the request to ranked search. Exact reads SHALL forward `changed_since`, `query`, `category`, and once host-approved `scope` to their ambient feed. Any advertised parameter supplied outside its defined mode SHALL return zero results and a structured error naming the parameter plus the mode that accepts it; no cross-mode parameter may be silently ignored.

For wiki and Goal enumeration modes, the connector SHALL preserve each owning capability's structured completeness receipt in `structuredContent`, including applied filters/scope, `snapshot_revision`, `snapshot_captured_at`, `snapshot_expires_at`, `count`, `withheld_count`, `total_matches`, `truncated_count`, `has_more`, `next_cursor`, and `complete`; terminal wiki enumeration SHALL also preserve non-null opaque `next_changed_since`, while non-terminal windows SHALL expose no advanceable poll token. Its bounded text projection SHALL remain faithful to whether more retained rows exist, whether rows were withheld by current visibility or withdrawal checks, and how to continue; text-envelope truncation SHALL NOT change, invent, or conceal the structured receipt. Goal-list text SHALL identify `next_cursor` when more Goals remain and SHALL NOT tell the user merely to narrow filters when an exact continuation exists.

Tool descriptions SHALL state that lexical search is best-effort, enumeration is the absence/completeness path, cursors/tokens are continuation state rather than authority, and a returned `next_changed_since` must be reused for gap-free polling. A visibility-partition change SHALL be described as returning `poll_rebaseline_required` plus the server-provided `rebaseline_changed_since`; an actor-only change with the same visibility partition SHALL be described as returning `poll_context_rebound` plus a same-fence `rebound_changed_since` that avoids full-epoch re-enumeration. Exact page chunks must retain the returned SHA-256, and a stale cursor/hash requires restart. No legacy alias, standalone pagination tool, or Village/web-app dependency SHALL be introduced.

Tool descriptions SHALL qualify the parameter name by handle and keep the enums disjoint: `read_page.scope` accepts only `discovery`, `coordination`, or `all`, while a separately accepted relay capability may define `write_page.scope=commons`; no description, schema, or routing branch may transfer a value from one handle's enum to the other.

The canonical `read_page` and `read_graph` tools SHALL retain `readOnlyHint=true` and `idempotentHint=true`. Owning enumeration handlers SHALL satisfy those hints by reusing an identical actor/query/public-manifest first-window snapshot instead of charging retry allocations and by making continuation cursors immutable positional tokens: with unchanged current withdrawal inputs, the same cursor SHALL return the same window and `next_cursor` without advancing server state or consuming quota. A newly withdrawn row SHALL still fail closed within the cursor's fixed processed range. Internal retained-state creation SHALL NOT make the public operation a mutation.

Before anonymous snapshot quotas are enabled, the Cloudflare front door SHALL overwrite any caller-supplied `X-Forwarded-For` with authoritative `CF-Connecting-IP` on every proxied MCP request. The origin SHALL trust that value only when the request arrives through authenticated tunnel/front-door provenance and SHALL derive a privacy-safe keyed requester partition without persisting the raw address in snapshot state. An unverified direct request, caller-selected forwarding header, or proxied request lacking authoritative forwarding provenance SHALL NOT mint an anonymous partition. An anonymous enumeration that cannot derive that partition SHALL return zero rows, `complete=false`, `anonymous_partition_unavailable`, and bounded retry guidance as an in-band tool result rather than a transport challenge or gateway error.

#### Scenario: tools list stays at seven handles
- **WHEN** a connector client performs `tools/list` after this change
- **THEN** the advertised names remain exactly `converse`, `get_status`, `read_graph`, `read_page`, `run_graph`, `write_graph`, and `write_page`
- **AND** no list-pages, continue-page, or list-goals handle is advertised

#### Scenario: scope enums remain handle-qualified
- **WHEN** a client inspects descriptions and schemas for `read_page` and `write_page`
- **THEN** `read_page.scope` advertises only `discovery`, `coordination`, and `all`
- **AND** `commons` is never accepted or suggested for `read_page.scope`, while read-side values are never transferred to a separately accepted `write_page.scope`

#### Scenario: read_page schema advertises complete wiki traversal
- **WHEN** a client inspects the advertised `read_page` input schema
- **THEN** it can discover the allowed relevance scopes, enumeration cursor, exact-read offsets, maximum character window, and SHA-256 continuation guard
- **AND** exact reads forward the documented category filter to their ambient feed

#### Scenario: changed-since filters stay on the enumeration route
- **WHEN** a caller without an exact `page` supplies `changed_since` together with `scope` or `category`
- **THEN** `read_page` invokes complete changed-since enumeration and forwards every supplied filter
- **AND** it does not silently route the request to ranked lexical search

#### Scenario: no-page ranked query cannot silently discard enumeration state
- **WHEN** a caller without an exact `page` combines a non-empty `query` with `changed_since` or an enumeration `cursor`
- **THEN** `read_page` returns zero results and a structured parameter/mode conflict
- **AND** it does not silently discard the enumeration discriminator or claim completeness for ranked search

#### Scenario: exact-page changed-since remains an ambient-feed filter
- **WHEN** a caller supplies an exact `page` together with `changed_since`, `query`, `scope`, or `category`
- **THEN** `read_page` performs the exact-page chunk read and forwards those inputs only to its ambient feed
- **AND** an enumeration `cursor` on that exact-page call fails with zero results and a structured parameter/mode error

#### Scenario: wiki cursor alone selects enumeration continuation
- **WHEN** a caller supplies a valid `read_page.cursor` without repeating `changed_since`
- **THEN** the connector routes to wiki changed-since enumeration using the cursor's bound boundary and filters
- **AND** a separately supplied mismatching `changed_since` fails with zero results rather than changing modes

#### Scenario: changed-since schema explains bootstrap and bound continuation
- **WHEN** a client inspects the advertised `read_page.changed_since` description
- **THEN** it can discover explicit ISO bootstrap boundaries and terminal `next_changed_since` poll tokens
- **AND** the description separates visibility-partition `poll_rebaseline_required` with server-provided `rebaseline_changed_since` from same-partition actor-only `poll_context_rebound` with same-fence `rebound_changed_since`

#### Scenario: read_graph schema advertises Goal continuation
- **WHEN** a client inspects the advertised `read_graph` input schema
- **THEN** it can discover the cursor used by `target=goals`
- **AND** the description states that ranked query search is not a completeness proof

#### Scenario: unsupported cursor is not silently discarded
- **WHEN** a caller supplies `cursor` to a `read_graph` target other than the complete Goal catalog enumerator
- **THEN** the connector returns a structured unsupported-cursor error with no target results

#### Scenario: exact page and enumeration cursor fail loudly together
- **WHEN** a caller supplies exact `page` together with an enumeration `cursor`
- **THEN** the connector returns zero page results and a structured error naming `cursor` plus wiki changed-since enumeration
- **AND** it does not dispatch exact read first and silently discard the cursor

#### Scenario: exact chunk inputs fail loudly on search or enumeration
- **WHEN** a caller supplies `offset`, `max_chars`, or `expected_sha256` with ranked search or changed-since enumeration
- **THEN** the connector returns zero results and names the invalid parameter plus exact page mode

#### Scenario: identical first-window retry stays idempotent
- **WHEN** a caller retries an identical enumeration first window against the same authority-filtered public manifest
- **THEN** the connector returns the same retained snapshot/initial continuation without consuming another snapshot quota unit
- **AND** the advertised read-only and idempotent hints remain truthful

#### Scenario: identical continuation retry stays positional
- **WHEN** a caller retries one wiki or Goal continuation cursor with unchanged current withdrawal inputs
- **THEN** the connector returns the same emitted/withheld window and same `next_cursor`
- **AND** no mutable continuation pointer advances and no additional quota unit is consumed

#### Scenario: caller cannot mint anonymous requester partitions
- **WHEN** one anonymous client varies caller-supplied forwarding headers across first-window requests
- **THEN** the front door overwrites them from authoritative transport metadata and the origin derives one requester partition
- **AND** two distinct authoritative client addresses derive distinct privacy-safe partitions without trusting direct-origin input

#### Scenario: structured receipt survives bounded text rendering
- **WHEN** a paginated read result exceeds the connector's text budget
- **THEN** `structuredContent` retains the complete owning-capability payload
- **AND** the bounded text states that the result is partial and identifies the server-issued continuation field

#### Scenario: anonymous public enumeration remains read-open
- **WHEN** an anonymous connector caller uses `read_page` changed-since enumeration or `read_graph target=goals`
- **THEN** the existing read-open authentication boundary remains in force
- **AND** each owning handler still applies its visibility rules before returning results or totals

#### Scenario: both priority chatbot hosts traverse beyond the first window
- **WHEN** final acceptance runs separate real Claude.ai and ChatGPT conversations with the installed live connector
- **THEN** each chatbot follows at least one server-issued cursor or page offset and reaches a terminal `complete=true` or `truncated=false` receipt
- **AND** neither recorded conversation depends on the TinyAssets web app

## MODIFIED Requirements

### Requirement: Cloudflare Worker Public Front Door

`https://tinyassets.io/mcp` SHALL be the only public user-facing MCP URL. A
Cloudflare Worker on the `tinyassets.io/mcp*` route SHALL proxy only canonical
`/mcp` traffic to the Access-gated tunnel origin `mcp.tinyassets.io`, injecting
the CF Access service-token headers (`CF-Access-Client-Id` /
`CF-Access-Client-Secret`) from Worker environment secrets. The Worker SHALL
stream SSE bodies straight through without buffering, SHALL preserve request
method and non-hop-by-hop headers except `X-Forwarded-For`, whose authoritative
overwrite behavior is defined below, and SHALL map any tunnel `5xx` (or an unreachable tunnel)
to an explicit `502` JSON body rather than falling through to the GoDaddy
origin. For every proxied MCP request, the Worker SHALL unconditionally replace
caller-supplied `X-Forwarded-For` with Cloudflare's authoritative
`CF-Connecting-IP`. If that authoritative value is missing, the Worker SHALL
strip `X-Forwarded-For` and continue proxying; the origin SHALL refuse to mint
an anonymous requester partition through the owning in-band denial envelope,
and this condition SHALL NOT become a Worker `502`. It SHALL NOT route,
redirect, proxy, alias,
translate, or return a compatibility response for `/mcp-directory*`; those
paths receive the ordinary edge 404. `mcp.tinyassets.io` is an internal
Access-gated origin and MUST NOT be presented as user-facing.

#### Scenario: Worker proxies canonical MCP only

- **WHEN** a client request arrives at `tinyassets.io/mcp`
- **THEN** the Worker rewrites `Host` to `mcp.tinyassets.io`, adds the CF Access service-token headers from env secrets, and forwards method, body stream, and non-hop-by-hop headers other than `X-Forwarded-For`, whose authoritative overwrite behavior is defined below
- **AND** the broad Worker binding terminates `/mcp-directory*` as an ordinary edge 404 without proxy, redirect, alias, or translation

#### Scenario: caller-supplied forwarding identity is overwritten

- **WHEN** a caller supplies any `X-Forwarded-For` value on a proxied MCP request
- **THEN** the Worker replaces it with authoritative `CF-Connecting-IP`
- **AND** if the authoritative value is missing, the Worker strips the caller value and continues proxying; anonymous snapshot/enumeration requests then receive origin `anonymous_partition_unavailable`, never a `502`, while authenticated and non-snapshot traffic proceeds under its ordinary contract

#### Scenario: unverified direct-origin metadata cannot mint a requester partition

- **WHEN** an anonymous snapshot/enumeration request reaches the origin without authenticated tunnel/front-door provenance, even if it supplies forwarding headers
- **THEN** the origin returns zero rows, `complete=false`, `anonymous_partition_unavailable`, and bounded retry guidance
- **AND** it does not persist raw addresses, mint a caller-selected partition, or change unrelated authenticated/non-snapshot traffic

#### Scenario: SSE bodies stream without buffering

- **WHEN** the tunnel origin returns a `text/event-stream` response
- **THEN** the Worker returns the upstream `ReadableStream` body directly without calling `.text()`/`.json()`/`.arrayBuffer()`

#### Scenario: Tunnel failure surfaces as an explicit 502

- **WHEN** the tunnel origin returns a `5xx` status or is unreachable
- **THEN** the Worker responds `502` with a `bad_gateway` JSON body, never a GoDaddy `404` fallthrough
