## MODIFIED Requirements

### Requirement: Authenticated creation grants founder ownership and binds a home
When creation is authenticated, the implementation SHALL attempt universe-index
registration before founder mutation, but registration failure SHALL be logged
and ignored. It SHALL then grant the founder `admin` ACL and bind the universe
as the founder's home only when no living home exists. An authenticated create
SHALL NOT write the host-global `.active_universe` marker; an anonymous/dev
create SHALL write it. If a later create step raises, rollback SHALL remove the
new universe directory when `shutil.rmtree` succeeds. Rollback SHALL swallow a
cleanup `OSError`, which can leave a partial directory, and SHALL NOT compensate
an index row, ACL grant, or host-global marker already written before the
failure. The ordinary flow has no fallible step after successful home binding.

#### Scenario: registration failure is best-effort
- **WHEN** index registration raises during an authenticated create
- **THEN** the failure is logged and creation continues to the founder grant and conditional home-binding steps

#### Scenario: founder create grants ownership without clobbering the active marker
- **WHEN** an authenticated founder creates a universe and the founder mutations succeed
- **THEN** an `admin` grant is recorded for the founder
- **AND** the `.active_universe` marker is not written for that create

#### Scenario: home binds only when no living home exists
- **WHEN** an authenticated founder without a living home creates a universe
- **THEN** that universe is bound as the founder's home
- **AND** a later create by a founder who already has a living home does not reassign the home

#### Scenario: rollback attempts directory cleanup without compensating earlier state
- **WHEN** a create step raises after an index row, ACL grant, or host-global marker has already been written
- **THEN** rollback attempts to remove the newly created universe directory
- **AND** does not compensate those earlier durable writes
- **AND** a cleanup `OSError` is swallowed, so a partial directory can remain

#### Scenario: anonymous create switches the local daemon
- **WHEN** an unauthenticated dev/tray create runs
- **THEN** the `.active_universe` marker is written with the new serial so the daemon switches to it
