## ADDED Requirements

### Requirement: Tray Starts One Credential-Neutral Host Daemon

The host tray SHALL start and supervise at most one credential-neutral daemon, persist only the auto-start toggle for daemon lifecycle, and expose no provider-start/provider-stop fleet controls. Provider assignment happens through the app/browser MCP setup surface.

The tray SHALL NOT pass `--provider` or any writer pin. It SHALL strip the complete canonical `AMBIENT_PROVIDER_AUTH_ENV_VARS` set from the child, matching the production entrypoint rather than maintaining a smaller desktop-only list. The daemon SHALL receive `TINYASSETS_DAEMON_INSTANCE_KEY=daemon` and the tray's absolute `TINYASSETS_DATA_DIR`.

#### Scenario: A second daemon start is refused

- **WHEN** the credential-neutral daemon is already alive and the tray receives another start request
- **THEN** it refuses the second start and creates no additional daemon process

#### Scenario: Spawned daemon is credential-neutral, not provider-pinned

- **WHEN** the tray starts a host daemon for the active universe
- **THEN** the child process receives no provider-selection argument or environment
- **AND** the ambient provider/credential environment variables are removed from the child
- **AND** the daemon resolves the universe's assigned serving credential at runtime and holds fail-closed when none is available

#### Scenario: Auto-start drives singleton startup

- **WHEN** saved preferences enable auto-start
- **THEN** the tray launches exactly one credential-neutral daemon during startup

## REMOVED Requirements

### Requirement: Tray Provider Controls Enforce Current Host Constraints

**Reason**: Provider-shaped tray processes and host provider selection are retired; credentials are assigned to workflows through the app/browser MCP.

**Migration**: Start one credential-neutral host daemon and manage workflow serving bindings through setup.
