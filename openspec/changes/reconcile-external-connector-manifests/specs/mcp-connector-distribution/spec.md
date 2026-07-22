## ADDED Requirements

### Requirement: Distribution preserves three connector product contracts
TinyAssets connector metadata and maintained integration guidance SHALL model
three products separately: the remote live `/mcp` connector, the local MCPB
package, and the remote directory-review surface. Equality between handle
names or schemas SHALL NOT imply equivalent transport, authentication, actor
resolution, configuration, storage, deployment, authority, or acceptance.

#### Scenario: Remote live connector is identified
- **WHEN** metadata or guidance describes the live connector
- **THEN** it identifies `tinyassets.universe_server` over Streamable HTTP at `https://tinyassets.io/mcp`
- **AND** its advertised set is exactly `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}`
- **AND** it describes the deployed WorkOS/OAuth resource-server boundary, anonymous reads, and identity-gated write/costly/admin calls
- **AND** it identifies `write_graph`, `run_graph`, `write_page`, and `converse` as the registered pre-dispatch anonymous-write challenges

#### Scenario: Local MCPB package is identified
- **WHEN** metadata or guidance describes the MCPB package
- **THEN** it identifies the staged `tinyassets.universe_server` launched by `packaging/mcpb/server.py` over local stdio
- **AND** its advertised set is the same seven names as the remote live connector without claiming other product equivalence
- **AND** it states the package's local configuration and current dev/no-auth posture

#### Scenario: Remote directory-review surface is identified
- **WHEN** metadata or guidance describes a Registry or ChatGPT directory artifact
- **THEN** it identifies `tinyassets.directory_server` over Streamable HTTP at the mounted `/mcp-directory` surface or current versioned `/mcp-directory/catalog/<version>` URL
- **AND** its advertised set is exactly `{read_graph, write_graph, run_graph, read_page, write_page}`
- **AND** `converse`, `get_status`, hidden legacy fat tools, and catch-all `action` inputs are absent
- **AND** status is served through `read_graph(target=status)` with directory-safe redaction
- **AND** its auth behavior is documented from observed per-handle behavior rather than inferred from either seven-handle product

### Requirement: Local MCPB metadata matches the staged runtime it delivers
The MCPB artifact SHALL declare the middleware-applied advertised catalog of
the staged runtime it launches over stdio. Packaging validation SHALL stage the
normal artifact, enumerate that staged runtime, and fail when the catalogs
differ; schema validity alone SHALL NOT count as catalog-parity proof.

#### Scenario: MCPB metadata matches its bundled universe server
- **WHEN** the MCPB bundle is staged for validation
- **THEN** the manifest tool-name set equals the result of enumerating the staged `tinyassets.universe_server` with middleware applied
- **AND** both sets equal `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}`
- **AND** hidden legacy fat tools are absent from the declared and advertised sets

#### Scenario: Runtime catalog drift fails packaging validation
- **WHEN** a handle is added to or removed from the bundled runtime without the same catalog change in the staged MCPB manifest
- **THEN** the semantic parity check fails with the missing and extra tool-name sets
- **AND** a schema-only manifest validation cannot make the packaging gate green

### Requirement: The MCPB is a local stdio product with explicit configuration and auth posture
The MCPB SHALL launch the staged `tinyassets.universe_server` through
`packaging/mcpb/server.py` over stdio. Its manifest SHALL require a
user-selected `tinyassets_data_dir` mapped to `TINYASSETS_DATA_DIR` and MAY
accept `default_universe` mapped to `UNIVERSE_SERVER_DEFAULT_UNIVERSE`. The
current manifest SHALL NOT be described as WorkOS/OAuth-backed: it neither
exposes nor sets `UNIVERSE_SERVER_AUTH`, so the runtime's unset default selects
`DevAuthProvider` and relies on the local host/process boundary. Changing that
posture requires a separate reviewed auth/package change.

#### Scenario: Configured local package launches over stdio
- **WHEN** an MCPB-compatible host installs the package with an existing isolated data directory and optionally supplies a default universe
- **THEN** the host launches `uv run --project ${__dirname} ${__dirname}/server.py`
- **AND** the wrapper validates and exports the selected data directory, preserves optional default-universe configuration, and invokes `universe_server.main(transport="stdio")`
- **AND** the client enumerates exactly the seven declared handles

#### Scenario: Missing required data directory fails closed
- **WHEN** the local MCPB launcher receives an empty, missing, or non-directory `TINYASSETS_DATA_DIR`
- **THEN** it fails before starting the MCP transport with an actionable configuration error
- **AND** it does not silently fall back to a maintainer or platform data directory

#### Scenario: Catalog presence does not claim functional identity parity
- **WHEN** the current MCPB starts with its manifest-provided configuration and no independently supplied auth mode
- **THEN** the runtime selects `DevAuthProvider`
- **AND** a `converse` call without a resolved actor returns `auth_required`
- **AND** package metadata does not promise WorkOS sign-in, remote OAuth challenges, remote user isolation, or functional parity merely because `converse` is listed

### Requirement: Directory artifacts remain bound to the remote directory-review surface
The MCP Registry remote and ChatGPT submission packet SHALL describe
`tinyassets.directory_server` and remain bound to exactly the five reviewed
directory handles unless a separate reviewed change modifies that product.

