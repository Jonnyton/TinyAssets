## RENAMED Requirements

- FROM: `### Requirement: Status And Loop Presentation Keep Distinct Operational Truths`
- TO: `### Requirement: Status And Workflow Presentation Keep Distinct Operational Truths`

## MODIFIED Requirements

### Requirement: The Public Site Ships As A Static Multi-Route Application

The public website SHALL ship as a static multi-route application. The current
production deployment source is the React/Next static export under
`WebSite/site-react`; the SvelteKit tree under `WebSite/site` is the retained
rollback source until a separate approved migration removes or restores it.
Both present trees SHALL expose or preserve the checked-in public route set,
including the home, start, goals, host, wiki, graph, loop, commons, catalog,
economy, alliance, contribute, notebook, soul, patterns, fine-print, legal,
and account surfaces, and both SHALL remain scan-clean so rollback cannot
resurrect the retired product.
The retired `/patch-loop` route SHALL be a static soft landing that explains
task automations are user-authored/remixable designs and directs visitors to
patterns or commons; it MUST NOT load a hidden compatibility application or
status feed. Retired `connect`, `status`, and `proof` routes SHALL remain
soft-landing aliases that direct visitors to their current destinations rather
than becoming dead links. Generated static assets SHALL include the canonical
hostname, crawler policy, sitemap, brand marks, and machine-readable `llms.txt`
committed with the deployed site.

#### Scenario: A retired proof route is visited

- **WHEN** a visitor opens `/proof` or `/status`
- **THEN** the page explains that operational evidence moved to `/fine-print` and directs the visitor there

#### Scenario: Retired patch-loop route is visited

- **WHEN** a visitor opens `/patch-loop`
- **THEN** the page explains that task automations are ordinary user-authored and remixable designs and directs the visitor to generic patterns or commons
- **AND** it loads no community-loop status, workflow, issue, label, or compatibility-loop data

#### Scenario: Static production build is requested

- **WHEN** the website build script runs successfully
- **THEN** the React/Next production tree emits a static application containing the checked-in public routes and assets without requiring a website application server
- **AND** the retained Svelte rollback tree also builds and remains free of retired product behavior

### Requirement: Browser MCP Reads Use The Public Connector Contract

The browser MCP client SHALL use JSON-RPC over HTTP, initialize an MCP session
before tool calls, preserve a returned `Mcp-Session-Id`, accept JSON or
server-sent-event responses, and retry transient failures up to three total
attempts. In local development it SHALL send `/mcp-live` through the Vite proxy
to `https://tinyassets.io/mcp`; in production it SHALL use same-origin `/mcp`.
Tool calls SHALL prefer object-valued `structuredContent` and MAY parse text
content only as a compatibility fallback.

Every browser or snapshot read that can reach a public artifact SHALL run
without caller credentials and SHALL consume only a server-enforced public
projection. If a consolidated handle does not enforce public visibility or
cannot prove bounded collection/body completeness, the website MUST NOT call
that projection as a public read. It SHALL instead retain clearly labelled
checked-in snapshot data or render an explicit unavailable state. Required
snapshot jobs SHALL fail without writing when authentication is configured,
the MCP SDK is unavailable, collection metadata is malformed or ambiguous at
its request cap, or a page body is truncated.

As of the 2026-07-27 exact-head privacy review, anonymous `get_status` and
`read_graph target=goal|goals|run|runs` projections do not meet that boundary
and MUST NOT be called by browser or public-snapshot code. Raw status includes
operator/activity detail that is not a server-enforced public projection.
Among the graph collection/detail targets, only `target=graphs` discovery is
currently proven to apply its server-side visibility boundary. It remains
discovery rather than proof of a complete inventory when the result cap is
reached without pagination. A
`read_page` inventory that explicitly declares `scope=discovery` and carries
an omission note MAY support a discovery-only view when that scope and note
remain visible; it MUST NOT be relabelled as a complete wiki inventory or
replace a full-scope checked-in snapshot. Anonymous exact `read_page` can
currently return known coordination paths omitted from discovery. A public
browser therefore MUST NOT accept arbitrary exact page paths. Any snapshot
body read MUST be provenance-bound to a path returned by the already-validated
inventory for that same refresh, and a full snapshot replacement MUST require
an audience-safe complete inventory rather than discovery scope.
Checked-in Goal data is not self-authenticating: a historical normalizer
defaulting a missing visibility field to `public` is not publication proof.
Every retained Goal row MUST have independent, explicit public-publication
provenance or be removed from every public snapshot mirror and rendered
surface.

#### Scenario: Tool response includes structured content

- **WHEN** a browser tool call returns both `structuredContent` and summary text content
- **THEN** the website uses `structuredContent` as the tool result

#### Scenario: Gateway returns an SSE response

- **WHEN** an MCP JSON-RPC request succeeds with `Content-Type: text/event-stream`
- **THEN** the client parses the first `data:` event as the JSON-RPC response while preserving the MCP session identifier

#### Scenario: Gateway is transiently unavailable

- **WHEN** an MCP request returns HTTP 502, 503, or 504 on an early attempt
- **THEN** the client retries with bounded incremental delay and ultimately exposes an error if all three attempts fail

#### Scenario: A graph projection lacks public visibility enforcement

- **WHEN** `read_graph target=goal|goals|run|runs` can return caller-owned or cross-user private state
- **THEN** browser clients and public snapshot jobs do not call that projection
- **AND** retained checked-in Goal or run data is labelled as snapshot data rather than a live public read

#### Scenario: A checked-in Goal has only normalized visibility

- **WHEN** a Goal snapshot says `visibility=public` but its historical generator could have defaulted a missing value and no independent publication record exists
- **THEN** the Goal is removed from every public snapshot mirror and rendered surface
- **AND** a retained Goal names the independent checked-in public-publication evidence that authorizes it

