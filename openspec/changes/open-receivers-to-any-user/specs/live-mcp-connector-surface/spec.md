## ADDED Requirements

### Requirement: Any authenticated user can discover an opened receiver
The canonical handle set SHALL remain the existing six. Discovery SHALL be reached
as an additional `read_graph` target backed by a new extensions read action, not a
new top-level tool.

An authenticated caller SHALL be able to list or substring-search receivers whose
owners marked them discoverable, receiving the sender view only. A receiver its
owner did not mark discoverable SHALL NOT appear in any result, and neither SHALL
a revoked one. The result SHALL be bounded by an explicit limit.

#### Scenario: A user finds a peer's receiver without being told its id
- **WHEN** an authenticated user reads the discovery target, optionally with search text
- **THEN** each result carries the receiver id, owner label, description, contract,
  generation and exposure flags
- **AND** carries no owner branch id, node id, snapshot or universe id

#### Scenario: A closed receiver is not findable
- **WHEN** a receiver's owner has not marked it discoverable
- **THEN** it is absent from every other user's discovery result, with or without
  search text matching its description

#### Scenario: Discovery is attributable
- **WHEN** a caller without a current authenticated principal and admin authority
  on their own universe reads the discovery target
- **THEN** the read is refused

### Requirement: The served surface teaches delivering between universes
The exposure fields SHALL be documented on the connector and served
`write_graph` descriptions. The long-form procedure — build a receiver on your own
step, open it, find other people's, connect an output, deliver, read the receipt —
SHALL be reachable as a `write_graph` handbook chapter named in the resident
chapter index, and the behavioral prompt SHALL point at it where an agent looks
when a user asks to let other users send them something.

The guidance SHALL be vendor-neutral and SHALL NOT be written toward one use such
as bug reports, so it does not narrow what users build on the primitive.

#### Scenario: An agent asked to accept work from other users finds the primitive
- **WHEN** a user asks their universe to let any other user send it something
- **THEN** the served guidance names the receiver primitive and how to open it
- **AND** does not require the agent to mint a public unauthenticated endpoint

#### Scenario: The handbook and its index agree
- **WHEN** the handbook index is read
- **THEN** it names the delivering chapter, and that chapter is fetchable verbatim
  through the read handle
