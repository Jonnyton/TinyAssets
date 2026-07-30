## ADDED Requirements

### Requirement: Scoped wiki canary bearer grants no general identity

The server SHALL recognize `TINYASSETS_WIKI_CANARY_TOKEN` only as request-local
authority for one exact, non-batch `write_page` call targeting
`drafts/notes/uptime-probe.md`; it SHALL keep the caller anonymous for every
generic authentication, OAuth-scope, founder, and permission check. The feature
SHALL be entirely disabled when the configured value is absent or contains
fewer than 32 UTF-8 bytes, and token comparison SHALL use a constant-time
primitive without logging bearer material.

#### Scenario: Exact reserved call receives narrow authority
- **WHEN** a bearer equal to a valid configured canary token accompanies the
  exact reserved `write_page` request shape
- **THEN** the request dispatches with only the dedicated canary-write authority
- **AND** the current identity remains anonymous

#### Scenario: Adjacent page and other action fail closed
- **WHEN** the same bearer targets any other filename, adds a routing argument,
  appears in a batch, or calls another authenticated action
- **THEN** the bearer grants no authority or identity and the existing
  invalid-token or anonymous-write rejection applies

#### Scenario: Missing or short configuration disables the feature
- **WHEN** `TINYASSETS_WIKI_CANARY_TOKEN` is unset, empty, or shorter than 32
  UTF-8 bytes
- **THEN** no presented bearer can activate canary authority
- **AND** the anonymous-write gate remains intact
