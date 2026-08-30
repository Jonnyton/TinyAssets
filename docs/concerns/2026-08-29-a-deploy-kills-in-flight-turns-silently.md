# A deploy kills every in-flight turn, and nothing tells anyone

**Filed:** 2026-08-29
**Verified:** 2026-08-29, live, twice in one day on the founder's own universe.
**Severity:** P1 — it destroys work the user's own subscription is paying for,
and the user is told nothing true about why.

## What happened

07:12Z: the founder's universe was sent *"try again"* and began a five-step
GitHub job. By 07:25Z it was running hard — 9 provider processes on the droplet.
At 07:26:04Z the daemon container was recreated by an ordinary deploy (two
unrelated PRs merged to `main`; auto-merge → build → `deploy-prod`). The turn
vanished:

* no reply recorded in the conversation store;
* no log line — the process that would have written one was gone;
* the browser reloaded on the new build and restored the thread from history,
  so the in-flight exchange simply disappeared from the screen;
* the founder's own request tab had been approved minutes earlier, so from
  their side the universe was unblocked, asked to continue, and then went
  silent for half an hour.

Earlier the same day the same shape hit a colour-change turn mid-`PUT`: the
deploy from the *previous* fix landed under the test of that fix.

## Why it matters

The founder's rule (2026-08-29): *"a turn should continue till finished unless
interrupted by the user or should stop for some other reason."* A deploy is a
legitimate other reason. **Silence is not.** Right now a deploy is
indistinguishable, from the user's chair, from the universe having done
nothing — and the platform ships several times a day.

It also makes the platform untestable through its own front door: every fix to
the served turn deploys, and every deploy kills the turn that would prove the
fix. Two of today's live tests died this way before producing a result.

## What would fix it

1. **Drain before recreate.** `deploy_fail_safe.sh` should ask the daemon to
   stop admitting turns, wait for in-flight served turns to finish (bounded —
   the idle watchdog already bounds a hung one), then recreate. Long turns are
   the product; the deploy should wait for them, not the other way round.
2. **Or mark the casualty.** If the container must go, record a terminal
   `interrupted_by_deploy` turn in the conversation store on shutdown so the
   user sees *"your universe was restarted mid-turn by a platform update —
   say 'continue' to pick up"* instead of nothing. Cheap, and honest.
3. **Resume.** The universe's memory already carries the job state (the branch
   exists, the blob sha was read); a `continue` after restart should pick up.
   Today that works only because the agent re-derives it.

(1) is the real fix; (2) is the floor and should ship regardless.

## How to resolve this file

Delete it when a served turn in flight across a production deploy either
finishes or leaves the user a truthful notice — observed once on the live
surface, not inferred from a test.

## Two more casualties, 2026-08-30

- 02:05Z: the #2698 deploy restarted the container while another session's heartbeat-automation turn was being served; the app showed the bubble as 'never confirmed' and the session had to resend in two steps.
- 03:46Z: the #2705 deploy restarted the container while the founder's universe was mid-way through a one-line README edit (branches `auto/tiny-docs-touch-20260830e`/`f` already created on GitHub); the app showed 'the reply was cut off in transit'. Three more PRs from other sessions were armed with auto-merge at the time, so any resend had to wait for their deploys - with several sessions landing PRs, a 5-minute served turn has no clean window. The fix is on the deploy side (drain served turns before the swap, or hand the turn to the new container), not on the founder's side.
