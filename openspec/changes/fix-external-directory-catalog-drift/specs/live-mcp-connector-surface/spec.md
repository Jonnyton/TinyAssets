## ADDED Requirements

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
- **THEN** a read-only request to its remote URL succeeds and returns the current versioned directory catalog
