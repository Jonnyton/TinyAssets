# Design: run-owner-proof

## D1. One liveness primitive, reused, not a second one

`tinyassets/automations.py` already proves a lease holder's death with an OS lock:
`hold_process_liveness(base, holder)` locks `<data>/.consumer_liveness/<holder>.lock`
for the process lifetime, and `_probe_holder` answers `dead` only when that file
exists and nobody holds its lock. The kernel drops the lock on any exit, a
deploy's SIGKILL included. This change moves that code into
`tinyassets/process_liveness.py`, keeping the `.consumer_liveness/` directory so
scoped reset needs no new root entry. It adds:

```python
def owner_token() -> str           # this process's token, "proc_<hex>", lock taken on first call
def owner_state(token) -> "alive" | "dead" | "unknown"
```

- The token is minted lazily on first use. A fork child mints its own and closes its
  copies of the parent's lock descriptors, so it cannot keep a dead parent "alive".
- It matches the existing `^[A-Za-z0-9_-]{1,128}$` holder pattern. The seat holder
  `pid:hex` does not match it, which is why seats can never be proven alive today.
- `unknown` covers a missing file, a probe error, or an unregistered token.
  `unknown` is never treated as dead.
- The automation consumer keeps its own `consumer_id` lease holder: one process
  may hold several tokens. Only runs and seats adopt `owner_token()`.

## D2. Runs record their owner

- `runs.owner_token TEXT` is nullable and added by the existing idempotent
  column migration.
- Run insertion stamps the creating process's token. Every transition to
  `running` re-stamps it with the executing process's, because whoever takes a
  run forward owns it (a resume, or a worker that did not queue it).
- `owner_token()` takes the process's liveness lock before it returns the token,
  so no row can name an owner whose proof does not exist yet. Engine MCP children
  take theirs on their first run, lazily, so there is no separate start-up call.
- The consumer's cleanup of dead holders' lock files keeps any file an in-flight
  run still names: that file is the run's proof of death.

## D3. Recovery ends exactly the provably dead

One function, `recover_dead_owner_runs(base)`, in the process that holds
`.run_recovery.lock` (#4125):

```
SELECT run_id, owner_token FROM runs
 WHERE status IN (queued, running) AND owner_token IS NOT NULL   -- plus the family/admission exclusions
for each distinct token: owner_state(token) == "dead"  -> interrupt its rows + outbox rows (one txn)
```

It is called:
- at boot, where it replaces the time cutoff for rows that have a token;
- on a watcher tick (`RUN_OWNER_WATCH_SECONDS = 15`) on the server's existing
  maintenance thread;
- right after `engine_mcp_http`'s supervisor respawns a dead child.

What changes for each kind of row:
- **Rows with no token** (written before this change) keep #4125's boot rule:
  started before the lock holder began.
- **The read-time orphan check is deleted.** A read never ends a run: a row is
  ended by proof or not at all. There is no lasting second path for rows with no
  token; they get the one-time boot cutoff.
- **An alive owner's run is never touched, however long it is quiet.** That is the
  founder rule that a served turn runs until it is finished.
- **A live but wedged process** stays covered by the existing run timeout and
  cancellation, which end it through a normal terminal transition.

## D4. Durable terminal-event outbox

```sql
CREATE TABLE run_terminal_outbox (
  run_id TEXT NOT NULL, seq INTEGER NOT NULL,   -- one row per terminal TRANSITION
  status TEXT NOT NULL, created_at REAL NOT NULL, delivered_at REAL,
  PRIMARY KEY (run_id, seq)
);
CREATE TRIGGER run_terminal_outbox_on_transition AFTER UPDATE OF status ON runs
  WHEN NEW.status IN (terminal) AND OLD.status NOT IN (terminal) ...
```

- **Written by a trigger.** A trigger writes the row in the status write's own
  transaction, so no terminal path can skip it: `update_run_status`, recovery,
  `terminalize_unstarted_run`, delivery recovery, or any direct SQL. It fires only
  on a non-terminal to terminal transition. `seq` counts transitions, so a resumed
  run that ends again owes a second event (astra round 1).
- **Delivery.** Delivery runs after commit: from the writer for its run, and from
  the watcher and at boot for rows owed longer than 30 s.
- **Acknowledgement only on success.** A delivery is acknowledged only after the
  emit succeeds (`strict`). A failed emit stays owed.
- **Idempotent wake.** The consumer registers at most one wake per
  `(subscription, event occurrence)`, enforced by a unique partial index on
  `automations.event_key`:
  - a terminal event's occurrence is `<run>#<seq>`;
  - a request answer's occurrence is its whole payload, because two answers
    differ by item and status.
- **Known gap (nonblocking).** Two deliveries racing past the pre-insert lookup
  can both charge the registration usage meter before the unique insert keeps
  one wake. The seats change deletes that meter.
- **Why not transactional across both DBs.** The two databases are separate SQLite
  files, and cross-file atomicity is not available. At-least-once delivery plus an
  idempotent consumer is the same shape `_enqueue_workspace_terminal` uses.

## D5. Seats reclaim on proven death (with `two-dimension-usage-limits`)

`universe_seats._reap` becomes:

```
for each seat:
  state = owner_state(holder)
  if state == "dead":                          reclaim now (no expiry wait)
  elif state == "alive":                       never reclaim (it may be mid provider call)
  elif expires_at < now:  # unknown            reclaim (never-registered holder)
```

- The holder becomes `owner_token()`.
- After a deploy, a dead container's seats come back on the first acquisition
  instead of up to 120 s later.
- A live holder that misses its refreshes keeps its seat. This is astra's round-1
  finding 1 on that lane, now enforced by a proof that can actually return "alive".

## D6. What is deliberately not done

- **No heartbeat or progress timestamps as death evidence.** That is the guess
  being removed.
- **No cross-container ownership.** One data dir is served by one container. Two
  containers on one data dir would each hold their own locks correctly (flock is
  per open file), and that is sufficient.
- **No change to the MCP surface.** Owners see the effect: loops that keep going,
  and `interrupted` only for runs that really died.
