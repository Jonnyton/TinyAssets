# Universe visibility

## ADDED Requirements

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
