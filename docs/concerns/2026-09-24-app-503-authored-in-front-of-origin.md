# App `POST /mcp` 503s that the origin never served

**Filed:** 2026-09-24
**Verified:** 2026-09-24. The evidence below comes from read-only droplet log reads and anonymous probes.
**Severity:** P1. Founder sends failed, and the layer that authored the 503 is still unknown.

## Source (verbatim)

> Chrome, https://tinyassets.io/mcp/app, 2026-09-24 about 18:31–18:39 UTC, founder account.
> Two typed sends ("Retest your workflow checklist") were not delivered; the third
> worked (saved 11:39 AM PDT). The tab's network log showed several
> `POST https://tinyassets.io/mcp` responses with status **503**, interleaved
> with 200s. Bodies were not captured. The `tinyassets-daemon` access log shows
> only 200/401 for `POST /mcp` in that window — no 5xx.

## What is established

- **The droplet did not author it.** In `docker logs --timestamps tinyassets-daemon`, `POST /mcp`
  has no 5xx from 18:25 to 18:45 UTC. The `tinyassets-tunnel` logs have no entries after 06:04 UTC.
- **The tab's requests before its reload never reached the droplet.** The founder's tab loaded at
  06:36 UTC. From then until 07:22 UTC it renewed its token every ~4 minutes and ran the HEAD
  build-check every 10 minutes. After 07:22 there is no `POST /mcp/app/token` and no
  `HEAD /mcp/app` until the reload at 18:33:38. The machine slept, and the tab resumed at about
  18:31. Anything that tab sent between the resume and the reload got its answer from somewhere
  other than the droplet.
- **No second tunnel connector is serving now.** At about 18:45 UTC I sent 40 anonymous
  `initialize` probes tagged `?probe=send503xN`. All 40 answered 401, and all 40 appear in the
  droplet access log.
- **The Worker cannot author a 503 itself.** `deploy/cloudflare-worker/worker.js` turns an
  unreachable tunnel and any non-JSON origin 5xx into **502**. It passes through only a JSON 5xx,
  marked with `X-TA-Origin-Status`. The one JSON 503 in the repo on every path is
  `tinyassets/origin_admission.py` (`platform_not_cloud`), and it is served only by an
  **off-cloud** origin reached through a connector. The desktop tray could enroll such a connector
  until #3913 (2026-09-21).

## Open: which layer answered

Two candidates remain, ranked. One response header set would decide between them.

1. **Cloudflare, in front of the Worker.** Candidates are a security or bot challenge or
   rate-limit rule applied to one client (a resumed tab bursts every queued timer), or a Worker
   runtime error such as 1102 (resources exceeded, answered as 503). This fits best: only this
   client was affected, and a document reload (18:33) made its later calls succeed. Discriminator:
   an HTML body, a `cf-mitigated` header or a Cloudflare error page, and **no**
   `X-TA-Origin-Status`.
2. **A transient second connector on tunnel `b59f3cd9…`** served by an off-cloud daemon.
   Discriminator: body `{"error":"platform_not_cloud"}` with `X-TA-Origin-Status: 503`. Check:
   Cloudflare dashboard → Zero Trust → Networks → Tunnels → the production tunnel → Connectors.
   It should list exactly one connector (the droplet). Remove any other connector and rotate the
   tunnel token.

Neither can be settled from this checkout, because no Cloudflare API credential is available here.
The zone's Security Events for 18:25–18:40 UTC would settle the first one directly.

## Follow-up that makes the next occurrence self-attributing

PR `claude/app-send-503-drop` makes every HTTP failure on `/mcp` carry `status`, `cf-ray`,
`X-TA-Origin-Status`, `content-type` and a body sample. It writes them to the console, and it
shows the status and ray in the notice. A screenshot of the next notice is then enough to look up
the Cloudflare ray.

## Unrelated observation

`docker inspect tinyassets-tunnel` shows the tunnel token in the container's `Cmd`
(`tunnel run --token …`), not only in `Env`. Anyone with docker access on the droplet can read it
either way. It is noted here because the redaction I applied during this investigation covered
only `Env`.
