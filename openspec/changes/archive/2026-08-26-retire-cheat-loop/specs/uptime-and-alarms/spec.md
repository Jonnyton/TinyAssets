## ADDED Requirements

### Requirement: Generic Platform Observation Has No Task-Dispatch Self-Heal

The uptime-and-alarms capability SHALL own a generically named platform observer
that reads public MCP observation freshness, open P0 outage state, Tier-3
clean-clone smoke, production deploy, website deploy, and recent revert-rate
evidence. It SHALL report bounded per-stage/overall evidence to stdout or a
generic read-only artifact and exit non-zero when a retained required stage is
red. The observer SHALL NOT write the alarm/incident sink itself. An
independently owned alarm-sink consumer MAY consume the bounded output under
its own narrow incident authority. Neither component SHALL enqueue user work,
select a Goal canonical, dispatch another workflow as self-heal, execute a
repair, write wiki/repository content, or expose any `community-loop` or
`auto-ship` named product surface.

The observer job SHALL have only required read permissions such as
`contents:read`, `actions:read`, and metadata. It MUST NOT receive
`actions:write`, `contents:write`, `issues:write`, `pull-requests:write`, or a
write-capable reusable/manual input. A distinct alarm-sink job MAY receive
`issues:write` only when required by the canonical incident owner and SHALL
receive no workflow-dispatch or repository-content authority.

#### Scenario: A red retained stage reaches the alarm sink

- **WHEN** the platform observer classifies a retained required uptime or deploy
  stage as red
- **THEN** its overall result is red, its process exits non-zero, and the
  bounded evidence is available to the independent alarm-sink consumer
- **AND** the observer itself performs no issue, workflow, task, repository, or
  wiki mutation

#### Scenario: Healthy observation is read-only

- **WHEN** every retained required stage is green
- **THEN** the observer reports green and exits zero
- **AND** no user workflow, repository content, wiki content, or queue state is
  mutated

#### Scenario: Observer credentials cannot dispatch or repair

- **WHEN** the generic observer workflow is inspected or exercised with a red result
- **THEN** its job has no actions-write, contents-write, issues-write, pull-request-write, repository-write, or repair credential/call
- **AND** no manual or reusable input can enable workflow dispatch or corrective work

#### Scenario: Alarm sink is independently least-privileged

- **WHEN** the canonical incident owner consumes a bounded red observation
- **THEN** only its separate sink job may use narrowly scoped incident authority such as issues-write
- **AND** that job has no actions-write, repository-content write, repair, or user-task dispatch authority

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
