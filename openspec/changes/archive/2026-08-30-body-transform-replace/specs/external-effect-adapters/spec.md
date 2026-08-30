## MODIFIED Requirements

### Requirement: The outbound packet can encode, decode, reference and join body text without the model carrying the bytes

The body transform vocabulary SHALL also include `$ta.replace`:
`{"$ta.replace": {"in": <text>, "old": <text>, "new": <text>, "count": <n>}}`
replaces exactly `count` (default 1) occurrences of `old` inside `in` with
`new`, each operand resolved through the same transforms. The effector SHALL
refuse the whole call, sending nothing, when `old` is empty, is not found in
`in`, or occurs a number of times other than `count`, or when `count` is not
a positive integer. All other clauses of this requirement are unchanged.

#### Scenario: One line of a fetched file is changed without the model carrying the file

- **WHEN** a write node's body uses `$ta.replace` over the decoded content of
  an earlier fetch node, with `old` the exact current line and `new` the
  intended line
- **THEN** the written file differs from the fetched one only in that line,
  byte for byte elsewhere

#### Scenario: A typo in the old text changes nothing

- **WHEN** `old` does not occur in the fetched text, or occurs twice with
  `count` 1
- **THEN** the call is refused with `invalid_body_transform` and nothing is sent
