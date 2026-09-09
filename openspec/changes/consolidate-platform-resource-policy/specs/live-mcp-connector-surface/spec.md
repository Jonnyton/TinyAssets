## ADDED Requirements

### Requirement: Authorized status explains platform resource observations
Existing authenticated status SHALL offer authorized universe-scoped resource
observations with timestamp, actual activity scope and limits, workspace
allocation/transport/storage distinctions, and explicit availability. Reads
SHALL create, migrate, reconcile and change nothing. No new handle or authority
SHALL be introduced.

#### Scenario: Owner asks about usage
- **WHEN** the app's pinned agent reads status for its authorized universe
- **THEN** it receives observed usage and actual policy scope without needing operator database access

#### Scenario: Meter is missing or unreadable
- **WHEN** a trustworthy observation cannot be obtained
- **THEN** the field is unknown or unavailable, not a fabricated zero, and independent status still works

#### Scenario: Canary or unrelated user reads status
- **WHEN** a caller is not authorized for private universe usage
- **THEN** no private counts, paths, run identifiers or holder identities are disclosed

#### Scenario: The oldest charge is about to expire
- **WHEN** status reports a rolling-window expiration
- **THEN** it gives a UTC next-charge-expiration instant and does not guarantee enough capacity for an unspecified future request
