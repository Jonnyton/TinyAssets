## ADDED Requirements

### Requirement: Select providers through the advertised handles without depositing a credential

A universe owner SHALL select which providers their universe may use through the
advertised canonical handles, and the selection surface SHALL accept only
identifiers of providers already enrolled and requester-owned for that owner and
universe. The surface SHALL expose no field capable of carrying a provider
credential, SHALL reject credential-shaped input rather than storing or ignoring
it, and SHALL add no advertised MCP handle.

#### Scenario: owner selects an enrolled provider
- **WHEN** an authenticated owner selects a provider that is enrolled, requester-owned, active, and unexpired for their universe
- **THEN** the selection is recorded and the effective provider set is returned

#### Scenario: credential-shaped input is refused
- **WHEN** any field of a selection request carries an API key, token, or other credential-shaped value
- **THEN** the request is rejected, nothing is persisted, and the value is never written to storage or logs

#### Scenario: unenrolled provider is refused
- **WHEN** an owner selects a provider that is not enrolled for that owner and universe, or whose binding is revoked or expired
- **THEN** the selection is rejected naming the unenrolled provider, and any prior selection is left unchanged

#### Scenario: advertised handle set is unchanged
- **WHEN** the live surface is asked for its tool catalog
- **THEN** the canonical handle set is exactly as before this change

### Requirement: A selection constrains the routable provider set

Recording a selection SHALL set the routable provider set to exactly the
preferred provider together with its accepted fallbacks, intersected with the
enrolled set. A provider outside that set SHALL NOT serve work for the universe,
and ordering alone SHALL NOT be treated as a constraint.

#### Scenario: unselected provider cannot serve work
- **WHEN** every provider in the effective set fails and an unselected but enrolled provider is available
- **THEN** the work fails closed and the unselected provider is not invoked

#### Scenario: selection narrows rather than reorders
- **WHEN** a selection is recorded
- **THEN** the persisted routable set equals the selected set intersected with the enrolled set, and is not merely an ordering over a wider set

### Requirement: Empty accepted fallbacks fail closed

An empty accepted-fallbacks list SHALL mean that only the preferred provider may
serve the work. When the preferred provider is unavailable and no fallback is
accepted, resolution SHALL fail with a named error and SHALL NOT widen to any
other provider.

#### Scenario: sole provider unavailable
- **WHEN** a policy declares a preferred provider with no accepted fallbacks and that provider is unavailable
- **THEN** resolution fails naming the unavailable provider and no other provider is invoked

### Requirement: The enrolled set is the boundary and the universe selection is a default

Resolution SHALL treat the enrolled, requester-owned provider set as the only
boundary. The universe selection SHALL apply as the default when a workflow
declares no policy of its own, and SHALL NOT prevent a workflow from naming any
other enrolled, requester-owned provider. An empty effective set SHALL fail
closed with an error naming which input produced it.

#### Scenario: workflow names an enrolled provider outside the universe default
- **WHEN** a branch declares a preferred provider that is enrolled and requester-owned but is not in the universe selection
- **THEN** that provider is used, because the universe selection is a default rather than a ceiling

#### Scenario: workflow declares no policy
- **WHEN** a branch declares no provider policy
- **THEN** the universe selection applies as the default, intersected with the enrolled set

#### Scenario: unenrolled provider is still refused
- **WHEN** a workflow names a provider that is not enrolled and requester-owned
- **THEN** resolution fails closed, because enrollment is the boundary the universe selection is not

#### Scenario: empty effective set names its cause
- **WHEN** the effective set resolves empty
- **THEN** the error names whether the workflow policy, the universe selection, or the enrolled set produced the empty result
