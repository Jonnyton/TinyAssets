## MODIFIED Requirements

### Requirement: Capability claims match real consumption
The platform SHALL distinguish preserved definitions, supported consumers,
activated installations and completed execution. The layout/turn-consumer adapter
SHALL NOT claim native-device event routing, foreign-harness loading or
whole-setup migration merely because their components round-trip.

Arbitrary executable UI is no longer in that list: a separate governed renderer now
executes a user-authored `tinyassets.app-ui.v1` bundle inside a sandboxed,
opaque-origin document whose only capability is a closed message bridge acting as
the viewing user (`composable-ui-experiences`). That renderer is a distinct
capability from this adapter — this adapter still renders only the four trusted
surfaces and carries no HTML, CSS, script or URL — so a design that needs the
executable renderer SHALL be reported against that capability rather than as an
unsupported requirement of this one.

#### Scenario: A design requires a renderer the platform does not have
- **WHEN** the receiver inspects a design naming a renderer neither this adapter
  nor the executable-bundle renderer provides
- **THEN** the UI identifies the missing governed renderer requirement
- **AND** ordinary layout and turn-consumer support are reported separately

#### Scenario: A design carries an executable UI component
- **WHEN** the receiver inspects a design whose component is a supported
  executable UI bundle
- **THEN** it is not reported as an unsupported renderer requirement
- **AND** it is installable into the receiver's own private configuration, where it
  runs against the receiver's own bridge and universe

### Requirement: Installation preserves private universe continuity
Installing or selecting consumed content SHALL write only the receiver's private
universe configuration and SHALL NOT alter conversation history, model access, or
any other private setting it did not name. The private installation SHALL be
reachable without the receiver having published anything: its reference to a public
definition SHALL be optional, so a receiver that has adopted no published design
still has its own configuration to install into. Creating that configuration SHALL
be scoped to the calling owner and SHALL be idempotent, returning an existing row
with its stored configuration intact rather than replacing it.

#### Scenario: Installation leaves unrelated private settings alone
- **WHEN** a receiver installs or selects consumed content
- **THEN** only the configuration fields that installation names are written
- **AND** conversation history and model access are unchanged

#### Scenario: A receiver with nothing published still has somewhere to install
- **WHEN** a receiver that has adopted no published design installs content
- **THEN** its private configuration is created with no public definition reference
- **AND** nothing about that receiver becomes publicly listable

#### Scenario: Re-creating the private configuration is not a reset
- **WHEN** creation is repeated after content has been installed
- **THEN** the existing configuration is returned unchanged
- **AND** no second private configuration exists for that owner and role
