## Context

**Today.** One container runs one uvicorn process (`universe_server`). That process:
- serves MCP and the app;
- runs every agent turn in a FastMCP worker thread;
- is the single writer of `agent_turns` (the load-bearing assumption in `storage/agent_turn_boot.py`);
- drives the scheduler, automations, outbox and seats.

**What a turn's authority is.** A served turn is authorised by a process-local provider-request capability, minted per MCP tool call. `auth/middleware.py` reserves it in `on_call_tool`. The tool wrapper (`universe_server.py:~385`) claims it and revokes it before the result is released. The capability is bound to the issuing pid and to the worker thread.

**Phase 1 (#4278).** The deploy waits for in-flight work, up to 45 minutes, and then recreates the container.

**Target.** #4263 D11/S8: frontends plus exactly one owner under a generation-fenced lease. New requests queue while the owner changes, and never fail. The owner handover drains, then journals what is left, and nothing replays. Interfaces I3/I8/I9 are fixed by #4263.

**Collaborators.**
- **cp-scheduler (S8b, #4276):** the `OwnerLease` seam: `tinyassets/control_plane/lease.py`, `current_owner_lease()` / `set_owner_lease()`, `LeaseLost`, `proof`, `verify_lease_proof`.
- **agent-loop (S7):** the journal writer under the lease.
- **deploy-incident (#4272):** the frontend blue-green switch. HAProxy on 8001, colours on 8011/8012, a ready handshake, and a 10 min frontend stream drain.
- **dots-research (S2):** the mid-turn lost-message fix.

**Superseded.** `durable-turn-inbox` (spec/durable-turn-inbox, 876aeff4). Its Codex shape refute is the input to D6, D7 and D9 below:
- replay has no authority to run a turn;
- a queued run must be a frozen terminal with a projection;
- account deletion sweeps by the current home only;
- the learned cursor can cross unprocessed messages;
- carryover and steering are deleted before they are persisted;
- there is no admission barrier.

## Goals / Non-Goals

**Goals:**
- A deploy of frontend-only code interrupts nothing.
- A deploy of owner code interrupts only turns still running at the owner drain bound, and those are reported, never replayed.
- New requests during a handover wait and are then served with their own live authority. None is refused.
- No message the owner sends is ever lost: it is either answered, or shown back verbatim in the thread with an honest notice.
- At most one owner commits at a time, on one host and across a restore.

**Non-Goals:**
- Cross-host and standby promotion. That needs S1 (platform-state durability); the provider-API fencing is D11's job there. This change fences on one host.
- Boxes (S4/S5). `boxhostd` gets a barrier stub.
- Moving the credential broker into its own process (S6). The barrier acks the in-process broker.

## Decisions

### D1. The lease: one row, a monotonic generation, death proven by the holder's flock rather than a clock
`<data_root>/.owner_lease.db` holds the table `owner_lease(singleton CHECK=1, generation, holder_token, proof_sha256, acquired_at, released_at)`.

Acquire runs inside `BEGIN IMMEDIATE`. It succeeds when either:
- `released_at` is set; or
- `process_liveness.owner_state(holder_token)` reads DEAD. The previous holder took its liveness flock at acquisition, and the kernel drops that flock only when the process dies.

Then:
- `generation := max(row.generation, max fence over all owner databases, max(agent_turns.owner_generation)) + 1`. The fence and journal terms are D1's restore-safe incarnation.
- A fresh 32-byte proof is minted; only its sha256 is stored.

While the holder is alive, a contender waits; it is never refused.

*Alternative rejected:* expiry by time. A paused process (GC, a frozen VM, a SIGSTOP) outlives a TTL and wakes up still thinking it is the owner. The fence (D3) would stop its commits, but flock-proven death means a live owner is never displaced at all. `verify_lease_proof(G, proof)` is true only for the currently held G (constant-time compare).

### D2. `agent_turns.owner_generation` replaces the boot rule
- **Migration.** `ALTER TABLE agent_turns ADD COLUMN owner_generation INTEGER NOT NULL DEFAULT 1`. Run it in `ensure_schema`, outside any transaction, under the existing idle-connection rule.
- **Writes.** `create` stamps the caller's G.
- **Reconcile** (`agent_turn_reconcile.reconcile_orphaned_turns`):
  - it requires `lease.held()`;
  - it settles WORKING rows with `owner_generation < G`;
  - it settles them through the same transitions it uses today.
- **The status projection** (`universe_working_turn`) treats a row as live only if `owner_generation == current G`.

`BootTurns` stays only as the in-process claim set, used to release a cancelled task. Its created-at disjunct is deleted, together with its single-writer caveat; the lease now enforces that caveat. `tests/test_orphaned_turn_reconcile.py` gains two cases:
- **standby start:** the new owner process starts before the old one releases. It reconciles nothing until it holds the lease, and then settles only G-1 rows.
- **restore order:** a recovered journal is ahead of the recovered lease. The generation is still above both.

### D3. Fenced writes: a fence row in every owner database, checked in the write transaction
Each owner-written database gets `owner_fence(singleton CHECK=1, generation)`. Writes go through `fenced(conn, lease)`:
1. `BEGIN IMMEDIATE`;
2. read the fence;
3. if `fence != lease.generation`, raise `LeaseLost`;
4. otherwise run the body, then `COMMIT`.

The barrier (D4) advances fences with its own fenced write at G. A stale owner therefore serialises behind it and then fails the check. It never commits.

The inventory of owner databases is task 1.3. It starts from the data-root `.tinyassets.db` (journal and provider work authority), `.account_seats.db`, `.runs.db` (root and per universe), and the automations, outbox and notification stores. A store left out of the inventory is a store a stale owner can still write. The inventory is therefore a test: every `sqlite3.connect` writer reachable from the owner process uses `fenced`, or is listed with a reason.

### D4. Activation barrier, in order
A new owner at G:
1. advances every owner database's fence to G;
2. sends `fence(G, proof)` to each effect executor, and waits for an ack that it has persisted G, cancelled and closed everything under an older G, and refuses anything below G (#4263 D5);
3. runs reconcile (D2);
4. opens admission (D5).

An executor that cannot ack blocks activation and pages. The executors today:
- the in-process provider/egress broker, whose ack is the cancellation of every tracked stream older than G;
- a `boxhostd` stub that acks.

### D5. One admission point, in the same transaction as the journal row
The owner starts a turn with one fenced transaction on the journal database. It:
- checks `owner_admission.open = 1` (a column on the fence row, so one read covers both);
- inserts the `agent_turns` row at G.

The handover closes admission with a fenced write. So every request is in exactly one of two states:
- recorded, counted, and drained;
- answered `admission_closed` to the frontend, which then queues it (D7).

No request can pass a hold check and then miss both the queue and the seat count. This is the refute's barrier finding. Seats stay as they are (concurrency limits); the deploy's in-flight count reads the journal at G instead of guessing from seats.

### D6. The frontend asserts identity; the owner mints the capability
**The channel.** Frontends talk to the owner over a Unix socket on a volume shared only by those two services (`/run/tinyassets/owner.sock`). Every connection is checked twice:
- by `SO_PEERCRED`: the uid must be the frontend's;
- by an HMAC over each frame, keyed by a per-owner-generation secret. The owner writes that secret 0600 into a directory only the frontend uid can read.

**The forwarded turn start** carries the identity the frontend VERIFIED from the bearer (`current_mcp_message_identity()`): user id, session id, request id, tool name. It also carries the request arguments.

**Minting.** The owner mints its own provider-request capability for that identity and request: the same record shape as `_PROVIDER_REQUESTS`, issued in the owner process, bound to the turn's task. It revokes the capability when the turn ends. The interlocutor tier and the identity ContextVar are bound in the owner's turn context from the same assertion.

This is the authority change. A compromised frontend can act as any user it can authenticate, which is no more than it can already do today, because today the frontend IS the turn runner.

*Alternative rejected:* forwarding the bearer token to the owner and re-verifying it there. That puts long-lived credentials on a second hop and duplicates OAuth verification.

### D7. Queue during a handover: hold the LIVE request, and persist its text first
When the owner socket is unavailable, or answers `admission_closed`, the frontend keeps the client's request open and retries. It uses the live request's own authority when the new owner opens, and is bounded by `FRONTEND_QUEUE_BOUND_S` (default 900). The client sees a progress event: "TinyAssets is finishing an update; your message is next".

**Persist first.** Before it does anything else with a converse request (including the first forward), the frontend appends the message verbatim to `pending_requests` (`<data_root>/.pending_requests.db`), keyed by (user, request id). The owner deletes the row once the turn's founder row is recorded in the thread.

**A row left behind is a lost request.** That happens when the client disconnected, the bound passed, or the frontend died. The owner drains such rows on activation and on a timer. It posts the message back into the thread verbatim with a notice ("this message was not answered; send it again") and deletes the row. **Nothing is executed from this journal.** There is no replay authority, and none is needed.

Account deletion sweeps this journal by owner user id across every universe, not by the current home. That was the refute's former-home finding.

### D8. Handover sequence (owner deploys)
Step 4 is the open question Q1.
1. Start the new owner as standby. It is not serving and does not hold the lease, so it cannot reconcile (D2).
2. Signal the old owner to close admission (D5).
3. The old owner drains: in-flight turns finish, up to `OWNER_DRAIN_BOUND_S`.
4. At the bound, the old owner journals what is left, cancels it, releases the lease, and exits. Those turns are reconciled by the new owner into held states with the "interrupted" notice.
5. The new owner acquires at G+1 and runs the barrier (D4). Then it reconciles, opens admission, and announces ready to the frontends.
6. Frontends flush their held requests.

The deploy measures `failed_requests` (target 0) and `interrupted_turns` per handover, and publishes both to the job summary and `get_status`.

### D9. Owner text is acknowledged only after it is persisted
`agent_steering` deletes carryover before returning it, and deletes delivered steering before the caller records it (`agent_steering.py:217,227`). Both become read-then-acknowledge: the source record is retired only after the consuming turn has durably recorded the text, either in the turn input or in the thread.

The live 2026-10-02 loss (a message sent mid-turn vanished, unpersisted, with no notice) is required to be impossible under this rule. dots-research owns that fix in S2. This change adds the invariant test.

### D10. Frontend-only deploys
`runtime_paths` already classifies changed files. A deploy whose changes touch only frontend modules takes the #4272 blue-green path and touches no owner. Any owner-module change takes the D8 path. The split of modules into frontend and owner is part of task 3.1, and the classifier is a test.

## Risks / Trade-offs

- **[The owner drain bound still cuts long turns on owner deploys]** That is honest and measured, and the bound is configurable. Frontend-only deploys no longer pay it. See Q1 for the shape that removes it.
- **[Frontend-asserted identity]** D6: no wider than today. The local channel is peer-checked and HMAC'd.
- **[Every owner write gains a fence read]** One indexed singleton read inside a transaction that already holds the write lock.
- **[Topology change]** Two processes mean two images or two entrypoints. The memory budget is in `capacity-is-memory-not-cpu`: the frontend is small.

## Migration Plan

The work ships as four slices, each its own PR, live-verified before the next:
- **B1:** lease, generation, fence and reconcile, all inside the current single process. It acquires the lease at boot. No behaviour change except the reconcile rule.
- **B2:** barrier and admission.
- **C1:** the frontend/owner process split and capability minting.
- **C2:** the handover deploy path, the pending journal and the metrics.

Rollback for each slice is a revert. The added column and tables are additive.

## Open Questions

**Q1 (shape; needs the lead and openshell-spike).** Single owner (#4263 D11) or per-universe ownership?

With ONE owner, step 3 of D8 makes every NEW request on the platform wait for the slowest in-flight turn, up to the drain bound: 10 minutes by #4263's default, 45 by phase 1's. With per-universe ownership, the lease is keyed per universe and every universe has its own G. The new owner takes each universe as soon as that universe's in-flight turns end. A request then waits only behind its own universe's running turn, which is what interactive seats already do today. A turn runs until it finishes, and nobody else waits for it.

Cost: a lease and fence per universe, and a barrier per universe move. This matches the per-command-center boxes #4263 D1 is heading to.

**Recommendation:** per-universe ownership, with a platform-wide owner for the scheduler and outbox (S8b's lease). It is a deviation from D11's "exactly one", so it needs approval before B1.

**Q2.** `FRONTEND_QUEUE_BOUND_S` (900) and `OWNER_DRAIN_BOUND_S` (#4263 says 600; phase 1 used 2700). Proposal: 2700 for the owner while the shape is single-owner; per-universe makes it moot.

**Q3.** Does the in-process broker's "ack" (cancel streams older than G) cover every effect path today, including HTTP connections, effectors and engine children? Task 2.1 inventories it.
