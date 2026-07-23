## ADDED Requirements

### Requirement: The installed GUI command uses the current platform name

Package metadata SHALL publish the GUI command `tinyassets` and SHALL resolve it to `tinyassets.desktop.launcher:main`. It MUST NOT publish the retired product name `workflow` as a GUI-command compatibility alias. This command contract covers the source-installed desktop launcher only; it MUST NOT be treated as proof of a packaged one-click installer or supported tray packaging on every operating system.

#### Scenario: Installed GUI entry points are inspected

- **WHEN** a caller reads the `[project.gui-scripts]` table from `pyproject.toml`
- **THEN** the table maps `tinyassets` to `tinyassets.desktop.launcher:main`
- **AND** it contains no `workflow` GUI command

#### Scenario: The GUI command is used as install evidence

- **WHEN** an operator verifies the current source-installed desktop entry point
- **THEN** the `tinyassets` command is valid evidence for the launcher entry point
- **AND** that evidence alone does not claim a one-click installer or cross-platform tray package
