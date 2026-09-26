## Context

`converse` today: assemble the persona prompt → the writer turn (1 inference +
one more per tool step) → `extract_learning` (a 3rd inference) → `return reply`.
Measured 2026-09-25 (`tests/test_converse_turn_cost.py`): the extraction is a
full round-trip that starts only after the reply text exists, so the founder waits
for platform bookkeeping. Production, 2026-09-26 UTC, free universe: two recall
turns at 3 rounds each.

Three verified constraints bound the solution space (citations in
`docs/concerns/2026-09-25-converse-turn-round-trip-cost.md`):

1. **The HTTP response IS the delivery.** The app `await`s `MCP.converse`;
   `conversation_store.record_exchange` is memory, not a channel the client polls.
   There is no post-response hook — `_register_structured_tool` returns the value
   straight to FastMCP.
2. **The lease dies with the request, on purpose.** That wrapper's `finally` calls
   `revoke_provider_request`; `validate_provider_request_carrier` refuses a
   carrier whose registry record is not `claimed`.
3. **In-flight reservations are the concurrency guard.**
   `provider_assignment.reserve_served_provider_budget` sums unsettled rows and
   refuses once the remaining output allowance drops below 1, so a concurrent
   secondary call can make the FOREGROUND call lose the race.

And a founder rule: every account behaves the same — no plan or tier branches.

## Goals / Non-Goals

**Goals:**
- The reply returns as soon as it exists. No learning work on the founder's clock.
- The founder's next turn still knows what they just taught (read-your-writes).
- The foreground turn keeps budget priority, structurally.
- Identical on every account, every provider, every universe.

**Non-Goals:**
- Extending the request lease's lifetime. See D1 — the safer design does not.
- A general "the daemon may call the model as you" primitive. The deferred path is
  pinned to one operation with one prompt shape and one effect.
- Changing what `commit_learning` accepts, the tolerant parsing, the field
  filtering, or the never-break-the-reply guarantee. All preserved verbatim.
- The per-round prompt size (that was `engine-tool-manual-on-demand`).

## Decisions

### D1 — Authority is RE-DERIVED at drain time, never carried

The brief framed this as a lease-lifetime change. It should not be one. Two
options:

* **Carry the lease** — hand the capability to a deferred registry with a sealed
  operation, a launch allowance of 1 and a short expiry.
* **Re-derive** — store (owner, universe, binding_id, binding_revision) with the
  watermark and, at drain time, resolve the serving binding from durable state
  under a new `converse_learning` operation, exactly as `background_branch_run`
  already does (`provider_assignment.reserve_served_provider_budget` already
  branches on that operation with its own binding-match rule).

**Re-derive wins on safety, not only on tidiness.** A carried lease authorizes work
the owner may have revoked in the meantime: it was minted when the binding was
live, and `validate_provider_request_carrier` checks the LEASE, not the binding's
current state. Re-deriving fails closed on a revoked binding, a deleted universe, a
changed home, or a rebound provider — all of which are exactly the states where a
platform-initiated call must not happen. It also leaves invariant 2 untouched, so
nothing about the request path changes.

The cost of re-deriving is that there is no verified request principal at drain
time. That is already solved in this repo the same way: `background_branch_run`
derives the owner from durable ownership, not from a request. The deferred path
inherits that precedent rather than inventing one.

### D2 — Stage 1 removes the call; stage 2 is the rare fallback

The uncomfortable part of any deferred design is the platform spending the user's
provider budget with no user present. So spend it as rarely as possible.

```
turn N:  reply returned immediately           watermark: turn N unsettled
turn N+1: prompt says "you have an unrecorded  ← ZERO extra calls
          lesson from last turn"; the turn
          already holds write_brain, the
          previous turn in history, and its
          brain files. It writes → watermark
          advances.
   |
   └─ still unsettled after K turns or T minutes
        → stage 2: deferred extraction on the maintenance worker
```

Stage 1 is where the saving is permanent: the round-trip disappears rather than
moving. It is also more faithful — the universe writes with the whole turn in
context and edits rather than overwrites, which is what "the universe is the sole
writer of its own brain" already asks for.

