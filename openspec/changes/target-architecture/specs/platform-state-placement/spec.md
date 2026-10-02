## ADDED Requirements

### Requirement: Platform state lives outside every agent environment

Every platform-owned record SHALL live under the cell's platform root,
resolved only through `PlatformStatePaths`. That covers the credential vault;
the run, consent, usage, attention, conversation and session stores; rules;
auto-review results; activity records; pending effects; proposals; import
quarantine; the browser profile; and locks and stamps. No box, jail, extension
process or browser sandbox SHALL mount or reach the platform root. The platform
SHALL refuse to open a platform store found inside a command center's files.

#### Scenario: A pre-created consent database is refused
- **WHEN** an agent creates a file named like the consent database inside its command center's files, carrying an active consent row
- **THEN** the platform never opens it, and the external-call consent gate still reads only the platform-root store

#### Scenario: No agent environment sees the vault
- **WHEN** any process in any box or jail lists or opens every path it can reach
- **THEN** no platform-root file is among them

### Requirement: Cross-user transactional domains live in Postgres; per-account state stays in per-account SQLite

The catalog, ledger, inbox and market SHALL be stored in Postgres behind
`TransactionalStore`. A cell's effects on them SHALL be written through the
cell's transactional outbox, in the same transaction as their cause. State
owned by one account SHALL stay in that account's SQLite stores, opened through
`store_for(account)`.

#### Scenario: A market effect survives a crash
- **WHEN** a cell commits a turn that records a market listing and crashes before pumping
- **THEN** the outbox row survives, and the listing reaches Postgres exactly once after restart

### Requirement: SQLite stores meet a version floor and replicate continuously off-region

Every runtime image SHALL link SQLite 3.51.3 or later, and SHALL assert it at
startup, refusing to start below the floor. Every SQLite store SHALL replicate
continuously to off-region object storage with point-in-time restore. Exactly
one writer SHALL hold a replica path.

#### Scenario: An old SQLite refuses to start
- **WHEN** an image linking SQLite 3.46.1 starts
- **THEN** startup fails loudly, naming the floor

#### Scenario: A regional loss is recoverable
- **WHEN** the primary region is lost
- **THEN** every SQLite store restores from the off-region replica to within seconds of the loss
