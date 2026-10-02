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

### D2. Acquisition: voluntary release, or kernel-proven death of the WHOLE owner tree; restore is gated
A process acquires `owner_key` inside `BEGIN IMMEDIATE` on the lease store. There are two distinct paths, plus first use, and no acquisition happens while a restore is in progress (below).

- **Voluntary release.** The row is `released`. The old owner released it in D4's idle transaction, so it holds no execution for that key.
- **Death recovery** (round-2 finding 1). The holder's process dying is NOT enough: today's HTTP engines are ordinary subprocesses (`engine_mcp_http.py:277`) that can outlive the server and keep dispatching. So every process that executes for an owner takes a **shared** flock (`LOCK_SH`) on that owner's tree lock `.owner_tree/<holder_token>.lock`, inherited by being opened at that process's own start, never by fd inheritance:
  - the server process;
  - every engine child;
  - every worker the owner spawns.

  Death recovery requires `LOCK_EX|LOCK_NB` on the tree lock to SUCCEED. The kernel grants that only when no member of the tree is alive, whatever killed it. This is kernel-proven quiescence of every executor that could still act for the old generation. Effects those processes already sent externally remain potentially completed: they are reconciled as unknown (D2 of #4263), never replayed. The holder's own liveness token (`process_liveness`) still blocks a contender while it is alive.

  **Admission is serialised against recovery** (round-3 finding 1). An `LOCK_EX` that succeeds proves only that no member holds the lock NOW. A child that had been spawned but had not yet locked could join afterwards. So:
  - every child, AFTER taking its `LOCK_SH`, re-reads the lease row and executes only if the row still names exactly its spawn holder, generation and proof (`verify_lease_proof`). Otherwise it exits without acting;
  - the recovering contender holds its `LOCK_EX` on the old tree lock until its new lease row (and new proof) is committed.

  A delayed child therefore either joins before the `LOCK_EX`, which blocks recovery until it dies, or joins after and finds the lease replaced. Tree membership is keyed by the ORIGINAL holder token, which the child receives in its environment, not by its own post-fork token (`process_liveness.py:169` rotates that).
- **First use.** No row exists for the key.

**The acquirer:**
- sets `generation = max(row.generation, catalog_high_water(owner_key)) + 1`. `catalog_high_water` reads the per-key fence high-water that the lease store itself records. Every `advance_fence`/`init_fence` writes the store's fence and the lease store's `fence_high_water(owner_key, store)` together, with the store write first; a crash between them leaves the store ahead, and restore reads the stores themselves;
- mints a 32-byte proof and stores only its sha256;
- records its own `owner_token` and tree lock.

**Liveness retention.** Cleanup (`runtime/assigned_queue_consumer.py:~265`) must never delete a liveness file or tree lock that a lease row, or a pending row's frontend (D7), names. An UNKNOWN holder blocks; it is never read as dead.

**Restore** (round-2 finding 2: a gate, not a scan).
- The lease store carries `restore_state(singleton, state CHECK IN ('none','in_progress'), started_at, manifest_json)`. Every acquisition and every `init_fence` refuses while `state = 'in_progress'`. An interrupted restore therefore fails closed: no owner can start until the tool is re-run to completion.
- `scripts/owner_lease_restore.py` runs in a fixed order:
  1. takes the host-mutation flock and holds it to the end;
  2. stops the stack (`docker compose stop daemon` plus every service that mounts the data volume, found by a volume-mount scan, not a process-name scan);
  3. sets `restore_state = 'in_progress'` in its own committed transaction;
  4. reads every store in the catalog (below), plus a deterministic offline enumeration: each registered store KIND declares a complete path enumerator over the data root, including nested layouts such as `<data_root>/.agent-sessions/<universe>/` (`agent_sessions.py:84`, `agent_steering.py:79`, `agent_rules.py:175`). Discovery then never depends on catalog contents (round-3 finding 3). A test asserts that every store kind has an enumerator, and that the enumerator finds a store created at each of its layouts;
  5. computes each key's high-water as the max of the recovered lease generation, every recovered fence, and every `agent_turns.owner_generation` (round-2 finding 3: the recovered lease generation is included);
  6. writes each key's row `released` at that high-water, writes the manifest, and sets `state = 'none'` in ONE transaction.
- Containers restart only after the tool exits.

### D3. Two write primitives, plus first-fence initialisation and one durable store catalog
**`fenced(conn, owner_key, lease)`** is used for ordinary owner mutations. It requires an idle connection and raises otherwise. It then runs:
1. `BEGIN IMMEDIATE`;
2. read `owner_fence[owner_key]`;
3. if the fence is not equal to `lease.generation`, raise `LeaseLost`;
4. run the body;
5. `COMMIT`.

It is the one transaction: a helper that commits inside the body is a bug, and a test asserts `conn.in_transaction` holds through the body.

**`advance_fence(conn, owner_key, lease)`** is called only during acquisition, after `verify_lease_proof`. It requires the stored fence to be below `lease.generation` and writes it.

**`init_fence(conn, owner_key, lease)`** applies when a store has NO fence row for the key (a store created after acquisition, such as a new universe's `.runs.db`). It requires `verify_lease_proof` and writes the fence at the current generation (round-2 finding 3).

**The store catalog.** `owner_store_catalog(store_path PK, store_kind, scope, owner_key, registered_at)` lives in the lease store. Every owner-store constructor registers its path before its first fenced write. Restore reads the catalog plus the offline scan.

**Schema and migrations are extracted, not wrapped** (round-2 finding 4). Today, `SQLiteProviderWorkAuthorityStore.connection()` runs its schema, the receipt table rebuild (which commits on its own, `provider_work_authority.py:266,303`) and its column migrations on EVERY open. `AgentTurnJournal._transaction` calls `ensure_schema` before its transaction, and automations (`automations.py:625`) and run input admissions (`run_input_admissions.py:48`) migrate at runtime too. B1 moves every rebuild and `ALTER` into one startup migration step (`tinyassets/storage/migrations.py`), run under the host-mutation flock before the server takes any lease. Store opening keeps only `CREATE ... IF NOT EXISTS`. The B1 inventory test asserts that no connection helper runs `ALTER`, a rebuild, or `executescript` outside that step.

Under C2's mixed-version operation, an old owner may still be serving while a new one has started. Migrations are therefore additive-only: no drop, no rename, no rebuild. A rebuild needs a declared maintenance window (#4263's schema-cutover exception).

**The registry test.** `OWNER_STORES` plus the catalog. The inventory test fails on any writer reachable from the owner entrypoints that is neither fenced nor listed with a reason.

**Engine writes in B1** (round-2 finding 1). Engine children receive the owner key, generation and proof in their environment at spawn. They open their own connections and write through `fenced` with that generation, so an orphaned engine from an older generation commits nothing.

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

### D5a. State shared across command centers never lives in owner memory; frontends route by command center
These are openshell-spike's conditions for per-command-center ownership, from the #4263 D11 amendment (61d124eb on spec/target-architecture-amend-1).

**Shared state stays in shared stores.** During a handover, one account's command centers can sit in two owner processes. Anything counted per account or per host therefore stays in a shared store, written under `BEGIN IMMEDIATE`, and is never cached in a process:
- **Seats.** They live in `.account_seats.db`, already shared, with per-account counting and leases.
- **Host-capacity admission.** This is boxhostd's single queue in S4.
- **Meter rows.** They are append-only and owner-fenced per command center, and aggregated per account.

**Frontends route by command center.** Each turn start and cancel goes to that command center's current owner, through a `cc → (owner endpoint, generation)` map kept in the lease store. Queueing is per command center. A cancel always reaches the owner that holds the turn: it is routed by the turn's `owner_generation`, not by the current map entry.

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
- **B1.** It consists of:
  - the migration extraction (D3);
  - the lease store, with tree locks, `restore_state`, the catalog and `fence_high_water`;
  - keyed fences: `fenced`, `advance_fence` and `init_fence`;
  - `owner_generation`, with reconcile per key `< G` after acquisition;
  - the restore tool;
  - engine children writing fenced at their spawn generation.

  The current single process takes the tree lock at start, then acquires `platform`, plus each `cc:` key lazily on first use. Its engines join its tree. Because the server and its engines share the container's PID namespace under tini, a container restart kills the whole tree, and the next boot's death-recovery acquisition proves it.

  Revert safety: B1's columns and tables are additive, and B0 makes old inserts tolerate them. A revert leaves the migration step's additive changes in place, and they are harmless.
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
| 4 | Kernel-lock sound for cooperative ownership (AGREE) | D2 keeps the liveness flock and adds the tree lock |
| 5 | Death proof lost; restore | D2 |
| 6 | Wrapper not a boundary; advance rejected | D3 |
| 7 | Barrier topology | D4 (idle move) |
| 8 | Whole executions | D5 |
| 9 | Abandonment / ack | D7 |
| 10 | Custody | D7 |
| 11 | Learning / deletion races | D7, D8 |
| 12 | Shared stores under per-command-center ownership | D1 |
| 13 | Drain contradiction; B1 coherence | D4, D10, Migration |

## Round-2 refute (ADAPT) cross-reference

| # | Finding | Status |
|---|---|---|
| 1 | Owner death does not prove engine death | D2 tree lock (`LOCK_SH` per executor, `LOCK_EX` proves the whole tree dead); D3 engines write fenced at their spawn generation |
| 2 | Restore needs a gate, not a scan | D2 `restore_state` plus fail-closed acquisition, held flock, stack stop by volume mount |
| 3 | Restore can lower a generation; dynamic stores | D2 includes the recovered lease generation; D3 catalog, offline scan and `init_fence` |
| 4 | Migrations must be extracted | D3: extracted into one startup step, additive-only, inventory test |
| 5-7, 11 | B2: cross-database admission, exactly-once settlement, spawned descendants, gap-aware learning | **Must resolve in the B2 design addendum before B2 starts** |
| 8-10 | C1: one winning pending transition, the abandoned projection's authorisation, a principal-scoped deletion exclusion | **Must resolve before C1** |
| 12 | C2: force scope = container; phase-1 cap rules transitional; closing a busy key makes its requests wait | **Must resolve before C2**. Direction: close a key only at its idle instant, so no request waits behind a turn |

## Round-3 refute (final round): ADAPT, two must-fixes, both applied as prescribed

| # | Finding | Status |
|---|---|---|
| 1 | A delayed child can join the tree after the exclusive probe succeeds | D2: the child validates holder, generation and proof after `LOCK_SH`, and the contender holds `LOCK_EX` through lease replacement (the reviewer's prescribed fix) |
| 2 | Restore gate | AGREE |
| 3 | The offline scan misses nested store layouts | D2: a complete path enumerator per store kind, with a test (the reviewer's prescribed fix) |
| 4 | Migration extraction | AGREE, enforceable |

Review cap reached (3 rounds). Taken to the lead per AGENTS.md; no fourth round.

## B1 as built (feat/owner-lease-b1): refinements from its code review

Three refinements came out of the Codex code review of B1. The design above is otherwise unchanged.

- **Founder and members.** A tree's FOUNDER is the process that started it, the daemon, from `main()` before anything is spawned. Every other member is a spawned executor that joined through `TINYASSETS_OWNER_TREE`. Engines join at their own startup, and they refuse to start if the founder is gone. A member acts only while its founder holds its member lock, and it never takes a key by death recovery; succeeding a dead owner is the founder's job. This is how D2's "a child validates its spawn owner" holds without passing a proof to every child.
- **Pre-lease rows are generation 0.** The first acquisition of any key is generation 1. So the first leased boot settles a leftover from before B1, as the boot rule it replaces did.
- **Open-time migrations are gated, not yet extracted.** `owner_stores.MIGRATES_ON_OPEN_BEFORE_C2` names every connection helper that migrates a schema when a store is opened (`provider_work_authority.connection()`, and the journal's additive `owner_generation` ALTER). The journal ALTER is re-checked under `BEGIN IMMEDIATE`, so it is race-free. C2 cannot set `HANDOVER_ENABLED` while either list in `owner_stores` (`FENCE_BEFORE_C2`, `MIGRATES_ON_OPEN_BEFORE_C2`) is non-empty. Full extraction into a startup step is owed before C2, together with the 82 writers still awaiting a fence.
- **Owed before C2 (B1 code review round 3, P2, non-blocking today):** `recover_dead_keys` runs once, at founder start. Suppose a key was skipped because an old engine child was still alive. That can happen only with overlapping owners, and today's deploy stops the old container first, so it cannot happen now. Once that child exits, nothing retries the recovery, and a new child cannot succeed the dead holder. C2's handover must retry recovery when a skipped holder dies. Note too that each recovery costs a SQLite busy wait plus a fence per key; measure it before many keys exist.

## B2 design addendum: round-2 findings 5, 6, 7 and 11, resolved before B2 is built

### B2-1. Admission state lives beside each execution's own row (round-2 finding 5)
There is no cross-database counter. The fence row gains a column: `owner_fence(owner_key, generation, admission_open)`, present in EVERY owner store, alongside the generation. An execution start checks `admission_open = 1` and inserts its own row in ONE fenced transaction on ITS store. That store is the journal for turns, the run's own `.runs.db` for runs, and the automations store for fires.

Closing a key is a fenced write of `admission_open = 0` to every cataloged store for that key. Until every store is closed, the key is never tested for idleness, so a partial close is conservatively non-idle. Once all are closed, the set of open executions can only shrink, so the idle test cannot race a new start. A key is released only after an idle test, in a lease-store transaction, that re-verifies every store is still closed.

### B2-2. "Open" means a live execution claim, not a counter (round-2 finding 6)
Each execution holds an `exec_claims(exec_id, owner_key, member, parent_exec_id, started_at)` row in its own store.
- It is inserted in the admission transaction.
- It is deleted in the executing process's `finally`, AFTER worker and effect teardown. That ordering is what ties settlement to teardown, not to a terminal-looking row.
- A claim whose member lock is free belongs to a process that died. It is not open, and its row is reconciled by generation as today.

So no decrement can be lost or doubled, there is no CAS to get wrong, and a crash anywhere leaves either a live claim (still open, which is correct) or a dead one (not open, which is also correct). Idle for a key means: every store is closed, and no claim with a live member exists for that key.

### B2-3. Spawned descendants are continuations with their own claims (round-2 finding 7)
A start that carries `parent_exec_id`, whose parent claim is live, is a CONTINUATION. It is admitted even while the key is closing, and it inserts its own claim. Examples are an agent node's `run_graph`, or a turn's tool round that enqueues work.
- **Fire-and-forget children.** The parent may finish first, and the child's own claim keeps the key non-idle until the child's teardown.
- **Across processes.** The parent id travels with the child to the engine process. That process is a member of the same tree, so its claim is counted.
- **Durable fires do not block idleness.** A trigger row that has not started holds no claim. It waits, durably, for the key to open under its new owner. "Nothing queued" in D4 therefore means no frontend-held request for the key, not "no durable fire".

### B2-4. Learning advances over a gap-free processed range (round-2 finding 11)
Learning settlement uses explicit ranges. `settle_learned_cursor(from_turn, to_turn)` advances only across turns that are each either processed by this settlement or marked `learn_excluded`. Rows a turn did not process stop the advance at the first gap. Rows projected back from abandoned pending requests (C1) are marked `learn_excluded`: never claimed as learned, never blocking. A later turn that processes a gap row advances past it.
