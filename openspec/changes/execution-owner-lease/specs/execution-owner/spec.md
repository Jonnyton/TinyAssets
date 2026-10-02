## ADDED Requirements

### Requirement: One Owner Commits At A Time Under A Generation-Fenced Lease
The platform SHALL run agent turns, write `agent_turns`, and perform owner-side mutations only in a process holding the owner lease. A lease SHALL be acquired only when the previous holder released it or its liveness lock proves it dead. Each acquisition SHALL take a generation greater than every generation recorded in the lease store, in any owner database fence, and in `agent_turns.owner_generation`. Every owner-side mutation SHALL commit only inside a write transaction that reads its database's fence and finds the owner's own generation.

#### Scenario: A stalled old owner commits nothing
- **WHEN** an owner at generation G pauses, a new owner acquires G+1 and advances the fences, and the old owner then resumes
- **THEN** every write the old owner attempts raises `LeaseLost` and nothing it does is committed

#### Scenario: A live owner is never displaced by a clock
- **WHEN** a contender tries to acquire while the holder's liveness lock is still held
- **THEN** the contender waits and does not acquire, however long the holder has been quiet

#### Scenario: A restore cannot reuse a generation
- **WHEN** a recovered turn journal holds rows at a generation above the recovered lease row
- **THEN** the next acquisition's generation is above both

### Requirement: Reconciliation Follows The Lease Generation
Startup reconciliation SHALL run only after the owner holds the lease. It SHALL settle only working `agent_turns` rows whose `owner_generation` is below the owner's generation. A status surface SHALL report a working row as activity only if its `owner_generation` equals the current generation.

#### Scenario: A standby owner leaves the live owner's turns alone
- **WHEN** a new owner process starts while the old owner still holds the lease and is running turns
- **THEN** the new process settles nothing until it holds the lease, and then settles only rows from earlier generations

### Requirement: Admission And The Journal Row Are One Transaction
A turn SHALL start only through one fenced transaction that both checks that owner admission is open and records the turn's journal row at the owner's generation. Closing admission SHALL be a fenced write to the same database. A request that finds admission closed SHALL be returned to its frontend to queue, not refused to the client.

#### Scenario: No request slips through a handover
- **WHEN** admission closes while requests are arriving
- **THEN** every request is either recorded as an in-flight turn that the handover drains, or returned to its frontend to queue; none is admitted without a journal row

### Requirement: A Frontend Holds The Live Request During A Handover And Never Loses Its Text
A frontend SHALL persist a conversation request's message verbatim to the pending-request journal before acknowledging or forwarding it. While the owner is unavailable or closed, it SHALL hold the client's request open and forward it, with that request's own authenticated identity, when an owner opens, up to its queue bound. A pending row left behind without a recorded founder turn SHALL be posted back into the owner's thread verbatim with a "not answered, send it again" notice and SHALL NOT be executed. Account deletion SHALL remove pending rows by owner across every universe.

#### Scenario: A message sent mid-handover is answered with its own authority
- **WHEN** the owner sends a message while the execution owner is handing over
- **THEN** the client sees an update-in-progress status, and once the new owner opens, the turn runs under that request's identity and the reply reaches the client

#### Scenario: A request the client abandoned is shown back, not run
- **WHEN** the client disconnects before the handover ends
- **THEN** the message appears in the thread verbatim with a notice to send it again, and no turn runs for it

### Requirement: Owner Text Is Acknowledged Only After It Is Persisted
Carryover and steering text SHALL be retired from their source records only after the consuming turn has durably recorded it in the turn input or the thread.

#### Scenario: A crash after consuming carryover loses nothing
- **WHEN** a turn consumes carryover and the process dies before the turn records it
- **THEN** the carryover is still present for the next turn
