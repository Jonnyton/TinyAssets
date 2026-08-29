# External effect adapters — body encoding transform

## ADDED Requirements

### Requirement: The outbound packet can ask the effector to encode, decode, reference and join body text

The generic `authenticated_external_call` effector SHALL treat a one-key JSON
object anywhere inside `request.body` (object values and list elements, at any
depth) whose key is one of `$base64`, `$from_base64`, `$ref`, `$concat` as a
transform applied before the wire request leaves the credential-blind path:
`{"$base64": X}` sends the base64 of X's UTF-8 bytes; `{"$from_base64": X}`
yields the UTF-8 text of base64 X (whitespace-tolerant, as content APIs wrap
it); `{"$ref": "a.b.0.c"}` yields the value at that dotted path in the run's
state, traversing JSON-encoded strings and list indices; `{"$concat": [X, …]}`
joins texts. X MAY itself be a transform. This SHALL be the only
channel-specific-looking knowledge the effector gains: one encoding and the
run's own state, never any service. The reason for the reference operator is
the second live failure (2026-08-29): a "repair" that let the model re-type a
file came back with 36 differences — bytes that pass through the model are
transcribed, not copied — so the model SHALL be able to author only the delta
while the effector moves every other byte. A malformed transform (wrong type,
an unresolvable path, an index out of range, bytes that are not UTF-8 text)
SHALL refuse the whole call with the effector's secret-free error dict
(`error_kind: invalid_body_transform`; never a raise, never a partially
transformed body). A body that contains no transform SHALL be sent
byte-for-byte as today.

#### Scenario: A file write sends text, the worker encodes it

- **GIVEN** a node emits a packet whose `request.body` is
  `{"message": "docs: append a line", "content": {"$base64": "<full file text>"}, "sha": "<blob sha>", "branch": "auto/x"}`
- **WHEN** the effector dispatches it
- **THEN** the request body sent is the same object with `content` replaced by
  the base64 of the text's UTF-8 bytes, and no `$base64` key remains

#### Scenario: Append one line without the model touching the file's bytes

- **GIVEN** the run's state holds the fetched file response under `fetched`
  (a JSON string whose `content` is wrapped base64)
- **WHEN** the packet's body is
  `{"sha": {"$ref": "fetched.sha"}, "content": {"$base64": {"$concat": [{"$from_base64": {"$ref": "fetched.content"}}, "<new line>\n"]}}}`
- **THEN** the request sent carries base64 whose decoded bytes are exactly the
  fetched file plus the new line, and the model authored only the new line

#### Scenario: A malformed sentinel is refused, not half-sent

- **WHEN** `request.body` contains `{"$base64": 42}`, `{"$from_base64": "not base64"}`,
  `{"$ref": "no.such.key"}` or `{"$concat": "x"}`
- **THEN** the effector returns its secret-free error dict (`invalid_body_transform`,
  naming the path and type, never a value) and sends nothing

#### Scenario: Packets without the sentinel are unchanged

- **WHEN** `request.body` contains no `$base64` value
- **THEN** the wire body is identical to the pre-change behaviour (dict/list
  JSON-encoded by the worker, string passed through)

#### Scenario: The live proof (the naive test that filed this)

- **WHEN** a user's agent, asked in the live app to append one line to
  `README.md` and open a PR, writes the file through this transform
- **THEN** the resulting commit differs from `main` by exactly the appended
  line (2026-08-29 without it: `README.md +2/-87`, every newline a literal
  `\n`, after a first `422 content is not valid Base64`)