#### Scenario: Browser initialization sends its completion notification

- **WHEN** a public browser completes MCP session initialization
- **THEN** both the initialize request and `notifications/initialized` request omit browser credentials
- **AND** later public reads cannot inherit cookie-authenticated caller context through that session

#### Scenario: Playground receives an invalid or over-broad result

- **WHEN** a permitted Playground request returns an invalid collection, a non-discovery page scope, missing omission metadata, truncation, or unexpected response fields
- **THEN** the Playground rejects or allowlist-sanitizes the result before rendering parsed, raw, error, or wire views
- **AND** no unvalidated response body is copied into a user-visible trace

#### Scenario: Raw status includes operator detail

- **WHEN** anonymous `get_status` can return activity records, task or worker identifiers, local paths, persona state, cost data, or authentication health
- **THEN** browser clients and the public playground reject that call before network I/O
- **AND** server reachability is derived only from a successful visibility-filtered public projection

#### Scenario: A public graph discovery is requested

- **WHEN** a public browser needs current graph discovery while the unsafe Goal and run projections remain unfixed
- **THEN** it may call only the server-filtered `read_graph target=graphs` projection
- **AND** it does not infer Goal or run visibility from that result

#### Scenario: A public snapshot is given caller credentials

- **WHEN** a snapshot refresh is started with an MCP bearer or other caller credential
- **THEN** it fails before connecting or writing an artifact
- **AND** credential-like URL query or fragment parameters fail before the URL is logged

#### Scenario: A repository snapshot records its public remote

- **WHEN** a public repository snapshot is generated from any local checkout
- **THEN** it records the known canonical public TinyAssets repository URL
- **AND** it never copies a developer-local origin URL, credential, username, host, or filesystem path into the artifact

#### Scenario: A page inventory is explicitly discovery-scoped

- **WHEN** `read_page` returns `scope=discovery` with an explicit note naming omitted coordination content
- **THEN** a discovery-only surface may use the result while preserving that scope and omission note
- **AND** a full-wiki view or snapshot replacement treats it as insufficient

#### Scenario: An anonymous caller supplies a known omitted page path

- **WHEN** a public browser or playground receives `read_page page=<path>` for a path not returned by its validated discovery inventory
- **THEN** its execution boundary rejects the call before network I/O
- **AND** parser or UI restrictions are not treated as the sole enforcement point

#### Scenario: A snapshot reads an exact page body

- **WHEN** a snapshot worker prepares an exact `read_page` call
- **THEN** the requested path must belong to the validated inventory from that refresh
- **AND** discovery scope alone cannot authorize replacing the full checked-in snapshot

#### Scenario: A body or bounded collection cannot prove completeness

- **WHEN** a page body is truncated, completeness metadata is not strict integer data, or a collection exactly fills an unpageable request cap without a cursor or authoritative total
- **THEN** the public read fails closed and preserves the prior labelled snapshot

#### Scenario: A required snapshot cannot load its MCP SDK

- **WHEN** a required snapshot refresh cannot import the MCP SDK
- **THEN** the job exits non-zero before writing and cannot report a successful refresh

### Requirement: Status And Workflow Presentation Keep Distinct Operational Truths

The website SHALL distinguish server reachability, platform uptime evidence,
and user-authored workflow activity. Its vital-sign read SHALL require the
public `read_graph target=graphs` discovery to succeed before reporting the
server as reachable. It MUST NOT fetch raw `get_status` while that response can
include operator or private detail. Goal, run, release, queue, cost, persona,
and authentication-health evidence SHALL remain absent or come from a clearly
labelled checked-in public projection while their live projections are unsafe.
The generic `/loop` presentation MAY derive workflow activity from the
visibility-filtered public universe discovery when it labels that discovery
provenance. It MAY add active run, queue-item, or run-recency signals only after
those fields have a server-enforced public projection and their live/snapshot
provenance is labelled. It MUST NOT present those signals as a privileged
platform loop.

Both production and rollback site trees SHALL remove checked-in
`community-loop-status.json`, all `community_change_context` callers, the homepage
`ChatDemo.svelte` file-to-daemon-to-gates-to-live narrative, community-loop
workflow/label/issue assumptions, patch-loop feeds, and fine-print branding. A
generic platform-uptime snapshot MAY be displayed only when it is produced by
the independently owned uptime/alarm contract and clearly labeled as platform
observation; it MUST NOT be used as evidence that user task work is moving.

#### Scenario: Server is reachable but no recent work exists

- **WHEN** status and public reads succeed but there is no active or recent user-authored workflow signal
- **THEN** the site reports the server as reachable and workflow activity as absent or asleep
- **AND** generic uptime evidence is not relabeled as task-loop movement

#### Scenario: Last extension run is historical

- **WHEN** the most recent user-authored workflow run is terminal and older than the historical cutoff
- **THEN** the site labels it as historical rather than active workflow evidence
- **AND** it does not seek a patch-loop feed, community-watch fallback, or platform-owned task route

#### Scenario: Legacy community-loop fallback is absent

- **WHEN** live workflow activity is unavailable
- **THEN** the site renders unavailable/snapshot truth without reading a community-loop JSON, workflow, label, issue, or patch-loop feed
- **AND** it does not infer a platform-owned automation loop from GitHub monitor evidence

#### Scenario: Production and rollback sources are scan-clean

- **WHEN** website source, static assets, fine print, tests, and build output for the React production tree and Svelte rollback tree are scanned
- **THEN** no shipped community-loop status artifact, patch-loop application, `community_change_context` caller, homepage privileged-loop narrative, workflow/label fallback, or privileged-loop promise remains
- **AND** neither deploy nor rollback can resurrect the retired product
