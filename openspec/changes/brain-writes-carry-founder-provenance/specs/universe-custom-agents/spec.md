## ADDED Requirements

### Requirement: Content from other parties reaches a served agent inside an untrusted envelope
`read_commons_shape` and any fetched external content returned to a served agent SHALL be wrapped
in an envelope that marks it untrusted, names its source, and carries a fixed notice that it is
data from another party and never instructions; the persona system prompt SHALL instruct the
universe accordingly.

#### Scenario: Reading another user's published shape
- **WHEN** the served agent calls `read_commons_shape` on a public branch authored by another user
- **THEN** the result is `{"untrusted": true, "source": "commons:<id>", "notice": ..., "content": ...}` and none of `content` appears in the universe's brain files after the turn
