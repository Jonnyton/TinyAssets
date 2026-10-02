# A message sent while an update is pending is kept and answered after it, never lost

## Why

#4278 makes a deploy wait for running turns before it swaps the daemon, with a 45 minute cap. That leaves one gap, which the lead and the Codex refute both named. Each turn ends, but a new one starts while the deploy is waiting, so the count of turns in flight never reaches zero. The deploy then hits the cap and cuts whatever is running.

The fix is to stop admitting new turns for the length of the swap. Lead decision, 2026-10-02: a held message that vanishes at the swap breaks never-lose and fail-loudly. The admission hold therefore ships only together with persisting the message and replaying it on the new boot, so nothing the owner sends is ever lost.

This is also the first slice of #4263 D11/S8: "frontends forward turn starts to the owner and queue them while the owner hands over. New requests never fail; they queue." The durable inbox built here is the queue that the owner handover (`execution-owner-lease`, next) drains.

## What Changes

- **Deploy hold.** After a soft deadline (the cap minus a margin), the waiting deploy marks the hold in its pending marker. A held platform admits no NEW turn.
- **Queue, do not refuse.** A turn that arrives during a hold is persisted before anything else runs: a durable inbox row carries the authenticated owner, the universe, the session, the message, the input method and the model choice. The reply says plainly that the message is queued and will be answered right after the update. The thread shows the message at once, marked queued.
- **Replay once.** The next boot drains the inbox once it has reconciled orphaned turns. Each queued message runs as a turn of the same owner, on the same thread, under that owner's current authority, which is re-checked at replay and never carried over from enqueue time. The reply lands in the thread, and the queued mark resolves. Replay is idempotent on the inbox id: a crash mid-drain never answers a message twice.
- **The swap waits for zero.** With admission held, the deploy waits for in-flight work to finish, up to the existing cap, and then swaps. The new boot drains the queue.
- **Spec the as-built phase 1.** `uptime-and-alarms` gains the deploy-waits-for-in-flight-work requirement that #4278 shipped.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `uptime-and-alarms`: a deploy waits for in-flight work, and a hold queues new turns durably and replays them after the swap.

## Impact

- **Code:** `deploy/wait_for_turns.sh`, `scripts/turns_in_flight.py` (marker hold field), `tinyassets/universe_server.py` (converse admission path), `tinyassets/universe_intelligence.py`, `tinyassets/conversation_store.py` (queued mark), a new inbox store, and boot drain wiring next to `agent_turn_reconcile`.
- **Storage shape:** a new per-data-root inbox table, and a queued state on a founder conversation row.
- **Authority:** replay runs a turn with no live request. It must re-derive the owner's authority from current state at replay. This is the part that needs cross-family review.
- **Public surface:** the `converse` reply for a held turn is a new outcome. The reply is honest text plus a structured `queued` marker; the tool contract is unchanged.
