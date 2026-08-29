## ADDED Requirements

### Requirement: An automation belongs to a universe and its owner
An automation SHALL be stored as a row bound to exactly one universe and to the authenticated
principal that created it, who MUST hold an admin ACL on that universe at creation; a request
without an authenticated principal or without that ACL SHALL be refused.

#### Scenario: Anonymous registration is refused
- **WHEN** `write_graph target=automation operation=create` arrives without an authenticated principal
- **THEN** the daemon refuses with `authentication_required` and stores nothing

#### Scenario: Owner sees and controls it
- **WHEN** the owner lists, pauses, resumes or deletes the automation from their surface
- **THEN** the change is applied to that row only and reflected on the next read

### Requirement: Execution derives authority from the current serving assignment
Each due run SHALL resolve the universe's current provider assignment and credential custody at
run time and launch through the served carrier under foreground admission and budget; no run
SHALL depend on an executor runtime identity, a provider recorded at preparation, or any
host-supplied enrollment manifest.

#### Scenario: Provider switched between runs
- **WHEN** the owner rebinds the universe to a different provider and a run comes due
- **THEN** the run launches on the new provider without any re-preparation

#### Scenario: Daemon restarted between runs
- **WHEN** the daemon restarts and the same run comes due
- **THEN** the run launches once; the `(automation_id, due_at)` fence prevents a second launch

### Requirement: A registration that cannot fire is refused loudly
The daemon SHALL refuse to store an automation or schedule that cannot run at that moment, with
a named reason, instead of accepting it silently.

#### Scenario: Consumer flag off
- **WHEN** the assigned-queue consumer is disabled and an owner registers an automation
- **THEN** the daemon returns `automation_unavailable` with reason `consumer_disabled`

### Requirement: One principal's failure is one recorded refusal
When a due run cannot be authorized, the daemon SHALL record one refusal row for that automation
and continue with the others; it SHALL NOT abort the pump.

#### Scenario: Owner lost admin
- **WHEN** the owner's admin ACL on the universe was revoked before a run came due
- **THEN** a refusal is recorded, the automation is paused with that reason, and other universes' runs proceed

### Requirement: Nothing executes outside a user's universe
The daemon SHALL run no host-owned worker, no platform actor, and no automation whose owner is
not a user principal with an admin ACL on its universe.

#### Scenario: Fleet services absent
- **WHEN** the deploy converges the compose project
- **THEN** no `worker*` service exists and no `tinyassets.cloud_worker` process runs
