## ADDED Requirements

### Requirement: Platform state lives only under the universe's runtime directory
Every platform-owned file or directory of a universe SHALL be resolved through one function to a location under `.runtime/state/`, created without following links, and the daemon SHALL NOT read any platform-owned name from the universe root once that universe has migrated. The universe's tool jail SHALL bind the universe root read-write only for a migrated universe, with `.runtime/` masked from the jail.

#### Scenario: an agent-planted platform file grants nothing
- **WHEN** the agent creates a file at its universe root with the name of a platform database, such as a consent store
- **THEN** no daemon decision reads it, and authority is unchanged

#### Scenario: the agent writes anywhere in its own root
- **WHEN** the agent of a migrated universe writes a new file at its root
- **THEN** the write succeeds, and the file is the user's

#### Scenario: migration refuses a link
- **WHEN** a legacy platform entry at the universe root is a symbolic link
- **THEN** migration removes the link without following it, and nothing outside the universe is read or moved
