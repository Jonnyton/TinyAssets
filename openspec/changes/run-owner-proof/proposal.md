# A run, and a seat, end only when their owning process provably died

## Why

A 24/7 loop an owner builds from `run_completed` subscriptions must survive
deploys, crashes and engine-child restarts. Today nothing records WHICH process
owns an in-flight run, so every recovery path guesses:

- **Boot sweep** (`runs.recover_in_flight_runs`, fixed in #4125). It interrupts
  runs that started before the lock-holding server began. That is correct after
  a deploy, but it cannot see a crash inside the running container.
- **Read-time orphan check** (`runs._mark_orphaned_run_if_needed`). This treats
  "no Future in MY process and no progress for an hour" as dead.
  - Each serving universe has an engine MCP child that executes runs, so a
    sibling's live but quiet run is taken for dead.
  - A crashed child's run is ended silently after an hour, so the owner's loop
    stops. (Filed as a P1 concern from #4125; this change resolves and deletes it.)
  - Announcing that guess forks loops (astra, #4125 round 2): a wrongly ended run
    can still finish and announce itself, giving two wakes and two chains.
- **Seats** (`universe_seats.py`, two-dimension-usage-limits). A seat is
  reclaimed when its lease has expired AND its holder is not proven alive. Its
  holder token `pid:hex` fails the liveness-file token pattern, so it can never be
  proven alive. In practice that makes seat reclamation a timeout alone.
- **Announcements are not durable.** `run_completed` is emitted after the
  status commit. A crash between the two loses it, and no later sweep selects a
  row that is already terminal.

## What Changes

1. **One process-liveness primitive** (`tinyassets/process_liveness.py`). Every
   process that executes agent calls or runs holds one owner token for its life:
   the server, each engine MCP child, and any worker.
   - The token proves liveness with the OS lock that `automations.hold_process_liveness`
     already uses (`.consumer_liveness/<token>.lock`; the kernel drops it on any death).
   - It answers `alive | dead | unknown` for any token and never guesses.
   - Runs, seats and automation leases all use it.
2. **Every run records its owner token** at creation, and a resumed run records
   its new owner's.
3. **Recovery ends exactly the runs whose owner is provably dead**, and nothing else.
   - It runs in the recovery-lock holder at boot, on a short watcher tick, and
     when the engine supervisor respawns a dead child.
   - A row with no token (from before this change) keeps today's boot-sweep rule.
   - The read-time orphan check stops ending runs that carry a token.
4. **A durable terminal-event outbox.**
   - Every terminal transition, whether a normal finish or a proven-death
     recovery, writes an outbox row in the same transaction as the status.
   - It is delivered at least once: right after commit, then by the watcher and at boot.
   - A wake is registered at most once per `(subscription, run_id)`, so delivery
     is effectively exactly once.
5. **Seats reclaim on proven death.**
   - A seat whose holder is provably dead is reclaimed at once, without waiting
     for its expiry.
   - An expired seat whose holder is provably alive is never reclaimed.
   - The lease timeout alone applies only to a holder that never registered a
     liveness lock (unknown).
   - The seat holder token becomes the process-liveness token.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `graph-execution-substrate`: in-flight recovery by proven owner death; the
  terminal-event outbox.
- `universe-seats` (added by `two-dimension-usage-limits`): the reclamation rule
  keys off the same proof.
- `user-owned-automations`: `run_completed` delivery is at-least-once with an
  idempotent wake.

## Impact

- **Storage.** A nullable `owner_token` column on `runs`, a new
  `run_terminal_outbox` table in the runs DB, and a unique
  `(subscription_id, event run_id)` guard on event wakes in `automations.db`.
  Additive only. Rows written before the change keep their current behaviour.
- **Code.**
  - `runs.py`: create, resume, `update_run_status`, recovery, and the read-time check.
  - `api/runs.py` and `universe_server.main` for boot.
  - `engine_mcp_http` supervisor and `engine_mcp_server` for the child's token.
  - `automation_events.py` and `universe_seats.py`.
- **Coordination.** The `two-dimension-usage-limits` lane
  (`claude/limits-two-dims`) owns `universe_seats.py`. The seat change here is
  one function (`_reap`) plus the holder token. It lands with that lane's
  agreement, or that lane builds it against this primitive.
- **No MCP surface, auth or money change.**
