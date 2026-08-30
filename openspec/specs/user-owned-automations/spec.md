# User-Owned Automations

## Purpose

Universe-owned, owner-controlled scheduled and event-triggered branch runs. An automation belongs to exactly one universe and to the authenticated principal who created it with an admin ACL on that universe. Each due run resolves the universe's current serving provider assignment and credential custody at the moment it fires and executes through the daemon's own assigned-queue consumer, under the same foreground admission and budget as a manual `run_graph` -- no host-run worker fleet, executor runtime identity, or preparation-time provider pin is a prerequisite. A registration that cannot fire is refused loudly with a named, owner-actionable reason, and one principal's authorization failure at run time is a single recorded refusal, never an abort of the pump for other universes.

## Requirements

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
a named reason, instead of accepting it silently. Registration SHALL refuse exactly what
foreground admission refuses: a row admission would reject is a row that fails every period
forever. Each reason SHALL reach the owner as a sentence they can act on, not a bare token.

#### Scenario: Consumer flag off
- **WHEN** the assigned-queue consumer is disabled and an owner registers an automation
- **THEN** the daemon returns `automation_unavailable` with reason `consumer_disabled`

#### Scenario: A workflow the owner did not author
- **WHEN** an owner registers a readable but foreign-authored branch, which foreground admission
  refuses because it requires `branch.author == principal`
- **THEN** the daemon returns `automation_unavailable` with reason `branch_not_owned`

#### Scenario: Serving on an open compute provider
- **WHEN** the universe's assignment is ready but names an open `api_key_http` provider, which
  foreground admission refuses outright
- **THEN** the daemon returns `automation_unavailable` with reason `no_serving_assignment`, and
  the owner-facing sentence names the subscription requirement rather than an absent assignment

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

### Requirement: Schedule controls are admitted by the owner's coarse scope and authorized by the row's universe ACL
The actions that undo a schedule registration — `pause_schedule`, `unpause_schedule`,
`unschedule_branch` — SHALL carry the same permission tier as `schedule_branch` (`costly`), so the
coarse scope every authenticated founder holds admits the call to the handler. The handler SHALL be
the authority: it MUST require an authenticated request-local identity (never a caller-supplied or
environment-derived actor) and a CURRENT admin ACL on the schedule row's own universe before
mutating the row. Platform `admin` scope MUST NOT be required to control a schedule the caller's
universe owns. A row whose universe cannot be established from its stored owner SHALL be refused for
every caller.

#### Scenario: The owner stops their own schedule from their own session
- **GIVEN** a principal whose grants are `read, write, costly, submit_request, list` and no
  `tinyassets.extensions.admin`
- **AND** a schedule row in a universe where that principal holds a current admin ACL
- **WHEN** they call `extensions action=unschedule_branch` (or `pause_schedule`, `unpause_schedule`)
- **THEN** the scope gate admits the call and the handler performs the mutation

#### Scenario: Coarse scope alone does not authorize another universe's schedule
- **GIVEN** the same coarse-scoped principal
- **AND** a schedule row in a universe where they hold no admin ACL
- **WHEN** they call any of the three actions
- **THEN** the handler refuses with `owner_not_admin` and the row is unchanged

#### Scenario: A delegated universe admin who is not the row's creator may control it
- **GIVEN** a coarse-scoped principal granted an admin ACL on the row's universe after the row was
  created by someone else
- **WHEN** they call any of the three actions
- **THEN** the mutation succeeds

#### Scenario: A legacy row with no recoverable universe is refused for everyone
- **GIVEN** a fleet-era schedule row whose stored owner cannot establish a universe
- **WHEN** any principal, including a universe admin, calls any of the three actions
- **THEN** the handler refuses with `owner_not_admin`
