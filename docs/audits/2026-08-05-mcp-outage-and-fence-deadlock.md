# P0: /mcp down, and the fence that cannot let go

`current: 2026-08-05 ~22:00Z`. **Production is still down at time of writing.**
`https://tinyassets.io/mcp` → HTTP 502.

## Blast radius, measured

| Surface | State |
|---|---|
| `tinyassets.io/` | **200** — site fine |
| `mcp.tinyassets.io/mcp` | **403** — CF Access answering, tunnel alive |
| `tinyassets.io/mcp` | **502** — daemon fenced, not serving |

DNS, the Worker route, and cloudflared are all healthy. The daemon is stopped
by an unsafe fence.

## Cause

PR #2326 added a fifth worker container (`tinyassets-worker-founder`).
`retire_cheat_loop_deploy_fence.EXPECTED_CONTAINERS` lists daemon + four
workers and is compared with **exact set equality**, so deploy 31043701408
failed at `Transitional task 2.1 prove exact fleet` and the next step stopped
and restart-fenced every volume consumer — the daemon included, which is what
took `/mcp` down. Cleanup also masks `tinyassets-daemon.service`.

Cross-family review predicted this exact failure; the verdict arrived after
#2326 had already merged.

## The deadlock

Every in-band recovery path is blocked:

- A normal deploy refuses: preflight rejects any prior non-restored fence state.
- `restart-daemon.yml` refuses: its first step is `guard-host-mutation`.
- `p0-outage-triage.yml` refuses: same guard. **The outage triage tool cannot
  run during the outage state it exists for.**
- `recover-unsafe` is the only door, and it kept refusing.

## Six recovery attempts, six different refusals

| Run | Refusal | Fix attempted |
|---|---|---|
| 31047068243 | `extra production-volume consumers` | #2334 added `--retire-extra-consumer` |
| 31047718991 | `RUNNING extra volume consumer` | #2335 — the recorded flag is true for EVERY member at fence time |
| 31047957677 | `cannot prove ... stopped` | #2336 — cleanup had REMOVED, not stopped, the container |
| 31048315265 | canary 502 at +0.7s | #2337 — recovery had no health wait; daemon needs 60s |
| 31048717230 | canary red 17× over 240s | #2338 — added daemon/tunnel diagnostics |
| 31049384995 / 31049698106 | `stopped fleet removal intent is invalid` | #2339 — insufficient (see below) |

Each failed attempt **mutates durable fence state**, so every attempt failed at
a different place than the one before.

## Where it is stuck now

`stopped fleet removal intent is invalid` has **three** raise sites
(`fence.py:2655, 2877, 2895`). #2339 purges the retired name from the
enumerations in the in-memory `state` dict inside
`_validate_unsafe_recovery_source`, but the later removal path re-derives from
the **durable state file**, so the purge does not reach sites 2877/2895.

`_validate_stopped_fleet` requires
`set(stopped_fleet_removal["container_ids"]) == EXPECTED_CONTAINERS` and that
the plan equal its `recorded_source` map. Both were captured while the founder
container existed, so they enumerate one name more than `EXPECTED_CONTAINERS`
now does.

## What actually resolves it

Host-side inspection. The fence state is at
`/var/lib/tinyassets-deploy/retire-cheat-loop-task-2-1-fence.json`; `main` now
carries the correct four-service compose. `docker ps -a` plus
`docker logs tinyassets-daemon` settles in seconds what six dispatches could
not, and a manual `docker compose up -d` restores service without further
state churn.

## Durable lessons

1. **A fleet membership change is a five-place change.** compose, the
   exact-fleet fence, both rotation-phase counts, the HMAC verifier, and
   ship-logs. Nothing enforced agreement; #2327 added that invariant.
2. **The uptime canary skipped its probe whenever a deploy failed** —
   `workflow_run.conclusion == 'success'`. This outage went unalarmed for 40+
   minutes. The `*/5` cron does not cover the gap: GitHub throttles it to
   ~1.5–2h in practice. Fixed in #2331.
3. **A safety fence needs an in-band exit.** Every recovery tool guarded on the
   fence, including the outage-triage tool, so the system could fence itself
   into a state only a human with SSH could leave.
4. **Recovery could never satisfy its own success check** — it probed the
   public URL 0.7s after starting a daemon with a 60s boot, and the failing
   probe re-fenced the fleet it had just restored.
