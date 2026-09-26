# universe-visibility (delta)

## ADDED Requirements

### Requirement: A universe is private until its owner exposes it

Nothing in a user's universe SHALL be visible, accessible, or interactable to
another user unless the owner exposed it (founder, 2026-09-26). The platform
SHALL NOT declare an open level on a universe's behalf: creation without an
explicit level SHALL declare `private`, and the migration that declares legacy
undeclared universes SHALL declare `private` rather than deriving an open level
from any pre-existing default.

#### Scenario: A universe created without a stated level

- **GIVEN** an authenticated owner creating a universe and passing no visibility
- **WHEN** the universe is born
- **THEN** its declared level SHALL be `private`, and another authenticated user
  with no grant on it SHALL be refused discovery, metadata, and content.

#### Scenario: An owner is not limited by their own universe's privacy

- **GIVEN** a private universe
- **WHEN** its owner, or a holder of a read/write/admin grant on it, reads or
  writes it
- **THEN** access SHALL be permitted, because public-projection visibility binds
  only readers who hold no grant.

#### Scenario: A legacy undeclared universe

- **GIVEN** a universe with no declared level and a legacy public-read bit set
- **WHEN** the declaring migration runs
- **THEN** the universe SHALL be declared `private`, and the open legacy bit
  SHALL NOT be read as an owner's choice.

### Requirement: A declaration records whether its owner chose it

Every recorded visibility level SHALL carry the provenance of the decision, so
that a level chosen by an owner is distinguishable from one a default or a
migration supplied. A level with no recorded provenance SHALL be treated as
supplied, not chosen.

#### Scenario: A migration does not undo an owner's decision

- **GIVEN** a universe its owner explicitly exposed
- **WHEN** the private-by-default migration runs again
- **THEN** that universe SHALL NOT be flipped, because its provenance records an
  owner's choice.

### Requirement: An owner can expose their own universe

The platform SHALL provide the owner of a universe a way to change its declared
visibility level after birth, on the same surface they use for every other
owner-only universe write. The change SHALL be refused to a caller without write
authority on that universe, SHALL refuse an unrecognized level naming the
recognized set, and SHALL record the owner as the provenance of the new level.

#### Scenario: The owner publishes

- **WHEN** a universe's owner sets its visibility to `public`
- **THEN** the declared level SHALL be `public`, its provenance SHALL record the
  owner's choice, and another authenticated user SHALL be able to read it.

#### Scenario: A non-owner attempts to expose someone else's universe

- **WHEN** an authenticated principal with no write authority on a universe sets
  its visibility
- **THEN** the call SHALL be refused and the declared level SHALL be unchanged.
