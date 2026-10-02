# Frontend blue-green behind a local switch (target-architecture S8.7/S8.8)

**Status:** proposed. Owner of the surrounding slice: turn-handover (S7/S8). This note specifies
only the **traffic switch** for frontends. It builds no turn handover and no execution owner.
**Closes, when shipped:** `docs/concerns/2026-10-01-deploys-are-not-zero-downtime.md`.

## Where we are (measured)

- Every daemon deploy is a stop-then-start on one port. On 2026-10-02 #4242's deploy measured a
  **27 s** public 502 window: a 20 s bounded drain plus about 6 s of boot
  (`docs/audits/2026-10-01-deploy-drain-repro/INCIDENT.md`).
- cloudflared runs with `network_mode: host`, and its dashboard ingress is `http://localhost:8001`.
  The daemon publishes `127.0.0.1:8001`. Nothing else can serve until the old container is gone.
- The old process cannot keep serving while it drains. uvicorn closes its listener on SIGTERM,
  and sse-starlette cancels open SSE streams as shutdown starts
  (`docs/audits/2026-09-26-pr4039-drain-repro.py`).

## Why not now: two daemons would be two writers

Today one process is both frontend and execution owner: the scheduler, the assigned-queue
consumer, the turn journal and reconcile. Running an old and a new daemon side by side, even for
seconds, runs two schedulers and two consumers over the same SQLite stores. target-architecture
S8 is explicit: the owner/frontend split "must land before any second writer exists".

**So frontend blue-green depends on S8.3** (frontend/owner RPC with queueing during handover).
Until that lands, the honest state is the measured stop/start window. No interim blue-green is
proposed, because any overlap before the split is a double-writer bug.

## The switch

A small reverse proxy takes over `127.0.0.1:8001`, the port cloudflared already targets, so the
dashboard ingress does not change. It forwards to whichever frontend colour is live:

```
cloudflared (host net) --> 127.0.0.1:8001  local switch (HAProxy, host net)
                                              |-- 127.0.0.1:8011  frontend-blue
                                              '-- 127.0.0.1:8012  frontend-green
                           frontends --RPC--> execution owner (one, leased; S8)
```

**Choice: HAProxy**, over Caddy, Envoy and a SO_REUSEPORT trick.
- Its runtime API (`set server ... state drain|ready` over a local admin socket) moves new
  connections between colours **without a reload**. Established connections, including
  long-lived SSE streams, stay on the old colour until they end. That is exactly D11's "an old
  frontend keeps its open client connections until those streams end".
- It health-checks both colours and never routes to a colour that is not ready.
- A reload is needed only to change the topology, which is rare. Its config is validated
  (`haproxy -c`) before any reload, so a bad config cannot take the port.
- **SO_REUSEPORT was considered and rejected.** Both uvicorns would bind 8001 and the kernel would
  share new connections between them. But the old process still has to shut down to stop taking
  traffic, and shutdown cancels its SSE streams. The streams are the thing a frontend deploy must
  not break.
- Cost: one official `haproxy` image pinned by digest, about 10-20 MB RSS, no spend.

## Deploy protocol (frontend-only deploy)

1. **Start the idle colour**, say green on 8012, with the new image. It connects to the owner over
   the local RPC and completes an explicit **ready handshake** (S8a, turn-handover, agreed
   2026-10-02) before the switch may route to it. It owns nothing.
2. **Health gate:** the switch's health check, plus a loopback canary through 8012 directly
   (`mcp_public_canary.py --url http://127.0.0.1:8012/mcp`, as the canary principal). On failure:
   stop green, leave blue alone. That is a failed deploy with zero user impact, and no rollback is
   needed.
3. **Switch:** `set server be/green state ready` then `set server be/blue state drain`. New
   requests go to green at once, and blue keeps its open streams.
4. **Drain blue:** wait until the switch reports blue's current sessions = 0, **capped at 10
   minutes**, then stop blue. The cap governs only open client streams. Turn lifetime is the
   owner's drain bound (turn-handover's), and once frontends are split, a turn runs in the owner,
   not in the frontend. So a stream cut at the cap does **not** end its turn: the turn keeps
   running, and the client reads the answer from the thread, as it already does after a dropped
   stream. 10 minutes covers ordinary MCP/app streams without letting one hour-long stream hold a
   deploy. It is measured as "streams cut at cap per deploy" and revised from that number.
5. **Verify through the public path:** `mcp_public_canary.py --url https://tinyassets.io/mcp
   --assert-handles` and `deployed_sha.py --assert-contains`.
6. **Rollback** at any point before blue is stopped is one API call (`blue ready`,
   `green drain`). After blue is stopped, rollback is the same protocol run in reverse with the
   previous image.

**Owner changes are not frontend deploys.** When the execution owner's code changes, S8's owner
handover runs: stop admitting, drain up to the bound, journal, release the lease, successor at
generation+1. Frontends queue during it. This switch is not involved. The deploy workflow decides
which path from the diff: frontend modules, owner modules, or both (S8.8).

## Failure modes

| Failure | Effect | Mitigation |
|---|---|---|
| The switch process dies | port 8001 refuses, public 502 | `restart: unless-stopped`; the watchdog probes 8001 through it; the proxy restarts in well under a second; its state lives in the config plus a server-state file |
| The admin socket is reachable by a tenant | traffic hijack | a unix socket, root-owned 0600, on the host only; never in a jail bind |
| Both colours unhealthy | 502 | the same as today's failed boot; the deploy stops at step 2, before blue is touched |
| A colour/port mix-up | the new image never gets traffic | step 5 asserts the public `deployed_sha` matches the new image, not just green |
| The cap is hit with streams still open on blue | those streams end | measured and reported, the same metric S8 uses for interrupted turns |

## Tasks: a separate change after S8.3's RPC lands (deploy-incident lane)

Agreed with turn-handover 2026-10-02: one owner per change. These five ship as their own change
once S8.3 lands, not folded into the S8 handover PR.

1. A `switch` service in `deploy/compose.yml` (haproxy, host net, binds 127.0.0.1:8001). Frontend
   services `frontend-blue`/`frontend-green` on 8011/8012. The daemon stops publishing 8001.
2. `deploy/haproxy.cfg`: one backend, two servers, health checks, the admin socket, and
   `load-server-state-from-file`.
3. `deploy_fail_safe.sh`: the colour protocol above for frontend-only deploys. The
   host-mutation lock covers the whole sequence.
4. Watchdogs probe through 8001 (unchanged) and stand down while the lock is held (already true
   since #4242).
5. A scripted deploy loop with a request-level error probe (S8.10): 0 failed requests.

## Founder decisions

None. No spend, and no user-visible change beyond fewer 502s.
