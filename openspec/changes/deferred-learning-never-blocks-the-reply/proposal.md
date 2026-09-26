## Why

`converse` produces the founder's reply, then spends a THIRD model round-trip on
learning extraction, then returns (`_learn_from_turn` sits above `return reply`).
The founder waits on a call whose output cannot change their answer. On a free
source that is tens of seconds of every single turn, and production confirmed the
shape: on 2026-09-26 UTC two recall turns on the free universe ran 3 rounds each.

It cannot simply be deferred — three verified facts
(`docs/concerns/2026-09-25-converse-turn-round-trip-cost.md`):

* the reply is delivered by the HTTP response (the app `await`s `MCP.converse`;
  `record_exchange` is memory, not delivery) and the MCP tool wrapper has no
  post-response hook;
* the provider lease is revoked in `_register_structured_tool`'s `finally`, and
  `validate_provider_request_carrier` refuses a carrier whose registry record is
  no longer `claimed`, so a thread outliving the request loses authority BY
  DESIGN;
* in-flight reservations are a deliberate concurrency guard, so running the
  secondary call alongside the foreground one can make the FOREGROUND call lose
  the budget race — a slow reply is better than a lost one.

## What Changes

The turn stops making the second call at all in the common case, and the
platform's fallback stops being on the founder's clock.

- **A durable learned-watermark per conversation.** One cursor row per session
  ("the last founder turn whose lesson is settled"), so "what have I not learned
  yet?" is derivable from turns the store already holds verbatim. No queue table,
  no migration of existing rows.
- **Stage 1, the common path: the universe records the lesson inside its NEXT
  turn, at zero extra cost.** A turn with an unsettled watermark is told so, and
  it already holds `write_brain`, the previous turn in its history, and its brain
  files. Recording advances the watermark. This removes the round-trip
  permanently rather than moving it.
- **Stage 2, the fallback: a deferred extraction, off the founder's clock.** A
  watermark unsettled past a bound (turns or minutes) is extracted by the daemon's
  existing periodic maintenance worker under a NEW `converse_learning` operation.
  Rare by construction, because stage 1 handles the ordinary case.
- **Foreground budget priority is structural, not arithmetic.** The deferred
  extraction is refused while that universe has ANY in-flight foreground
  reservation, and it reserves only if a full foreground turn's worth of allowance
  remains after it. It also keeps `secondary_call=True`, so it can never write the
  shared cooldown.
- **`converse` no longer calls the extractor.** `_learn_from_turn` is removed from
  the reply path; the reply returns as soon as it exists.
- **No lease outlives its request.** Deliberately NOT the design. Authority at
  drain time is RE-DERIVED from durable ownership the way `background_branch_run`
  already does, so a binding the owner has since revoked fails closed instead of
  being authorized by a carried lease. See design.md D1.
- One path for every account and provider: same watermark, same stages, same
  floor, no plan, tier, source or universe branch.

## Capabilities

### New Capabilities
- `deferred-turn-learning`: the learned watermark, the in-turn recording path, the
  deferred fallback's authority and budget floor, and the guarantee that no
  learning work runs on the founder's reply clock.

### Modified Capabilities
- `universe-personification-and-relay`: the as-built requirement currently reads
  "After the reply turn, `converse` SHALL run a separate provider call". That
  becomes: the reply SHALL NOT wait on learning, and learning SHALL be settled
  either in a later turn or by the deferred path — with the tolerant parsing,
  field filtering and never-break-the-reply guarantees preserved verbatim.

## Impact

- `tinyassets/universe_intelligence.py` — `_learn_from_turn` leaves the reply
  path; the extractor gains the deferred entry point.
- `tinyassets/conversation_store.py` — the watermark cursor (additive table) plus
  read/advance.
- `tinyassets/universe_server.py` — the maintenance loop gains the drain tick; the
  converse handle stops depending on learning completing.
- `tinyassets/provider_assignment.py` — `converse_learning` as a known operation
  with the foreground floor.
- `openspec/specs/universe-personification-and-relay/spec.md` — the requirement
  above.
- Tests: `tests/test_learning.py`, `tests/test_learning_never_locks_out.py`,
  `tests/test_converse_turn_cost.py` (the round-trip count assertion drops from 3
  to 2 for a one-tool turn — that IS the deliverable), plus new coverage for the
  watermark, the floor and the drain.
- Not touched: the public connector surface, the canonical handle set, the
  request-lease lifetime.
