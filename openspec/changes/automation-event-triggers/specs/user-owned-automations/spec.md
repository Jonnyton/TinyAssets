# user-owned-automations (delta)

## ADDED Requirements

### Requirement: An engine event wakes the owner's subscribed automation

An automation SHALL be creatable with trigger kind `event`, naming an
`event_type` the engine emits (`run_completed` or `pending_request_answered`)
and an optional equality `event_filter` over that event's payload fields. A
`run_completed` subscription SHALL name `branch_def_id` in its filter. An event
row SHALL never be due on a clock. Each emitted event that matches an active
subscription SHALL store a one-shot wake for the subscribed branch, with the
payload under `inputs.event`, and the automation pump SHALL fire it with every
run-time check an automation already has. An event SHALL be stamped with the
principal that caused it, recorded when the run was created, and SHALL wake
only subscriptions that principal owns in that principal's own home universe.
An event with no principal SHALL wake nothing. A cancelled run SHALL announce
nothing.

#### Scenario: A run finishing wakes the branch that follows it
- **GIVEN** an owner's `run_completed` subscription filtered on branch A
- **WHEN** a run of A reaches a terminal status, or a deploy interrupts it
- **THEN** one wake of the subscribed branch is stored with `inputs.event` naming the run and its outcome, and the pump runs it once

#### Scenario: An answer from any surface wakes a subscribed branch
- **WHEN** the owner answers or dismisses a pending request, through the app or the connector's `answer_request`
- **THEN** one wake is stored with the request id, kind and status

#### Scenario: Another user's activity wakes nothing
- **WHEN** a different user's run finishes in the owner's universe, a visitor-driven run of the universe finishes, someone else cancels the owner's run, or someone else answers a request
- **THEN** no wake is stored for the owner's subscription

#### Scenario: A subscription that could not fire is refused
- **WHEN** an owner subscribes to an event the engine does not emit, filters on a field the event lacks, or omits `branch_def_id` from a `run_completed` filter
- **THEN** nothing is stored and the refusal names the reason

### Requirement: A scheduler subscription names only an emitted event

`subscribe_branch` SHALL refuse any event type the engine does not emit, and
SHALL name automation events as the replacement. It SHALL NOT store a row that
cannot fire.

#### Scenario: A retired event type is refused
- **WHEN** a caller subscribes to `canon_change`, `branch_run_completed`, `canon_upload` or `pr_open`
- **THEN** the action returns `event_type_not_subscribable` and stores nothing
