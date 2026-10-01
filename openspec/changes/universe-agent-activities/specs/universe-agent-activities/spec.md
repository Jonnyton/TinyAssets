## ADDED Requirements

### Requirement: Activity records live in platform storage outside the universe
The platform SHALL keep every activity record, effect intent and status event in `.agent-sessions/<universe>/agent-activities.db` under the data root, outside every universe folder, where no tool jail, provider jail or workflow can read or write it. Activity ids SHALL be minted by the platform. A record SHALL name its owner principal, derived server-side from the authenticated creator and never from tool arguments or templates, its agent, its session key `activity:<id>`, its title, brief, origin, status, outcome, result summary, last completed tool call, and its runner's liveness token and generation. The store's bytes SHALL be charged to the owning universe's quota. Each activity SHALL keep at most 200 status events. Before an account's `.agent-sessions/<home>` is removed, every activity in it SHALL be fenced and failed so no live runner can recreate it.

#### Scenario: the agent cannot forge its own activity state
- **WHEN** the agent writes to any path from bash, a workflow or a provider jail
- **THEN** no activity record, effect intent or event changes

#### Scenario: account deletion removes activities
- **WHEN** the owner deletes their account while an activity is running
- **THEN** the activity is fenced and failed and the universe's `agent-activities.db` is removed with the rest of `.agent-sessions/<home>`

### Requirement: An activity spends compute as an `activity` work item under the owner's authority
An activity SHALL be admitted as work item kind `activity` in the provider authority store, through the same assignment, manifest, credential and budget admission as a foreground run. Its subject validation SHALL require the activity to be in progress under the same runner token and generation, the owner principal to be unchanged, the universe to be the owner's founder home, and the owner to hold the admin ACL; if ownership fails, the activity SHALL fail with `owner_lost`. If no compute is connected it SHALL wait on the owner with that reason. A runner taking over SHALL advance the receipt generation, fencing the previous runner's receipt.

#### Scenario: a former owner's activity stops
- **WHEN** the universe's owner changes while an activity is queued
- **THEN** the activity fails with `owner_lost` before any model call

### Requirement: Activities are dispatched durably with one live runner each
A dispatcher SHALL run on the automation pump's cadence and whenever an activity is created or answered, and SHALL select queued activities and in-progress activities whose runner's liveness lock exists and is unheld; a live or unknown runner SHALL NOT be taken over. Seats SHALL be requested without blocking a thread, keeping the activity's queue position; an activity over the seat count SHALL wait visibly and never be refused. Claiming SHALL set the runner token and advance the runner generation by compare-and-set, and every runner write SHALL carry its generation so a superseded runner's writes change nothing. While waiting on the owner or paused, an activity SHALL hold no seat. An owner answer SHALL re-queue the activity only if it answers the request the activity is waiting on.

#### Scenario: over the seat count, an activity waits
- **WHEN** an activity is queued while every background seat is held
- **THEN** it records one waiting-for-seat event and starts when a seat frees, with no thread blocked meanwhile

#### Scenario: a stalled runner cannot overlap its replacement
- **WHEN** a runner's process is alive but stalled past its lease
- **THEN** no other runner takes the activity over

#### Scenario: an approval does not hold a seat
- **WHEN** an activity waits on an owner approval
- **THEN** its seat is released and a queued activity takes it

### Requirement: An activity's external effects are recorded before they fire
For a run started by an activity, the effector SHALL record an effect intent keyed by the run, node, effect index and a digest of the resolved request (method, URL and transformed body) as planned, SHALL durably commit it as sent before the request leaves, and SHALL send nothing if either write fails or the intent already exists. After the request it SHALL record confirmed or failed with a safe receipt; transport uncertainty after the request was written SHALL be recorded as unknown, never failed. When such a run is interrupted, planned intents SHALL become failed and sent intents unknown; the activity SHALL NOT continue until each unknown intent is resolved, and an unresolvable one SHALL become an owner question answered as happened, not happened or try again. Only try again SHALL permit a new attempt.

#### Scenario: a deploy during a send
- **WHEN** the daemon restarts after an activity's effect was committed as sent but before its outcome was recorded
- **THEN** the activity asks the owner whether it happened and does not send it again unless told to try again

### Requirement: Activities resume after a restart from their last completed tool call
A runner taking over an in-progress activity SHALL continue its session natively when the adapter can resume, or otherwise from a session built from the record: the brief, the completed tool calls from the durable turn journal or their safe summaries, the partial result and the effect resolutions. It SHALL be told it was interrupted and SHALL NOT re-execute a completed tool call.

#### Scenario: two activities and a deploy
- **WHEN** two activities are in progress and the daemon restarts
- **THEN** both continue without the owner reconnecting, and neither repeats a completed tool call

### Requirement: The agent and the owner manage activities through one contract
The universe agent's served tools SHALL offer `write_graph target=activity` with operations `start`, `stop`, `pause` and `resume`, and `read_graph target=activities` and `target=activity`, scoped to the agent's own universe. Starting an activity from inside an activity SHALL be refused with `nested_activity_unavailable`. The owner's app SHALL offer list, stop, pause, resume and delete for the authenticated owner's own home only, with compare-and-set on the record's revision. Listing, and an activity's events and effect intents, SHALL be returned completely, paged by an explicit cursor and never cut at a size cap. Stopping SHALL keep the partial result. Status changes SHALL reach the agent's main session as platform-composed lines whose only agent-supplied text is the activity's quoted, one-line, length-bounded title.

#### Scenario: a long list is complete
- **WHEN** the agent lists its activities and there are more than one page
- **THEN** each page carries a cursor to the next until every activity has been returned

#### Scenario: stop keeps the work
- **WHEN** the owner stops a running activity
- **THEN** it stops at its next tool boundary and its result summary so far remains on the record
