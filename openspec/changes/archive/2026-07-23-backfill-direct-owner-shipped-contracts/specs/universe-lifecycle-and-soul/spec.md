## ADDED Requirements

### Requirement: Universe switching is publicly write-gated before its scope-specific helper
The public `universe(action = "switch_universe")` dispatcher SHALL classify switching as a write and SHALL run named action-scope authorization followed by target-universe write ACL authorization before invoking the switch helper. An anonymous public caller or an authenticated caller without the required scope and target `write` or `admin` access SHALL receive the applicable authorization error before the helper can change `.active_universe`. An authorized authenticated request reaching the helper SHALL require a non-empty id naming an existing universe, return `status = "selected"` and `scope = "request"`, and SHALL NOT write the host-global marker; the caller is instructed to pass the selected id on each subsequent call. The helper's anonymous branch, reachable only by a direct/internal helper invocation rather than the public dispatcher, SHALL write the selected id directly to `.active_universe` and return `status = "switching"` with the current approximate restart note. Authentication decisions SHALL use request identity rather than an environment actor fallback, and the marker write SHALL NOT claim atomic replacement or cross-process serialization.

#### Scenario: Anonymous public switching is denied before the helper
- **WHEN** an anonymous caller invokes the public `universe` dispatcher with `action = "switch_universe"` and an existing target id
- **THEN** action-scope or write-ACL authorization rejects the call before the anonymous marker-writing helper branch
- **AND** `.active_universe` is not changed

#### Scenario: Authenticated public switching requires scope and target write access
- **WHEN** an authenticated caller lacks either the required action scope or target-universe `write` or `admin` access
- **THEN** the public dispatcher returns the applicable authorization error without invoking the switch helper

#### Scenario: Authenticated selection is request-scoped
- **WHEN** an authenticated request with the required action scope and target write access selects an existing universe
- **THEN** the result reports `selected` with request scope
- **AND** the host-global `.active_universe` marker is not created or changed

#### Scenario: Direct helper rejects a missing id
- **WHEN** the low-level switch helper is invoked directly without `universe_id`
- **THEN** it returns `universe_id is required` and writes no marker

#### Scenario: Direct helper rejects an unknown universe
- **WHEN** the low-level switch helper is invoked directly with an id whose directory does not exist
- **THEN** it returns a not-found error plus the non-hidden directory names currently available under the universe root
- **AND** it writes no marker

#### Scenario: Direct anonymous helper selection is host-global
- **WHEN** an anonymous internal caller invokes the switch helper directly for an existing universe and the marker write succeeds
- **THEN** `.active_universe` contains the selected id and the result reports `switching`

#### Scenario: Direct anonymous marker failure is returned
- **WHEN** an anonymous internal caller invokes the helper directly for an existing universe but writing `.active_universe` raises `OSError`
- **THEN** the result reports the marker-write failure instead of reporting a successful switch
