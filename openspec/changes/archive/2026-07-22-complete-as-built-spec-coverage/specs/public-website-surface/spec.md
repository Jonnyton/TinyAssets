## ADDED Requirements

### Requirement: The Public Site Ships As A Static Multi-Route Application

The canonical website under `WebSite/site` SHALL build with SvelteKit's static adapter and expose the checked-in public route set, including the home, start, goals, host, wiki, graph, loop, patch-loop, commons, catalog, economy, alliance, contribute, notebook, soul, patterns, fine-print, legal, and account surfaces. Retired `connect`, `status`, and `proof` routes SHALL remain soft-landing aliases that direct visitors to their current destinations rather than becoming dead links. The generated static assets SHALL include the canonical hostname, crawler policy, sitemap, brand marks, and machine-readable `llms.txt` committed with the site.

#### Scenario: A retired proof route is visited

- **WHEN** a visitor opens `/proof` or `/status`
- **THEN** the page explains that operational evidence moved to `/fine-print` and directs the visitor there

#### Scenario: Static production build is requested

- **WHEN** the website build script runs successfully
- **THEN** SvelteKit emits a static application containing the checked-in public routes and assets without requiring a website application server

### Requirement: Public Project Views Distinguish Live Reads From Baked Snapshots

The site SHALL carry baked MCP and repository snapshots for first paint and SHALL label baked values as snapshots. Browser refresh paths SHALL query the public MCP surface and GitHub API, stamp successful reads with their fetch time and source, and retain or disclose the most recent baked/good state when a live read fails. A failed live read MUST be rendered as unavailable or failed evidence and MUST NOT relabel baked counts, universes, goals, repository data, or loop events as live.

#### Scenario: Live host read succeeds

- **WHEN** the host page retrieves the current public universe list
- **THEN** it replaces its visibly stamped baked list with public universes shaped from the live response
- **AND** it displays a live read timestamp

#### Scenario: Live host read fails

- **WHEN** the host page cannot retrieve the public universe list
- **THEN** it identifies the read failure and continues to label any retained list with its snapshot or most-recent-good provenance
- **AND** it does not show the retained data as a current live read

### Requirement: Browser MCP Reads Use The Public Connector Contract

The browser MCP client SHALL use JSON-RPC over HTTP, initialize an MCP session before tool calls, preserve a returned `Mcp-Session-Id`, accept JSON or server-sent-event responses, and retry transient failures up to three total attempts. In local development it SHALL send `/mcp-live` through the Vite proxy to `https://tinyassets.io/mcp`; in production it SHALL use same-origin `/mcp`. Tool calls SHALL prefer object-valued `structuredContent` and MAY parse text content only as a compatibility fallback. Public project reads SHALL use the current consolidated handles and actions rather than presenting snapshot data as a successful connector call.

#### Scenario: Tool response includes structured content

- **WHEN** a browser tool call returns both `structuredContent` and summary text content
- **THEN** the website uses `structuredContent` as the tool result

#### Scenario: Gateway returns an SSE response

- **WHEN** an MCP JSON-RPC request succeeds with `Content-Type: text/event-stream`
- **THEN** the client parses the first `data:` event as the JSON-RPC response while preserving the MCP session identifier

#### Scenario: Gateway is transiently unavailable

- **WHEN** an MCP request returns HTTP 502, 503, or 504 on an early attempt
- **THEN** the client retries with bounded incremental delay and ultimately exposes an error if all three attempts fail

### Requirement: Status And Loop Presentation Keep Distinct Operational Truths

The website SHALL distinguish server reachability from loop activity. Its vital-sign read SHALL require `get_status` and the public universe list to succeed before reporting the server as reachable, while failed goals or extension-run reads SHALL degrade to absent optional evidence. It SHALL derive loop-awake state from an active run, a running queue item, or a run/universe signal within the current one-hour window. Patch-loop presentation SHALL identify its source, warnings, current run/event evidence, and historical-terminal limitations, and SHALL fall back to the checked-in community-loop status or public GitHub monitor evidence when the live extension path has no current run. It MUST NOT collapse a reachable server into a claim that the work loop is moving.

#### Scenario: Server is reachable but no recent work exists

- **WHEN** status and public reads succeed but there is no active run, running queue item, or movement signal within one hour
- **THEN** the site reports the server as reachable and the loop as asleep

#### Scenario: Last extension run is historical

- **WHEN** the most recent patch-loop run is terminal and older than the historical cutoff
- **THEN** the patch-loop feed records that limitation and seeks recent run or community-watch evidence
- **AND** it does not present the old terminal run as active

### Requirement: Host And Install Copy States Current Availability Truthfully

The public host surface SHALL describe the supported source path as Python 3.11+, repository clone, virtual environment, editable install, and the checked-in `tinyassets` or `tinyassets-mcp` entry points. It SHALL state that the Windows tray currently ships from source and that no packaged one-click installer is present in releases. It SHALL identify macOS/Linux tray support as in progress and SHALL identify hosted-cloud signup, pricing, and waitlist as unavailable, routing interest to the public project channel rather than rendering a non-functional signup control.

#### Scenario: Visitor asks for the Windows installer

- **WHEN** a visitor reads the host setup section
- **THEN** the site presents the source clone/install command path and explicitly states that no packaged installer exists yet

#### Scenario: Visitor explores hosted cloud

- **WHEN** a visitor reaches the hosted-cloud section
- **THEN** the site states that there is no signup, waitlist, or pricing flow today and offers the current GitHub request route
- **AND** it does not present hosted capacity as available

### Requirement: Public And Private Indexing Boundaries Are Declared

The site's crawler policy SHALL allow public pages to search and AI-grounding crawlers while disallowing `/account`, `/auth/`, `/editor/`, and `/admin/` from indexing. The sitemap SHALL contain only intended public routes and SHALL use the canonical `https://tinyassets.io` origin. These declarations are advisory web metadata and MUST NOT be treated as authentication or access control for private application surfaces.

#### Scenario: Crawler requests policy

- **WHEN** a crawler reads `/robots.txt`
- **THEN** it receives an allow policy for the public site, explicit exclusions for private route prefixes, and the canonical sitemap location
