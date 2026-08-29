# External effect adapters — body transforms

## ADDED Requirements

### Requirement: The outbound packet can encode, decode, reference and join body text without the model carrying the bytes

The generic `authenticated_external_call` effector SHALL treat a one-key JSON
object anywhere inside `request.body` (object values and list elements, nested
up to 32 levels) whose key is one of `$ta.base64`, `$ta.from_base64`,
`$ta.ref`, `$ta.effect`, `$ta.concat` as a transform applied before the wire
request leaves the credential-blind path. Names are namespaced so a user's own
payload keys (`$ref`, `$set`, …) are never interpreted. `{"$ta.base64": X}`
sends the base64 of X's UTF-8 bytes; `{"$ta.from_base64": X}` yields the UTF-8
text of base64 X (whitespace-tolerant, as content APIs wrap it);
`{"$ta.ref": "key.a.0.b"}` yields a value from the run's state whose root
`key` MUST be one of the emitting node's declared `input_keys`, a
state_schema-defaulted key, or one of the node's own output keys — never the
whole final state; `{"$ta.effect": "node.response.body.x"}` yields a value
from the evidence of an EARLIER node's generic-call effect in the same run
(effects fire in node order; a later or unknown node is refused);
`{"$ta.concat": [X, …]}` joins texts. X MAY itself be a transform. JSON-encoded
strings are traversed and lists indexed. This SHALL be the only knowledge the
effector gains beyond shape: one encoding and the run it belongs to, never a
service. A malformed transform (wrong type, an unfenced or unresolvable path,
an index out of range, bytes that are not UTF-8 text, nesting past 32, or a
transformed body over 8 MiB) SHALL refuse the whole call with the effector's
secret-free error dict (`error_kind: invalid_body_transform`; paths and types
in the message, never values; nothing sent). A body containing no `$ta.*`
transform SHALL be sent byte-for-byte as today, its own `$`-keys included.

#### Scenario: A file write sends text, the effector encodes it

- **WHEN** a packet's `request.body` is `{"message": "m", "content": {"$ta.base64": "<text>"}}`
- **THEN** the request sent carries `content` as the base64 of the text's UTF-8
  bytes and no `$ta.` key remains

#### Scenario: Append one line without the model touching the file's bytes (the live case)

- **GIVEN** a branch with two nodes declaring `effects: ["authenticated_external_call"]`,
  `fetch` (a GET packet for the file) listed before `write`
- **WHEN** `write`'s body is
  `{"sha": {"$ta.effect": "fetch.response.body.sha"}, "content": {"$ta.base64": {"$ta.concat": [{"$ta.from_base64": {"$ta.effect": "fetch.response.body.content"}}, "<new line>\n"]}}}`
- **THEN** in ONE run the fetch fires, then the write sends base64 whose decoded
  bytes are exactly the fetched file plus the new line, and the model authored
  only the new line (2026-08-29 without this: `422 content is not valid Base64`,
  then `README.md +2/-87`, then a re-typed file `+22/-14`)

#### Scenario: A reference is fenced to what the node may see

- **WHEN** a packet uses `{"$ta.ref": "private"}` and `private` is not among the
  node's declared `input_keys`, schema-defaulted keys, or its own output keys
- **THEN** the call is refused with `invalid_body_transform`, the message names
  the key but not its value, and nothing is sent
- **AND** `{"$ta.effect": "later_node…"}` for a node listed after the emitting
  node, or with no such effect, is refused the same way

#### Scenario: A user's own `$`-keys are not transforms

- **WHEN** `request.body` contains `{"schema": {"$ref": "#/$defs/X"}}` or `{"$set": …}`
- **THEN** it is sent exactly as written

#### Scenario: A malformed transform is refused, not half-sent

- **WHEN** `request.body` contains `{"$ta.base64": 42}`, `{"$ta.from_base64": "not base64"}`,
  `{"$ta.ref": "no.such.key"}`, `{"$ta.concat": "x"}`, nesting past 32 levels,
  or a transformed body over 8 MiB
- **THEN** the effector returns its secret-free error dict and sends nothing
