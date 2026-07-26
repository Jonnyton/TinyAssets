## ADDED Requirements

### Requirement: Generic Platform Observation Has No Task-Dispatch Self-Heal

The uptime-and-alarms capability SHALL own a generically named platform observer
that reads public MCP observation freshness, open P0 outage state, Tier-3
clean-clone smoke, production deploy, website deploy, and recent revert-rate
evidence. It SHALL report per-stage and overall health, use the canonical
operational alarm/incident sink, and exit non-zero when a retained required
stage is red. The observer and its workflow SHALL NOT enqueue user work, select
a Goal canonical, dispatch another workflow as self-heal, execute a repair,
write wiki/repository content, or expose any `community-loop` or `auto-ship`
named product surface.

#### Scenario: A red retained stage reaches the alarm sink

- **WHEN** the platform observer classifies a retained required uptime or deploy
  stage as red
- **THEN** its overall result is red, its process exits non-zero, and the
  canonical alarm/incident sink receives the observation
- **AND** no workflow or task dispatch is attempted

#### Scenario: Healthy observation is read-only

- **WHEN** every retained required stage is green
- **THEN** the observer reports green and exits zero
- **AND** no user workflow, repository content, wiki content, or queue state is
  mutated

#### Scenario: Revert rate is classification evidence

- **WHEN** the observer evaluates recent REVERT activity
- **THEN** it classifies the rate into OK, WARN, or CRITICAL according to
  bounded thresholds
- **AND** the classification does not initiate corrective work

#### Scenario: Shipped artifact names are generic

- **WHEN** runtime, workflow, test, package, configuration, and current operator
  surfaces are scanned after the migration
- **THEN** the observer uses generic uptime/alarm names
- **AND** no executable or build artifact is named for the retired community
  patch loop
