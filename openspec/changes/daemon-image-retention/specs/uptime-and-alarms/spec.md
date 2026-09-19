## MODIFIED Requirements

### Requirement: Disk-pressure timer preserves ordered alert, rotation, and disposable-host remediation
The system SHALL preserve the persistent hourly/minute-27/post-boot disk timer
and ordered alert, transcript rotation and retention commands with accepted
statuses 0 and 1. Alarm and retention SHALL measure pressure as
`100 * (1 - available_bytes / total_bytes)` with unknown measurements causing no
deletion. At the default85% trigger, automatic retention SHALL remove only
individually registry-verified immutable TinyAssets daemon cache images under
deployment serialization, preserving all container references, current daemon,
two recent older rollback candidates, configured and receipt rollback references.
Both hourly and weekly automatic cleanup entrypoints SHALL use this same narrow
policy, never broad prune, journal vacuum, volume, container or user-data deletion.
Retention SHALL stop at75% pressure, four removals or its120-second work budget,
whichever comes first, and report unmet pressure and unavailable evidence.
Registry verification SHALL occur before acquiring the fence-then-mutation
locks; the locked phase SHALL have a maximum60-second budget. Any fence-state
file SHALL refuse deletion. The current configured image and authoritative
volume-root release receipt SHALL be reread before every removal. Unknown
image-store filesystem mapping SHALL refuse even dry-run planning; zero
available bytes with a positive total SHALL be measured as100% pressure.

#### Scenario: Pressure alert preserves the cleanup chain
- **WHEN** disk alerting crosses its default80% threshold and returns1
- **THEN** systemd continues rotation and the bounded retention threshold check
- **AND** unexpected process statuses still fail the unit

#### Scenario: Recoverable old daemon cache relieves pressure
- **WHEN** pressure reaches85%, guards permit mutation and exact registry recovery is verified
- **THEN** only unreferenced unprotected immutable daemon image refs are removed non-force, oldest first, with fresh reference and pressure checks
- **AND** low watermark and work bounds stop further removals

#### Scenario: Unknown state does not authorize deletion
- **WHEN** lock/fence, current image, protected refs, measurement or remote recovery cannot be established
- **THEN** retention emits a sanitized refusal or unknown result and performs no unsafe deletion

#### Scenario: Dry-run and weekly scheduling remain narrow
- **WHEN** retention runs dry or through the weekly cleanup timer
- **THEN** dry-run never deletes and weekly execution obeys the identical pressure, recovery and preservation gates
