## MODIFIED Requirements

### Requirement: Host-Independent Public Canary And Incident Lifecycle

The platform SHALL run the Layer-1 public uptime control path on GitHub Actions
every five minutes, on manual dispatch, and after every completed `Deploy prod`
workflow (`.github/workflows/uptime-canary.yml`). The probe job SHALL run only
after a successful deploy completion, while the alarm sink SHALL distinguish
the probe result as literal red, literal green, or unknown. The bundle SHALL
probe the canonical MCP handshake, a real tool call, daemon last activity,
sustained revert-loop state, and wiki persistence plus authorization policy.
When `TINYASSETS_WIKI_CANARY_TOKEN` is present in the probe environment, the
wiki sub-probe SHALL attach it only to an exact reserved `write_page` call,
write a fresh per-run marker, require a successful write response for
`drafts/notes/uptime-probe.md`, and then verify that same marker through
anonymous `read_page`. When the credential
is absent or empty, the sub-probe SHALL instead require an anonymous
`write_page` HTTP 401 with a non-empty `WWW-Authenticate` challenge and verify
the previously persisted anonymous-readable draft, so missing CI credentials
alone cannot make the uptime bundle red. A present but rejected credential,
an accepted write to a non-exact path, a read mismatch, an invalid anonymous
challenge, or another HTTP/network failure SHALL remain red with the existing
step-specific diagnostics. The `live-mcp-connector-surface` capability owns the
underlying pre-dispatch challenge protocol; this requirement owns its uptime
evidence and workflow diagnostic propagation. The bundle SHALL combine
executed sub-probes into one red/green result, open a `p0-outage` issue after
two consecutive red runs, append evidence while red, and comment recovery then
close the issue only on literal green. An unavailable, empty, or unrecognized
current result, including a skipped probe after a failed deploy, SHALL be
unknown: the sink SHALL make no label or issue mutation, SHALL not page, and
SHALL complete successfully so unknown cannot become red threshold evidence.
MCP protocol and handle correctness remain owned by
`live-mcp-connector-surface`; this requirement owns probe orchestration and
incident state.

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

#### Scenario: Credentialed wiki write is read back

- **WHEN** the scoped service token is present and the reserved `write_page`
  call reports `drafts/notes/uptime-probe.md`
- **THEN** the wiki sub-probe anonymously reads that page and requires the
  written canary content to match
- **AND** any rejected write, different path, or read mismatch is red

#### Scenario: Missing credential preserves gate and read evidence

- **WHEN** the scoped service token is absent or empty in the canary environment
- **THEN** the wiki sub-probe treats an anonymous `write_page` HTTP 401 with a
  non-empty `WWW-Authenticate` header as green gate evidence
- **AND** it verifies the persisted anonymous-readable canary draft without
  failing solely because the credential is missing
