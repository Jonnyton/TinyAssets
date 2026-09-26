# graph-execution-substrate (delta)

## ADDED Requirements

### Requirement: A rejected credential is its own failure class

A run whose effect was DELIVERED and answered with a status meaning the presented
credential is no longer accepted SHALL carry failure class
`credential_rejected`, with `actionable_by: "user"`.

The trigger SHALL be a delivered HTTP 401 unconditionally, and a delivered HTTP
403 only where the response body unambiguously says the credential itself is
invalid, revoked or expired. A 403 that says the credential may not do something
SHALL keep its existing class: replacing a working key is the wrong ask.

The test applied to a 403 body SHALL use generic credential vocabulary only — no
service or vendor name SHALL appear in it — and SHALL be bounded to the body of
the row whose status it is reading, so a word in another row of the same summary
cannot decide this row's class.

The class SHALL be decided before the refusal-word heuristic, because a revoked
token's own body contains a word that heuristic reads as an authority refusal.

#### Scenario: a delivered 401
- **WHEN** a node's effect is delivered and the far side answers 401
- **THEN** the run's failure class is `credential_rejected` and `actionable_by`
  is `user`

#### Scenario: a delivered 403 saying the key is dead
- **WHEN** a delivered 403's body names the credential as invalid, revoked or
  expired
- **THEN** the failure class is `credential_rejected`

#### Scenario: a delivered 403 about what the key may do
- **WHEN** a delivered 403's body describes a permission or scope rather than the
  credential's validity
- **THEN** the failure class is not `credential_rejected`

#### Scenario: a refusal made before the wire
- **WHEN** an effect is refused by the platform before any request is sent
- **THEN** its existing class is unchanged, whatever its text says

### Requirement: The action for a rejected credential is the replace card

`credential_rejected`'s suggested action SHALL tell the agent to raise the
replace-credential request for that destination in the same turn, and SHALL tell
it not to retry, not to widen the grant, and not to answer the owner in prose
instead of raising the card. Retrying sends the same dead secret and widening
changes nothing.

The error row recorded for a delivered effect failure SHALL name the
connection's `destination`, so the card can be raised for the connection that
actually failed rather than for a guess.

#### Scenario: the agent is told what to raise
- **WHEN** a run fails with `credential_rejected`
- **THEN** its suggested action names the rotation action and the destination
  field to read, and tells the agent not to retry

#### Scenario: which connection failed
- **WHEN** a delivered effect failure is recorded
- **THEN** its `external_write_errors` row carries the destination of the
  connection the call used
