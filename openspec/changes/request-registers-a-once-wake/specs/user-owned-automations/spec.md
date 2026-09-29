# user-owned-automations (delta)

## ADDED Requirements

### Requirement: An owner's request registers a one-shot wake of the universe loop

`write_graph target="request"` from the universe's owner SHALL store a one-shot
automation, trigger kind `once`, due now, that runs the universe's declared loop
branch. The request's text and type SHALL be the run's inputs. The automation
pump SHALL fire it with every run-time check an automation already has. One
`idempotency_key` SHALL yield at most one wake, and a replay SHALL return the
first result. A request from any other principal SHALL be refused with
`request_owner_only` and SHALL store nothing. A retired queue field set to a
non-default value SHALL be refused with `request_field_retired:<field>` and
SHALL store nothing. The wake id SHALL derive from the owner, the universe and
the key under a domain separator, with each field length-prefixed, so no key
reaches another owner's or universe's wake. The same key with a different
canonical body SHALL be refused with `idempotency_key_body_conflict`.
Request-admission tasks still pending when this ships SHALL be cancelled with
an event recording the reason `request_retired_to_wake`, and never deleted.

#### Scenario: The owner's request runs the loop once
- **WHEN** the owner sends `write_graph target="request" text="summarise today" idempotency_key=k1`
- **THEN** the result names an `automation_id`, and the pump starts exactly one run of the loop branch with `request = "summarise today"`

#### Scenario: A replay does not wake twice
- **WHEN** the owner sends the same request with `idempotency_key=k1` again
- **THEN** the first result is returned and no second wake is stored

#### Scenario: Another user cannot spend the owner's compute
- **WHEN** a user with write access who is not the owner sends a request to the universe
- **THEN** it is refused with `request_owner_only` and no wake is stored

#### Scenario: A retired queue field is refused, not ignored
- **WHEN** a request sets `directed_daemon_id`
- **THEN** it is refused with `request_field_retired:directed_daemon_id`

#### Scenario: A request left pending by the old queue gets a reason
- **WHEN** the daemon starts with a request-admission task still pending
- **THEN** the task is `cancelled`, its event records `request_retired_to_wake`, and its row is kept
