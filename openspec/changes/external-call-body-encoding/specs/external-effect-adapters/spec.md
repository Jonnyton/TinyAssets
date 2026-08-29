# External effect adapters — body encoding transform

## ADDED Requirements

### Requirement: The outbound packet can ask the worker to base64-encode a body field

The generic `authenticated_external_call` effector SHALL treat a JSON value of
the exact shape `{"$base64": "<string>"}` anywhere inside `request.body`
(object values and list elements, at any depth) as an instruction to send the
base64 encoding of that string's UTF-8 bytes in its place. The transform SHALL
run before the wire request leaves the credential-blind path and SHALL be the
only channel-specific-looking knowledge the effector gains: it knows one
encoding, not any service. A sentinel whose value is not a string SHALL be
refused with the effector's secret-free error dict (never a raise, never a
partially transformed body). A body that contains no sentinel SHALL be sent
byte-for-byte as today.

#### Scenario: A file write sends text, the worker encodes it

- **GIVEN** a node emits a packet whose `request.body` is
  `{"message": "docs: append a line", "content": {"$base64": "<full file text>"}, "sha": "<blob sha>", "branch": "auto/x"}`
- **WHEN** the effector dispatches it
- **THEN** the request body sent is the same object with `content` replaced by
  the base64 of the text's UTF-8 bytes, and no `$base64` key remains

#### Scenario: A malformed sentinel is refused, not half-sent

- **WHEN** `request.body` contains `{"$base64": 42}` or `{"$base64": {"nested": true}}`
- **THEN** the effector returns its secret-free error dict naming the field and
  sends nothing

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
