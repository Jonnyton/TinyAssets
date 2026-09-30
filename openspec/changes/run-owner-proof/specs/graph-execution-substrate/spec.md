## ADDED Requirements

### Requirement: An in-flight run SHALL be ended by recovery only when its owning process is provably dead
Every run SHALL record, at creation and whenever a process resumes it or takes it running, the owner token of that process, and every run-executing process SHALL hold that token's operating-system liveness lock for its whole life. Recovery SHALL interrupt a queued, running or resumed run that carries an owner token only when that owner's lock file exists and no process holds it, and SHALL never interrupt one whose owner is alive or unknown, however long it has been quiet. Recovery SHALL run in the process holding the data dir's run-recovery lock at boot, on a watcher tick, and after a crashed engine child is respawned. A read SHALL NOT end a run that carries an owner token. A run with no owner token, written before this requirement, SHALL keep the boot rule: it is interrupted only if it started before the recovering process began.

#### Scenario: A crashed engine child's run is recovered promptly
- **WHEN** the process executing a run dies while the server keeps running
- **THEN** within one watcher tick the run is marked interrupted and its terminal event is delivered

#### Scenario: A live, silent run is never recovered
- **WHEN** a run's owning process is alive but has recorded no progress for longer than any grace window
- **THEN** no recovery path and no read marks it interrupted

#### Scenario: A deploy's runs are recovered at boot
- **WHEN** the container is recreated while runs were in flight
- **THEN** the new server interrupts exactly the runs owned by the dead processes and delivers their terminal events

### Requirement: Every terminal run transition SHALL be recorded in a durable outbox and delivered at least once
Every transition of a run from a non-terminal into a terminal status SHALL write an outbox row keyed by the run and the transition's sequence number, in the same transaction as the status, whatever code path wrote the status. The terminal event SHALL be delivered after commit and redelivered by the watcher and at boot while undelivered, and SHALL be acknowledged only after its delivery succeeded, so neither a crash between the status commit and delivery nor a failed delivery SHALL lose it. A resumed run that ends again SHALL produce a second, distinct terminal event.

#### Scenario: A crash after the status commit still announces the run
- **WHEN** the process dies after committing a run's terminal status and before emitting its event
- **THEN** the next watcher tick or boot delivers the event

#### Scenario: A resumed run is announced each time it ends
- **WHEN** a run is interrupted, resumed, and then completes
- **THEN** its subscribers receive one event for the interruption and one for the completion
