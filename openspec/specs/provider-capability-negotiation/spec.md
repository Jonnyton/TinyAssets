# Provider Capability Negotiation

## Purpose

Declare, validate, discover, and revoke bounded auxiliary capabilities on an existing user-owned provider connection without creating credential authority or changing provider routing.

## Requirements

### Requirement: Auxiliary capability declarations reuse existing provider authority
TinyAssets SHALL let an authenticated universe owner declare or revoke bounded, non-secret auxiliary capability metadata on the exact connection and grant currently powering that universe, without creating credential authority or changing provider routing.

#### Scenario: Owner declares realtime Voice on the current provider
- **GIVEN** the founder's current serving provider resolves to an active user-owned HTTP connection and universe grant
- **WHEN** the founder declares a `realtime_voice` capability implementing `tinyassets.voice.v1`
- **THEN** TinyAssets stores the canonical descriptor against that connection
- **AND** the existing credential reference, endpoint allowlist, method scopes, grant, and serving selection remain unchanged

#### Scenario: Capability endpoint is outside existing authority
- **WHEN** a capability descriptor names a session URL that is not already allowed for `POST` by the connection
- **THEN** TinyAssets refuses the declaration before writing anything
- **AND** it does not extend the endpoint allowlist or mint a replacement grant

#### Scenario: Owner revokes an auxiliary capability
- **WHEN** the authenticated owner disables a capability on the current provider connection
- **THEN** TinyAssets deletes only that non-secret capability declaration idempotently
- **AND** the underlying connection, credential, universe grant, and primary writer remain unchanged

#### Scenario: Connection removal cannot resurrect a capability
- **GIVEN** a connection has a declared auxiliary capability
- **WHEN** the connection is removed and a connection for the same universe and destination is later re-provisioned with the same deterministic connection id
- **THEN** the old capability declaration is absent
- **AND** the replacement connection remains capability-unconfigured until its owner makes a fresh authenticated declaration

### Requirement: Capability resolution is current-provider exact and fail-closed
TinyAssets SHALL derive auxiliary capability readiness from the authenticated founder's current serving provider and live universe grant, and SHALL NOT guess support or search for a substitute provider.

#### Scenario: Current provider advertises an authorized capability
- **WHEN** the current provider's exact connection has a valid capability declaration and its connection, grant, owner, universe, method, and endpoint checks all pass
- **THEN** capability resolution returns ready with only bounded non-secret metadata

#### Scenario: Current provider powers text but not realtime Voice
- **WHEN** the current provider has no valid `realtime_voice` declaration or its adapter exposes no provider-neutral realtime bridge
- **THEN** resolution reports the exact provider capability gap
- **AND** it does not request a second credential, use platform authority, or select another provider

#### Scenario: Another connection advertises the capability
- **WHEN** a different connection owned by the same user advertises realtime Voice but is not the current serving provider connection
- **THEN** resolution does not silently select it
- **AND** it remains unavailable until the user explicitly changes authority through the existing connection/provider path

### Requirement: Capability metadata is bounded and secret-free
TinyAssets SHALL accept and expose only a versioned capability kind, protocol, HTTPS session URL, bounded service label, and optional HTTPS privacy URL. A readiness response SHALL additionally expose the closed, machine-readable `remediation` enum `existing_connection_surface` or `none`; this field is derived by the server and is not stored in the capability descriptor. Capability storage and responses MUST contain no credential reference, secret value, temporary bearer, model routing override, or billing authority.

#### Scenario: Capability metadata is read by the app
- **WHEN** the authenticated app requests capability status
- **THEN** the response contains only the provider capability state, the closed remediation enum, and disclosure-safe metadata
- **AND** logs, exceptions, traces, and serialized connection views contain no credential material
- **AND** existing public connection payloads and redacted connection views do not gain the capability descriptor

#### Scenario: Bridge identity changes
- **WHEN** a declaration changes the protocol, session URL, service label, or privacy URL
- **THEN** Voice returns a different disclosure identity derived from the complete canonical descriptor and connection id
- **AND** a prior disclosure acceptance cannot authorize the changed bridge

#### Scenario: Capability document is malformed or oversized
- **WHEN** a declaration has unknown fields, an unsupported protocol, invalid URL, control characters, userinfo, a fragment, or exceeds its bound
- **THEN** TinyAssets rejects it with a stable secret-free error before mutation

#### Scenario: Capability gap has an authorized remediation
- **WHEN** the current provider lacks a compatible declaration and its existing connection surface exposes an authorized remediation
- **THEN** readiness returns `remediation: existing_connection_surface`
- **AND** otherwise readiness returns `remediation: none`
