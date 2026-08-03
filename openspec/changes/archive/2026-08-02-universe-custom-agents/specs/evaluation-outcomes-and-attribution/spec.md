## ADDED Requirements

### Requirement: Agent component attribution is append-only and locally verified
The attribution system SHALL preserve each public agent remix as append-only child-component to parent-component lineage, SHALL derive bounded generation depth from verified local parents, SHALL keep per-child-component credit at or below `1.0`, and SHALL distinguish unresolved external origin declarations from verified attribution edges.

#### Scenario: Verified local component sources earn attribution
- **WHEN** a child agent component cites existing parent components in the local public commons
- **THEN** the platform writes immutable verified lineage edges with their declared credit shares and derived generation depth

#### Scenario: External origin does not manufacture local credit
- **WHEN** an imported portable definition declares a parent component that is not resolvable in the local commons
- **THEN** the platform may preserve that declaration as informational origin metadata
- **AND** it does not write a verified attribution edge or assign local credit for that declaration
