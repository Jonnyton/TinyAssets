## MODIFIED Requirements

### Requirement: Release reads use the named canary principal

`GET /mcp/pulse` SHALL require a valid user bearer or the canary bearer and SHALL
return `git_sha`, `image_tag`, `deployed_at` and `uptime_seconds`. The first three
fields come from the mutable release receipt, with empty strings when absent;
uptime is elapsed since app construction, not process birth or container start.
The response SHALL name no universe, user or run. The deploy gate
(`scripts/deployed_sha.py`) reads it with the canary bearer. Public website
clients SHALL NOT call it without a signed-in user's bearer.

Only the already-resolved canary principal MAY additionally receive
`platform_runtime_provenance`: a bounded sanitized peek of the answering
process's cached startup observation. This peek SHALL NOT resolve metadata,
initialize the cache or upgrade a refusal. Missing or PID-inherited observations
SHALL remain unknown. The field SHALL carry only defined verdict/reason/mode
tokens and typed observation booleans, never identifiers, addresses, paths,
credentials or user-authored content. Its absence SHALL mean unknown, not cloud
acceptance. Ordinary authenticated callers SHALL retain exactly the four base
fields. No new principal or permission is granted.

The provenance readback SHALL NOT establish binary freshness from the mutable
receipt, container incarnation from uptime, all-worker coverage, attestation,
custody or enforced admission. The optional diagnostic in the deploy gate SHALL
reuse its existing pulse response and leave receipt-assertion exit semantics
unchanged; unknown provenance is not a pass of cloud-only acceptance.

#### Scenario: the deploy gate reads production's sha
- **WHEN** `GET /mcp/pulse` is requested with the canary bearer
- **THEN** the response is HTTP 200 carrying the four base fields and nothing a user authored
- **AND** an optional provenance field reports only the answering process's cached observation

#### Scenario: an ordinary signed-in user reads pulse
- **WHEN** a valid non-canary user bearer requests pulse
- **THEN** the response contains exactly the four base fields and no provenance field

#### Scenario: provenance has not been observed in this process
- **WHEN** the canary reads pulse before observation or after inheriting a parent cache
- **THEN** provenance is unknown without a metadata read or cache initialization

#### Scenario: an unsigned browser requests pulse
- **WHEN** `GET /mcp/pulse` is requested without a bearer
- **THEN** the response is the OAuth 401 challenge and no release fields are returned

#### Scenario: a deeper path is not exempt
- **WHEN** `GET /mcp/pulse/extra` is requested with no bearer
- **THEN** the response is the 401 challenge
