# Two things the learned cursor still needs before anything READS it

**Filed:** 2026-09-26 (reviewer's prerequisite (2) on PR #4001; the concurrency item added by the lead's review of #4004)
**Verified:** 2026-09-26, local Windows, repo venv, against `origin/main` `21acf391`
**Severity:** P2 — INERT today because nothing reads the cursor; it becomes a spend
surprise on the founder's own credential the moment a reader lands

`conversation_learned` shipped in #4001 as the record of which conversation turns have
had their lesson settled. Stage 1 never reads it: the skip decision comes from this
turn's own journal, and the cursor is written for the deferred (stage 2) drain that
does not exist yet.

**Whoever creates the stage-2 change: both of these are tasks before the reader.**

## `start_learned_cursor` has no caller

It exists precisely so an existing conversation's cursor begins at its LATEST turn, and
months of history are never re-extracted on the founder's own credential. **No caller
exists.** Every pre-existing conversation therefore reads 0, and the first stage-2 drain
would treat its entire history as owed — the exact spend surprise the function was
written to prevent, arriving with the reader.

Fix direction: seed it lazily at first read (the drain seeds any session it has never
seen before extracting), or at first `converse` for a session with history and no cursor
row. **Lazy-at-first-read is the safer of the two**: it cannot be skipped by a session
that never takes another turn, and it keeps the rule inside the reader that depends on
it.

## Also: two concurrent turns in one session, and the first to settle over-claims

`settle_learned_cursor`'s `through_turn` defaults to **the latest turn at settle
time**, not to what the settling turn actually produced. One founder on two surfaces
(web and phone) is one session, so two turns can overlap — and then the first to settle
claims its neighbour's span as well, including a neighbour whose learning FAILED.

Reproduced against `origin/main` `21acf391` plus #4004:

```
cursor settled at 2
turn A begins: latest = 2        turn B begins: latest = 2
A records its exchange  -> 4
B records its exchange  -> 6
A settles (from_turn=2) -> 6     # B's span, turns 5-6, is now claimed
```

B's extraction can fail and never settle; the cursor already says turn 6 is done, so no
drain retries it. Note the hazard is one-directional: whoever settles SECOND finds the
cursor moved and is refused (`settled != from_turn`), which is the safe direction — its
own lesson is merely re-extracted later.

Fix direction: **bound the settle by the settling turn's OWN last `turn_no`**, passed as
`through_turn`, instead of reading "latest" again. The piece that is missing today is
that `record_exchange` returns `bool` — a turn has no way to learn which turn numbers it
wrote. Have it report them (or return the assigned `turn_no`), then the handle passes
that as `through_turn` and a concurrent neighbour's rows are out of reach by
construction. Per-turn settlement rows would also solve it, at more storage.

## The other prerequisite is fixed

Prerequisite (1) — `latest_turn_no` failing SOFT to 0, so the contiguity guard compared
0 against a cursor legitimately at 0 and the settle claimed the whole unsettled history
— is fixed in PR #4004: the read answers `None` for unknown, `from_turn` is a required
keyword whose `None` refuses, and an unknown `through_turn` refuses too. The repro is a
test there.

Delete this file when the stage-2 change carries both as tasks.
