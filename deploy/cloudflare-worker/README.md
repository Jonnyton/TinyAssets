# Cloudflare Worker — `tinyassets.io/mcp` path router

**Status:** Shipped after the 2026-04-20 single-entry cutover. This is the real
fix for the 2026-04-19 P0 URL-mismatch outage: route `tinyassets.io/mcp*`
to the tunnel origin at `mcp.tinyassets.io`, while leaving the GitHub Pages
landing intact for all other paths.

**After deploy:** the canonical public MCP URL returns to
`https://tinyassets.io/mcp`. Installed TinyAssets chatbot connectors pointing
at that URL start working again without any user action.

---

## What this solves

Before the Worker:

- `tinyassets.io` apex serves GitHub Pages (landing page).
- `mcp.tinyassets.io` serves the Cloudflare Tunnel → TinyAssets daemon.
- Installed TinyAssets chatbot connectors point at `https://tinyassets.io/mcp`.
- `tinyassets.io/mcp` has no route rule → falls through to the landing origin's 404
  → Claude.ai reports "Session terminated." This was the 2026-04-19 P0.

After the Worker deploys:

- Same DNS (tinyassets.io still Cloudflare-fronted).
- Same GitHub Pages origin for apex paths (landing unchanged).
- NEW: the Worker runs on route `tinyassets.io/mcp*`. Any `/mcp*`
  request gets proxied to `mcp.tinyassets.io` (tunnel origin) as a
  streaming pass-through. Apex `/` + non-`/mcp` paths still hit GitHub Pages.

---

## Files in this directory

| File | Purpose |
|---|---|
| `worker.js` | The Worker script itself — pure Fetch API proxy. |
| `wrangler.toml` | Cloudflare Worker deploy config (name, route, compat date). |
| `worker.test.js` | 30 unit tests via `node --test` — exercise header preservation, streaming pass-through, 5xx→502 translation, etc. |
| `README.md` | This file. |

---

## Deploy path A — Wrangler CLI (recommended for ops)

Requires [Wrangler](https://developers.cloudflare.com/workers/wrangler/install-and-update/)
on PATH (`npm install -g wrangler` or `npx wrangler@latest`).

```bash
cd deploy/cloudflare-worker

# One-time: authenticate. Opens a browser to the Cloudflare login flow.
wrangler login

# Validate the config + worker before pushing.
wrangler deploy --dry-run --outdir /tmp/wrangler-out

# Deploy. Publishes worker + registers the route tinyassets.io/mcp*.
wrangler deploy
```

Verify:

```bash
# Canary should exit 0 within ~60s of deploy (DNS + edge propagation).
python ../../scripts/mcp_public_canary.py \
    --url https://tinyassets.io/mcp --verbose
```

Rollback:

```bash
# Either deploy a previous version, or delete the Worker + route.
wrangler rollback                               # previous version
wrangler delete                                 # full removal
```

Tail live Worker logs:

```bash
wrangler tail
```

---

## Deploy path B — Dashboard (for operators without Wrangler)

If you'd rather click than CLI:

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) → `tinyassets.io` zone.
2. **Workers & Pages** → **Create Application** → **Create Worker**.
3. Name: `tinyassets-mcp-proxy`. Click **Deploy** (default "Hello World"
   placeholder is fine at this step).
4. Open the new Worker → **Edit code** → replace the entire editor
   contents with the body of `worker.js` from this directory → **Save and deploy**.
5. On the Worker overview page: **Triggers** → **Routes** → **Add route**.
   - Route: `tinyassets.io/mcp*`
   - Zone: `tinyassets.io`
   - Save.
6. Verify with the canary (see path A verify step).

**If the Worker fails to save** with a syntax error, double-check the
editor got the full `worker.js` body including the `export default {}`
at the bottom. The dashboard editor sometimes truncates on paste of
large files; `wc -l worker.js` locally should match the editor's line
count.

---

## Canonical URL reference

Post-deploy:

| URL | Purpose |
|---|---|
| `https://tinyassets.io/mcp` | **Canonical — installed TinyAssets chatbot connectors.** Worker routes to tunnel. |
| `https://mcp.tinyassets.io/mcp` | Direct-tunnel origin — Access-gated, not user-facing. Use only for internal Access/service-token debugging. |
| `https://tinyassets.io/` | GitHub Pages landing (unchanged). |

---

## How the Worker handles MCP

MCP streamable-http has two failure modes a naive proxy breaks:

1. **Server-sent events.** MCP returns responses as SSE frames
   (`event: message\ndata: {...}\n\n`). A proxy that calls `.text()` or
   `.json()` on the response buffers the whole body, breaking streaming
   for any response that takes time to generate.

   The Worker treats the response body as a `ReadableStream` and
   passes it through to the client without touching the bytes. 4 tests
   cover this — including one that uses an explicit `ReadableStream`
   to assert the stream identity is preserved.

2. **Session headers.** Claude.ai's MCP client uses `Mcp-Session-Id`
   to persist session state across requests. The Worker forwards all
   non-hop-by-hop headers verbatim, including `Mcp-Session-Id`,
   `Authorization`, `Accept: text/event-stream`, etc. Covered by
   dedicated tests.

Hop-by-hop headers (RFC 7230 §6.1 — `Connection`, `Transfer-Encoding`,
`Upgrade`, etc.) are explicitly stripped to avoid forwarding connection
semantics that don't apply to the upstream hop.

---

## Failure modes + 502 translation

The Worker returns **502 Bad Gateway** with a JSON body in two cases:

- Tunnel origin unreachable (network error from `fetch()`).
- Tunnel origin returns 5xx.

This is deliberate. A 502 is unambiguous: the Worker saw an upstream
problem. Letting the fallthrough go to the landing origin's 404 is what caused the
original P0's diagnostic confusion ("is the tunnel down? or is the
Worker broken? or is the route wrong?"). Explicit 502s end that
ambiguity.

4xx responses pass through untouched — those are client errors the
upstream wants to report verbatim, not proxy errors.

---

## Running tests locally

Node 18+ required (uses the built-in `node:test` runner + Fetch API).

```bash
cd deploy/cloudflare-worker
node --test worker.test.js
```

Expect `30 passed, 0 failed`. CI wires this into the existing
`.github/workflows/docker-build.yml` or its own workflow once the
Worker lands; for now the test runs locally.

---

## Known limitations + follow-ups

- **One-way proxy, no caching.** Cloudflare's edge cache is bypassed
  by default for Worker-proxied requests. MCP responses are per-session
  and shouldn't be cached anyway, so this is correct — but if we ever
  want to cache static MCP-served assets, we'd add `cf: {cacheTtl}` to
  the upstream fetch.

- **No rate limiting in the Worker.** Upstream daemon sees the full
  request volume. If we ever hit abuse, Cloudflare WAF / Rate Limiting
  adds on top of the Worker without code change.

- **Single origin.** Multi-region failover (primary Hetzner + fallback
  Fly) is a Row D concern, not Row Worker. When that lands, this
  Worker's `TUNNEL_ORIGIN` grows into an ordered list + retry logic.

- **CI deploy is automated.** Any push to `main` that touches
  `deploy/cloudflare-worker/**` triggers `.github/workflows/deploy-worker.yml`,
  which runs Wrangler + a post-deploy canary. PRs get a dry-run only.
  Required repo secret: `CLOUDFLARE_API_TOKEN` with scopes
  `Account:Workers Scripts:Edit`, `Zone:Workers Routes:Edit`,
  `Zone:Zone:Read`. Also set `CLOUDFLARE_ACCOUNT_ID` as a repo secret.
