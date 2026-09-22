## ADDED Requirements

### Requirement: A bounded conversation preview names its own full size
`get_status` with `include_conversation` SHALL, for each turn it returns, carry the
turn's stable store identifier, its full length in Unicode code points, and whether
the returned text was bounded. The returned text SHALL remain bounded and the
identifier SHALL be the key accepted by the lossless read below, so a client never
pairs a preview to a stored message by text or timestamp.

#### Scenario: A bounded turn is identifiable
- **WHEN** a retained turn is longer than the per-turn preview bound
- **THEN** the turn reports `truncated: true`, its full `total_chars`, and an `id`
  that the lossless read accepts
- **AND** the preview text itself is unchanged in length or content.

#### Scenario: A short turn claims no loss
- **WHEN** a retained turn fits inside the preview bound
- **THEN** it reports `truncated: false` and a `total_chars` equal to its own length.

#### Scenario: The identifier grants nothing
- **WHEN** a caller holds a turn identifier from another account's thread
- **THEN** the lossless read resolves its own principal and home and returns no
  bytes of that thread.

### Requirement: The connector serves the rest of a bounded message losslessly
The public connector SHALL expose a read-only retrieval of one retained message of
the authenticated caller's own conversation, selected by the identifier above and
returned in exact Unicode-code-point chunks with a server-supplied continuation
offset. The read SHALL derive its principal and universe home from the verified
caller at call time, SHALL NOT accept a caller-supplied session, principal or
store path, SHALL NOT create or migrate a store, and SHALL NOT change any state.
Execution or delivery receipt metadata SHALL NOT be treated as authorization.

#### Scenario: A long reply is recovered whole
- **WHEN** the caller reads a bounded turn by its identifier and follows each
  returned continuation offset until none is returned
- **THEN** the concatenated chunks equal the stored message exactly, including
  characters outside the Basic Multilingual Plane.

#### Scenario: An unauthenticated or foreign caller reads nothing
- **WHEN** the call carries no verified principal, or carries a different account's
- **THEN** it is refused, or resolves to that caller's own thread, and in neither
  case returns another account's content.

#### Scenario: Retention is stated, never fabricated
- **WHEN** the identified message is not retained
- **THEN** the read says so and returns no reconstructed or approximated text.
