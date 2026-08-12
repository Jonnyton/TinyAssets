# desktop-host-runtime Specification

## Purpose
Define the current source-installed desktop host, including tray supervision, provider controls, launcher/dashboard integration, notifications, and shortcut utilities without claiming a packaged installer.
## Requirements
### Requirement: The Source Tray Owns One Host Control Process Per Lock Path

The source-shipped `tinyassets_tray.py` entry point SHALL acquire the checkout-local `logs/.tray.lock` before starting its tray manager, and a second launch using that same lock path while it is held SHALL exit successfully without starting another manager. The tray manager SHALL launch and supervise provider-pinned daemon subprocesses, the local MCP server, and the optional tab watchdog; it MUST leave the local Cloudflare tunnel disabled unless `TINYASSETS_TRAY_ENABLE_TUNNEL` is explicitly truthy and a tunnel token is available. The current lock does not prevent a second source checkout from starting its own manager. As-built limitation: this is a source-installed Windows-first runtime; the repository does not ship a one-click installer, and macOS/Linux tray packaging is not claimed.

#### Scenario: Double-launch is harmless

- **WHEN** the tray entry point cannot acquire its checkout-local lock because another tray process using the same lock path holds it
- **THEN** it reports that TinyAssets Server is already running and returns exit code zero
- **AND** it does not construct or run a second `UniverseServerManager`

#### Scenario: Local tunnel is opt-in

- **WHEN** the tray starts with `TINYASSETS_TRAY_ENABLE_TUNNEL` unset or false
- **THEN** it starts no `cloudflared` process and records the tunnel as down
- **AND** the daemon and local MCP startup paths remain available

### Requirement: The Tray And Its Children Share One Active Universe Root

The host tray SHALL resolve its universe root through `tinyassets.storage.data_dir`, read and maintain `.active_universe` under that root, and pass the same absolute root to daemon and MCP subprocesses. If the marker is absent or invalid, it SHALL choose the first sorted universe containing `PROGRAM.md`, then the first sorted non-hidden directory, and finally `default-universe`. While running, a valid marker change SHALL switch the active universe and restart the auto-start provider daemons against the newly selected directory.

#### Scenario: Startup recovers an active universe without a marker

- **WHEN** the data root has no valid `.active_universe` marker and contains a universe directory with `PROGRAM.md`
- **THEN** the tray selects that directory and writes its name to the marker

#### Scenario: Marker change switches daemon scope

- **WHEN** `.active_universe` changes to the name of another directory under the shared data root
- **THEN** the tray updates its active universe, stops the current provider daemons, and starts the configured defaults with `--universe` pointing inside that same data root

### Requirement: Tray Health Is Observable And Supervised

The tray SHALL distinguish process liveness from HTTP readiness for the MCP and public tunnel, surface daemon, MCP, tunnel, watchdog, universe, and provider state in its menu and hover text, and close daemon log handles when their processes exit or are stopped. The background monitor SHALL restart a previously-started MCP server, tunnel, or watchdog after process death with bounded backoff, but it SHALL NOT manufacture a healthy state when an HTTP probe fails. A fresh per-universe `.runtime_status.json` MAY supply best-effort provider detail only when no tray-managed daemon is visible; stale or malformed status SHALL be ignored, while a parseable naive timestamp SHALL be interpreted as UTC before freshness is checked.

#### Scenario: Dead daemon is reaped

- **WHEN** a tracked daemon subprocess exits
- **THEN** the health check removes it from the running-provider set and closes its log handle
- **AND** the tray no longer represents that daemon as alive

#### Scenario: MCP process is alive but not ready

- **WHEN** the MCP subprocess is running but the local HTTP probe has not succeeded
- **THEN** the tray reports MCP as loading rather than serving
- **AND** the public endpoint action remains unavailable

#### Scenario: Fresh external runtime status fills only the visibility gap

- **WHEN** no tray-managed daemon is alive and the active universe has a valid runtime-status payload updated within 30 seconds
- **THEN** the hover text may display its pinned or active provider label
- **AND** that payload does not replace the tray's subprocess set as the authority for managed daemon liveness

### Requirement: Desktop Components Expose Launcher, Dashboard, Tray, And Notification Behavior

The `tinyassets.desktop` package SHALL provide a launcher that selects or creates a universe, starts the daemon off the UI thread, supports pause/resume and reload controls, and can hide to a tray binding. Its dashboard handler SHALL translate daemon events and overview snapshots into metrics for progress, dispatcher, queue, and earnings panes. The host tray service SHALL multiplex multiple dashboard bindings onto one shared tray icon, and removing the last binding SHALL stop that icon. Desktop notifications MUST degrade to logging when no tray exists or tray delivery fails, rather than propagating the notification failure into daemon work.

#### Scenario: Multiple dashboards share one tray

- **WHEN** two dashboards bind to the host tray service
- **THEN** the service starts one tray icon and exposes both dashboard entries through it
- **AND** unregistering the final dashboard stops the shared tray

#### Scenario: Dashboard events update user-visible progress

- **WHEN** the dashboard handler receives scene, chapter, judge, stuck-recovery, or error events
- **THEN** it updates the corresponding metrics, tray state, notification, or activity-feed line defined for that event
- **AND** an unknown event is ignored without crashing the daemon

#### Scenario: Notification delivery is best-effort

- **WHEN** a completion or error notification is emitted without a tray, or the tray notification call raises
- **THEN** the notification manager logs the message and does not propagate the delivery error

### Requirement: Desktop Shortcut Creation Is A Source Utility

The desktop shortcut utility SHALL create a Windows desktop launcher for the repository's GUI entry point, preferring a `.lnk` through the Windows Script Host and falling back to a `.bat` file when COM shortcut creation is unavailable. It MUST reference the current Python GUI interpreter and bundled icon when those are resolved from the source checkout. This utility SHALL NOT be represented as a packaged installer or an automatic installation flow.

#### Scenario: Windows shortcut helper is unavailable

- **WHEN** the optional `winshell` helper needed to create a Windows `.lnk` is not installed
- **THEN** it writes a desktop `.bat` launcher targeting the source entry point
- **AND** it returns the path of the fallback shortcut

### Requirement: The installed GUI entrypoint is the TinyAssets launcher with tunnel off by default
The package SHALL publish the `tinyassets` GUI command as `tinyassets.desktop.launcher:main`. Starting through that installed GUI entrypoint SHALL construct the local daemon through the launcher without supplying a tunnel request; the legacy repository-local `tinyassets.pyw` helper remains a distinct source launcher that explicitly supplies `--tunnel`.

#### Scenario: Installed GUI command resolves to the canonical launcher
- **WHEN** packaging metadata for GUI scripts is inspected
- **THEN** the `tinyassets` command resolves to `tinyassets.desktop.launcher:main` and no `workflow` GUI command is canonical

#### Scenario: Installed launcher starts without a tunnel flag
- **WHEN** a user starts the installed `tinyassets` GUI command
- **THEN** the launcher starts its daemon controller without requesting an API tunnel

#### Scenario: Legacy source launcher remains explicit
- **WHEN** a developer directly runs the repository-local `tinyassets.pyw`
- **THEN** that helper supplies `--tunnel` explicitly and does not redefine the installed GUI default

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
