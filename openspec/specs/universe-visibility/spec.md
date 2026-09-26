# universe-visibility Specification

## Purpose
Define and enforce how universe existence, metadata, and content are exposed, including fail-closed
anonymous discovery and page-level narrowing.

## Requirements
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
owner-only universe write. Authority to expose a universe SHALL be OWNER
authority, strictly narrower than authority to edit it: a principal holding only
a `write` grant SHALL be refused. The change SHALL refuse an unrecognized level
naming the recognized set, SHALL refuse a caller whose token lacks write scope,
and SHALL record the owner as the provenance of the new level.

#### Scenario: The owner publishes

- **WHEN** a universe's owner sets its visibility to `public`
- **THEN** the declared level SHALL be `public`, its provenance SHALL record the
  owner's choice, and another authenticated user SHALL be able to read it.

#### Scenario: A non-owner attempts to expose someone else's universe

- **WHEN** an authenticated principal with no authority on a universe sets its
  visibility
- **THEN** the call SHALL be refused and the declared level SHALL be unchanged.

#### Scenario: A delegated writer attempts to publish

- **GIVEN** a principal holding a `write` grant on someone else's universe
- **WHEN** they set its visibility to `public`
- **THEN** the call SHALL be refused, the declared level SHALL be unchanged, and
  no owner provenance SHALL be recorded — editing a universe is not authority to
  decide who else may see it.

### Requirement: A level withholding content is enforced by every content reader

A reader that serves a universe's raw content SHALL gate on the `read_content`
capability, not on the legacy public-read bit alone. A level that withholds
content SHALL withhold it from every such reader, so that an owner selecting that
level is given the boundary it names.

#### Scenario: Raw activity lines under a metadata-only level

- **GIVEN** a universe its owner declared `metadata_only`
- **WHEN** an authenticated principal holding no grant on it reads a surface that
  returns raw log lines from that universe
- **THEN** the content SHALL be withheld, even though the legacy public-read bit
  is set to keep the level's metadata capabilities working.

### Requirement: Every universe declares an explicit visibility level

Every universe SHALL carry an explicit visibility level, and the platform SHALL fail closed when a
universe has no declared level rather than defaulting to visible. Legacy universes SHALL either be
assigned a level or carry a recorded reason for remaining as-is.

#### Scenario: Undeclared visibility does not default to open

- **GIVEN** a universe with no declared visibility level
- **WHEN** an unauthenticated reader attempts to discover or read it
- **THEN** the platform SHALL refuse rather than serve it as public.

### Requirement: Existence, metadata, and content are separately granted

Visibility SHALL express discovery of existence, reading of metadata, and reading of content as
separate capabilities. A level that withholds content SHALL NOT implicitly permit enumeration of the
universe's name, size, or activity dates.

#### Scenario: Enumeration is withheld when only content is public

- **GIVEN** a universe whose level permits content reads but not discovery
- **WHEN** an unauthenticated reader lists universes
- **THEN** that universe SHALL NOT appear in the listing, because existence is granted separately
  from content.

### Requirement: Visibility is enforced at both universe and page granularity

The platform SHALL evaluate visibility per universe and per page, so that a scope containing mixed
material cannot expose a restricted page through a permissive universe-level setting.

#### Scenario: A restricted page in an open universe stays restricted

- **GIVEN** an openly-discoverable universe containing one page marked more restrictively
- **WHEN** an unauthenticated reader reads that universe's pages
- **THEN** the restricted page SHALL be withheld while the rest are served.

### Requirement: A reader can tell what they are looking at

The platform SHALL make a universe's declared visibility observable to a reader that is permitted to
discover it, so that neither a person nor an agent has to infer the boundary from its absence.

#### Scenario: Visibility is stated, not inferred

- **GIVEN** an unauthenticated reader discovering a universe
- **WHEN** they inspect it
- **THEN** the declared visibility level SHALL be reported alongside the content they are permitted
  to see.
