## ADDED Requirements

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
