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

### Requirement: Workflow policy narrows the universe selection and never widens it

Branch- and automation-level policy SHALL be resolved as the intersection of the
workflow policy, the universe selection, and the enrolled set. A workflow SHALL
NOT reach a provider excluded by the universe selection. An empty intersection
SHALL fail closed with an error naming which input produced the empty set.

#### Scenario: workflow requests a provider the universe excluded
- **WHEN** a branch declares a preferred provider that the universe selection excludes
- **THEN** resolution fails closed and the excluded provider is not invoked

#### Scenario: empty intersection names its cause
- **WHEN** the effective set resolves empty
- **THEN** the error names whether the workflow policy, the universe selection, or the enrolled set produced the empty result
