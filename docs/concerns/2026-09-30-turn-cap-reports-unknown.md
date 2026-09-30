---
severity: P1
title: The turn's own absolute cap reports `unknown` — "we could not identify why" for a deadline we set ourselves
filed: '2026-09-30'
summary: '`AgentTurn` wraps the turn in a bare `asyncio.timeout`, so hitting the absolute cap raises a plain `TimeoutError` carrying no `failure_class`; `_served_failure_code` reads it as `unknown` and the owner is told the cause is unidentifiable, even though `InteractiveDeadlineError` exists for exactly this and the cap is our own number.'
---

# The turn's own absolute cap reports `unknown`

**Filed:** 2026-09-30. **Verified:** same day, by running the real mapper (command below).
**Corrected:** 2026-09-30, same day, after a Codex refute round — see
*What this file no longer claims*. The mapper defect is unchanged; the
attribution of the live row to a specific cap was overstated and is withdrawn.
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

## What round 21's row means, and what it does not pin

The observed row — `agent_turn_rounds state="failed"`, `reply_json NULL`, turn
`held_transport` — has **two** producers in this codebase, and the evidence
available does not choose between them:

1. **In-band.** The coordinator's `except BaseException`
   (`tinyassets/agent_turn_coordinator.py:411-425`) commits
   `finish_inference(reply=None)` for the in-flight round when ANY exception
   escapes `await self.adapter.infer(...)`. The journal writes that as
   `state="failed"` / `reply_json NULL`
   (`tinyassets/storage/agent_turn_journal.py:631-648`), frontier
   `held_transport` (`agent_turn_journal.py:304`).
2. **At startup.** `tinyassets/agent_turn_reconcile.py` settles a row left in
   `inference_started` by a dead container with the SAME transition
   (`finish_inference(None)` → `held_transport`), keyed on boot ownership. Its
   own docstring tabulates it.

So round 21 was **not necessarily** a provider error, and it was **not**
necessarily a timeout either. What is established is only that the round was in
flight and its outcome was never recorded — which is what `held_transport`
means.

One candidate is the turn's own absolute cap: the coordinator wraps the whole
round loop in `async with asyncio.timeout(timeout)`
(`agent_turn_coordinator.py:371`), and at the cap `asyncio.timeout` cancels the
inner task, so `CancelledError` is raised inside `infer`, handler (1) runs, and
`__aexit__` re-raises a bare `TimeoutError`. That path produces exactly this row.
**Whether this turn hit it is unproved** (see below).

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

Whenever that path IS taken, we know the cause precisely — the turn hit a cap
*we* set — and still report it as unidentifiable. The class already
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

## What this file no longer claims (Codex refute, 2026-09-30)

Two claims in the first draft were wrong and are withdrawn. The mapper defect
above is independent of both and stands.

1. **"The turn hit the 600s cap."** A SERVED founder turn's cap is **3600s**,
   not 600s: `tinyassets/universe_intelligence.py:253`
   (`_SERVED_ABSOLUTE_CAP_S = 3600.0`) and `served_absolute_cap_s`, whose own
   docstring records that a bound derived from the library's 600s default
   "called a healthy founder turn dead after ten and a half minutes".
   `providers/base.py:111`'s 600s is the library default, which the served path
   overrides. Nothing establishes that this turn ran an hour, so the cap is a
   candidate, not the cause — and the reconciler (producer 2 above) explains the
   row with no timeout at all.
2. **"The client does not time a long turn out."** It does: the body reader is
   bounded per chunk — `const chunk = await this._bound(reader.read(),
   ...silence())` (`tinyassets/onboarding/app.html:1120`), at `SILENCE_MS:
   120000` (`app.html:1003`). It bounds inter-chunk SILENCE, not total duration.

   That bound is nonetheless **excluded for this turn by its error class**: it
   raises `stream_silent` ("your universe stopped sending anything back",
   `app.html:1101-1102`), and what the app showed was `stream_truncated` ("the
   reply was cut off in transit", `app.html:1084-1085` / `1320-1321`) — the
   class raised only where the bytes STOPPED before the answer. Recorded as a
   discriminator in
   `docs/concerns/2026-08-28-converse-sse-stream-has-no-keepalive.md`, which is
   where the transport question belongs.

So the app's sentence is the CLIENT's own transport verdict and is accurate
about what the browser saw: the stream ended without a terminal frame for that
request. Fixing the class below changes what the owner is told when the server's
answer DOES arrive; it does not make a cut stream arrive.

**What would settle round 21:** the container's `StartedAt` either side of
2026-09-30T01:07Z (reconciler vs in-band) and the turn's `created_at` to
`updated_at` span against 3600s. Neither was captured.

## How to resolve this file

Delete it when the command in **The defect** prints `interactive_deadline` for
the coordinator's cap and a served turn that exceeds its cap shows the
ran-out-of-time notice, with date and surface stamped.
