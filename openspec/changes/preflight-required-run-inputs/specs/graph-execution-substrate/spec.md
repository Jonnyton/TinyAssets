## ADDED Requirements

### Requirement: Run preflight resolves required state conservatively from graph topology
The execution substrate SHALL analyze the frozen Branch snapshot before persistence,
treating prompt placeholders and unguarded literal code-state accesses in the
straight-line prefix of the sandbox entry function as mandatory,
counting caller inputs and non-`None` schema defaults as initially available, and
counting a node output only when every possible activation reaches that consumer
after a producer has completed, including outputs merged from synchronized ordinary
fan-out siblings. An `input_keys` allowlist entry alone SHALL NOT make a key required.

#### Scenario: Guarded code access remains a runtime choice
- **WHEN** a code node conditionally dereferences or pops a state key only after checking for its presence, or handles its absence through control flow
- **THEN** preflight does not require the key and the code node's existing runtime behavior decides the result

#### Scenario: Guaranteed predecessor output satisfies a later consumer
- **WHEN** a required key is absent initially but every reachable route to its consumer passes through an earlier node that declares the key in `output_keys`
- **THEN** the key is resolved by preflight and does not block run admission

#### Scenario: Conditional join does not assume one route's output
- **WHEN** a consumer is reachable through multiple routes and at least one route does not first produce a required key
- **THEN** preflight reports the key as unresolved

#### Scenario: Ordinary fan-in merges parallel sibling output
- **WHEN** an ordinary fan-out activates parallel siblings and one sibling produces a key consumed after their shared barrier
- **THEN** preflight treats the merged key as available to the downstream consumer

#### Scenario: Loop output is not assumed on first entry
- **WHEN** a node can receive a key only from a later loop iteration and the key is absent initially
- **THEN** preflight reports the key as unresolved for the first entry

### Requirement: Missing-input diagnostics are stable and actionable
The run surface SHALL return unresolved inputs with the stable failure class
`missing_required_inputs`, exact sorted key names, and schema-derived type and
example-shape guidance, and SHALL apply the same contract to live-definition and
immutable-version targets.

#### Scenario: Multiple missing inputs are deterministic
- **WHEN** preflight finds multiple unresolved keys
- **THEN** `missing_input_keys` is sorted and `input_guidance` provides each key's declared type, optional description, and JSON-compatible example shape

#### Scenario: Live and immutable targets share diagnostics
- **WHEN** equivalent live-definition and immutable-version targets are submitted with the same unresolved inputs
- **THEN** both refusals use the same failure class, missing-key ordering, guidance shape, and suggested retry action

#### Scenario: Falsey supplied values count as present
- **WHEN** `inputs_json` explicitly supplies a required key with a falsey JSON value
- **THEN** preflight treats the key as supplied and leaves value interpretation to existing runtime behavior
