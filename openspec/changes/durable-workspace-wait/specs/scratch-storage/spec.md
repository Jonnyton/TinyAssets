## ADDED Requirements

### Requirement: Runs that need a busy workspace wait durably, in arrival order, before they start

A depth-zero run with an authenticated owner and a universe, whose admitted graph declares a `workspace` effect, SHALL take a durable wait ticket in its universe's workspace database at admission. It SHALL NOT start executing nodes until its ticket is first among that universe's tickets and no other run holds the universe's job lock or host slot. While waiting it SHALL remain `queued`, hold no executor worker, and expose `workspace_wait` with its state, 1-based position and waiting-since time, without exposing any holder identity. While the first ticket's run has not yet been handed to a worker, job-lock acquisition SHALL refuse `workspace_busy` to every other run that does not already hold the lock. Acquisition SHALL consume the acquiring run's ticket in the same transaction. Every terminal status SHALL remove the run's ticket in the transaction that enqueues its workspace release. A lock release, terminal release, cancellation, startup recovery and periodic sweep SHALL nominate the first waiting run. That run SHALL be dispatched from its durable admission envelope, with freshly bound owner provider authority.

#### Scenario: two overlapping runs both complete in order
- **WHEN** run A holds the universe's workspace and run B, which needs it, is admitted
- **THEN** B stays `queued` with `workspace_wait.state = "waiting"` and position 1, executes no node, and starts only after A's release is processed; both complete

#### Scenario: arrival order is honoured
- **WHEN** runs B then C are admitted while A holds the workspace
- **THEN** B starts before C, and C cannot acquire the lock while B's ticket is first in line

#### Scenario: a restart while waiting
- **WHEN** the daemon restarts while B is waiting and has not started
- **THEN** startup recovery does not mark B `interrupted`; B keeps its place and is dispatched when the workspace is free

#### Scenario: no replay of started work
- **WHEN** the daemon restarts after a queued-workspace run has started
- **THEN** that run is settled `interrupted` as before, its ticket is removed, and it is never re-dispatched

#### Scenario: cancelling a waiting run
- **WHEN** the owner cancels B while it waits
- **THEN** B is settled `cancelled` without executing a node, its ticket is removed, the holder's lease and locks are untouched, and the next waiter is nominated
