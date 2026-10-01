## ADDED Requirements

### Requirement: Activity records live in platform storage outside the universe
The platform SHALL keep every activity record, pending effect and status event in `.agent-sessions/<universe>/agent-activities.db` under the data root, outside every universe folder, where no tool jail, provider jail or workflow can read or write it. Activity ids SHALL be minted by the platform. A record SHALL name its owner principal, authenticated when the record was created, its agent, its parent activity if any, its session key `activity:<id>`, its title, brief, origin, status, outcome, result summary and the sequence number of its last completed tool call. Records SHALL be counted against the owning universe's storage and removed with the owner's account.

#### Scenario: the agent cannot forge its own activity state
- **WHEN** the agent writes to any path from bash, a workflow or a provider jail
- **THEN** no activity record, pending effect or event changes

#### Scenario: account deletion removes activities
- **WHEN** the owner deletes their account
- **THEN** the universe's `agent-activities.db` is removed with the rest of `.agent-sessions/<home>`

### Requirement: An activity runs on the owner's identity and compute with no request
An activity SHALL run as the owner recorded on it, proven again at the start of every run, and on the owner's own provider under foreground admission and budget, never a platform model. If the owner no longer owns the universe, the activity SHALL fail with `owner_lost`. If no compute is connected, it SHALL wait on the owner with that reason. While running it SHALL hold one agent seat of kind `activity` in the background class, waiting for one without a deadline and never refused; it SHALL release the seat whenever it rests (completed, failed, waiting on you or paused). One runner per activity SHALL be guaranteed by a lease.

#### Scenario: over the seat count, an activity waits
- **WHEN** an activity starts while every background seat is held
- **THEN** it records a waiting-for-seat event and starts when a seat frees

#### Scenario: an approval does not hold a seat
- **WHEN** an activity waits on an owner approval
- **THEN** its seat is released and a queued activity takes it

### Requirement: An activity's external effects are recorded before they fire
While an activity runs, each external effect SHALL be recorded as planned with an idempotency key derived from the activity, the tool call and the exact action before it is attempted, marked sent immediately before the wire, and marked confirmed or failed with a safe receipt after. A second attempt with the same key SHALL NOT be sent. After a restart a sent effect without an outcome SHALL be unknown; the activity SHALL NOT continue until each unknown effect is reconciled, and an effect that cannot be reconciled SHALL become an owner question ("this may already have happened") answered as happened, did not happen or try again. Only try again SHALL permit a new attempt.

#### Scenario: a deploy during a send
- **WHEN** the daemon restarts after an activity's effect was marked sent but before its outcome was recorded
- **THEN** the resumed activity asks the owner whether it happened and does not send it again unless told to try again

### Requirement: Activities resume after a restart from their last completed tool call
At boot the platform SHALL find every in-progress activity whose lease holder is gone, resolve its pending effects, and start a runner that continues the activity's session natively when the adapter can resume, or otherwise from a session built from the record: the brief, the completed tool calls' safe summaries, the partial result and the effect resolutions. A resumed activity SHALL NOT re-execute a tool call at or before its last completed one.

#### Scenario: two activities and a deploy
- **WHEN** two activities are in progress and the daemon restarts
- **THEN** both continue without the owner reconnecting, and neither repeats a completed tool call

### Requirement: The agent and the owner manage activities through one contract
The universe agent's served tools SHALL offer `write_graph target=activity` with `start`, `stop`, `pause` and `resume`, and `read_graph target=activities` and `target=activity`, scoped to the agent's own universe. Starting an activity from inside an activity SHALL be refused with `nested_activity_unavailable` until nested activities are specified. The owner's app SHALL offer the same list, stop, pause and resume for the authenticated owner's own home only, with compare-and-set on the record's revision. Listing SHALL return every activity, paged by an explicit cursor and never cut at a size cap. Stopping SHALL keep the partial result. Status changes SHALL reach the agent's main session as platform-composed lines that carry no model text.

#### Scenario: a long list is complete
- **WHEN** the agent lists its activities and there are more than one page
- **THEN** each page carries a cursor to the next until every activity has been returned

#### Scenario: stop keeps the work
- **WHEN** the owner stops a running activity
- **THEN** it stops at its next tool boundary and its result summary so far remains on the record
