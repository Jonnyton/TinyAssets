## MODIFIED Requirements

### Requirement: Tray Provider Controls Enforce Current Host Constraints

The host tray SHALL list the providers known to `tinyassets.preferences`, allow a user to start or stop the host, persist one default provider plus the auto-start toggle, and start configured defaults with local providers ordered first. It SHALL reject unknown providers and SHALL reject a second distinct local provider while one local provider is running.

Spawned daemons SHALL be credential-neutral: the tray SHALL NOT pass `--provider` and SHALL NOT set `TINYASSETS_PIN_WRITER`. Instead it SHALL strip the ambient provider/credential environment (`TINYASSETS_PIN_WRITER`, `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_OAUTH_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) from the child so the daemon cannot inherit a host credential, and each daemon SHALL resolve every universe's own assigned serving credential at runtime (credential-driven execution). Every spawned daemon SHALL still receive a distinct `TINYASSETS_DAEMON_INSTANCE_KEY` and the tray's absolute `TINYASSETS_DATA_DIR`. The provider list the tray shows is a preference surface only; provider selection no longer pins the spawned daemon.

#### Scenario: A second local provider is refused

- **WHEN** one provider classified as local is alive and the user starts a different local provider
- **THEN** the tray refuses the second start and creates no daemon process for it

#### Scenario: Spawned daemon is credential-neutral, not provider-pinned

- **WHEN** the tray starts a host daemon for the active universe
- **THEN** the child process receives neither `--provider` nor `TINYASSETS_PIN_WRITER`
- **AND** the ambient provider/credential environment variables are removed from the child
- **AND** the daemon resolves the universe's assigned serving credential at runtime and holds fail-closed when none is available

#### Scenario: Preferences drive startup

- **WHEN** saved preferences enable auto-start and name known default providers
- **THEN** the tray returns those providers in local-first order and launches the host during startup
- **AND** unknown saved provider names are ignored
