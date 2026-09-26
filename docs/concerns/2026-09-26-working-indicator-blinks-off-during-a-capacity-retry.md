# The working indicator goes dark while a turn is retrying after a capacity fallback

**Filed:** 2026-09-26
**Verified:** 2026-09-26 — Codex refute-review of PR #4020 (head
`30536615dc94f7ae08d672bfad4aa953ec797879`), Windows worktree, by source tracing
**Severity:** P2

## Source (verbatim, Codex on PR #4020)

> Related lifecycle mismatch: WORKING_STATES at
> `tinyassets/storage/agent_turn_journal.py:38` excludes held_transport and
> held_native_capacity. Those can still be inside an ongoing coordinator run:
> `tinyassets/agent_turn_coordinator.py:279` records failure, line 282 continues
> on a capacity fallback, and lines 461-510 choose the next candidate.
> `tinyassets/storage/agent_turn_journal.py:520` explicitly permits resumption.
> A status observation during that interval reports idle and slows the page
> back to its 30-second poll. Simply including every held row would also be
> wrong: terminal holds need to remain distinct from active retry ownership.

## What was fixed on #4020, and what was not

Two other findings from the same review were fixed in that PR and are not open:
the stale bound now resolves the cap the coordinator will actually enforce
(`universe_intelligence.served_absolute_cap_s`, 3600s for a granted turn) instead
of the provider library's 600s default, and the read opens its own non-creating
`mode=rw` connection so an observation can no longer initialize ledger storage.

This one was not, because the cheap fixes are both wrong:

* Adding the two retryable holds to `WORKING_STATES` would report every
  TERMINAL `held_transport` row as live work. A turn that held and was never
  retried stays in that state forever, so the indicator would stick on — the
  failure mode the whole bound exists to prevent.
* A second, tighter age bound for held rows only guesses at the same
  distinction from outside.

## Measured exposure

`AgentTurnCoordinator._next_after_capacity` is synchronous (no `await`), and
`begin_round` runs inside the next `adapter.infer(...)`, so the window is one
inference-setup await — sub-second to a couple of seconds. The app polls at 10s
while a turn is live, so a poll can land in it, blink the indicator off, and drop
back to the 30s beat until the next poll. Compared with the defect #4020 fixed
(no indicator at all, for any turn this page did not start) this is small, and it
self-corrects on the following poll.

## Resolve when

The journal records retry OWNERSHIP rather than leaving it inferrable only from a
held state plus elapsed time — e.g. a state or flag the coordinator sets when it
decides to continue after a capacity boundary, which
`universe_working_turn` can then read directly. That is a change to
`agent_turn_records.STATES` and to what `_read` validates, i.e. a storage-shape
change, so it needs an `openspec/changes/` proposal before code.

Do not resolve this by widening `WORKING_STATES`.
