## MODIFIED Requirements

### Requirement: Declared node effects dispatch at node time and a failed effect fails its node

As each node of a Branch run completes, the runtime SHALL inspect that node's
declared `effects`, find matching packets only in the node's declared output
keys (rendered against the state merged with the node's delta), and dispatch
the registered sink adapter before the next node runs. The full result SHALL
be kept in memory for the rest of the run so a later node may reference an
earlier node's `response.status` / `response.body` (`$ta.effect`) only when
that node is a graph ancestor; persisted evidence stays bounded. A packet MAY
declare `accept_statuses` (a list of integers) at its top level; a delivered
call answered ≥ 400 with a status not in that list, a packet refused before
the wire, an adapter crash or an unknown sink SHALL fail the node and the run
(`external write failed - <node>/<sink>: <error> [<kind>]`), and later nodes
SHALL NOT run. Each node's effects fire at most once per run. The post-run
dispatcher remains only for callers that compile without an effect chain and
SHALL NOT run for a chain-compiled run. All other clauses of this requirement
are unchanged.

#### Scenario: a later node reads an ancestor's full body
- **WHEN** node `fetch` delivered a 6.8 KB document and node `edit` (a graph descendant) references `fetch.response.body.content`
- **THEN** the reference resolves to the full body, not the 4 KiB persisted preview

#### Scenario: a sibling cannot be referenced
- **WHEN** two nodes fan out from the same parent and one references the other's effect
- **THEN** the packet is refused as `invalid_body_transform` naming the missing ancestor, every run, regardless of which sibling ran first

### Requirement: The outbound packet can encode, decode, reference and join body text without the model carrying the bytes

The `$ta.*` transform vocabulary (`$ta.base64`, `$ta.from_base64`, `$ta.ref`,
`$ta.effect`, `$ta.concat`, `$ta.replace`) is FROZEN as of this change: it
SHALL NOT be extended. A new edit shape is a code node. All clauses of this
requirement are otherwise unchanged.

#### Scenario: a code node's output feeds the next packet
- **WHEN** a code node returns `{"content": <text>, "sha": <sha>}` under its declared `output_keys` and the next node's packet body uses `{"$ta.base64": {"$ta.ref": "content"}}` with `content` in its `input_keys`
- **THEN** the write carries the code node's text, base64-encoded by the effector, and the model never carried the bytes
