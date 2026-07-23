## ADDED Requirements

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
