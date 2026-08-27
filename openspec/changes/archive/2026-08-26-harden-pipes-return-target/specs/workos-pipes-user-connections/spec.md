## ADDED Requirements

### Requirement: Canonical authorization return target

The connection authorization action MUST send WorkOS Pipes the canonical MCP
return target `https://tinyassets.io/mcp`, regardless of any stale legacy
environment override.

#### Scenario: Stale host override is ignored

- **GIVEN** `WORKOS_PIPES_RETURN_TO` is set to a different URL
- **WHEN** the connection authorization action prepares the WorkOS request
- **THEN** the request uses `https://tinyassets.io/mcp`
