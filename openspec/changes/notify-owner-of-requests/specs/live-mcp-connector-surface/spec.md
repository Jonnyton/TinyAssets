# live-mcp-connector-surface (delta)

## ADDED Requirements

### Requirement: A request may carry answerable items
`write_graph target="pending_request" operation="ask"` SHALL accept an optional `items` list of at most 50 entries, each carrying an `item_id` matching `[a-z0-9][a-z0-9_.-]{0,63}` that is unique within the request, a title, an optional body, and optional non-secret fields. The stored request SHALL retain the supplied `item_id` values verbatim, and `read_graph target="pending_requests"` SHALL project each item with its current status and answer.

#### Scenario: One request holds several tasks
- **WHEN** the owner's universe asks with three items whose ids are `a`, `b` and `c`
- **THEN** one pending request is stored, and reading it returns those three ids with status `pending`

#### Scenario: A duplicate or malformed item id is refused
- **WHEN** an ask repeats an `item_id`, omits one, or supplies one that does not match the pattern
- **THEN** the ask is refused naming the offending field, and no request is stored

#### Scenario: Items beyond the bound are refused
- **WHEN** an ask carries more than 50 items
- **THEN** the ask is refused stating the bound, and no request is stored

#### Scenario: Items satisfy the at-least-one-field rule
- **WHEN** an ask carries no top-level fields and at least one item that carries a field
- **THEN** the ask is accepted, rather than refused for having no field

### Requirement: Items do not change the identity of a request without them
A request's deduplication identity SHALL include its items only when it has items, so a request with none keeps the identity it had before items existed. An existing pending request SHALL still deduplicate, and an existing standing decision SHALL still match.

#### Scenario: A standing decision survives
- **WHEN** an owner dismissed a request with "don't ask me this again", and the identical request with no items is asked afterwards
- **THEN** the ask is refused as already settled and no new request is stored

#### Scenario: An itemised ask is its own question
- **WHEN** the same kind, title and body are asked once without items and once with them
- **THEN** they are two distinct requests

### Requirement: An item never carries a credential
The ask SHALL refuse a `secret` field inside any item, and SHALL refuse `items` on any request whose `action.type` is not `answer`. A secret value SHALL never be written to the request store or to an item answer.

#### Scenario: A secret field inside an item is refused
- **WHEN** an ask carries an item with a field of type `secret`
- **THEN** the ask is refused and no request is stored

#### Scenario: Items on a deposit request are refused
- **WHEN** an ask carries `items` together with a `connect_http`, `connect`, `rotate_http`, `extend_http` or `remove_http` action
- **THEN** the ask is refused stating that items are only available on an `answer` request

### Requirement: The owner answers the whole request or one item
The answer path SHALL accept an optional `item_id`, resolving exactly that item and leaving the request `pending` unless it was the last unresolved item. An item SHALL resolve at most once. When every item is resolved the request SHALL resolve as `answered` carrying the per-item answers. A whole-request answer or dismiss SHALL close the request and report the remaining items as unanswered rather than inventing answers for them.

#### Scenario: Answering one item leaves the rest waiting
- **WHEN** the owner answers item `a` of a three-item request
- **THEN** item `a` reads as answered with its values, and the request is still `pending` with `b` and `c` waiting

#### Scenario: An item of an edited request is not answered
- **WHEN** a request's stored items no longer reproduce what the owner was shown, and one of its items is answered
- **THEN** the answer is refused naming that the request changed, and neither the item nor the request is resolved

#### Scenario: The same item cannot be answered twice
- **WHEN** the owner submits an answer for item `a` twice
- **THEN** the second submission reports that the item is already resolved and does not overwrite the first answer

#### Scenario: The last item closes the request
- **WHEN** the owner answers the final unresolved item
- **THEN** the request resolves as `answered` and its answer carries every item's values

#### Scenario: A whole-request answer does not fabricate item answers
- **WHEN** the owner answers the request as a whole with two items still unresolved
- **THEN** the request is `answered` and those two items are reported as unanswered

### Requirement: A background run raises a request as its owner
A run executing under the owner's bound run identity SHALL be able to raise a request in that owner's own universe through the engine surface, and that request SHALL be indistinguishable in the rail from one raised in a chat turn. A caller that is not an `admin` of the named universe SHALL receive the uniform absent-resource refusal.

#### Scenario: An automation's run asks its owner
- **WHEN** a branch run bound to the owner raises an ask with items
- **THEN** the request is stored in that owner's universe and reads back through the owner's own surface

#### Scenario: A run in another user's universe asks nothing
- **WHEN** a run bound to one user names another user's universe on the ask
- **THEN** the ask is refused with the uniform absent-resource envelope and no request is stored anywhere
