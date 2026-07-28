# public-website-surface Specification

## Purpose
Define the static public website's route, live-versus-snapshot provenance, browser MCP, operational presentation, install-copy, and indexing contracts.
## Requirements
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

### Requirement: Hosted Preview Source Pipeline Preserves The Untrusted-Build Boundary

The hosted React preview source pipeline SHALL execute pull-request-controlled
install, test, and build commands only in an unprivileged workflow with
read-only repository permission, no persisted checkout credential, and no
deployment secret. A separate exact-trusted-default-branch workflow SHALL
perform secretless provenance validation and artifact sanitization before a
fresh protected-environment job can receive any Cloudflare credential. When
separately activated, the credentialed job MUST consume only the normalized
static tree and matching deterministic manifest, MUST independently regenerate
and byte-compare that manifest before computing the published SHA-256 from the
regenerated manifest bytes, MUST NOT execute artifact content, and SHALL use
fixed trusted Worker code, Worker name, Wrangler configuration, exact action
revisions, lockfile-pinned Wrangler, and a dedicated preview-only account
credential. Credentialed publication MUST remain disabled until
`activate-hosted-preview-publication` records accepted external isolation proof.

#### Scenario: Pull-request code builds a preview candidate

- **WHEN** a pull request changes site source, dependencies, package scripts, or the unprivileged build workflow
- **THEN** those changes execute without Cloudflare secrets, repository-write or deployment permission, persisted checkout credentials, a persisted/shared cache that crosses the trust boundary, or a shared credentialed runner workspace
- **AND** the workflow uploads only one short-lived attempt-specific static-export candidate

#### Scenario: Any pull request changes repository source

- **WHEN** any pull request is opened, reopened, or synchronized, including one that does not match the hosted-preview build paths
- **THEN** an unfiltered read-only check runs the parsed trust-boundary contract and all preview validator fixtures
- **AND** branch protection can require that check without waiting for a path-filtered workflow that never starts

#### Scenario: A successful same-repository build enters trusted intake

- **WHEN** the trusted-default-branch workflow observes a successful pull-request build
- **THEN** its secretless intake verifies the exact workflow ID/path, repository, one open default-branch pull request, current same-repository head, run attempt, and one non-expired artifact ID with reported size no larger than 25 MiB before retrieval
- **AND** it downloads only that artifact ID from that workflow run
- **AND** it does not present the artifact API's reported digest as independently verified byte provenance
- **AND** platform extraction remains in the secretless time-bounded job before repository entry/directory/depth/path/expanded-byte limits apply

#### Scenario: Intake receives a hostile or malformed artifact

- **WHEN** the artifact contains a symbolic link, hard link, special entry, unsafe or colliding path, literal percent in a path component, file with executable mode bits, package/deployment control, archive-extension file, unexpected extension, missing static-export root, or file/directory/entry/depth/path/expanded-size excess
- **THEN** intake rejects it before any protected environment or Cloudflare credential is loaded
- **AND** it does not execute or copy the rejected entry
- **AND** the exact limits are 10,000 files, 2,000 directories, 12,000 total entries, depth 32, 512 Unicode characters and 1,024 UTF-8 bytes per relative path, 25 MiB per file, and 250 MiB expanded total
- **AND** a valid root contains `index.html`, `404.html`, and `_next/static`

#### Scenario: Intake receives a valid static export

- **WHEN** every candidate entry satisfies the bounded static-file contract
- **THEN** intake copies only regular bytes into a clean tree without execution and emits a sorted SHA-256 manifest
- **AND** intake does not claim that an API-reported artifact digest independently verifies the copied bytes
- **AND** the fresh credentialed job independently revalidates the tree, regenerates the manifest, requires a byte-identical match, then computes the published SHA-256 from those regenerated manifest bytes before staging trusted deployment code

#### Scenario: A sanitized current preview is published

- **WHEN** a separately accepted activation receipt exists and the pull request remains open at the exact validated same-repository head
- **THEN** the protected job installs the exact lockfile-pinned toolchain without lifecycle scripts and uploads an undeployed Worker version under a DNS-bounded base-36 alias derived from PR number, run ID, and attempt
- **AND** it does not deploy that version to shared traffic, create a production route or domain, or use a production-account credential
- **AND** trusted code rejects missing, duplicated, malformed, control-bearing, cross-worker, or cross-subdomain upload receipts before exporting any provider identity
- **AND** a separate least-privilege job rechecks the head before posting the provider-generated immutable version URL, never-reused alias URL, full head SHA, run/attempt, exact source artifact ID, verified sanitized-manifest SHA-256, and Cloudflare version ID
- **AND** a later platform run cannot reuse the run/attempt alias, and the provider-generated version URL remains byte-immutable

#### Scenario: A pull-request head is stale at the pre-upload recheck

- **WHEN** the open pull request no longer has the exact head validated by secretless intake when the pre-upload recheck runs
- **THEN** the protected job fails before starting the credential-bearing upload step
- **AND** no stale preview URL is posted as current review evidence

#### Scenario: A pull-request head changes during publication

- **WHEN** the pull-request head changes after the pre-upload recheck races with an already-starting upload
- **THEN** any resulting upload uses a never-reused alias and immutable version URL, so it cannot repoint earlier evidence
- **AND** the independent comment job rechecks the current head and does not advertise the raced upload as current

#### Scenario: Preview JavaScript requests a blocked service path

- **WHEN** the isolated preview receives a path that canonically equals `/mcp` or a descendant, enters `/.well-known/oauth-*`, `/.well-known/openid-*`, or `/.well-known/mcp*`, or cannot be safely canonicalized after bounded escape decoding, slash normalization, dot-segment handling, trailing-dot or space stripping, and case folding
- **THEN** the exact trusted Worker runs before asset lookup and returns a no-store `503`
- **AND** a shadowing static `mcp` asset cannot bypass the Worker
- **AND** it neither proxies nor embeds the production MCP origin
- **AND** other canonical requests fall through to the static asset binding

#### Scenario: A fork build completes

- **WHEN** a preview build originates from a fork
- **THEN** build and test evidence may complete without secrets
- **AND** no credentialed public preview publication runs

#### Scenario: The source bootstrap lands before external activation

- **WHEN** this source bootstrap is merged without an accepted `activate-hosted-preview-publication` receipt
- **THEN** the GitHub preview environment holds no publication credential
- **AND** no credentialed hosted preview is accepted as active or proven
- **AND** the successor change and STATUS host-action remain open
