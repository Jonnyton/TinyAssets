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
- A turn that recorded its own lesson returns its reply immediately. No turn is
  ever slower than it is today.
- No lesson is ever lost — continuous self-learning is a founder law, so the
  guaranteed pass survives until something equally guaranteed replaces it.
- The founder's next turn knows what they just taught (read-your-writes).
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

### D2 — Stage 1 records IN-TURN; the existing pass is the fallback, still synchronous

**Re-scoped by the lead, 2026-09-26, and the correction matters.** My first draft
had stage 1 recording the lesson in the NEXT turn. That loses the fact outright if
the founder never sends another message, and "observable" is not "kept":
continuous self-learning is a founder law, so no lesson may be at risk of never
being written. It also would not have removed the call — it moved it.

The shape is therefore:

```
turn N ─ the turn itself is told: "you have not yet recorded what your founder
         taught you THIS turn". It already holds write_brain and the exchange,
         so it records IN-TURN, inside the round-trips it is already paying for,
         and that advances the cursor.
           │
           ├─ cursor settled when the turn ends  → reply returns immediately.
           │                                        ZERO extra round-trips. The
           │                                        common case once the prompt
           │                                        asks for it.
           │
           └─ cursor NOT settled when the turn ends → the existing post-reply
                                                      extract_learning runs,
                                                      synchronously, exactly as
                                                      today. Nothing is lost,
                                                      ever.
```

So the latency win is conditional and self-limiting: a turn that recorded its own
lesson pays nothing extra; a turn that did not pays exactly what it pays today.
No turn is ever slower than now, and no lesson is ever dropped.

This also makes stage 2 a genuinely measurable proposition rather than a guess:
the cursor-settle RATE from stage 1 is the number that says how often the fallback
still fires, and stage 2 (the deferred, unattended path with D1 authority) is
designed against that rate instead of against my estimate of it.

Stage 1's own risk is unchanged and is why the fallback stays: on 2026-08-22 the
universe recited founder-taught facts in chat without writing them, which is why
the `brain_section` instruction exists at all. The difference is that the fallback
now runs only when the in-turn write did not happen, instead of on every turn.

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

### D5 — Cadence (stage 2 only)

Read-your-writes is no longer a cadence question: stage 1 records inside the turn
that learned the fact, so the founder's next turn sees it whatever the tick does,
and the synchronous fallback covers the turn that did not record. Cadence therefore
only governs stage 2, once it exists, and its job is narrower: settle the leftovers
that the fallback also failed to settle (a 429'd extractor, a crash between reply
and write). The existing maintenance thread's 300 s tick is adequate for that, plus
a no-op fast path when every cursor is settled — one indexed read.

## Risks / Trade-offs

- **Stage 1 does not write, so nothing is saved.** → the existing synchronous pass
  runs at the end of that same turn, exactly as today. The only cost is that the
  turn is no faster than now. Nothing is lost, which is the whole reason the
  fallback stays (lead, 2026-09-26).
- **The in-turn instruction makes the turn write things it should not.** → the
  wording adds no new authority: `write_brain` is already founder-allowlisted and
  already governed by the same honesty floor and the same "only clear, direct,
  stable facts my founder actually gave me" rule the `brain_section` states. What
  changes is that the turn is told whether it has already done it.
- **The prompt grows.** → one short block, and only for a turn with an unsettled
  cursor. The per-round budget ratchet
  (`tests/test_converse_turn_cost.py`) is what keeps that honest.
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

The behaviour change is observable in one number, now CONDITIONAL: a one-tool turn
whose in-turn write settled the cursor costs 2 model round-trips instead of 3, and a
turn that did not record still costs 3. `tests/test_converse_turn_cost.py` asserts 3
unconditionally today, so it gains the settled case as a second scenario rather than
flipping outright.

## Resolved (lead, 2026-09-26)

- **D1 CONFIRMED.** Re-derive authority at drain time from durable ownership; do
  not lengthen the lease.
- **Stage 1 alone: OVERRULED as I scoped it.** Removing the guaranteed pass is not
  acceptable, and recording "in the NEXT turn" loses the fact if the founder never
  sends one. Stage 1 records IN-TURN and the existing synchronous pass remains the
  fallback whenever the cursor is unsettled at turn end (D2).
- **This change is stage 1 + the fallback.** Stage 2 — the deferred, unattended
  path under D1 authority — is its own change, designed against the cursor-settle
  rate stage 1 produces.

## Open Questions

- **Does the in-turn instruction actually get obeyed?** That is the whole bet, and
  it is not answerable locally: 2026-08-22 says the universe can be told to write
  and not write. The cursor-settle rate is the measurement, and it is the first
  number to report after deploy. If it is low, stage 2 is not optional and the
  latency win is small — which is exactly why the fallback stays.
- **Stage 2's trigger bound** (how long an unsettled cursor may sit before the
  unattended path fires) is deliberately left to that change, when the settle rate
  exists. Guessing it now would be tuning a threshold on invented data.
