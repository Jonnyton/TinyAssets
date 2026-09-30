---
severity: P1
title: The 600s turn cap reports `unknown` — "we could not identify why" for a deadline we measured ourselves
filed: '2026-09-30'
summary: '`AgentTurn` wraps the turn in a bare `asyncio.timeout`, so hitting the absolute cap raises a plain `TimeoutError` carrying no `failure_class`; `_served_failure_code` reads it as `unknown` and the owner is told the cause is unidentifiable, even though `InteractiveDeadlineError` exists for exactly this and the cap is our own number.'
---

# The 600s turn cap reports `unknown`

**Filed:** 2026-09-30. **Verified:** same day, by running the real mapper (command below).
**Severity:** P1 — the honest-notice contract this violates is the one that was
already fixed once, for a different class, in the same function.

## Source (verbatim)

From the live evidence that opened the branch-create work (prod, free account
`u-01ky3zh1arr8qth8jee7zx63pq`, turn `c7d6279d4af74d798375d3f13780140e`,
2026-09-30T01:07Z, model `nvidia/nemotron-3-ultra-550b-a55b:free`):

> The universe spent 16 of 21 rounds failing `write_graph target=branch
> operation=create` and never produced a branch or automation, then the turn
> died (held_transport) and the app showed "Delivery could not be confirmed:
> the reply was cut off in transit". […] Diagnose why round 21 failed
> (agent_turn_rounds state=failed, reply_json NULL).

## What round 21 was

Not a provider error. The coordinator bounds the whole turn:

* `tinyassets/agent_turn_coordinator.py:370-371` —
  `timeout = self.config.stream_timeout_profile().absolute_cap_s`, then
  `async with asyncio.timeout(timeout)` around the entire round loop.
* `tinyassets/providers/base.py:111` — `DEFAULT_ABSOLUTE_CAP_S = 600.0`.

At 600s `asyncio.timeout` cancels the inner task, so `CancelledError` is raised
inside `await self.adapter.infer(...)`. The coordinator's own
`except BaseException` (`agent_turn_coordinator.py:411-425`) then commits
`finish_inference(reply=None)` for the in-flight round, which the journal writes
as `state="failed"`, `reply_json NULL`
(`tinyassets/storage/agent_turn_journal.py:631-648`) and whose frontier is
`held_transport` (`agent_turn_journal.py:304`).

**That is exactly the observed row.** 21 rounds — 16 of them a failing build
retry — is how a turn reaches a ten-minute wall. So round 21 did not fail; the
*turn* ran out of time, and round 21 is the round that was in flight when it did.

## The defect

`asyncio.timeout.__aexit__` converts the cancellation into a bare
`TimeoutError`. A bare `TimeoutError` carries no `failure_class` and no
`attempts`, so every branch of `_served_failure_code`
(`tinyassets/universe_server.py:2762-2782`) misses and it returns `"unknown"`:

    $ python -c "from tinyassets import universe_server as us; \
      from tinyassets.conversation_failure import failure_notice; \
      r = us._served_failure_record(TimeoutError()); \
      print(r.code, r.stage); print(failure_notice(r))"
    unknown None
    Your universe's turn stopped - we could not identify why; we cannot tell
    whether this is a connection, usage, billing, or platform problem, so rather
    than guess we have recorded the details. We can't tell whether actions ran,
    so actions may already have occurred. [...]

We identified it precisely: the turn hit a cap *we* set. And the class already
exists — `InteractiveDeadlineError` with
`failure_class = "interactive_deadline"` (`tinyassets/exceptions.py:60-68`),
staged `model_reply` in `STAGE_OF_CLASS`
(`tinyassets/conversation_failure.py:132`), with its own owner-facing words at
`conversation_failure.py:45`. The providers raise it for *their* caps; the
coordinator's turn-wide cap raises nothing and reaches the notice as `unknown`.

This is the same shape as the bug the comment at `universe_server.py:2430-2434`
records being fixed for context overflow: "the one failure whose cause we
measured ourselves" read as "we could not identify why".

## Why this is filed rather than fixed in the branch-create PR

The fix is in the turn lifecycle (`agent_turn_coordinator`) and the served
failure record, not on the branch-authoring surface the PR changes. It is
floor-class (turn state + owner-facing honesty), so it wants its own lane, its
own tests and its own cross-family round. Bundling it would also put two intents
in one PR.

## What the fix is

Convert the coordinator's own cap into the typed class instead of letting a bare
`TimeoutError` escape: catch `TimeoutError` at the `asyncio.timeout` boundary in
`AgentTurn` and re-raise `InteractiveDeadlineError`, so the notice says the turn
ran out of time and `stage` is `model_reply`. Effects stay `unknown` — a
cancelled round genuinely may have acted — which the existing wording already
handles. Tests: the mapper's code for the coordinator's raise, and a turn whose
cap is set small enough to fire in-band.

## What this file does NOT claim

The app's own sentence — "Delivery could not be confirmed: the reply was cut off
in transit" — is the CLIENT's transport verdict (`stream_truncated`,
`tinyassets/onboarding/app.html:1080-1085`), and it is accurate about what the
browser saw: no terminal frame arrived for that request. The client does not
time a long turn out (it bounds response HEADERS only, `app.html:1199-1203`), so
whichever hop dropped a stream this long is the open question already filed as
`docs/concerns/2026-08-28-converse-sse-stream-has-no-keepalive.md` — this file
does not duplicate it. Fixing the class above changes what the owner is told
when the server's answer DOES arrive; it does not make a cut stream arrive.

## How to resolve this file

Delete it when the command in **The defect** prints `interactive_deadline` for
the coordinator's cap and a served turn that exceeds its cap shows the
ran-out-of-time notice, with date and surface stamped.
