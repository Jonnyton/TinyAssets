## ADDED Requirements

### Requirement: Status identity evidence varies across three response shapes
The system SHALL expose distinct identity evidence on the audited early-first-contact, dispatcher-config-error, and full `get_status` paths without claiming those are the only possible error or authorization envelopes. An authenticated account that omits `universe_id` and has no complete bound home SHALL receive the early first-contact shape containing `first_contact.event = "no_universe_yet"`, `first_contact.note`, `about`, `next_step_for_user`, and `schema_version = 1`; this shape SHALL omit `session_boundary`. A dispatcher-config load failure after universe resolution and access approval SHALL return `error = "config_load_failed"`, `detail`, `universe_id`, and `universe_exists`; this shape SHALL also omit `session_boundary`. A full status response SHALL include `session_boundary` with `prior_session_context_available`, `account_user`, `last_session_ts`, and `note`.

#### Scenario: Untargeted no-home status returns before session identity assembly
- **WHEN** an authenticated account with no complete bound home universe calls `get_status` without an explicit `universe_id`
- **THEN** the response is the early first-contact shape with `schema_version = 1`
- **AND** `session_boundary` is absent

#### Scenario: Configuration failure returns before session identity assembly
- **WHEN** a resolved universe's dispatcher configuration raises during load
- **THEN** the response contains `config_load_failed`, its detail, the universe id, and whether the universe directory exists
- **AND** `session_boundary` is absent

#### Scenario: Full status attributes the current account
- **WHEN** status reaches the full response and request authentication supplies a non-anonymous subject
- **THEN** `session_boundary.account_user` equals that authenticated subject

#### Scenario: Authless full status uses the legacy environment actor
- **WHEN** status reaches the full response without a non-anonymous request subject
- **THEN** `session_boundary.account_user` equals `UNIVERSE_SERVER_USER`, defaulting to `anonymous`

#### Scenario: Prior-session evidence is a best-effort activity-tail match
- **WHEN** one of the newest 20 activity-log lines contains the raw `account_user` string anywhere and begins with a bracketed timestamp
- **THEN** the newest such substring match makes `prior_session_context_available` true and supplies that timestamp as `last_session_ts`
- **AND** this is best-effort substring evidence rather than verified actor attribution, so a name contained inside another value can match and an empty account string matches every line
- **AND** no match or any handled scan error yields false with `last_session_ts` set to null
