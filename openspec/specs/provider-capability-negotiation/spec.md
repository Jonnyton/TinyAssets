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

### Requirement: A source without a list endpoint draws candidates from a reviewed list
A source kind whose sources cannot enumerate their own models SHALL draw candidate model
ids from a tracked file per source kind, holding only the source kind and a sorted,
duplicate-free list of well-formed identifiers. A malformed file SHALL be refused rather
than read as an empty list. The file SHALL be packaged into every runtime artifact and a
change to it SHALL trigger a deployment, since an absent file is indistinguishable from
an unlisted source kind.

#### Scenario: A model id is added to the list
- **WHEN** a pull request adding the id is merged and deployed
- **THEN** every universe on that source kind offers it on the next read
- **AND** no per-provider code or release is required

#### Scenario: The list file is malformed
- **WHEN** the file is invalid, unsorted, duplicated, or holds a bad identifier
- **THEN** the read raises rather than silently offering fewer models

#### Scenario: A source enumerates its own models
- **WHEN** a source can call its provider's list endpoint
- **THEN** its ids arrive through discovery and it needs no entry in any file

### Requirement: A model id a user supplied stays that user's own
A model id an owner supplied and successfully used SHALL be recorded for that owner, SHALL
remain on that owner's own candidate list, and SHALL NOT be shared, published, aggregated
or counted across owners. Two universes of one owner SHALL be one owner. The record SHALL
be that owner's data and removed with their account.

#### Scenario: An owner uses an account-bearing selector
- **WHEN** the id embeds that owner's own account or deployment
- **THEN** it stays on their list and no other user can see it

#### Scenario: The owner narrows their model access
- **WHEN** an id that previously worked is no longer granted
- **THEN** it is still offered as that owner's own history, and is not admitted

### Requirement: A candidate to grant is never an admitted candidate
A candidate contributed by a reviewed list or by an owner's own history SHALL NOT be
admitted and SHALL NOT enter the routing order until that universe's accepted model access
includes it. Each SHALL carry an availability basis distinguishing it from the source's own
verified models, and a reason stating that access is required. Only the newest model of each
class SHALL be offered from a list, derived from the identifier's own shape with no vendor
or model names in platform code.

#### Scenario: Before the grant
- **WHEN** a contributed id is outside the universe's accepted model access
- **THEN** it is visible, unadmitted, carries a needs-access reason, and is absent from the order

#### Scenario: After the grant
- **WHEN** the owner grants access to that id
- **THEN** it becomes an admitted candidate and a turn can run on it
