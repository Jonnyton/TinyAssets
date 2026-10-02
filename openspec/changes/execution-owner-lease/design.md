## Context

**Today.** One container runs one uvicorn process (`universe_server`). That process:
- serves MCP and the app;
- runs every agent turn in a FastMCP worker thread;
- is the single writer of `agent_turns`, which is the load-bearing assumption in `storage/agent_turn_boot.py`;
- drives the scheduler, automations, outbox and seats.

A served turn is authorised by a process-local provider-request capability. `auth/middleware.py` `on_call_tool` mints it per MCP tool call, from the bearer it re-verifies on the actual message (line ~948). The capability is one-use and worker-bound, and the tool wrapper (`universe_server.py:~383`) revokes it before the result is released. Background tasks get none.

**Phase 1 (#4278).** The deploy waits for in-flight work, up to 45 minutes, then recreates the container.

**Target.** #4263 D11/S8. **Lead decision (Q1, 2026-10-02): PER-COMMAND-CENTER ownership.**
- Each command center has its own lease and fence.
- One platform authority covers the scheduler, triggers, outbox, metering and the allocator. This is cp-scheduler's S8b `OwnerLease` seam (#4276).
- The reason: one user's long turn must never make another user's request wait, which would be cross-user impact against the floor.
- openshell-spike amends #4263 D11 to match.

**Collaborators.**
- **cp-scheduler (S8b, #4276):** `tinyassets/control_plane/lease.py`: `current_owner_lease()`, `set_owner_lease()`, `LeaseLost`, `proof`, `verify_lease_proof`.
- **agent-loop (S7):** the journal writer.
- **deploy-incident (#4272):** frontend blue-green behind HAProxy, with a ready handshake.
- **dots-research (S2):** the mid-turn lost-message fix.

**Input.** Two Codex shape refutes (gpt-6-astra, 2026-10-02), both ADAPT:
- the superseded `durable-turn-inbox` (876aeff4): replay has no authority;
- round 1 of this design (13 findings).

This revision answers both; the round-1 cross-reference is at the end.

## Goals / Non-Goals

**Goals:**
- **A deploy never cuts a running turn or run.** A command center moves to new code only when it is idle. A turn runs until it finishes, and nobody else waits for it.
- **No new request is refused.** One that arrives while its own command center is moving waits for seconds and is then served under its own live authority.
- **No owner text is lost.** Every message is answered, or shown back verbatim in the thread with an honest notice. Nothing executes twice.
- **At most one owner commits for a command center at a time,** including across a restore.

**Non-Goals:**
- Cross-host standby promotion (S1).
- Boxes (S4/S5).
- A broker in its own process (S6).
- This change also does not make the PLATFORM authority's own handover seamless: the scheduler, outbox, metering and allocator stay a short single-owner swap under S8b's lease. Durable trigger rows mean a fire is late, never lost.

## Decisions

### D1. Scope: ownership keys, not one singleton
**Owner keys.** Every ownership fact is keyed:
- `cc:<command_center_id>` for a command center's executions;
- `platform` for the S8b duties.

**Lease store.** `<data_root>/.owner_leases.db` holds one row per key: `owner_lease(owner_key PK, generation, holder_token, proof_sha256, state CHECK IN ('open','closing','released'), acquired_at, released_at)`.

**Fences.** In every shared store, the fence is keyed: `owner_fence(owner_key PK, generation)`. Never a singleton: advancing B's fence must not fence A, which was round-1 finding 12.

**Effect-executor fencing** is scoped by owner key. There is no global "cancel everything older than G".

### D2. Acquisition: released, or provably dead; restore is an explicit offline step
A process acquires `owner_key` inside `BEGIN IMMEDIATE` on the lease store. One of three conditions must hold:
- the row is `released`;
- `process_liveness.owner_state(holder_token) == DEAD`;
- no row exists.

The acquirer:
- sets `generation = max(row.generation, max_fence_seen(owner_key)) + 1`;
- mints a 32-byte proof and stores only its sha256;
- stores its own `owner_token`, so it holds the token's liveness flock for its whole life.

**Liveness retention.** `process_liveness` cleanup must never delete a token that a lease row names. The lease store is added to the cleanup's "still named" check (`runtime/assigned_queue_consumer.py:~265`). An UNKNOWN holder (its liveness file is missing) blocks acquisition. It is never read as dead (round-1 finding 5).

**Restore.** After a restore, liveness files are not trusted. `scripts/owner_lease_restore.py` refuses unless no daemon or engine process is running against the data root (it checks the host-mutation lock plus a process scan). It then reads EVERY registered owner store's fences and `agent_turns.owner_generation` per key. It writes each key's high-water as a `released` row at that generation, and records a restore manifest. Ordinary acquisition then takes high-water + 1.

Ordinary acquisition never scans every store. It reads only `max_fence_seen` from the stores registered for that key (D3), because restore has already established the high-water.

### D3. Two write primitives, one registry
**`fenced(conn, owner_key, lease)`** is used for ordinary owner mutations. It requires an idle connection and raises otherwise. It then runs:
1. `BEGIN IMMEDIATE`;
2. read `owner_fence[owner_key]`;
3. if the fence is not equal to `lease.generation`, raise `LeaseLost`;
4. run the body;
5. `COMMIT`.

It is the one transaction: a helper that commits inside the body is a bug, and a test asserts `conn.in_transaction` holds through the body.

**`advance_fence(conn, owner_key, lease)`** is called only during acquisition, after `verify_lease_proof`. It requires the stored fence to be below `lease.generation` and writes it. It is a different primitive from `fenced`, so the equality check does not reject it (round-1 finding 6).

**Schema and migrations** run before any process takes a lease, from the startup migration step, under the host-mutation lock. This covers `provider_work_authority`'s `executescript`, the table-rebuild migration, and `ensure_schema`. Store opening is therefore read-and-additive only. A standby or stale process can create missing tables with `IF NOT EXISTS`, but it never rebuilds or alters a table outside that lock.

**`OWNER_STORES`** is the explicit registry of owner-written stores, each with its scope (per command center or platform). The inventory test fails on any writer reachable from the owner entrypoints that is neither fenced nor listed with a reason. Dynamic per-universe stores register through their own constructor.

### D4. A command center moves only when it is idle, so the barrier has nothing to cancel
**This is the central change from round 1** (findings 7, 8 and 13). For each command center, an owner handover is:
1. The new owner process starts in standby. It holds no keys, serves nothing, and reconciles nothing.
2. The old owner sets `state = 'closing'` on every key it holds. A closing key admits only CONTINUATIONS of work already admitted (D5), never new work.
3. A key is released when its command center is IDLE, in ONE transaction on that command center's admission row: no admitted execution is open (turn, run or effect, per D5), and nothing is queued.
4. The new owner acquires the key, advances its fences (D3), runs the effect-executor barrier for that key, reconciles `owner_generation < G` for that key, and opens it.

**Why the barrier is trivial here.** Because a key is released only when idle, the old owner holds no execution for it. Nothing exists to cancel, and no old broker worker can still be running for it. The executor barrier for that key is therefore an ack that it has persisted G and refuses anything below G for the key. That makes it provable: there is nothing live to account for, which was round-1 finding 7.

**A command center that never goes idle** keeps its old owner. The old owner process exits when it holds zero keys. Turns run until finished. The cost is that an old owner process lingers (memory), and that is measured.

**The one bounded exception is an operator force** (a security fix, say): `owner-handover --force <key|all>`. It stops the old owner CONTAINER (cgroup kill), which is the proof that every child is dead. The new owner then reconciles that key's open work into held states, with the interrupted notice. Force is never automatic.

**Requests for a key that is closing or in transfer** are held by the frontend (D7). Since a key moves only at an idle instant, they wait for seconds, not behind a turn. Background starts for that command center wait in their durable source (D5).

**The platform key** moves the same way, gated on platform-duty idleness (no tick or pump mid-flight). That is S8b's concern, and it uses the same primitives.

### D5. Admission covers whole executions, including runs and effects
**The admission row** is `cc_admission(owner_key PK, state, open_executions, queued)` in the journal store, written only with `fenced`. Every execution start is a NEW admission, and it increments `open_executions` in the same fenced transaction that records the execution's own row. The starts are:
- an agent turn (`AgentTurnJournal.create`);
- a run admission (`run_input_runtime`'s admission transaction);
- an automation or wake fire;
- a consumer reservation.

Its end decrements the count. The end is settled terminal, cancelled, or reconciled.

**A continuation does not increment.** A continuation is an agent node inside an admitted run, or a tool round inside an admitted turn. It carries its parent's admission id and is allowed while the key is `closing`. Round-1 finding 8: no run is refused mid-flight.

**Background starters never get `admission_closed`.** These are the scheduler, automation pump and wakes, all under the platform lease. They read the key's state before dispatch and leave the fire durable (queued) until the key is open under its new owner. A late fire is fine; a lost one is not.

The deploy's in-flight probe (phase 1) becomes, per key, `open_executions`. Seats remain as concurrency limits only.

### D6. Request authority: an explicit, accepted trust boundary plus owner-side resolution
**The trust boundary is accepted, and named.** The frontend is the platform's authentication authority, as the monolith is today. A compromised frontend can assert any user. That is no wider than a compromised monolith, which can already forge process-local authority. It is still a real concentration of trust, recorded as such (round-1 finding 2).

**Narrowing that does hold:**
- The owner executes only for a request with an open frontend connection, and only one execution per operation id (D6a).
- The socket carries `SO_PEERCRED` plus a per-key-generation HMAC, so only the frontend uid can reach the owner, and only a current frontend can speak.

**The envelope** forwarded per request:
- the full verified `Identity` (user id, capabilities, tenant metadata, auth method);
- the MCP session and request ids;
- the tool name;
- the arguments.

The owner binds that Identity into its own request context, so `current_actor_id()`, the action-scope checks and first-contact home creation behave exactly as today, with the same capabilities and no more (round-1 finding 1).

**The tier is never accepted from the frontend.** The owner re-resolves it against the current exact-universe admin grant, as `universe_intelligence.py:~1407` already does.

**The capability** is minted in the owner, bound to the turn task and the operation id. It is revoked at the turn's end.

**Request kinds:**
- MCP and app requests use this path.
- Autonomous work uses `work_invocation` authority, unchanged (`workflow_agent.py`), and never this envelope.

### D6a. Operation identity makes retries observe, not re-run
**The op id.** The frontend assigns `op_id` (a uuid) when it first persists the request (D7). The owner's admission inserts `cc_operations(op_id PK, owner_key, principal, session_id, target, args_digest, execution_ref, state)` in the same fenced transaction as the execution row.

**A retried forward with the same `op_id`** finds the row and ATTACHES to the existing execution's stream or terminal; no second execution starts. If the principal, target or args digest differ, it is refused as a conflict (round-1 finding 3).

**Cancellation** is an event keyed by `op_id`. Applied before admission, it marks the pending row cancelled. Applied after admission, it is the owner's stop for that execution (`turn_interrupt`), never a dropped request.

### D7. Pending requests: account-scoped holding with explicit states, not custody
**Persist first.** Before it forwards or acknowledges anything, the frontend appends `pending_requests(op_id PK, principal, session_id, frontend_token, target_hint, message, args_json, state, created_at)` with `state = 'pending'`.

**What the row is.** It is account-scoped temporary holding, not conversation custody. It grants nothing. Its destination is resolved and authorised only by the owner, at admission (round-1 finding 10). Retention: deleted after projection, or after 30 days when abandoned. It is exported with the account and deleted with the account.

**States:**
- `pending`, then `admitted`, when the owner's admission writes `op_id`;
- then `projected`, when the thread has recorded the founder row. A projection receipt holds the `op_id` and turn number, and the row is deleted only after the thread read-back verifies it;
- or `abandoned`.

**Abandonment is a FACT, not row age.** A row is abandoned when either:
- the frontend recorded the client's disconnect before admission; or
- `frontend_token`'s liveness reads DEAD while the row is still pending (round-1 finding 9).

Abandoned rows are projected back into the thread as the message plus "this was not answered; send it again". The projection is idempotent on `op_id` (ext_id `pending:<op_id>`), and it is never executed.

**Deletion** takes the account-deletion admission exclusion and rechecks the tombstone on both sides:
- the frontend's insert;
- the owner's projection.

So a delete cannot race a late insert (round-1 finding 11).

### D8. Learning advances only over processed turns
`settle_learned_cursor` takes an explicit `to_turn` (no "latest row" default). The served path passes the exact founder and reply turn numbers it processed. Rows projected from abandoned pending requests are marked `processed = 0` and are never covered by another turn's settlement (round-1 finding 11).

### D9. Owner text is acknowledged only after it is persisted
`agent_steering` carryover and steering become read-then-acknowledge. The source row is retired only after the consuming turn's durable record of that text exists in the turn input or the thread (`agent_steering.py:217,227`). This is the invariant behind the live 2026-10-02 mid-turn loss; dots-research owns that fix (S2). This change adds the invariant test.

### D10. Frontend-only deploys
`runtime_paths` classifies changed files. Frontend-only changes take #4272's blue-green, and old frontends keep their open streams until those streams end. There is no stream cap that could cut a response (round-1 finding 13). A stream that the client itself drops does not end the turn: the turn lives in the owner, and its reply lands in the thread. Any change to an owner module takes D4.

## Migration Plan (B1 is coherent and revertible)

- **B0 (precursor, deployed first).** `AgentTurnJournal` inserts name their columns (`agent_turn_journal.py:~410` is positional today). After that, an added column cannot break a revert.
- **B1. Lease store, keyed fences, `owner_generation`, `advance_fence` and `fenced`, the registry and the restore tool.** The current single process acquires `platform` plus every `cc:` key at boot (acquire by key, lazily on first use). It reconciles `< G` per key. The fence is initialized at acquisition. Revert: the columns and tables are additive and unused by old code.
- **B2. Admission rows and op ids, whole-execution counting, and continuation carriage.** Also the D9 steering fix and the D8 cursor fix.
- **C1. Frontend/owner process split, the D6 envelope and minting, the pending journal (D7), and the module classifier.**
- **C2. The `deploy-prod` handover path (D4) and the frontend-only path (D10).** Phase 1's wait becomes per-key idleness. Add the metrics (failed requests, interrupted turns, lingering old-owner time) and the force path.

## Risks / Trade-offs

- **[An old owner lingers behind a never-idle command center]** Memory is spent and measured. Force is an operator action that cuts only that key's work, honestly.
- **[The frontend concentrates authentication trust]** Accepted and named. No wider than today.
- **[Every start gains a fenced admission write]** One write in a transaction that already exists for the journal or run row.
- **[The platform key's swap delays fires]** Durable triggers: late, not lost.

## Open Questions

- **Q2.** The frontend's hold bound for a key in transfer. Proposal: 120s; past that, the client gets an honest retryable status and the pending row remains.
- **Q3.** Is idleness per command center the right grain when one account owns several? Ownership is per command center, so one busy center does not hold the account's others.

## Round-1 refute cross-reference

| # | Finding | Answered in |
|---|---|---|
| 1 | Envelope lacks capabilities; tier must be re-resolved | D6 |
| 2 | Frontend can assert any user | D6 (accepted, named boundary) |
| 3 | Retry executes twice | D6a |
| 5 | Death proof lost; restore | D2 |
| 6 | Wrapper not a boundary; advance rejected | D3 |
| 7 | Barrier topology | D4 (idle move) |
| 8 | Whole executions | D5 |
| 9 | Abandonment / ack | D7 |
| 10 | Custody | D7 |
| 11 | Learning / deletion races | D7, D8 |
| 12 | Shared stores under per-command-center ownership | D1 |
| 13 | Drain contradiction; B1 coherence | D4, D10, Migration |
