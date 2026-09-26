## Tasks

Held at the design gate: the lead reviews design.md before any code, because D1
settles how unattended provider authority is derived. Task 1 is the question that
may re-scope everything below it.

- [ ] 1. Lead decision on design.md Open Question 2: ship STAGE 1 ALONE first (no
  authority change at all, the latency win lands, the failure mode becomes
  observable), and make stage 2 its own change — or keep both stages here. Record
  the answer in design.md before starting task 2.
- [ ] 2. The learned cursor: additive table beside `conversation_backfill`, read +
  advance, starting at the latest turn for an existing conversation so history is
  never re-extracted. Idempotent advance.
- [ ] 3. Remove `_learn_from_turn` from the reply path in `converse`, and leave the
  turn's pending span recorded against the cursor instead.
- [ ] 4. Flip `tests/test_converse_turn_cost.py`: a one-tool turn is TWO model
  round-trips, and nothing runs between the reply existing and `converse`
  returning. That assertion flipping is the deliverable.
- [ ] 5. Stage 1: a turn whose cursor is unsettled is told so and given the earlier
  exchange, with no extra round-trip; recording advances the cursor.
- [ ] 6. Test stage 1 end to end on the real converse path: unsettled cursor ->
  the turn is told -> an in-turn brain write -> cursor advanced -> no extra call.
- [ ] 7. Test the cursor's failure semantics: a failed or skipped write leaves it
  unsettled, a crash never advances it, a burst is one span, and a double drain
  advances to the same place.

Stage 2 (only if task 1 keeps it here):

- [ ] 8. `converse_learning` as a known operation whose authority is RE-DERIVED at
  drain time from durable ownership, failing closed on a revoked binding, a changed
  home or a deleted universe. No lease outlives its request.
- [ ] 9. The foreground floor: refused while the universe has any in-flight
  foreground reservation, and refused if reserving would leave less than one
  foreground turn's allowance; still `secondary_call=True` and never sleeping.
- [ ] 10. The drain tick on the existing maintenance worker: a no-op when every
  cursor is settled, bounded per tick, and it can never raise into the loop.
- [ ] 11. Test the authority and the floor by driving the REAL drain: revoked
  binding refuses, in-flight foreground reservation defers, floor refuses, a 429
  leaves the shared cooldown untouched, and the operation cannot be substituted.
- [ ] 12. Sync the delta specs into `openspec/specs/`, archive in this same lane,
  and report the first live cursor-age number after deploy (the metric that says
  whether stage 2 fires at all).
