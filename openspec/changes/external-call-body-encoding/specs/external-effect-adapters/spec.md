# External effect adapters — body transforms

## ADDED Requirements

### Requirement: The outbound packet can encode, decode, reference and join body text without the model carrying the bytes

The generic `authenticated_external_call` effector SHALL treat a one-key JSON
object anywhere inside `request.body` (object values and list elements) whose
key is one of `$ta.base64`, `$ta.from_base64`, `$ta.ref`, `$ta.effect`,
`$ta.concat` as a transform applied in the effector process before the wire
request reaches the credential-blind worker. The `$ta.` namespace SHALL be
reserved: any other one-key object whose key starts with `$ta.` is refused,
and every other key — a user's own `$ref`, `$set` — is sent as written.
`{"$ta.base64": X}` sends the base64 of X's UTF-8 bytes; `{"$ta.from_base64": X}`
yields the UTF-8 text of base64 X (whitespace-tolerant; bytes that are not
UTF-8 text are refused — text files); `{"$ta.ref": "key.a.0.b"}` yields a
value from the run's state whose root `key` MUST be one of the emitting node's
declared `input_keys` or a state_schema-defaulted key — narrower than the
compiler's render view, never the whole final state; `{"$ta.effect":
"node.response.body.x"}` yields `response.body` (traversed as JSON) or
`response.status` — never headers — from the evidence of a node STORED EARLIER
in the branch whose generic-call effect already fired in this run (effects
fire in storage order; `write_graph` appends nodes in the order given);
`{"$ta.concat": [X, …]}` joins texts. X MAY itself be a transform. JSON-encoded
strings are traversed and lists indexed. This SHALL be the only knowledge the
effector gains beyond shape: one encoding and the run it belongs to, never a
service.

Bounds SHALL refuse the whole call before anything is sent, as the effector's
secret-free error dict (`error_kind: invalid_body_transform`; paths and types
in the message, never values): a body nested deeper than 32 levels anywhere;
a cumulative working set over 32 MiB, charged as each value is produced so a
repeated reference is refused at the second copy rather than after
materialising them all; a transformed body over 8 MiB; a wrong type; an
unfenced, unresolvable or out-of-range path. A body containing no `$ta.*`
transform SHALL be sent byte-for-byte as today.

The effect evidence that is PERSISTED (and shown to a model through
`read_graph target="run"`) SHALL keep at most a 4 KiB preview of a response
body, with its size and sha256; the full body SHALL be available only to later
nodes' transforms within the same dispatch.

#### Scenario: A file write sends text, the effector encodes it

- **WHEN** a packet's `request.body` is `{"message": "m", "content": {"$ta.base64": "<text>"}}`
- **THEN** the request sent carries `content` as the base64 of the text's UTF-8
  bytes and no `$ta.` key remains

#### Scenario: Append one line without the model touching the file's bytes (the live case)

- **GIVEN** a branch with two nodes declaring `effects: ["authenticated_external_call"]`,
  `fetch` (a GET packet for the file) stored before `write`
- **WHEN** `write`'s body is
  `{"sha": {"$ta.effect": "fetch.response.body.sha"}, "content": {"$ta.base64": {"$ta.concat": [{"$ta.from_base64": {"$ta.effect": "fetch.response.body.content"}}, "<new line>\n"]}}}`
- **THEN** in ONE run the fetch fires, then the write sends base64 whose decoded
  bytes are exactly the fetched file plus the new line; the model authored only
  the new line; and the persisted fetch evidence holds a bounded preview of the
  file, not the file (2026-08-29 without this: `422 content is not valid Base64`,
  then `README.md +2/-87`, then a re-typed file `+22/-14`; #2691 reached `+1/-0`
  only on the third attempt)

#### Scenario: References are fenced to what the node may see

- **WHEN** a packet uses `{"$ta.ref": "private"}` and `private` is not among the
  node's declared `input_keys` or schema-defaulted keys
- **THEN** the call is refused with `invalid_body_transform`, the message names
  the key but not its value, and nothing is sent
- **AND** `{"$ta.effect": "fetch.response.headers.set-cookie"}` (a header),
  `{"$ta.effect": "later.response.body"}` (a node stored later), or an unknown
  node are refused the same way

#### Scenario: A user's own `$`-keys are not transforms, and unknown `$ta.*` keys are refused

- **WHEN** `request.body` contains `{"schema": {"$ref": "#/$defs/X"}}` or `{"$set": …}`
- **THEN** it is sent exactly as written
- **AND WHEN** it contains `{"$ta.bas64": "…"}`
- **THEN** the call is refused (`unknown transform`), never sent as payload

#### Scenario: Bounds refuse before allocation

- **WHEN** a body references a 5 MiB fetched blob a hundred times, or nests
  1,100 plain objects, or would serialize past 8 MiB
- **THEN** the call is refused with `invalid_body_transform` at the first
  bound crossed — the working-set charge, the depth scan, or the size check —
  never a crash (`effector_crashed`) and never a partially built body
