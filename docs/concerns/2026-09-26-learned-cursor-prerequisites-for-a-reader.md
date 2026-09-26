# Nothing seeds the learned cursor, so a reader would re-extract every history

**Filed:** 2026-09-26 (reviewer's prerequisite (2) on PR #4001)
**Verified:** 2026-09-26, local Windows, repo venv, against `origin/main` `21acf391`
**Severity:** P2 — INERT today because nothing reads the cursor; it becomes a spend
surprise on the founder's own credential the moment a reader lands

`conversation_learned` shipped in #4001 as the record of which conversation turns have
had their lesson settled. Stage 1 never reads it: the skip decision comes from this
turn's own journal, and the cursor is written for the deferred (stage 2) drain that
does not exist yet.

**Whoever creates the stage-2 change: this is its first task, before the reader.**

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

## The other prerequisite is fixed

Prerequisite (1) — `latest_turn_no` failing SOFT to 0, so the contiguity guard compared
0 against a cursor legitimately at 0 and the settle claimed the whole unsettled history
— is fixed in PR #4004: the read answers `None` for unknown, `from_turn` is a required
keyword whose `None` refuses, and an unknown `through_turn` refuses too. The repro is a
test there.

Delete this file when the stage-2 change carries the seeding as a task.
