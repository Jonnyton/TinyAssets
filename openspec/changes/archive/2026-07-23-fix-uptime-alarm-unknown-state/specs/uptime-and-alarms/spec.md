## MODIFIED Requirements

### Requirement: Host-Independent Public Canary And Incident Lifecycle

The platform SHALL run the Layer-1 public uptime control path on GitHub Actions every five minutes, on manual dispatch, and after every completed `Deploy prod` workflow (`.github/workflows/uptime-canary.yml`). The probe job SHALL run only after a successful deploy completion, while the alarm sink SHALL distinguish the probe result as literal red, literal green, or unknown. The bundle SHALL probe the canonical MCP handshake, a real tool call, daemon last activity, sustained revert-loop state, and the wiki anonymous-write gate plus persisted read. It SHALL combine executed sub-probes into one red/green result, open a `p0-outage` issue after two consecutive red runs, append evidence while red, and comment recovery then close the issue only on literal green. An unavailable, empty, or unrecognized current result, including a skipped probe after a failed deploy, SHALL be unknown: the sink SHALL make no label or issue mutation, SHALL not page, and SHALL complete successfully so unknown cannot become red threshold evidence. MCP protocol and handle correctness remain owned by `live-mcp-connector-surface`; this requirement owns probe orchestration and incident state.

#### Scenario: Second consecutive red opens a durable incident

- **WHEN** the combined Layer-1 bundle is red and the prior completed uptime-canary run also failed
- **THEN** the alarm sink opens one GitHub issue labeled `p0-outage` with the probe exit and output
- **AND** subsequent red ticks append evidence to that open issue instead of creating a parallel incident

#### Scenario: Green closes the incident

- **WHEN** the combined Layer-1 bundle is literally green while a `p0-outage` issue is open
- **THEN** the alarm sink appends a `GREEN — RECOVERED` record and closes the issue as completed

#### Scenario: Unknown result preserves incident state

- **WHEN** the probe result is unavailable, empty, or unrecognized, including when a failed `Deploy prod` completion skips the probe job
- **THEN** the alarm sink records an Actions warning and summary without creating or querying labels or issues, without paging, and without failing the canary workflow
- **AND** an open `p0-outage` issue remains open until a literal green result is observed

#### Scenario: Downstream sub-probes respect upstream health

- **WHEN** the MCP handshake or real-tool probe fails
- **THEN** dependent activity, revert-loop, and wiki probes are skipped where they cannot produce meaningful evidence
- **AND** the upstream failure keeps the combined result red
