## MODIFIED Requirements

### Requirement: Bearer JWT validation is fail-closed, RS256-pinned, and audience-bound

When resolving a WorkOS bearer token the server SHALL pin the accepted signature algorithm to
RS256 (defending against algorithm-substitution), bind validation to the AuthKit issuer, require
the `exp` and `sub` claims, and reject any token whose subject is missing or `anonymous`. Audience
binding to the registered MCP resource indicator (`WORKOS_MCP_RESOURCE`) SHALL be required by
default; construction fails closed when it is absent. A token produced by a completed authorization
or reconnect for the advertised MCP resource SHALL be accepted when it satisfies those checks, and
subsequent refreshed authorization SHALL preserve the same validation boundary. Token resolution
logic lives in `tinyassets/auth/workos_provider.py`. As-built limitation: audience validation may
be disabled only by explicitly setting `WORKOS_ALLOW_NO_AUDIENCE` truthy, which is intended for
local/dev use and logs a warning; production must leave it unset.

#### Scenario: a same-issuer token without required claims is rejected
- **WHEN** a bearer token is signed by the issuer but lacks a valid `sub` or `exp`
- **THEN** token resolution returns no identity and the caller is treated as anonymous

#### Scenario: audience binding is required in production configuration
- **WHEN** the WorkOS provider is constructed without `WORKOS_MCP_RESOURCE` and without the dev opt-out
- **THEN** construction fails closed rather than accepting any same-issuer token

#### Scenario: authorized resource token is accepted
- **WHEN** a connector completes authorization or reconnect for the advertised MCP resource and presents an unexpired RS256 token with the configured issuer, exact audience, and required claims
- **THEN** token resolution returns the authenticated subject
- **AND** the caller is not downgraded to anonymous

#### Scenario: refreshed token retains the same boundary
- **WHEN** the connector refreshes or reauthorizes an authenticated session
- **THEN** the replacement token is accepted only when it satisfies the same algorithm, issuer, audience, expiry, and subject requirements

## ADDED Requirements

### Requirement: Token validation failures expose only a sanitized category

The WorkOS resource server SHALL emit an operationally visible, allowlisted
validation-failure category for a rejected bearer token while excluding the
token, JWT headers and payload, exception message, claim values, and
user-identifying data from logs and responses.

#### Scenario: audience failure is diagnosable without token disclosure
- **WHEN** a bearer token is rejected for an audience mismatch
- **THEN** production telemetry records the stable `audience` failure category
- **AND** neither the bearer token nor any claim value is recorded

#### Scenario: malformed token remains non-oracular to the caller
- **WHEN** a malformed bearer token is rejected
- **THEN** the caller receives the standard `401 invalid_token` response
- **AND** internal telemetry records only an allowlisted failure category