#### Scenario: Registry metadata resolves to the versioned directory catalog
- **WHEN** the MCP Registry manifest is generated or checked
- **THEN** its remote URL is the current versioned `/mcp-directory/catalog/<version>` URL produced by `directory_mcp_remote_url()`
- **AND** MCPB reconciliation does not retarget it to `/mcp` or a local package

#### Scenario: ChatGPT packet stays equal to the directory runtime
- **WHEN** the ChatGPT submission packet is validated
- **THEN** its tool-name set and annotations equal the middleware-applied directory runtime catalog
- **AND** `converse`, `get_status`, and every hidden legacy fat tool are absent

#### Scenario: Directory auth is not generalized from the live connector
- **WHEN** directory authentication behavior is documented or accepted
- **THEN** the evidence records that the directory surface inherits the remote app's configured bearer-resolution/write-gate middleware
- **AND** it records that missing-token directory calls are excluded from the live connector's registered pre-dispatch OAuth-challenge path
- **AND** it does not promise `/mcp`-equivalent OAuth UX without rendered evidence

### Requirement: Product acceptance evidence is non-substitutable
Each connector product SHALL be accepted through its own transport, host, auth,
configuration, and user path. Evidence from one product SHALL NOT satisfy an
acceptance gate for another.

#### Scenario: Remote live connector acceptance
- **WHEN** the remote `/mcp` product is accepted
- **THEN** evidence includes a Streamable-HTTP handshake, exact-seven enumeration, anonymous read, OAuth challenge plus signed-in write or `converse`, and applicable rendered chatbot proof
- **AND** post-change clean-use evidence is recorded or explicitly left unproven as a watch item

#### Scenario: Local MCPB acceptance
- **WHEN** the local package is accepted
- **THEN** an MCPB-compatible host installs and launches the changed artifact over stdio with an isolated temporary data directory
- **AND** evidence covers official schema validation, exact-seven enumeration, required and optional configuration wiring, observed auth posture, and safe usable local operations
- **AND** catalog listing alone does not conceal an unusable canonical operation such as actorless `converse`
- **AND** no remote canary is treated as installed-package proof

#### Scenario: Remote directory acceptance
- **WHEN** the directory product is accepted
- **THEN** evidence covers deterministic Registry generation, ChatGPT packet/runtime name-and-annotation parity, directory status redaction, the versioned endpoint, and applicable rendered directory-host behavior under observed auth
- **AND** no MCPB or `/mcp` proof is substituted for that evidence

### Requirement: Connector acceptance never consumes maintainer compute
The package, metadata, and acceptance suite SHALL NOT provide or consume a
maintainer/platform model, provider account, credential, quota, or compute for
user workloads. Catalog, launch, configuration, read, and auth-failure proofs
SHALL make zero provider calls. Any future acceptance that executes model work
SHALL use a complete requester-owned BYOC authority bundle or an accepted-market
compute/model grant; absent that authority it SHALL return held/setup-required
with zero provider invocation.

#### Scenario: Local converse limitation is tested without maintainer resources
- **WHEN** the current actorless MCPB `converse` behavior is verified
- **THEN** the call returns `auth_required` before provider selection or invocation
- **AND** no maintainer credential, personal Claude/OpenAI quota, or platform-funded compute is used

### Requirement: External integration guidance identifies the selected connector product
The maintained Polsia handoff SHALL contain a source-linked three-row product
matrix before prescribing an endpoint, transport, tool set, authentication,
configuration, or acceptance flow. It SHALL describe the current underscore
handle cutover and SHALL NOT instruct integrators to call hidden legacy fat
tools.

#### Scenario: Handoff is refreshed after manifest reconciliation
- **WHEN** an integrator reads the TinyAssets Polsia handoff after this change lands
- **THEN** it contains distinct rows for remote `/mcp`, local MCPB, and the remote versioned directory surface
- **AND** each row states its transport/location, exact advertised catalog, authentication/configuration posture, and product-specific acceptance evidence
- **AND** stale pre-cutover, pre-WorkOS, and legacy-action instructions are absent

#### Scenario: Naming-only rename does not satisfy the refresh
- **WHEN** a proposed handoff edit changes `Workflow` identifiers to `TinyAssets` but preserves stale technical instructions
- **THEN** the handoff refresh gate fails
- **AND** the edit is not accepted as completion of this change

#### Scenario: Shared handle names do not collapse remote and local products
- **WHEN** guidance calls the MCPB OAuth-backed, uses a remote canary as MCPB proof, or combines remote `/mcp` and MCPB because both advertise seven names
- **THEN** the handoff refresh gate fails
- **AND** the guidance must be corrected to the observed contract of each product

### Requirement: Legacy live-tool retirement waits for distribution readiness
Removal of hidden legacy registrations from `tinyassets.universe_server` SHALL
remain blocked until this distribution change lands, installed MCPB acceptance
exists, supported local-host migration evidence is recorded, and the MCPB
identity/authority limitation is either resolved or deliberately redesigned
and scoped. Remote telemetry proves only remote caller migration and SHALL NOT
stand in for local package evidence.

#### Scenario: Shared runtime retirement affects the next local bundle
- **WHEN** a later change proposes removing legacy registrations from `tinyassets.universe_server`
- **THEN** review records that the same source is staged into the MCPB package
- **AND** the retirement rebuilds and tests the staged bundle rather than referring to a nonexistent checked-in runtime mirror
- **AND** retirement remains blocked while required local product evidence or authority design is absent
