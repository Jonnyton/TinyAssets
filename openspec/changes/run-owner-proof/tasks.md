# Tasks: run-owner-proof

One PR for runs and the outbox (1.x–2.x). The seat task (1.7) lands in whichever
PR the `two-dimension-usage-limits` lane agrees to.

## 1. Build
- [x] 1.1 `tinyassets/process_liveness.py`: move the liveness lock and probe out of
      `automations.py`; add `owner_token()` (lazy, fork-safe) and `owner_state()`;
      `automations` re-exports so existing callers keep working.
- [x] 1.2 `runs.owner_token` column (idempotent migration), stamped by
      `create_run` and `resume_run`; `engine_mcp_server` takes its token at start.
- [x] 1.3 `recover_dead_owner_runs`: interrupt queued/running rows whose owner is
      provably dead; boot uses it for tokened rows and keeps #4125's cutoff for
      rows with no token.
- [x] 1.4 Watcher tick in the recovery-lock holder, plus a call right after the
      engine supervisor respawns a dead child.
- [x] 1.5 Read-time orphan check deleted: a read never ends a run (no lasting
      dual path; untokened pre-change rows get the one-time boot cutoff).
- [x] 1.6 `run_terminal_outbox`: insert in the same transaction as every terminal
      transition; deliver after commit; redeliver undelivered rows on tick and
      boot. Idempotent event wake per `(subscription_id, run_id)` in
      `automation_events` (unique partial index).
- [ ] 1.7 `universe_seats`: holder = `owner_token()`; `_reap` reclaims dead at
      once, never alive, expired-unknown by lease (coordinated with the seats lane).

## 2. Prove
- [x] 2.1 Real processes: a run owned by a killed child process is interrupted and
      announced within one tick; a run owned by a live, silent process is never
      touched; a restarted server recovers the dead container's rows.
- [x] 2.2 Outbox: crash between status commit and emit still delivers once;
      double delivery stores one wake; a self-following loop across a killed child
      forms exactly one chain.
- [ ] 2.3 Seats: a killed holder's seat is reclaimed before its expiry; a live
      holder past expiry keeps it; an unregistered holder falls back to expiry.
- [ ] 2.4 Mutation-check each gate; gpt-6-astra refute (≤3 rounds); Linux oracle.

## 3. Land
- [ ] 3.1 Deploy, `deployed_sha.py --assert-contains`, verify on the founder's loop;
      delete the P1 concern; sync deltas and archive.
