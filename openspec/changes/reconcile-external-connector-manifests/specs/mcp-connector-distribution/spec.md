## ADDED Requirements

### Requirement: Distribution Preserves Two Connector Product Contracts
TinyAssets connector metadata and maintained integration guidance SHALL model
two products separately: canonical remote `/mcp` and the local MCPB package.
Equality between handle names SHALL NOT imply equivalent transport,
authentication, actor resolution, configuration, storage, deployment,
authority, or acceptance.

#### Scenario: Canonical remote product is identified
- **WHEN** metadata or guidance describes hosted TinyAssets
- **THEN** it identifies `tinyassets.universe_server` over Streamable HTTP at `https://tinyassets.io/mcp`
- **AND** its advertised set is exactly `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}`
- **AND** it describes the deployed WorkOS/OAuth boundary, permitted anonymous reads, and identity-gated mutation/cost/private operations

#### Scenario: Local MCPB product is identified
- **WHEN** metadata or guidance describes the MCPB package
- **THEN** it identifies the staged `tinyassets.universe_server` launched by `packaging/mcpb/server.py` over local stdio
- **AND** its advertised set is the same seven names without claiming other product equivalence
- **AND** it states the package's required local configuration and observed local auth posture

#### Scenario: No third remote product is advertised
- **WHEN** current Registry, hosted-chatbot, website, or integration metadata is generated
- **THEN** it does not advertise `/mcp-directory`, a versioned descendant, or `tinyassets.directory_server`
- **AND** review-safe behavior is provided by canonical `/mcp`

### Requirement: Local MCPB Metadata Matches The Staged Runtime
The MCPB artifact SHALL declare the middleware-applied advertised catalog of
the staged runtime it launches over stdio. Packaging validation SHALL stage the
normal artifact, enumerate that staged runtime, and fail when catalogs differ;
schema validity alone SHALL NOT count as catalog-parity proof.

#### Scenario: MCPB metadata matches its bundled universe server
- **WHEN** the MCPB bundle is staged for validation
- **THEN** its declared set equals the middleware-applied staged runtime set
- **AND** both equal the canonical seven handle names
- **AND** hidden legacy fat tools are absent

#### Scenario: Runtime catalog drift fails packaging validation
- **WHEN** a handle changes in the bundled runtime without the same staged manifest change
- **THEN** semantic parity validation fails with missing and extra sets
- **AND** schema-only validation cannot make the packaging gate green

### Requirement: MCPB Is A Local Stdio Product With Explicit Configuration
The MCPB SHALL launch the staged server over stdio, require a user-selected
`tinyassets_data_dir` mapped to `TINYASSETS_DATA_DIR`, and MAY accept
`default_universe` mapped to `UNIVERSE_SERVER_DEFAULT_UNIVERSE`. It SHALL NOT
be described as WorkOS/OAuth-backed unless a separate reviewed package change
implements that boundary.

#### Scenario: Configured package launches locally
- **WHEN** a compatible host installs the package with an isolated existing data directory
- **THEN** the wrapper validates and exports configuration before starting stdio
- **AND** the client enumerates the seven declared handles

#### Scenario: Missing data directory fails closed
- **WHEN** the configured data directory is empty, missing, or not a directory
- **THEN** launch fails with an actionable error before MCP transport starts
- **AND** no maintainer or platform directory is selected

#### Scenario: Catalog presence does not claim identity parity
- **WHEN** MCPB advertises the same names as hosted `/mcp`
- **THEN** metadata does not promise remote OAuth, hosted isolation, or functional identity parity
- **AND** observed actor-dependent limitations remain explicit

### Requirement: Remote Distribution Binds To Canonical MCP
The platform MUST bind MCP Registry metadata, ChatGPT and Claude submission
artifacts, maintained remote client packs, and current integration guidance to
`https://tinyassets.io/mcp` and its exact seven-handle runtime contract. The
user-facing product, connector, app, and Registry display name SHALL be exactly
`TinyAssets`; environment labels such as `DEV`, `development`, or `staging`
SHALL NOT appear in the public product name.

#### Scenario: Public registrations use one durable name
- **WHEN** any current or generated remote registration artifact is validated
- **THEN** its user-facing name is exactly `TinyAssets`
- **AND** no public name contains `DEV`, `development`, `staging`, or another lifecycle qualifier

#### Scenario: Registry metadata resolves to canonical MCP
- **WHEN** the Registry manifest is generated for the migration release
- **THEN** its remote URL is `https://tinyassets.io/mcp`
- **AND** the manifest version is advanced so clients can observe the change
- **AND** Registry API proof confirms the published current version resolves to that URL

#### Scenario: Hosted-chatbot packets match canonical runtime
- **WHEN** ChatGPT or Claude metadata is validated
- **THEN** its tool names, schemas, security schemes, annotations, and descriptions match middleware-applied canonical `/mcp`
- **AND** all seven handles are represented
- **AND** submission tests and reviewer instructions exercise the observed OAuth and privacy contract

