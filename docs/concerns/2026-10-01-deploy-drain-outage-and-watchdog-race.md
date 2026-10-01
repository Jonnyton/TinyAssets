---
severity: P0
title: A deploy during a long turn is up to 180s of public 502, and the watchdogs race the swap
filed: '2026-10-01'
summary: 'Deploy run 36937114232 took /app and /mcp to 502 from 22:49:48Z to 22:53:04Z. The old daemon closes its listener on SIGTERM and then blocks in lifespan shutdown on the in-flight turn until docker SIGKILLs it at stop_grace_period=180s. Mid-drain, both host watchdogs restarted the daemon through their own compose runs without the host-mutation lock. That killed the new container and made the rollback fail on a compose temp-name conflict (rollback_failed, rc=3).'
---

# A deploy during a long turn is up to 180s of public 502, and the watchdogs race the swap

**Filed:** 2026-10-01
**Verified:** 2026-10-01, production droplet (`ssh workflow-droplet`), `docker events --since 40m`,
`journalctl --since "2026-10-01 22:45" --until "2026-10-01 22:56"`; repo at origin/main `6d272dde`.
**Severity:** P0 (Forever Rule: the public surface went down)

## Timeline (UTC, 2026-10-01)

- ~22:37: a long codex agent turn starts for universe `u-01kxm1vszd8hwp7em418asq8h9`.
- 22:49:41: deploy run 36937114232 pulls `sha256:ae2153093a67…` (main `6d272dde`).
- 22:49:48: compose `up -d` SIGTERMs old daemon `a28968a166cd`. uvicorn logs `Shutting down`,
  `ASGI callable returned without completing response`, then `Waiting for application shutdown`, and
  never logs `complete`. cloudflared logs `connection reset by peer` to `127.0.0.1:8001` from this second.
  **The public surface is 502 from here.**
- 22:51:20: `tinyassets-watchdog` logs `RED #3/3` and runs `sudo systemctl restart tinyassets-daemon.service`.
  The unit runs its own `docker compose up`, which issues a second stop of the same container. Nothing
  coordinates it with the deploy: neither watchdog takes `/var/lock/tinyassets-host-mutation.lock`.
- 22:52:48: dockerd logs `Container failed to exit within 3m0s of signal 15 - using the force` (exit 137).
- 22:52:49 to 22:52:52: two composes race the recreate.
  - The unit's compose fails with `No such container: a28968…`.
  - `daemon-watchdog.sh` restarts the container because the unit is not active.
  - `tinyassets-watchdog` hits RED 3/3 again and runs another `systemctl restart`.
  - Those restarts kill the deploy's new container `1cc5a277f659` (exit 143). The deploy reports
    `dependency daemon failed to start` and rolls back.
  - The rollback's `up -d` fails with `Conflict ... /1cc5a277f659_tinyassets-daemon is already in use`.
    That name is compose's temporary recreate name, created by the unit's concurrent compose.
    Result: `deploy_result=rollback_failed`, rc=3.
- 22:53:04: the unit's compose brings the previous image up healthy. Service restored.
- 22:55:52: deploy run 36937827533 lands `6d272dde` cleanly. No turn was in flight by then.

## Root cause

1. **The drain happens with no listener.** The drain from #4039 (`stop_grace_period: 180s`,
   `universe_server.GRACEFUL_SHUTDOWN_S = 170`) keeps a turn computing after SIGTERM. But uvicorn closes
   the only listening socket first, and the SSE reply is already cancelled, so every second of drain is a
   second of public outage. Lifespan exit waits on the FastMCP task group, which waits on the tool's
   uncancellable AnyIO worker thread. So only docker's SIGKILL bounds it.
2. **Three uncoordinated mutators.** Each watchdog reads the drain as a dead daemon and restarts it through
   a second compose run. That turns a slow deploy into a failed deploy and a failed rollback.

## Fix (in flight: branch `fix/deploy-hang-bounded-shutdown`)

Bounded short drain; the deploy stops the old container with an explicit `docker stop -t` bound; both
watchdogs stand down while the host-mutation lock is held; converge removes compose temp-named daemon
containers. Delete this file when the fix is deployed and a deploy with a turn in flight is proven.

## Reproduction (2026-10-01, Docker Desktop, compose v5.1.4, fastmcp 3.4.7, uvicorn 0.54.0)

`docs/audits/2026-10-01-deploy-drain-repro/run.py` runs a FastMCP tool that sleeps 600s, then recreates the
container while probing the port every 0.25s:

| variant | converge | port dead |
|---|---|---|
| `old`: created with a 60s grace (180s in prod, scaled), plain `up -d` | 61.2s | 61.5s |
| `first-deploy`: still created with 60s, `up -d --timeout 20` | 21.2s | 21.9s |
| `steady`: created with 20s, `up -d --timeout 20` | 21.3s | 21.4s |

Each converge equals the SIGKILL bound, not uvicorn's 10s graceful timeout. That confirms the lifespan
hang on the worker thread, and shows `--timeout` overrides the create-time StopTimeout.

## Not fixed by this, and worth doing

A deploy still costs stop + start (about 30s worst case plus boot) of 502. Zero-downtime needs the new
container healthy on a second port before traffic moves, which means a switchable origin: cloudflared's
dashboard ingress points at `localhost:8001` today.
