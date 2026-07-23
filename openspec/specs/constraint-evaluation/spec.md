# constraint-evaluation Specification

## Purpose
Define the shipped ASP-backed constraint surface, validation, scoring, and bounded synthesis behavior, including its current degraded and never-block modes.
## Requirements
### Requirement: ASP validation loads the configured rule text without inventing missing rules
The constraint runtime SHALL load rule text from the supplied rule-file path, defaulting to `data/world_rules.lp` resolved from the installed source layout, and combine it with caller facts and optional additional rules at validation time. It MUST warn and continue with empty base-rule text when the configured file is absent; the current runtime does not fail closed merely because that rule file is missing.

#### Scenario: The default world-rule file is present
- **WHEN** `ASPEngine()` is constructed in the standard checkout or image layout
- **THEN** it loads non-empty text from `data/world_rules.lp`
- **AND** validation includes that text with supplied facts

#### Scenario: The configured base-rule file is absent
- **WHEN** `ASPEngine` is constructed with a missing rule-file path
- **THEN** construction logs a warning and leaves its base-rule text empty
- **AND** construction does not itself raise an exception

### Requirement: ASP validation reports satisfiability and available solver evidence
The constraint runtime SHALL invoke Clingo to evaluate the composed ASP program and return `satisfiable`, `violations`, `models`, and `atoms`. It MUST return model and first-model-atom evidence for satisfiable programs, and MUST return no models or atoms for an unsatisfiable program.

#### Scenario: A satisfiable program is evaluated
- **WHEN** facts and rules admit at least one answer set
- **THEN** validation returns `satisfiable: true`
- **AND** `violations` is empty
- **AND** `models` and `atoms` contain the solver's shown-atom evidence when present

#### Scenario: An integrity constraint makes a program unsatisfiable
- **WHEN** facts violate an ASP integrity constraint
- **THEN** validation returns `satisfiable: false`
- **AND** `models` and `atoms` are empty
- **AND** `violations` contains the runtime's extracted potential integrity-constraint descriptions

### Requirement: Surface conversion and scoring produce the current shared constraint representation
The constraint runtime SHALL represent narrative constraints as the current optional-field `ConstraintSurface`, translate supported characters, institutions, relationships, resources, events, and related values into ASP facts, and score configured fields in the inclusive range from `0.0` to `1.0`. It MUST mark a freshly created empty surface as not ready and use `0.75` as the current readiness threshold.

#### Scenario: A populated surface is translated for ASP validation
- **WHEN** a surface contains characters with locked facts and an institution with public and hidden functions
- **THEN** `surface_to_asp_facts()` emits the corresponding `character`, `knows`, `institution`, `has_public_face`, and `has_hidden_agenda` facts

#### Scenario: An empty surface is scored
- **WHEN** `empty_constraint_surface()` is scored
- **THEN** the score is `0.0`
- **AND** `ready_to_write` is `false`

### Requirement: Synthesis routes rich and sparse inputs through the current bounded pipeline
Constraint synthesis SHALL use EXTRACT mode when provided source documents contain at least 500 words in total and GENERATE mode otherwise. It MUST populate a `ConstraintSurface`, score it, then validate and deepen it for at most three iterations before returning a result.

#### Scenario: Rich documents select extraction
- **WHEN** `process()` receives source documents totaling at least 500 words
- **THEN** it selects EXTRACT mode
- **AND** it derives the current template-based constraint, character, institution, system, location, timeline, writing-rule, and banned-pattern fields from the source text

#### Scenario: Sparse input selects generation
- **WHEN** `process()` receives no source documents or fewer than 500 total source words
- **THEN** it selects GENERATE mode
- **AND** it uses the current HTN decomposition and DOME expansion path before building the surface

### Requirement: Current degraded synthesis behavior is not represented as a quality guarantee
The current synthesis runtime MUST stop after at most three deepening attempts and set `ready_to_write` to `true` when that limit is reached, even if the final score remains below `0.75` or ASP validation is unsatisfied. It SHALL describe this as the existing never-block limitation, not as proof that the surface is complete, valid, or suitable for writing.

#### Scenario: Readiness is not reached within the bounded attempts
- **WHEN** a synthesized surface remains below the readiness threshold through all three validation/deepening attempts
- **THEN** synthesis returns the best-effort surface with `ready_to_write: true`
- **AND** the returned score may still be below `0.75`
- **AND** the result does not establish that all constraints were satisfied

### Requirement: Current solver and violation diagnostics have bounded fidelity
The constraint runtime MUST require Clingo at validation invocation time and SHALL not provide an alternative solver when that import or solver execution fails. For an unsatisfiable program it MUST report every textual integrity constraint found in the composed program as a potential violation rather than claim a minimal or exact unsatisfiable core.

#### Scenario: A caller invokes validation without an available solver
- **WHEN** Clingo cannot be imported at the point `validate()` or `validate_incremental()` runs
- **THEN** the current runtime propagates that dependency failure
- **AND** it does not synthesize a satisfiability result

#### Scenario: Multiple integrity constraints exist in an unsatisfiable program
- **WHEN** the composed program is unsatisfiable and contains several textual integrity constraints
- **THEN** the returned violation descriptions enumerate those constraints as potential causes
- **AND** callers do not treat that list as an exact solver-derived conflict core

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