#### Scenario: Historical evidence is preserved
- **WHEN** maintainers update current guidance from `/mcp-directory` to `/mcp`
- **THEN** dated proofs, audits, archived changes, and historical worktree records retain the endpoint they actually tested
- **AND** a new superseding current artifact or note carries the migrated truth

### Requirement: Product Acceptance Evidence Is Non-Substitutable
Each product SHALL be accepted through its own transport, host, auth,
configuration, and user path. Evidence from one product SHALL NOT satisfy
another product's gate.

#### Scenario: Canonical remote acceptance
- **WHEN** hosted `/mcp` is accepted
- **THEN** evidence includes Streamable-HTTP handshake, exact-seven enumeration, safe status projection, neutral instructions, metadata/runtime OAuth agreement, anonymous read, and authenticated mutation
- **AND** rendered ChatGPT and Claude conversations, Registry resolution, supported-client migration, and concurrency evidence are recorded
- **AND** post-change clean use is recorded or retained as an explicit watch item without being misrepresented as proven

#### Scenario: Local MCPB acceptance
- **WHEN** the local package is accepted
- **THEN** a compatible host installs and launches the changed artifact over stdio with an isolated data directory
- **AND** evidence covers schema, exact-seven enumeration, configuration wiring, observed auth posture, and provider-free usable operations
- **AND** remote canaries or OAuth proof do not substitute

### Requirement: Directory Route Removal Waits For Proven Migration
`/mcp-directory` and every versioned descendant SHALL remain temporary only
until canonical review-safety and supported-consumer migration gates pass.
After those gates, directory runtime code, mounts, catalog constants,
discovery metadata, Worker routing, and current operational guidance SHALL be
removed together. No redirect, proxy alias, or silent translation SHALL remain.

#### Scenario: Supported consumers migrate before removal
- **WHEN** route retirement is proposed
- **THEN** the MCP Registry current version is published and resolves to `/mcp`
- **AND** each maintained OpenAI and Claude registration points to canonical `/mcp`, or is removed/reclassified by the predeclared dated disposition
- **AND** each external review records its current accepted, published, pending, unavailable, rejected, or withdrawn state without making an unbounded vendor wait a route-retirement gate
- **AND** a pending or unavailable review proceeds past the cutover gate after its predeclared decision date records the registration as pending, unavailable, withdrawn, or unsupported
- **AND** current Codex, Cursor, Open WebUI, LibreChat, and every other maintained supported configuration has a recorded `/mcp` disposition
- **AND** supported consumers have current proof or are explicitly reclassified as read-only/unsupported
- **AND** a predeclared telemetry window records start, end, evidence source, and zero unexplained maintained callers
- **AND** the 2026-07-24 host directive supplies standing cutover authorization once these objective gates pass, without a second discretionary approval

#### Scenario: Removed route is not a shim
- **WHEN** retirement lands
- **THEN** `/mcp-directory*` has no mounted MCP server or catalog
- **AND** requests receive the normal absent-route response
- **AND** the edge does not redirect or proxy them to `/mcp`

### Requirement: Connector Acceptance Never Consumes Maintainer Compute
Package, metadata, and acceptance work SHALL NOT provide or consume a
maintainer/platform model, provider credential, quota, or compute for user
workloads. Model execution requires requester BYOC or an accepted-market grant;
without it the operation remains held/setup-required with zero provider calls.

#### Scenario: Auth and catalog proof is provider-free
- **WHEN** catalogs, redaction, auth challenges, launch, or migration are tested
- **THEN** no provider is selected or invoked
- **AND** no maintainer credential or personal Claude/OpenAI limit is used

### Requirement: External Guidance Identifies The Selected Product
Maintained integration guidance SHALL contain a source-linked two-row product
matrix before prescribing endpoint, transport, tool set, authentication,
configuration, or acceptance. It SHALL not instruct integrators to call hidden
legacy tools or the retired directory route.

#### Scenario: Handoff is refreshed
- **WHEN** an integrator reads the current TinyAssets handoff
- **THEN** it contains distinct rows for remote `/mcp` and local MCPB
- **AND** each row states transport, catalog, auth/configuration, and acceptance
- **AND** stale pre-cutover, pre-WorkOS, `/mcp-directory`, and legacy-action instructions are absent

#### Scenario: Naming-only edit does not satisfy refresh
- **WHEN** a change renames Workflow to TinyAssets but preserves stale technical instructions
- **THEN** the guidance gate fails

### Requirement: Legacy Live-Tool Retirement Waits For Distribution Readiness
Removal of hidden legacy registrations SHALL remain blocked until this
distribution change lands, installed MCPB acceptance exists, supported local
host migration evidence is recorded, and local identity limitations are
resolved or deliberately redesigned. Remote telemetry SHALL NOT substitute for
local package evidence.

#### Scenario: Shared runtime retirement affects the next local bundle
- **WHEN** a later change removes hidden registrations from `universe_server`
- **THEN** it rebuilds and tests the staged MCPB
- **AND** retirement remains blocked while required local evidence is absent
