# One execution owner under a fenced lease, so a deploy hands turns over instead of killing them

## Why

**Today the daemon is one process, and every deploy recreates it.** That process serves MCP and the app, runs every agent turn, writes the turn journal, and drives the scheduler and outbox. Every merge to main deploys and recreates it.

**Phase 1 (#4278) makes the deploy wait.** The deploy waits for in-flight work, up to 45 minutes, and then swaps. Two problems remain:
- A turn still running at the cap is cut.
- While a deploy waits, nothing new ships.

The founder's law is that a served turn runs until it is finished. Each merge should ship without cutting it.

**#4263 (target architecture, stamped, not yet merged) fixes the shape in D11/S8.**
- Replaceable frontends serve clients.
- Exactly one **execution owner** runs turns, under a lease with a monotonic generation.
- Every owner-side write is fenced on that generation.
- A deploy hands the owner over instead of killing it.
- New requests queue while the owner changes, and never fail.

This change is S8a: the lease, the fence, generation-based reconcile, and the frontend/owner split with the handover.

**The durable-turn-inbox approach failed review, and this change replaces it.** The Codex shape refute (2026-10-02) found that replaying a queued message after a swap has no authority to run a turn. A served turn needs a live, process-local provider-request capability that dies with the request. This change keeps the request LIVE in the frontend during the handover window, so its authority is never reconstructed.

## What Changes

**Owner lease.**
- One lease row with a monotonic generation G, a holder token, and the sha256 of a per-acquisition proof.
- It is acquired only after the previous holder released it or is PROVEN dead. Proof of death is its kernel-held liveness lock, not a clock.
- The new G is greater than every generation found in any store, so a restore cannot reuse an old generation.
- It plugs into the `OwnerLease` seam that `cp-scheduler` publishes in `tinyassets/control_plane/lease.py`: `generation`, `held()`, `check()`, `proof`, `verify_lease_proof`.

**Generation on turns.**
- `agent_turns.owner_generation` is added; existing rows are backfilled to 1.
- Startup reconcile settles only rows with `owner_generation < G`, and only after the lease is held.
- This replaces `BootTurns`' created-at rule (`storage/agent_turn_boot.py`).

**Fenced writes.**
- Every database the owner writes holds an `owner_fence` row.
- An owner mutation commits only inside `BEGIN IMMEDIATE`, and only if the fence equals the owner's generation. A stalled old owner therefore commits nothing.

**Activation barrier.**
- Before it serves, a new owner advances every fence to G.
- It pushes G to each effect executor and waits for each to acknowledge. Today that means the provider broker in-process; `boxhostd` is a stub until S4/S6.
- It reconciles, and only then opens admission.

**One admission point.**
- A turn starts only inside the owner, in the same fenced transaction that records its journal row.
- Closing admission for a handover is a write to that same database.
- So a request is either recorded as in flight (and drained), or refused into the queue. There is no gap between the hold check, the queue and the seat count; this is the refute's barrier finding.

**Frontend and owner as separate processes.**
- Frontends authenticate the client and forward turn start and stop to the owner over a local socket.
- The owner mints the turn's provider-request capability on its own side, from the frontend's authenticated assertion.
- During a handover, a frontend holds the live request and waits; it never refuses.
- Before it acknowledges anything, the frontend writes the owner's message verbatim to a durable pending-request journal. If the request is then lost (the client leaves, or the frontend dies), the owner posts the message back into the thread with an honest "not answered, send again" notice. It never runs it, which would need a replay authority.

**Owner text is never dropped.**
- Carryover and steering are acknowledged only after durable persistence, not deleted first (the refute's `agent_steering.py:217,227` finding).
- The mid-turn message loss seen live on 2026-10-02 is covered by the same rule. dots-research owns the S2 fix; this change requires the invariant.

**Deploy paths.**
- `deploy-prod` gets a frontend-only path, which is blue-green through deploy-incident's #4272 switch and interrupts nothing.
- It gets an owner-handover path for owner code changes.
- Phase 1's wait remains the owner path's drain.

**Metrics.** Failed requests per deploy (target 0) and interrupted turns per handover are measured and published.

## Capabilities

### New Capabilities
- `execution-owner`: the lease, the generation, fenced writes, the activation barrier, admission, and the frontend/owner turn protocol.

### Modified Capabilities
- `uptime-and-alarms`: the deploy hands the owner over (or deploys frontends only), and measures failed requests and interrupted turns.
- `live-mcp-connector-surface`: `converse` is served by a frontend that queues during a handover. The tool contract is unchanged.

## Impact

- **Code:** `tinyassets/control_plane/lease.py` (seam, from #4276), a new owner lease store, `storage/agent_turn_journal.py`, `storage/agent_turn_boot.py`, `agent_turn_reconcile.py`, `agent_turn_coordinator.py`, `auth/middleware.py` (capability minting in the owner), `universe_server.py` (frontend/owner split), `agent_steering.py`, `deploy/compose.yml`, `deploy-prod.yml`, `deploy/wait_for_turns.sh`.
- **Storage shape:** a new lease store; an `owner_fence` table in each owner-written database; `agent_turns.owner_generation`; a pending-request journal.
- **Authority:** the owner trusts an identity asserted by the frontend over an authenticated local channel. This needs cross-family review before code.
- **Topology:** the daemon container splits into frontend and owner processes (or containers).
- **Delivery:** in slices, one PR each: B1 lease+generation+fence+reconcile; B2 barrier+admission; C1 frontend/owner split+capability minting; C2 handover deploy path+pending journal+metrics.
