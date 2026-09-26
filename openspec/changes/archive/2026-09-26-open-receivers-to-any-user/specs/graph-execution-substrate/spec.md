## ADDED Requirements

### Requirement: An owner may open a receiver to any authenticated user
A receiver SHALL carry two independent owner-declared exposure flags, both
defaulting to closed: `open_to_all` (any authenticated principal may connect an
output and deliver) and `discoverable` (other users may find it). Neither SHALL be
expressible as a wildcard entry in the permitted-sender list, which SHALL continue
to hold exact principal names only.

An update SHALL PRESERVE any exposure field it does not name, and closing an
exposure SHALL require an explicit false. A value that is neither a boolean nor
absent SHALL be refused rather than coerced. Closing SHALL take effect for
in-flight senders at acceptance, not only at connect time. A revoked receiver
SHALL refuse delivery and SHALL NOT be discoverable or inspectable regardless of
either flag.

#### Scenario: A stranger delivers to an opened receiver
- **WHEN** an authenticated user not named in the permitted-sender list connects an
  output to a receiver its owner marked `open_to_all` and delivers
- **THEN** the delivery is accepted and executes under the receiver owner's authority
- **AND** the sender's principal and universe are recorded on the delivery

#### Scenario: A receiver that was never opened refuses a stranger
- **WHEN** the same user attempts to connect or deliver to a receiver with neither
  flag set and no matching permitted-sender entry
- **THEN** both are refused as not found, disclosing nothing about the receiver

#### Scenario: An unrelated edit does not change exposure
- **WHEN** an owner updates a receiver's contract or description without naming the
  exposure fields
- **THEN** the exposure flags and the per-sender limit are preserved
- **AND** a tightened limit is never silently restored to the default

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

A receiver's own branch MAY declare reserved attribution state fields, which the
platform SHALL fill from server-side link authority at acceptance so the owner's
downstream nodes can act on the sender. Those names SHALL be refused in a
receiver's advertised input contract, and SHALL additionally be refused at
acceptance when present in an already-stored contract, so no sender can supply,
map onto, or substitute a file reference into them. A declared attribution field
SHALL count as platform-supplied for exposure preflight, so declaring one without
a default does not make the receiver unexposable.

#### Scenario: The owner's graph reads who sent the deliverable
- **WHEN** a receiver's branch declares the reserved attribution fields and a
  delivery is accepted
- **THEN** the receiver's run inputs carry the sending principal id and universe id
- **AND** those values come from the stored link, never from the request payload

#### Scenario: A sender cannot claim another identity
- **WHEN** a sender attempts to include or map an output onto a reserved
  attribution field
- **THEN** the attempt is refused because the field cannot enter the contract

#### Scenario: A stored contract naming a reserved field cannot receive
- **WHEN** a receiver whose stored contract advertises a reserved attribution name
  is delivered to
- **THEN** acceptance refuses and names the field for its owner to rename
- **AND** no delivery, run or file copy is created

#### Scenario: A retry is validated on sender content alone
- **WHEN** a sender retries an accepted occurrence with identical content
- **THEN** the original receipt is returned and no second run is created
- **AND** platform-supplied attribution is carried forward from the stored record
  rather than recomputed, so a delivery accepted before attribution existed still
  replays

### Requirement: Deliveries to one receiver are rate limited per sender
Each receiver SHALL carry an owner-configurable maximum number of accepted
deliveries per sending principal per rolling window, with a safe default and
validated bounds, and SHALL NOT offer an unlimited setting. The limit SHALL be a
usage bound only: it SHALL NOT cap the number of receivers, nodes, links or
contract fields, and separate receivers SHALL carry separate budgets.

The limit SHALL be keyed on the sending principal alone, so founding additional
universes does not multiply an allowance. The check SHALL run inside the
acceptance transaction and before receiver resource admission, and additionally
before any cross-owner file copy, so a refused sender consumes neither the owner's
run budget nor its storage. A retry of an already-accepted occurrence SHALL neither
consume budget nor be refused. Refusal SHALL name itself and its numbers rather
than dropping the delivery silently.

#### Scenario: A sender exceeding the limit is refused by name
- **WHEN** one sender's accepted deliveries to a receiver reach its limit within
  the window and another new occurrence arrives
- **THEN** the delivery is refused with a reason naming the sender rate limit
- **AND** no run is reserved and no receiver admission ticket is spent

#### Scenario: A refused sender copies no bytes
- **WHEN** a sender past the limit sends a new occurrence carrying a file reference
- **THEN** the refusal precedes the copy and the receiving owner gains no custody object

#### Scenario: One sender's limit does not lock out another
- **WHEN** one sender exhausts its allowance on a receiver
- **THEN** a different sender's first delivery to that receiver is still accepted
