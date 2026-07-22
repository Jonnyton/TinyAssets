# Shared Goals and Convergence

## ADDED Requirements

### Requirement: Private Goal reads are owner-only

Goal read actions SHALL enforce `visibility=private` using the authenticated
viewer resolved from signed request context. Anonymous callers and authenticated
non-owners SHALL NOT receive another actor's private Goal through listing,
search, or direct lookup. A caller-supplied field and the
`UNIVERSE_SERVER_USER` environment value MUST NOT confer read authority.

#### Scenario: Anonymous list and search omit private Goals

- **GIVEN** a private Goal authored by Alice
- **WHEN** an anonymous caller lists Goals or searches for content unique to it
- **THEN** the private Goal SHALL be absent from results and counts

#### Scenario: Anonymous direct lookup does not disclose existence

- **GIVEN** a private Goal authored by Alice
- **WHEN** an anonymous caller reads that exact `goal_id`
- **THEN** the response SHALL use the same not-found envelope as a missing Goal

#### Scenario: Environment attribution does not grant read access

- **GIVEN** an anonymous request and `UNIVERSE_SERVER_USER=Alice`
- **WHEN** the caller reads Alice's private Goal
- **THEN** the Goal SHALL remain inaccessible because no signed request identity exists

#### Scenario: The signed-in owner can read their private Goal

- **GIVEN** a private Goal authored by Alice and a request signed as Alice
- **WHEN** Alice lists, searches, or directly reads that Goal
- **THEN** the Goal SHALL be returned with the existing Goal response shape
