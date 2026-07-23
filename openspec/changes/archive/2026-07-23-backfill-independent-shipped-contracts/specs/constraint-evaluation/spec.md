## ADDED Requirements

### Requirement: Incremental ASP validation uses cumulative multi-shot grounding with early-grounding limitations
`ASPEngine.validate_incremental` SHALL ground the configured base program and optional world rules once, then add and ground each scene as a new named step on the same solver control. It SHALL solve after every step and return one ordered `ValidationResult` per input scene, with earlier scene facts remaining in later models. As built, rules grounded before a predicate first appears in a later scene MAY be discarded by the grounder and therefore fail to constrain those later facts; the method SHALL NOT be treated as independent per-scene validation or complete incremental rule enforcement.

#### Scenario: Multiple scenes are solved in order
- **WHEN** a caller supplies two scene fact programs to `validate_incremental`
- **THEN** the engine returns two results in input order after grounding `step_0` and then `step_1` on the same base control

#### Scenario: Earlier scene facts remain in the later model
- **WHEN** a second scene is grounded after a first scene on the same control
- **THEN** the second solve's model includes facts from both scene programs

#### Scenario: Base rule can miss predicates introduced only by scene steps
- **WHEN** a base integrity rule references a predicate that has no instances until later scene programs are grounded
- **THEN** the current early-grounding path can return satisfiable even when the accumulated scene facts would violate that rule if the rule were re-grounded

#### Scenario: Empty scene batch
- **WHEN** a caller supplies no scenes
- **THEN** the base program is initialized and the method returns an empty result list
