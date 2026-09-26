## ADDED Requirements

### Requirement: An owner may open a receiver to any authenticated user
A receiver SHALL carry two independent owner-declared exposure flags, both
defaulting to closed: `open_to_all` (any authenticated principal may connect an
output and deliver) and `discoverable` (other users may find it). Neither SHALL be
expressible as a wildcard entry in `allowed_senders`; the permitted-sender list
SHALL continue to hold exact principal names only.

Closing a receiver SHALL take effect for in-flight senders at acceptance, not only
at connect time. A revoked receiver SHALL refuse delivery and SHALL NOT be
discoverable or inspectable regardless of either flag.

#### Scenario: A stranger delivers to an opened receiver
- **WHEN** an authenticated user who is not named in `allowed_senders` connects an
  output to a receiver its owner marked `open_to_all` and delivers
- **THEN** the delivery is accepted and executes under the receiver owner's authority
- **AND** the sender's principal and universe are recorded on the delivery

#### Scenario: A receiver that was never opened refuses a stranger
- **WHEN** the same user attempts to connect or deliver to a receiver with neither
  flag set and no matching `allowed_senders` entry
- **THEN** both are refused as not found, disclosing nothing about the receiver

#### Scenario: Opening does not disclose the owner's graph
- **WHEN** a stranger permitted by `open_to_all` inspects the receiver
- **THEN** the result carries only the advertised description, contract,
  generation, exposure flags and per-sender limit
- **AND** excludes the owner's branch id, node ids, snapshot, universe id, other
  permitted senders and every other delivery

### Requirement: A delivery carries its sender's identity to the receiving owner
Every accepted delivery SHALL be attributed to the authenticated sending principal
and the universe the send was made from. The receiving owner's side of the delivery
receipt SHALL disclose both; the sending side SHALL NOT gain any receiver-private
field by this.

A receiver's own branch MAY declare the reserved state fields
`delivery_sender_id` and `delivery_sender_universe_id`, which the platform SHALL
fill from server-side link authority at acceptance so the owner's downstream nodes
can act on the sender. Those names SHALL be refused in a receiver's advertised
`input_keys`, so no sender can supply or map onto them.

#### Scenario: The owner's graph reads who sent the deliverable
- **WHEN** a receiver's branch declares the reserved attribution fields and a
  delivery is accepted
- **THEN** the receiver's run inputs carry the sending principal id and universe id
- **AND** those values come from the stored link, never from the request payload

#### Scenario: A sender cannot claim another identity
- **WHEN** a sender attempts to include or map an output onto a reserved
  attribution field
- **THEN** the attempt is refused because the field cannot enter the contract

### Requirement: Deliveries to one receiver are rate limited per sender
Each receiver SHALL carry an owner-configurable maximum number of accepted
deliveries per sending principal per rolling window, with a safe default and
validated bounds. The limit SHALL be a usage bound only: it SHALL NOT cap the
number of receivers, nodes, links or contract fields.

The check SHALL run inside the acceptance transaction and before receiver resource
admission, so a refused sender consumes none of the owner's run budget. A retry of
an already-accepted occurrence SHALL neither consume budget nor be refused.
Refusal SHALL name itself rather than dropping the delivery silently.

#### Scenario: A sender exceeding the limit is refused by name
- **WHEN** one sender's accepted deliveries to a receiver reach its limit within
  the window and another new occurrence arrives
- **THEN** the delivery is refused with a reason naming the sender rate limit
- **AND** no run is reserved and no receiver admission ticket is spent

#### Scenario: Retrying an accepted occurrence is not new usage
- **WHEN** a sender at the limit retries an occurrence that was already accepted
- **THEN** the original receipt is returned and no second run is created
