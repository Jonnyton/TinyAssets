## Tasks

Re-scoped by the lead, 2026-09-26: D1 confirmed; stage 1 alone overruled. This
change is the IN-TURN recording plus the existing synchronous fallback, so no
lesson is ever lost and no turn is ever slower than today. Stage 2 (the deferred,
unattended path under D1 authority) is its own change, designed against the
cursor-settle rate this produces.

- [x] 1. The learned cursor: additive table beside `conversation_backfill`, read +
  advance, starting at the latest turn for an existing conversation so history is
  never re-extracted. Idempotent advance.
- [x] 2. Settle the cursor when the universe writes its own brain through the
  served brain-write handle, so recording is what advances it — never the reply,
  never the request completing.
- [x] 3. Tell the turn: a short block, only when the cursor is unsettled, saying the
  lesson is unrecorded and that the exchange is in front of it. No extra model
  call, no new authority — the brain-write gate and honesty floor are untouched.
- [x] 4. `converse` runs the existing `_learn_from_turn` ONLY when the cursor is
  unsettled at turn end, and skips it entirely when the turn already recorded.
- [x] 5. Test the settled path on the real converse path: an in-turn brain write ->
  cursor advanced -> `converse` returns with NO third round-trip.
- [x] 6. Test the unsettled path: no in-turn write -> the synchronous extraction
  still runs, exactly as today, and the lesson is persisted.
- [x] 7. Test the cursor's failure semantics: a failed or skipped write leaves it
  unsettled, a crash never advances it, and a double advance is idempotent.
- [x] 8. Test that a founder who never sends another message still has their lesson
  persisted — the regression the lead caught in the first draft.
- [x] 9. `tests/test_converse_turn_cost.py`: keep the 3-round-trip assertion for the
  unsettled turn and add the 2-round-trip assertion for the settled one, so the
  saving is pinned as conditional rather than claimed as unconditional.
- [x] 10. Mutation-check each new guard: skipping the cursor read, advancing on the
  reply instead of the write, and dropping the fallback must each turn a test red.
- [x] 11. One path for every account: no plan, tier, provider, source or universe
  branch in the cursor, the prompt block or the fallback decision — asserted.
- [x] 12. Sync the delta specs into `openspec/specs/`, archive in this same lane,
  and report the first live cursor-settle rate after deploy — the number stage 2 is
  designed against.
