## ADDED Requirements

### Requirement: Incremental validation accumulates scenes in input order

`ASPEngine.validate_incremental` SHALL create one Clingo control, ground the configured base rules plus optional caller world rules once, then add and ground each supplied scene as a distinct step in input order. It MUST solve after each addition and return one `ValidationResult` for each supplied scene. Because the same control is reused, facts grounded for earlier scenes SHALL remain active in later solves. For an unsatisfiable step, the current diagnostic text SHALL be derived from the base/world program plus that current scene only; it MUST NOT be represented as a minimal solver core or a complete textual reconstruction of every prior step.

#### Scenario: Later validation observes earlier grounded facts

- **WHEN** a caller supplies multiple scene fact strings
- **THEN** the runtime grounds and solves them in their input order using one accumulating control
- **AND** the result at each position reflects all facts grounded through that position
- **AND** the returned list has exactly one result per supplied scene

#### Scenario: No scenes are supplied

- **WHEN** a caller supplies an empty scene list
- **THEN** the runtime grounds the base/world program and returns an empty result list
- **AND** it does not invent a scene result

#### Scenario: An accumulated step is unsatisfiable

- **WHEN** the accumulated control becomes unsatisfiable after grounding a scene
- **THEN** that position returns `satisfiable: false` with no models or atoms
- **AND** its textual violation list retains the current bounded diagnostic behavior rather than claiming an exact accumulated unsatisfiable core
