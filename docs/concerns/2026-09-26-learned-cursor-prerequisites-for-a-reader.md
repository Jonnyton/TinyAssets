# Two things the learned cursor needs before anything READS it

**Filed:** 2026-09-26 (reviewer's prerequisites on PR #4001, verified and sharpened here)
**Verified:** 2026-09-26, local Windows, repo venv, against `origin/main` `21acf391`
**Severity:** P2 — both are INERT today because nothing reads the cursor; both make the
rows being written now mean something they should not

`conversation_learned` shipped in #4001 as the record of which conversation turns have
had their lesson settled. Stage 1 never reads it: the skip decision comes from this
turn's own journal, and the cursor is written for the deferred (stage 2) drain that
does not exist yet. So neither item below can hurt a user today. Both change what the
rows already on disk MEAN, which is why they are recorded rather than deferred to
whoever notices later.

**Whoever creates the stage-2 change: these are its first two tasks, before the
reader.**

## (1) The contiguity guard compares two values from the same failing reader

`universe_server.converse` reads `latest_turn_no` before `record_exchange` and passes
it as `settle_learned_cursor(from_turn=...)`, so a settle is refused unless the cursor
already stands there — that is what stops turn N claiming an owed turn N-1.

The reviewer flagged the raise path (the handle falls back to no `from_turn`, which is
non-contiguous). The realistic path is worse and needs no exception: **`latest_turn_no`
fails SOFT to 0** (`except Exception: return 0`), and `from_turn=0` is
indistinguishable from "this is the first turn in the conversation". Reproduced:

```python
cs.record_exchange(d, "s", "owed turn", "reply")     # turns 1-2, never settled
cs.record_exchange(d, "s", "second turn", "reply")   # turns 3-4
cs.settle_learned_cursor(d, "s", from_turn=0)        # -> 4
cs.learned_cursor(d, "s")                            # -> 4, the owed turn is claimed
```

So an unreadable store at exactly the wrong moment marks the whole history learned.
Fix direction: make the absence of a trustworthy `from_turn` **refuse** the settle
rather than fall back to the latest row — err toward owing, which costs a redundant
extraction, never a lesson. A sentinel distinct from 0 (or a required keyword) is the
shape; a default that means "no idea" must not be a value the guard can satisfy. Cf.
`docs/concerns/` history on defaults that hide a two-sided key mismatch.

## (2) Nothing calls `start_learned_cursor`, so every existing conversation reads as 0

`start_learned_cursor` exists precisely so an existing conversation's cursor begins at
its LATEST turn and months of history are never re-extracted on the founder's own
credential. **No caller exists.** Every pre-existing conversation therefore reads 0,
and the first stage-2 drain would treat its entire history as owed — the spend
surprise the function was written to prevent, arriving the moment a reader lands.

Fix direction: seed it lazily at first read (the drain seeds any session it has never
seen before extracting), or at first `converse` for a session with history and no
cursor row. Lazy-at-first-read is the safer of the two: it cannot be skipped by a
session that never takes another turn, and it keeps the rule in the reader that
depends on it.

## Not fixed in #4001

#4001 was approved and its auto-merge armed when these landed, and neither is
reachable by a user until a reader exists. Fixing (1) is a small change to code
`#4001` introduced; I can ship it as its own Tier 0/1 if the stage-2 change is far
off — say so and I will. Delete this file when the stage-2 change carries both as
tasks.
