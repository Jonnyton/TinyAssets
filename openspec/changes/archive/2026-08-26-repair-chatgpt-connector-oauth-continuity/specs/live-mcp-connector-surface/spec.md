## ADDED Requirements

### Requirement: Authenticated chatbot connector continuity

The remote MCP connector SHALL remain usable for authenticated calls after an
MCP-compatible chatbot completes OAuth authorization or reconnect, including
standards-based token refresh or reauthorization when required. The continued
session SHALL address the same authenticated TinyAssets account and authorized
universe, and SHALL require no personal computer, local credential broker, or
maintainer intervention.

#### Scenario: reconnect leads to an authenticated tool call
- **WHEN** a chatbot reconnects TinyAssets, completes authorization, and initializes the MCP session
- **THEN** its next authenticated tool call succeeds rather than receiving `401 invalid_token`
- **AND** the call is attributed to the authorized TinyAssets subject

#### Scenario: later call preserves authenticated identity
- **WHEN** the chatbot makes a later call after continuing, refreshing, or reauthorizing the connector session
- **THEN** the call reaches the same authenticated account and authorized universe
- **AND** no personal computer or local credential process is required

#### Scenario: connector continuity gates user-owned cloud automation
- **WHEN** a user prepares an ordinary cloud Branch that binds their authorized GitHub repository to their own delivery spec
- **THEN** activation is blocked until the user can inspect and control it through a rendered authenticated chatbot connector sequence
- **AND** direct MCP probes or local CLI access alone do not satisfy the gate
