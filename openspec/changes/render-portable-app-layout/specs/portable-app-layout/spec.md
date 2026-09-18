## ADDED Requirements

### Requirement: Caller identity fences private layout installation
The authenticated no-store app self response SHALL include only the caller's
principal_id. Layout reads, writes and read-backs SHALL require that principal's
configured app_experience binding in the current home, without provider_ref.

#### Scenario: Shared universe or incomplete inventory
- **WHEN** a collaborator's binding is listed, or a list reaches 100 rows, or
  more than one eligible own installation exists
- **THEN** collaborator bindings are not consumed and incomplete/ambiguous lists
  disable application without creating another binding

#### Scenario: Identity changes during a request
- **WHEN** the signed-in principal or home changes
- **THEN** pending layout results are discarded and no stale mutation is sent

### Requirement: Native declarative layouts are consumed by trusted controls
The app SHALL render one valid `tinyassets.app-layout.v1` component as an ordered
subset of its existing conversation, requests, models and status surfaces using
only trusted controls and comfortable/compact density.

#### Scenario: A compact shared layout changes the same app
- **WHEN** the user applies a validated compact layout with reordered surfaces
- **THEN** the existing live controls follow that order and density without
  replacing conversation data, draft input, pending requests or model choices

#### Scenario: Unsupported code or component data
- **WHEN** the layout is malformed, ambiguous, or requires an unsupported version
- **THEN** the app reports unsupported layout and retains a usable trusted view
- **AND** it executes no imported markup, scripts, styles, URLs or actions

### Requirement: Applying a public design preserves private authority and data
The app SHALL apply a selected public definition using a dedicated non-serving
AgentBinding under existing universe ACL and revision checks, preserving the
receiving user's private configuration and all operational data.

#### Scenario: A second owner adopts a public layout
- **WHEN** a second owner discovers and applies the first owner's public design
- **THEN** only their own layout binding is created or updated
- **AND** no source-owner binding, credential, conversation or grant is copied

#### Scenario: Concurrent or uncertain update
- **WHEN** a binding revision changes or a write result is uncertain
- **THEN** the app does not overwrite a newer revision or automatically replay
  the mutation, and reads current state before another explicit attempt

### Requirement: Layout publication remains separate from private application
The app SHALL use existing native definition publication/remix with component
lineage and explicit publication, preserving other components while excluding
private binding configuration and live content.

#### Scenario: Customize one component
- **WHEN** a user edits the layout component of another user's composition
- **THEN** the published child retains unknown components and component lineage
- **AND** applying it remains a separate explicit private operation

### Requirement: Trusted recovery and empty-universe setup remain available
The app SHALL keep layout selection and Restore default outside configurable
surfaces and SHALL create no layout binding automatically during first sign-in.

#### Scenario: A view hides the conversation
- **WHEN** a valid layout omits the conversation surface
- **THEN** Restore default remains visible and restores the original live nodes
  without losing messages or draft content

#### Scenario: First model connection
- **WHEN** an empty universe signs in
- **THEN** layout loading creates no binding and cannot redirect model bootstrap
  into an existing-setup recovery state