Stage 1's known failure mode is real and is why stage 2 exists: on 2026-08-22 the
universe recited founder-taught facts in chat without writing them, which is why
the `brain_section` instruction was added in the first place. The difference now is
that the watermark makes the failure OBSERVABLE (an unsettled cursor) instead of
silent, and stage 2 is a measurable backstop rather than an every-turn tax.

### D3 — Foreground priority is structural

Two rules, both cheap to check and neither arithmetic-dependent:

1. **The drain is refused while that universe has ANY in-flight foreground
   reservation.** The same `('reserved','indeterminate')` query the budget code
   already runs. So the deferred call cannot be the row that makes a founder's turn
   lose the race — it is not present while a turn is.
2. **A reserve floor.** The drain reserves only if a full foreground turn's worth of
   allowance still remains after its own reservation, so it cannot leave the next
   turn short even between ticks.

Plus what already holds: `secondary_call=True`, so its 429 never writes the shared
cooldown (#3988), and `retry_on_exhaustion=False`, so it never sleeps.

### D4 — The watermark is a cursor, not a queue

One row per session: the last founder turn whose lesson is settled. Pending work is
"founder turns after the cursor", read from `conversation_turns`, which already
holds the exact text verbatim (Hard Rule 9). Additive table alongside
`conversation_backfill`, no migration of existing rows, and idempotent: a drain
that runs twice advances the same cursor to the same place.

A burst of quick turns therefore drains as ONE extraction over the pending span
rather than one per turn — strictly fewer calls than today, and better grounded.

### D5 — Cadence

The existing maintenance thread ticks every 300 s, which is too slow to be the only
answer for a founder who types again in ten seconds. Two cheap additions:

* the drain gets its own short tick (a no-op when every cursor is settled — one
  indexed read);
* a turn whose own session has an unsettled cursor is told about it in stage 1, so
  the read-your-writes case is answered by the turn itself and never waits for a
  tick.

## Risks / Trade-offs

- **Stage 1 does not write, so a lesson sits unrecorded.** → the watermark makes it
  visible and stage 2 settles it; a metric on cursor age is the thing to watch
  live, and it is the first number to report after deploy.
- **The founder's next turn misses what they just taught.** → stage 1 puts the
  previous turn in front of the model with an explicit instruction to record it,
  and the turn's own history already contains the exchange, so the answer does not
  depend on the brain file being written yet.
- **The daemon spends the user's budget with no user present.** → rare by
  construction (stage 2 only), pinned to one operation, one prompt shape, one
  effect, refused while any foreground reservation is in flight, floored, and
  fail-closed on a revoked binding. The user's own binding is the only route.
- **Re-deriving authority at drain time is a new unattended call site.** → it
  cannot mint a carrier for anything else, cannot select a model outside the
  owner's plan, and is refused if the home changed. Needs cross-family review
  before it lands (AGENTS.md: authority changes).
- **A crash between the reply and the watermark advance loses a lesson.** → the
  cursor only advances on a recorded write, so a crash leaves it unsettled, which
  is the retry state. Never the reverse.

## Migration Plan

Additive table created on first use; no backfill (an existing conversation's
cursor starts at its latest turn, so history is not re-extracted — deliberate:
re-extracting months of turns would be a spend surprise). Rollback is the revert;
the cursor table becoming unused is harmless.

The behaviour change is observable in one number: a one-tool turn drops from 3
model round-trips to 2. `tests/test_converse_turn_cost.py` asserts 3 today, so
that assertion flipping IS the deliverable.

## Open Questions

- **K and T for stage 2** (turns / minutes before the fallback fires). Proposal: 1
  turn or 10 minutes, tuned after the live cursor-age number exists. Deliberately
  not guessed harder than that — my own memory of this repo says a text heuristic
  tuned on invented rows fails on the real distribution.
- **Should stage 2 exist at deploy, or should stage 1 ship alone and be measured
  first?** Shipping stage 1 alone is smaller, needs NO authority change at all, and
  its failure mode is observable rather than silent. That would split this into two
  changes and get the founder's latency win with nothing to review on authority.
  **Recommendation: yes — ship stage 1 first.** Flagged for the lead: it changes
  the scope of this change directory.
