## ADDED Requirements

### Requirement: Cloud-loop activation is gated by a closed owner-authority manifest
The system SHALL activate an unattended user-owned cloud loop only from a server-validated manifest that pins the owner, universe, immutable Branch version and hash, persisted Trigger and missed-fire policy, background target authority, background provider authority, provider binding generation, exact external-effect destination grant and caps, budgets, and activation generation. Every reference MUST be reread at activation; an absent, stale, revoked, mismatched, unimplemented, maintainer-owned, or market-supplied reference SHALL keep the loop inactive with a machine-readable reason.

#### Scenario: Cloud provider authority is not yet available
- **WHEN** every readiness edge passes except a cloud-usable Jonathan-owned provider binding
- **THEN** activation remains inactive and reports that exact dependency without using maintainer quota, process credentials, or market compute

#### Scenario: Complete current manifest activates
- **WHEN** the owner requests activation and every pinned manifest reference is current, authorized, and compatible
- **THEN** the system atomically commits one new activation generation bound to the exact Branch version and authorities

### Requirement: One generation-fenced controller owns the drain
The system SHALL maintain one logical activation lease for the repository drain and MUST allow only the current generation to admit slices or external effects. Cloud cutover SHALL require the local controller to be stopped and free of an unsettled claim before the cloud generation becomes active. Pause, stop, replacement, lease loss, and rollback SHALL fence new work from the prior generation.

#### Scenario: Tray remains active at cutover
- **WHEN** cloud activation is requested while the local tray controller still owns an active claim or controller generation
- **THEN** cloud activation is refused and no cloud slice is admitted

#### Scenario: Two cloud activations race
- **WHEN** two requests compare-and-swap from the same prior generation
- **THEN** exactly one activation commits and the loser observes the winning generation without dispatching work

#### Scenario: Rollback restores the bridge
- **WHEN** the owner rolls back from cloud to the local bridge
- **THEN** the system first fences cloud admission and settles the current irreversible boundary before permitting the bridge to acquire a new generation

### Requirement: The owner can manage and evolve the loop through a phone chatbot
The live connector SHALL let the authenticated owner use only the canonical handle set to inspect the active loop and full execution-affecting definition, pause, resume, stop, create and edit a draft, inspect an immutable anchored diff, run a side-effect-free test, publish a new immutable version, activate or rebind that version, and roll back. None of these lifecycle operations MAY require a desktop application, local filesystem, CLI, host login, maintainer intervention, or a new top-level MCP handle.

#### Scenario: Owner repairs a failed loop with the computer off
- **WHEN** Jonathan uses an authenticated phone chatbot to inspect a blocker, edits the responsible definition, reviews its exact diff, dry-tests it, publishes it, and activates it
- **THEN** every transition is owner-authorized and durably visible through the connector without any computer or operator step

#### Scenario: Summary omits a side effect
- **WHEN** a conversational summary would hide an execution-affecting field, external destination, authority source, or unresolved validation error
- **THEN** the full inspectable definition remains authoritative and the summary does not claim the loop is safe or complete

### Requirement: Version evolution is immutable and activation-safe
The system SHALL pin each slice to the immutable Branch version active when its logical attempt was issued. Draft tests SHALL simulate effects by default and SHALL NOT publish. Publishing SHALL create a new immutable version, and activation or rollback SHALL use a compare-and-swap from the reviewed activation generation so a concurrent edit or rebind cannot silently change the selected definition.

#### Scenario: Definition changes during activation
- **WHEN** the reviewed draft, published version, or activation generation changes before rebind commits
- **THEN** the rebind fails without changing the active version

#### Scenario: Active slice outlives a version update
- **WHEN** a new version becomes active while an earlier slice is settling its terminal receipt
- **THEN** the earlier slice remains pinned to its original version and no new slice is issued under the fenced generation

### Requirement: Continuation is durable, deduplicated, and restart-recoverable
The system SHALL persist each continuation as a logical period or event identity and SHALL admit at most one bounded slice for that identity. Duplicate trigger delivery, scheduler catch-up, or worker restart MUST reuse or reconcile the same logical attempt. A next slice SHALL remain ineligible until the prior slice has a terminal progress, blocked, or reconciled-effect receipt.

#### Scenario: Worker dies before provider invocation
- **WHEN** a cloud worker exits after claiming the logical attempt but before an irreversible provider or external-effect launch
- **THEN** recovery resumes or safely reclaims the same attempt and does not create a second repository claim

#### Scenario: Worker dies after an ambiguous GitHub write
- **WHEN** a worker exits after the destination may have accepted a write but before its receipt is terminal
- **THEN** the loop holds subsequent effects, reconciles the destination under the same system-derived identity, and never guesses that replay is safe

#### Scenario: Missed continuation is caught up
- **WHEN** the cloud scheduler or worker is unavailable across one or more due periods
- **THEN** the declared catch-up policy issues the bounded eligible continuation without silently discarding the outage or multiplying past periods into concurrent slices

### Requirement: Cloud-loop health reports useful progress and authority provenance
The system SHALL derive loop health from durable activation generation, active Branch version, current claim and phase, last useful progress, last terminal receipt, next retry, consecutive no-progress count, blocking reason, budgets, and target/provider/effect authority sources. A live scheduler or process heartbeat alone MUST NOT produce healthy status.

#### Scenario: Scheduler ticks without useful progress
- **WHEN** triggers continue firing but no slice produces useful progress within the declared threshold
- **THEN** health becomes held or unhealthy with the blocking phase and next remediation visible to the phone owner

#### Scenario: Authority source changes
- **WHEN** a receipt names an authority source or generation different from the active manifest
- **THEN** the attempt fails closed, health becomes unhealthy, and no later effect is admitted

### Requirement: Cutover acceptance proves zero-host user ownership
The system SHALL withhold accepted status until a live proof keeps Jonathan's computer off for at least 24 continuous hours, records useful cloud progress, survives a deliberate cloud-worker restart, and completes rendered phone-chatbot inspection, pause/resume, edit/diff, dry-test, publish, activate, and rollback. Acceptance MUST include concurrent activation/trigger/claim and revocation load evidence and MUST show no maintainer quota, market compute, tray/desktop/CLI dependency, duplicate claim, or repository-policy bypass.

#### Scenario: Twenty-four-hour run passes but phone evolution fails
- **WHEN** the cloud drain progresses for 24 hours but Jonathan cannot publish and activate a repaired version entirely through the phone chatbot
- **THEN** the change remains unaccepted and tray autostart is not retired

#### Scenario: Complete proof passes
- **WHEN** the computer-off continuity, restart, phone lifecycle, authority, concurrency/load, and repository-policy evidence all pass
- **THEN** the cloud drain becomes the accepted controller and the local tray drain is disabled from normal startup
