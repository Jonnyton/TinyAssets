## ADDED Requirements

### Requirement: Distributed connector metadata matches the runtime it delivers
Every distributed connector artifact SHALL declare its middleware-applied
advertised tool catalog or point to the versioned remote surface whose catalog
it delivers. Packaging validation SHALL compare the staged artifact with its
staged runtime and fail when the catalogs differ; schema validity alone SHALL
NOT count as catalog-parity proof.

#### Scenario: MCPB metadata matches its bundled universe server
- **WHEN** the MCPB bundle is staged for validation
- **THEN** the manifest tool-name set equals the result of enumerating the staged `tinyassets.universe_server` with middleware applied
- **AND** both sets equal `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}`
- **AND** hidden legacy fat tools are absent from the declared and advertised sets

#### Scenario: Runtime catalog drift fails packaging validation
- **WHEN** a handle is added to or removed from the bundled runtime without the same catalog change in the staged MCPB manifest
- **THEN** the semantic parity check fails with the missing and extra tool-name sets
- **AND** a schema-only manifest validation cannot make the packaging gate green

### Requirement: Directory artifacts remain bound to the directory-review surface
Artifacts intended for external directory review SHALL describe
`tinyassets.directory_server`, not the broader live/local universe-server
catalog. The MCP Registry remote and ChatGPT submission packet SHALL remain
bound to exactly the five directory handles `read_graph`, `write_graph`,
`run_graph`, `read_page`, and `write_page` unless a separate reviewed change
modifies the directory product.

#### Scenario: Registry metadata resolves to the versioned directory catalog
- **WHEN** the MCP Registry manifest is generated or checked
- **THEN** its remote URL is the current versioned `/mcp-directory/catalog/<version>` URL produced by `directory_mcp_remote_url()`
- **AND** reconciliation of the MCPB manifest does not retarget it to the live `/mcp` endpoint

#### Scenario: ChatGPT packet stays equal to the directory runtime
- **WHEN** the ChatGPT submission packet is validated
- **THEN** its tool-name set and annotations equal the middleware-applied directory runtime catalog
- **AND** `converse`, `get_status`, and every hidden legacy fat tool are absent

### Requirement: External integration guidance identifies the selected connector product
The maintained external integration handoff SHALL identify whether an
integration targets the live/local seven-handle universe-server product or the
five-handle directory-review product before prescribing a URL, tool set, or
authentication flow. It SHALL describe the current deployed cutover and current
WorkOS/OAuth boundary and SHALL NOT instruct integrators to call hidden legacy
fat tools.

#### Scenario: Handoff is refreshed after manifest reconciliation
- **WHEN** an integrator reads the TinyAssets Polsia handoff after this change lands
- **THEN** the handoff states that the live underscore-handle cutover has shipped
- **AND** it separately lists the seven live/local handles and five directory handles
- **AND** its connection/auth guidance reflects the current WorkOS/OAuth boundary
- **AND** stale pre-cutover legacy-action instructions are absent

#### Scenario: Naming-only rename does not satisfy the refresh
- **WHEN** a proposed handoff edit changes `Workflow` identifiers to `TinyAssets` but preserves pre-cutover or pre-WorkOS instructions
- **THEN** the handoff refresh gate fails
- **AND** the edit is not accepted as completion of this change
