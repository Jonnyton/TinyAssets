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
- **AND** it is installable into the receiver's own UI library, where it runs
  against the receiver's own bridge and universe
