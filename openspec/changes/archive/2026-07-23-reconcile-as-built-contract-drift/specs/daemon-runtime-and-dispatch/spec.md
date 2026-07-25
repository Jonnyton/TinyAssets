## MODIFIED Requirements

### Requirement: The work-target registry has an explicit lifecycle
Every durable `WorkTarget` record SHALL carry a `lifecycle` field.
`WorkTarget.from_dict` SHALL coerce that field to a string; `create_target`
SHALL accept the caller-supplied lifecycle without closed-enum validation. For
string inputs, arbitrary values SHALL round-trip. The module publishes the
conventional values `active`, `paused`, `dormant`, `complete`, `superseded`,
`marked_for_discard`, and `discarded`; transition helpers use the values
applicable to their operation. `mark_target_for_discard` SHALL set
`marked_for_discard` and record the review cycle. `discard_target` SHALL leave
the target marked until the configured review delay has elapsed, then set
`discarded`, retain the registry row, write the archival JSON copy, and record
the recoverability deadline.

#### Scenario: a target carries an explicit lifecycle state
- **WHEN** a target is created with the default lifecycle, a transition helper changes it, or generic construction/deserialization receives another string
- **THEN** the supplied lifecycle string is persisted and round-trips
- **AND** transition helpers use conventional named values, but the generic boundary does not enforce a closed enum

#### Scenario: discard is a delayed two-step, not immediate deletion
- **WHEN** a target is marked for discard and `discard_target` is called before the review delay has elapsed
- **THEN** the target stays `marked_for_discard`
- **AND** only after the delay does finalization set `discarded`, write the archival copy, and retain a recoverability deadline
