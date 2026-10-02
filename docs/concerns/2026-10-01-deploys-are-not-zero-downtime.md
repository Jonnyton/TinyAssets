---
severity: P2
title: Every daemon deploy still costs about 25s of public 502; zero-downtime needs a switchable origin
filed: '2026-10-01'
summary: 'A deploy stops the old daemon (bounded at 20s since the 2026-10-01 fix) and then boots the new one, and the public surface is down for the whole sequence. Nothing else can serve while that happens: cloudflared (network_mode host) routes to the single port localhost:8001. Zero-downtime needs blue-green: start the new container on a second port, wait until it is healthy, switch the origin, then drain the old one with no deadline pressure.'
---

# Every daemon deploy still costs about 25s of public 502

**Filed:** 2026-10-01
**Verified:** 2026-10-01. `deploy/compose.yml` publishes the daemon only on `127.0.0.1:8001`, and the
tunnel's dashboard ingress is `http://localhost:8001` (compose comments on the `cloudflared` service).
The repro in `docs/audits/2026-10-01-deploy-drain-repro/` measured a 21.4s dead window per recreate
during a long tool call.
**Severity:** P2. The P0 version, 3m16s of 502 per deploy during a turn, was fixed by #4242
(record: `docs/audits/2026-10-01-deploy-drain-repro/INCIDENT.md`). Measured after the fix on
2026-10-02: a 27s 502 window with a turn in flight. This file is what remains.

## What is true

- uvicorn closes its listener on SIGTERM, so the old process cannot serve while it drains.
- The new container cannot bind 8001 until the old one is gone.
- So downtime = drain bound (20s with a turn in flight, about 1s without) + boot (about 3 to 12s to the
  first answer).
- **A deploy ends any in-flight turn.** Observed 2026-10-02 at 01:30Z: the founder's village turn showed
  "reply was cut off in transit". `agent_turn_reconcile` settles the row truthfully at boot, but the
  turn's work is lost.
- **Turn survival is not reachable by tuning the drain.** It needs the target architecture's
  single-execution-owner handover (#4263 S7/S8), so a turn can move to, or keep running beside, the
  new process instead of dying with the old one. Until then, the user-visible notice must say that
  the turn was interrupted by a deploy, never imply it completed.

## Shape of the fix

1. Bring the new daemon up on a second loopback port (blue/green), with the same data volume. This
   needs the SQLite writer barrier to allow a short overlap, or a read-only warm-up. That is the hard part.
2. Move the origin. Either repoint the tunnel ingress at a stable local proxy that both colours sit
   behind, or switch the dashboard ingress per deploy (dashboard-configured today, so not automatable
   without the API).
3. Drain the old colour with no deadline, so long turns finish. That also closes the remaining half of
   `docs/concerns/2026-08-29-a-deploy-kills-in-flight-turns-silently.md`.

## How to resolve

Ship it, then show a production deploy with a probe running against `https://tinyassets.io/mcp` that
records zero non-401 answers. Delete this file then.
