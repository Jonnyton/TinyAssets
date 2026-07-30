# Public MCP Access-cookie freshness audit

Date: 2026-07-30
Environment: Windows audit lane at `3ac95e979a414d1247ae6c7183037fe154f7c88b`; implementation baseline `origin/main` at `13632583ee5bfbf3ae256b439c391536519bf724`; public edge `https://tinyassets.io/mcp`.
Scope: read-only revalidation of the STATUS P0; no Cloudflare, deploy, secret, or production mutation.

## Verdict

The P0 remains valid in current source. The Worker copies every upstream response header except its hop-by-hop denylist. `Set-Cookie` is not denied, so an upstream Cloudflare Access authorization cookie would be returned to the public caller. Current tests prove generic response-header pass-through but do not guard this credential boundary.

The live healthy-path behavior could not be revalidated because the public MCP endpoint was down during the audit. Sanitized GET and initialize POST probes both returned HTTP 502 without `Set-Cookie`. Absence on a Worker-generated failure response does not disprove exposure on the upstream success path.

## Evidence

1. Current-main implementation:
   - `deploy/cloudflare-worker/worker.js:60` defines the response denylist without `set-cookie`.
   - `deploy/cloudflare-worker/worker.js:182-188` copies every non-denied upstream header into the public response.
   - `deploy/cloudflare-worker/worker.test.js:317-346` covers generic pass-through and hop-by-hop stripping, but there is no `Set-Cookie` boundary test.
2. Sanitized live probe at `2026-07-30T16:56Z`:
   - GET `/mcp`: HTTP 502; response header names recorded; `Set-Cookie` absent.
   - initialize POST `/mcp`: HTTP 502; response header names recorded; `Set-Cookie` absent.
   - Cookie values were never printed or persisted.
3. Independent outage evidence:
   - Canonical `mcp_public_canary.py --assert-handles` returned HTTP 502 locally.
   - GitHub uptime run [30560114532](https://github.com/Jonnyton/TinyAssets/actions/runs/30560114532) failed the same handshake at `2026-07-30T16:09Z`.
   - Deploy issue [#1919](https://github.com/Jonnyton/TinyAssets/issues/1919) remains open after deploy run 30528360171 failed daemon health and rollback proof.

## Coordination implication

Keep the Access-cookie concern at P0 and freshness-stamp it 2026-07-30. Track the independently verified public 502 as a separate P0 outage. A later implementation lane should fail first on an upstream `Set-Cookie: CF_Authorization=...` regression test, strip credential-bearing response cookies without buffering SSE, deploy through normal gates, then repeat sanitized healthy-path and rendered chatbot verification.
