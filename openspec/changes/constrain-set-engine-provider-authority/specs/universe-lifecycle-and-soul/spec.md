## MODIFIED Requirements

### Requirement: Universe creation is atomic and self-serializing

The `create_universe` action (`tinyassets/api/universe.py`) SHALL generate a
fresh serial when no `universe_id` is supplied, and MAY accept an explicit id
for dev/existing-universe operations. It SHALL reject a supplied id that
contains a path separator (`/` or `\`) or begins with `.`, and SHALL refuse to
overwrite a directory that already exists. Creation MUST persist
`engine_assignment_state="unassigned"` and `allowed_providers=[]` before the
universe can be observed as living, so newborn work cannot use ambient host
providers or quota. If any step after the directory is created fails, the
partial directory SHALL be removed (rollback via `rmtree`) so a failed create
never leaves a bare, half-seeded, or authority-uninitialized directory that
would later read as a living universe.

#### Scenario: create without an id generates a serial
- **WHEN** `create_universe` is called with no `universe_id`
- **THEN** a fresh `u-`+ULID serial is generated and used as the new universe
  directory name
- **AND** the response reports `status: created` for that serial

#### Scenario: a path-traversal id is rejected
- **WHEN** `create_universe` is called with a `universe_id` containing `/`, `\`,
  or a leading `.`
- **THEN** the call returns an `Invalid universe_id.` error and no directory is
  created

#### Scenario: a newborn universe is provider deny-all
- **WHEN** creation succeeds before any engine assignment
- **THEN** the universe persists `engine_assignment_state="unassigned"` and
  `allowed_providers=[]`
- **AND** it is not observable as living before that authority state is durable

#### Scenario: a partial create is rolled back
- **WHEN** creation fails after the universe directory has been created,
  including failure to persist initial engine authority
- **THEN** the partially created directory is removed before the error is
  returned
- **AND** an `OSError` is surfaced as an error envelope while any other
  exception re-raises after cleanup
