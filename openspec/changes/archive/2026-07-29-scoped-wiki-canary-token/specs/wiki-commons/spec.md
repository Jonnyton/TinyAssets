## ADDED Requirements

### Requirement: Reserved canary authority writes one fixed draft

The wiki subsystem SHALL route dedicated canary authority only to
`drafts/notes/uptime-probe.md`, SHALL reject any non-exact `write_page` argument
shape at the tool boundary, and SHALL NOT redirect that authority to a promoted
page, patch, filing, universe page, custom category, or alternate filename.

#### Scenario: Reserved draft is written
- **WHEN** dedicated canary authority reaches `write_page` with category
  `notes`, filename `uptime-probe`, content, and `dry_run=false`
- **THEN** the server writes exactly `drafts/notes/uptime-probe.md`
- **AND** the response reports that exact relative path

#### Scenario: Scope mutation cannot reach an adjacent path
- **WHEN** any routing argument differs from the reserved full-write shape
- **THEN** the dedicated authority is not accepted
- **AND** no wiki path is mutated under that authority
