## ADDED Requirements

### Requirement: One Owner Commits Per Command Center Under A Keyed, Generation-Fenced Lease
The platform SHALL execute work for a command center, and perform that command center's owner-side mutations, only in a process holding that command center's owner key. The scheduler, triggers, outbox, metering and allocator SHALL run only under the platform owner key. A key SHALL be acquired only when its previous holder released it or the holder's liveness lock proves it dead. A holder whose liveness proof is missing SHALL block acquisition. Each acquisition SHALL take a generation above the key's previous generation and above every fence recorded for that key. Owner mutations SHALL commit only in one write transaction that reads that key's fence and finds the owner's generation. Fence advancement SHALL be a separate primitive, used only at acquisition after the lease proof is verified.

#### Scenario: A stalled old owner commits nothing for a moved command center
- **WHEN** an owner at generation G for a command center pauses, a new owner acquires G+1 for it and advances its fences, and the old owner resumes
- **THEN** every write the old owner attempts for that command center raises `LeaseLost`

#### Scenario: Moving one command center does not fence another
- **WHEN** command center B's key moves to a new owner while command center A's turn is still running in the old owner
- **THEN** A's turn keeps committing, because A's fence is untouched

#### Scenario: A restore cannot reuse a generation
- **WHEN** the platform is restored and the restore tool records each key's high-water from every registered store
- **THEN** the next acquisition of any key takes a generation above everything recovered

### Requirement: A Command Center Moves Only When Idle, And A Running Turn Is Never Cut By A Handover
An owner handover SHALL close the old owner's keys to new work while allowing continuations of admitted work. It SHALL release a key only in the transaction that observes that command center idle: no admitted execution open and nothing queued. The new owner SHALL acquire the key, advance its fences, run the effect-executor barrier for that key, and reconcile that key's earlier generations, before it admits new work. Only an explicit operator force SHALL cut a command center's running work. A force SHALL stop the old owner container, and its work SHALL be reconciled into held states with the interrupted notice.

#### Scenario: A long turn keeps its old owner until it finishes
- **WHEN** an owner deploy starts while a command center's turn has been running for an hour
- **THEN** that command center stays on the old owner until the turn finishes, other command centers move as they go idle, and nobody's request waits for that turn

### Requirement: Every Execution Start Is One Admission, And Retries Attach Rather Than Re-Run
Every new execution of a command center SHALL be admitted in one fenced transaction that counts it open and records its own row. That covers an agent turn, a run, an automation or wake fire, and a consumer reservation. Continuations of an admitted execution SHALL carry its admission id and SHALL be allowed while the key is closing. A request SHALL be admitted at most once per operation id. A retry with the same operation id SHALL attach to the existing execution, and a mismatched retry SHALL be refused as a conflict. Background starters SHALL leave a fire durably queued while its command center's key is closing or in transfer.

#### Scenario: A lost admission reply does not double-execute
- **WHEN** the owner admits a turn and the frontend never receives the reply and retries with the same operation id
- **THEN** the retry attaches to the running turn and no second turn starts

### Requirement: Request Authority Is The Verified Identity, Re-Resolved In The Owner
The owner SHALL execute a client request only under the full verified identity that the frontend forwards: user, capabilities, tenant metadata and session. It SHALL bind that identity into its request context. It SHALL re-resolve the interlocutor tier and universe access against current grants, and SHALL NOT accept them from the frontend. The provider-request capability SHALL be minted in the owner, bound to the execution and its operation id, and revoked at its end. Autonomous work SHALL keep its own invocation authority and SHALL NOT use this path.

#### Scenario: A first-contact request still creates the home
- **WHEN** a new founder sends `converse` with no graph id through a frontend
- **THEN** the owner creates and binds the home under that founder's own capabilities, exactly as the single process does today

### Requirement: Pending Request Text Is Persisted First And Never Lost Or Executed From Storage
A frontend SHALL persist each conversation request verbatim under an operation id, before it forwards or acknowledges it, in account-scoped pending storage that grants nothing. A pending row SHALL be deleted only after the owner's thread record of it is verified. A row SHALL be treated as abandoned only when the frontend recorded the client's disconnect before admission, or when its frontend is proven dead while the row is still pending. An abandoned row SHALL be projected into the thread verbatim with a "not answered, send it again" notice, idempotently. It SHALL NOT be executed and SHALL NOT be counted as learned. Pending inserts and projections SHALL recheck the account-deletion tombstone under the deletion exclusion.

#### Scenario: A frontend crash loses no message
- **WHEN** a frontend dies holding a request that was never admitted
- **THEN** the owner projects the message into the owner's thread with the notice, once

### Requirement: Owner Text Is Acknowledged Only After It Is Persisted
Carryover and steering text SHALL be retired from their source records only after the consuming turn has durably recorded it in the turn input or the thread.

#### Scenario: A crash after consuming carryover loses nothing
- **WHEN** a turn consumes carryover and the process dies before the turn records it
- **THEN** the carryover is still present for the next turn
