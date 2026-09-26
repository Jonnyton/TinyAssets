## ADDED Requirements

### Requirement: Long-form served-agent guidance is reachable, not resident

A served founder turn is an agentic loop, so the engine tool-definition block is
re-sent on EVERY model round-trip of the turn. Long-form guidance for an engine
handle SHALL therefore be reachable on demand rather than carried in the advertised
description on every round, and relocation SHALL be verbatim: no guidance may be
trimmed, summarised or rewritten by a relocation, and no capability may be removed.

Guidance SHALL stay resident in the advertised description when its absence would
produce a WRONG call rather than an absent one — the handle's purpose, its
operation catalogue, any payload shape whose violation is only refused after the
attempt, and its parameter documentation. Everything else MAY move to a named
chapter.

The advertised description SHALL carry an index naming every chapter of that
handle and when to fetch it, so a handle never has guidance the agent cannot
discover from what it is already holding.

#### Scenario: the advertised description no longer carries the long-form chapters
- **WHEN** the served engine tool block is assembled for a round
- **THEN** a relocated chapter's text is absent from the advertised description
- **AND** the description still names that chapter and when to fetch it

#### Scenario: relocation preserves every byte
- **WHEN** a handle's chapters are concatenated back in their documented order onto its resident description
- **THEN** the result equals the guidance that handle carried before relocation, byte for byte

#### Scenario: guidance that prevents a wrong first call stays resident
- **WHEN** the resident description is assembled
- **THEN** the handle's purpose, its operation catalogue, its `Args:` documentation and any payload shape refused only after the attempt are present without a fetch

### Requirement: The engine read handle serves the handbook read-only

The engine `read_graph` SHALL accept `target="handbook"`, scoped to the calling
universe like every other engine read and carrying no effect. With no `query` it
SHALL return the index of handles and their chapters. With
`query="<handle>.<chapter>"` it SHALL return that chapter verbatim. An unknown
handle or chapter SHALL be refused with the available names rather than returning
empty, and the handbook SHALL never be writable through any handle.

#### Scenario: the index lists every chapter that exists
- **WHEN** the served agent reads `target="handbook"` with no query
- **THEN** it receives every handle that has chapters and every chapter name for each

#### Scenario: a chapter comes back verbatim
- **WHEN** the served agent reads `target="handbook"` with `query="<handle>.<chapter>"`
- **THEN** it receives that chapter's exact text, unchanged and untruncated

#### Scenario: an unknown name is refused, not answered emptily
- **WHEN** the served agent asks for a handle or chapter that does not exist
- **THEN** the read is refused and the refusal names what is available

### Requirement: The per-round guidance budget is ratcheted

The total advertised description text across the served engine handles SHALL be
bounded by a ratchet recorded in the test suite, because that text is
re-transmitted on every round-trip of every served founder turn on every account.
Raising the ratchet SHALL require stating the per-round latency cost.

#### Scenario: growing the block fails the gate
- **WHEN** the served handles' descriptions total more than the recorded ratchet
- **THEN** the suite fails and names the largest contributor and its size

### Requirement: Guidance relocation is one path for every account

Which guidance is resident and which is reachable SHALL NOT vary by account,
plan, tier, provider, source or universe. Every served turn assembles the same
block.

#### Scenario: no per-account variation
- **WHEN** the tool block is assembled for any universe on any source
- **THEN** the resident guidance and the chapter index are identical
