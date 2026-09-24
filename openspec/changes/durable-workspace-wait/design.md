## Context

- Workspace locks, leases and the release outbox live in the universe's own
  runs database (`_pool_db(universe_dir)`); the run row lives in the root runs
  database. The lock belongs to the run from its first `create`/`checkout`
  admission until its terminal outbox entry is processed.
- Production app runs use the legacy executor path (`execute_branch_async` ->
  in-process `ThreadPoolExecutor`, 4 workers). Managed families are not
  enrolled in production. The admitted-input pipeline carries only file-input
  runs, and it holds (never replays) its started runs after a restart.
- `recover_in_flight_runs` rewrites every queued/running legacy row to
  `interrupted` at startup. Read-time orphan recovery does the same after an
  hour without progress.

## Decisions

**D1. The run waits before it starts, not inside a node.** A waiting run that
has executed no node cannot have produced any effect, so restarting its wait
after a crash can never replay work. A wait inside a node can replay work,
because the node body and sibling nodes have already run. So the run is the
unit that waits, and it waits for its turn at the universe's workspace.
Consequence: a workspace-using run holds its place from admission, not only
from its first checkout. That is the behaviour the acceptance asks for: the
second run waits, then starts when the first releases.

**D2. A new table in the pool database, not a reuse of the run queue or the
lock table.** `workspace_locks` is keyed `(scope, key)`, so it holds one
holder and no queue. The run "queue" is an in-memory executor and is not
durable. `runs.status` lives in a different database from the lock, and FIFO
consumption must be atomic with lock acquisition. So the change adds
`workspace_waiters(ticket INTEGER PRIMARY KEY AUTOINCREMENT, run_id UNIQUE,
universe_id, created_at, dispatched_at)` next to `workspace_locks`, created by
the same `ensure_schema`. AUTOINCREMENT gives an arrival order that is never
reused.

**D3. A ticket is a reservation.** A ticket is deleted when its run acquires
the lock, in the same transaction. It is also deleted in every terminal
transaction that already enqueues the run's workspace release
(`_enqueue_workspace_terminal`). Completion, failure, cancellation, restart
interruption and orphan recovery therefore all clean up. `_acquire_lock`
refuses `workspace_busy` to any other run while a different run's ticket is
first in line and that run has not yet been handed to a worker. Once the head
is dispatched (`dispatched_at`), nothing queued can start ahead of it, so the
reservation has done its job. A run the head launches, such as a child that
uses the workspace before its parent does, is then not locked out by its own
parent's ticket. Reentrant holders and the ticket run's own family are
unaffected.

**D4. Dispatch is event-driven and uses the run's durable admission.** A
waiting run is not given a worker. `nominate_workspace_waiter(universe_dir)`
picks the first ticket. If the lock and slot are free, it dispatches that run
as follows:

- reload the run's admission envelope (definition, recursion limit,
  concurrency choice), stored inputs and owner;
- bind a fresh foreground provider session for the owner, the same binding
  that the admitted-input and scheduled paths already use;
- submit the normal `_invoke_prepared_branch` worker under the owner's
  identity.

If the head run is terminal or missing, its ticket is dropped so that a dead
head cannot wedge the queue. Nominations fire after a sweep pass (lock
release), after a terminal release, after a waiting run is cancelled, at
startup recovery, and on every periodic sweep.

**D5. Restart.** Startup and read-time recovery skip queued runs that hold a
ticket and never started, then nominate their universes. A run that already
reached `running` is interrupted exactly as today, and the same terminal
transaction removes its ticket. A run that is not `queued` is never
re-dispatched.

**D6. Which runs are queued.** Only depth-zero root runs with an authenticated
owner, a universe, and at least one node declaring the `workspace` effect.
Children reuse their parent's lock. Runs without an owner or universe keep
today's bounded node wait.

**D7. Visibility.** While the ticket exists and the run is queued, `get_run`
adds `workspace_wait: {state, position, waiting_since}`. The run snapshot
surfaces it and states it in its text. Position counts only waiters in the
same universe, and no holder identity is exposed.

## Risks

- A waiting run whose dispatch fails is settled `failed` with the reason,
  which removes it from the queue. Nothing is retried silently.
- If a restart killed the holder, the waiter starts once that holder's
  release is processed (startup recovery enqueues it), not before.
- In the root/universe topology the host slot is per universe database, so
  queues are per universe. This change leaves that as it is.
