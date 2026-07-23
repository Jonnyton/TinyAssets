## ADDED Requirements

### Requirement: Universe switching has authenticated request scope and anonymous host scope
The system SHALL require a non-empty id naming an existing universe before switching. For a request whose permission actor is authenticated, switching SHALL return `status = "selected"` and `scope = "request"` without writing the host-global `.active_universe` marker; the caller is instructed to pass the selected id on each subsequent call. For an anonymous request, switching SHALL write the selected id directly to the host-global marker and return `status = "switching"` with the current approximate restart note. The authenticated decision SHALL use the request identity rather than an environment actor fallback, and the marker write SHALL NOT claim atomic replacement or cross-process serialization.

#### Scenario: Missing id is rejected
- **WHEN** `switch_universe` is invoked without `universe_id`
- **THEN** it returns `universe_id is required` and writes no marker

#### Scenario: Unknown universe is rejected with current choices
- **WHEN** `switch_universe` names a directory that does not exist
- **THEN** it returns a not-found error plus the non-hidden directory names currently available under the universe root
- **AND** it writes no marker

#### Scenario: Authenticated selection is request-scoped
- **WHEN** an authenticated request selects an existing universe
- **THEN** the result reports `selected` with request scope
- **AND** the host-global `.active_universe` marker is not created or changed

#### Scenario: Anonymous selection is host-global
- **WHEN** an anonymous request selects an existing universe and the marker write succeeds
- **THEN** `.active_universe` contains the selected id and the result reports `switching`

#### Scenario: Anonymous marker failure is returned
- **WHEN** an anonymous request selects an existing universe but writing `.active_universe` raises `OSError`
- **THEN** the result reports the marker-write failure instead of reporting a successful switch
