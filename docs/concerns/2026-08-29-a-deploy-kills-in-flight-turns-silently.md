---
severity: P1
title: A deploy kills every in-flight turn, silently
filed: '2026-08-29'
summary: 'the container is recreated under a running served turn: no reply, no log line, the thread reloads without it; killed two live tests in one day'
---

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

## PR #4039 review: SIGTERM closes the MCP reply before the turn finishes

**Re-verified:** 2026-09-26, local Windows/Python 3.14 development test;
FastMCP 3.2.0, MCP 1.28.0, uvicorn 0.49.0, sse-starlette 3.4.5.
This is dependency-level evidence, not a production observation.

**Source (verbatim review finding):** A larger Docker stop grace can preserve
worker execution, but does not by itself preserve the served MCP reply.

`tinyassets/universe_server.py:4173` builds the default SSE-response HTTP app.
FastMCP awaits the synchronous tool in an AnyIO worker thread; the MCP session
runner belongs to the lifespan task group. The worker calls the synchronous
converse implementation (`universe_server.py:2866`), the writer
(`universe_intelligence.py:1359,1051`), and `asyncio.run(turn.run())`
(`providers/call.py:116`). The coordinator awaits inference and tools
(`agent_turn_coordinator.py:279,356`); it does not detach these operations.
However, sse-starlette patches uvicorn's exit handler and cancels SSE responses
on shutdown. MCP creates EventSourceResponse without a shutdown-grace override.

Commands, from the repository root:

```
python -u docs/audits/2026-09-26-pr4039-drain-repro.py
python -u docs/audits/2026-09-26-pr4039-drain-repro.py --disable-sse-exit
python -u docs/audits/2026-09-26-pr4039-drain-repro.py --short-timeout
```

The first run disconnected after 0.477s with an incomplete chunked response,
before a two-second tool finished, despite a five-second server grace. The
worker finished at 1.983s. Disabling automatic SSE termination preserved the
result at 1.993s. With a 0.25s uvicorn timeout, the worker/lifespan still ran until
1.981s: uvicorn's request timeout does not bound lifespan shutdown or kill a
synchronous worker. Thus the PR's 290 < 300 comparison is not proof of clean
process exit. The Docker grace remains useful, but the HTTP-lifetime claim is
false. Preserve the reply across SIGTERM and test this transport boundary before
claiming served turns drain successfully.

There is also a first-rollout caveat: Compose v5.1.3
`pkg/compose/convergence.go:621-622` stops the OLD container using the optional CLI
timeout; `cmd/compose/create.go:147-152` returns nil unless `--timeout` was set.
`pkg/compose/create.go:222` writes stop_grace_period into the NEW container's
StopTimeout. `deploy/deploy_fail_safe.sh:329` supplies no timeout override. An old
container created without the setting still gets its old/default stop timeout
during the first rollout. Later recreates use the stored 300s value.

Primary dependency sources:
[SSE shutdown](https://github.com/sysid/sse-starlette/blob/v3.4.5/sse_starlette/sse.py),
[Compose recreate](https://github.com/docker/compose/blob/v5.1.3/pkg/compose/convergence.go#L621),
[Compose creation](https://github.com/docker/compose/blob/v5.1.3/pkg/compose/create.go#L222).

## Two more casualties, 2026-08-30

- 02:05Z: the #2698 deploy restarted the container while another session's heartbeat-automation turn was being served; the app showed the bubble as 'never confirmed' and the session had to resend in two steps.
- 03:46Z: the #2705 deploy restarted the container while the founder's universe was mid-way through a one-line README edit (branches `auto/tiny-docs-touch-20260830e`/`f` already created on GitHub); the app showed 'the reply was cut off in transit'. Three more PRs from other sessions were armed with auto-merge at the time, so any resend had to wait for their deploys - with several sessions landing PRs, a 5-minute served turn has no clean window. The fix is on the deploy side (drain served turns before the swap, or hand the turn to the new container), not on the founder's side.

## Phase 1, 2026-10-02: the deploy waits for in-flight work

`deploy-prod.yml` step "Wait for in-flight turns" (`deploy/wait_for_turns.sh`) now runs
before the swap. Each poll pipes `scripts/turns_in_flight.py` into the live container and
holds the swap while anything is in flight. Two things count:
- an account seat a live process holds, expired or not, which covers chat turns and graph
  agent nodes;
- a queued or running graph run whose owner is alive, which covers automations and code
  nodes, since those hold no seat.

The loop polls every 15s and proceeds on any of: idle, an unhealthy daemon, three
unanswerable polls, a recovery workflow queued behind it, or the 45 min cap. The image is
pulled before the wait. While it waits, `get_status` reports `deploy_pending`. Merges that
land during the wait coalesce through the `production-host-mutation` concurrency group into
one queued deploy of the newest sha. release-reconcile no longer treats a cancelled
(displaced) dispatch as the failed retry.

Evidence is the compose repro in `docs/audits/2026-10-02-deploy-waits-for-turns-repro/`.
The Codex refute verdict (ADAPT, 7 findings, all acted on) is in the PR body.

What this does NOT close:
- **Idle is a moment.** A turn that starts between the last poll and the swap is still
  cut by the 20s drain. The prefetch shrinks that window but does not remove it.
- **Past the 45 min cap, or on a yield to recovery, the turn is still cut.** The startup
  reconcile notice is what the user then sees.
- **Steady overlapping turns can hold every deploy to the cap.** The admission hold ships
  only together with persist-and-replay of held messages (lead decision 2026-10-02).
- **The real fix is Phase 2.** The new container serves while the old one finishes its
  turns, which is the single-execution-owner handover in #4263 S8 (change
  `execution-owner-lease`).

Keep this file until a live turn has been seen to survive a production deploy.
