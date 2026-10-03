## ADDED Requirements

### Requirement: Platform state that decides authority is not writable by the party it decides about

Platform state the daemon reads to decide what a command center is permitted to do SHALL NOT live inside that command center's folder, because the command center's own processes can write there. It SHALL live under the daemon-owned per-command-center sidecar directory, which no jail binds. A database found at a former in-folder path SHALL NOT be adopted as authoritative.

#### Scenario: A command center cannot forge its own consent
- **GIVEN** a command center whose own processes create an effector-consent database in its folder, holding a row granting an effect its owner never approved
- **WHEN** an effect is dispatched and the consent gate is consulted
- **THEN** the gate reads the daemon-owned sidecar database, the planted file is never adopted, and the effect is refused for want of consent

#### Scenario: A planted link at the old name changes nothing
- **WHEN** a link is planted at the former in-folder database name, pointing at another command center's database
- **THEN** the consent answer is unaffected, because the name is no longer read

### Requirement: The enumeration of what may stay is enforced, not written down

A test SHALL assert that no platform path helper resolves inside a command-center folder, with an explicit allowlist for state a command center's own code must read through its jail. A store added later SHALL fail that test rather than silently join the problem, and the account-deletion sweep SHALL be derived from the same enumeration so a relocated store cannot be missed.

#### Scenario: A new store placed inside a command center fails
- **WHEN** a path helper is added or changed so that it resolves inside a command-center folder, and it is not on the allowlist
- **THEN** the enumeration test fails and names the helper

#### Scenario: Deleting an account leaves no sidecar
- **WHEN** an account is deleted
- **THEN** no file belonging to any of its command centers remains under the sidecar directory

### Requirement: The move is one-way, resumable, and refuses an unaccountable state

The migration SHALL run under the exclusive data-layout lock before any role opens the data, and the layout marker SHALL refuse an image that predates the move. For each command center it SHALL be idempotent. Where both the in-folder and the sidecar database exist it SHALL refuse that command center loudly and change nothing, because that state is either an interrupted run or a planted file and guessing is how a forged file gets blessed. A migrated in-folder file SHALL be renamed aside rather than deleted, so the prior state is recoverable.

#### Scenario: Running the migration twice changes nothing
- **WHEN** the migration runs on a volume it has already migrated
- **THEN** it makes no change and the roles start

#### Scenario: An interrupted migration does not half-apply
- **WHEN** the migration is killed part-way through
- **THEN** the layout marker records that the move is in progress, and the next start resumes it before any role opens the data

#### Scenario: Both copies present is a refusal, not a merge
- **WHEN** a command center has both an in-folder and a sidecar database
- **THEN** the migration refuses that command center by name and leaves both files untouched

### Requirement: Carrying existing rows forward is disclosed to the owner

Because no provenance record exists for consent rows written before this change, the migration cannot prove an existing row was granted by the owner. Where rows are carried forward, the owner SHALL be shown once what was carried, so anything they do not recognise can be revoked. The alternative — carrying nothing and requiring every consent to be granted again — SHALL remain available as a one-line configuration of the same migration.

#### Scenario: The owner is told what survived the move
- **WHEN** the migration carries existing consent rows into the sidecar database
- **THEN** the owner is shown a one-time list of the effects and destinations carried forward, and may revoke any of them
