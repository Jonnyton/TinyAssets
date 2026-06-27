# DEPLOY — first ship of `tinyassets.io` on the new SvelteKit site

Walks through the cutover from the legacy GoDaddy "Asset Backed Currency"
landing to the new TinyAssets site, with no `/mcp` downtime.

## What ships

- `WebSite/site/` — SvelteKit static build, deployed to GitHub Pages
- `.github/workflows/deploy-site.yml` — CI: paths-filtered to
  `WebSite/site/**`, plus 6h cron + manual dispatch with optional
  snapshot refresh
- `WebSite/website-ship.bundle` — the prepared commit (use `ship.ps1`)

## Architecture (verified live, 2026-04-29)

```
                     ┌── DNS at Cloudflare (tim/kay.ns.cloudflare.com)
                     │
tinyassets.io        │
   ├─  /            ────►  GoDaddy hosted site (legacy crypto landing)
   │                       └─►  this is what the new site replaces
   │
   ├─  /mcp*        ────►  Cloudflare Worker (path-based route)
   │                       └─►  tunnel ──►  mcp.tinyassets.io ──► daemon
   │                       └─►  GATED BY CLOUDFLARE ACCESS (returns 403
   │                            on unauth OPTIONS preflight; browser-side
   │                            fetches from new site will be rejected)
   │
   └─  everything else  ──►  GoDaddy 404
```

After cutover, `/` is replaced by GitHub Pages. The Worker route on
`/mcp*` is path-based and **survives the apex DNS cutover automatically**
— you do not need to touch the Worker.

## Steps (do in order)

### 1. Push the prepared bundle from Windows

```powershell
cd C:\Users\Jonathan\Projects\TinyAssets\WebSite
.\ship.ps1
```

This clones a fresh `main` into `$env:TEMP\wf-ship`, fetches
`website-ship.bundle`, and pushes branch `website/ship-prototype` to
GitHub. Prints a compare URL.

### 2. Merge to main

Either:

- **Fast-forward:** `git push origin website/ship-prototype:main`
- **Or PR:** open the printed URL, review, merge.

The deploy workflow's path filter (`WebSite/site/**`) only fires on
this merge — none of the in-progress engine work on other branches will
trigger it.

### 3. Enable GitHub Pages

Repo Settings → Pages:

- **Source:** GitHub Actions (NOT "Deploy from branch")
- **Custom domain:** `tinyassets.io`
- **Enforce HTTPS:** check after the cert provisions (5–15 min)

### 4. DNS cutover at Cloudflare

DNS is at Cloudflare (you don't need to touch GoDaddy DNS). At the
Cloudflare dashboard for `tinyassets.io`:

| Type  | Name | Content              | Proxy  |
|-------|------|----------------------|--------|
| A     | @    | 185.199.108.153      | 🟠 on   |
| A     | @    | 185.199.109.153      | 🟠 on   |
| A     | @    | 185.199.110.153      | 🟠 on   |
| A     | @    | 185.199.111.153      | 🟠 on   |
| CNAME | www  | jonnyton.github.io   | 🟠 on   |

Existing apex records pointing at GoDaddy → delete them.
Existing `/mcp*` Worker route → leave alone.

After the records propagate, set Cloudflare SSL/TLS mode to
**Full (strict)** once the GitHub Pages cert provisions.

### 5. Smoke test

- `https://tinyassets.io` → new TinyAssets hero ("Summon a daemon. Bind a universe…")
- `/wiki` → renders 47 promoted pages, "fetched at YYYY-MM-DDThh:mm" timestamp under LiveBadge
- `/graph` → constellation with 59 nodes, 126 edges, 19 orphans counter
- `/legal` → safe-harbor block with Delaware/JAMS terms
- `/connect`, `/host`, `/contribute`, `/economy`, `/patterns`, `/alliance` → all render

If `/wiki` and `/graph` show **"Live fetch failed: error — showing
baked snapshot"**, that's expected today: the `/mcp` endpoint is gated
by Cloudflare Access. The baked snapshot is the prototype's actual
data layer for now (re-baked daily by CI cron).

### 6. (Optional) Enable true browser-side live readout

To make `/wiki` and `/graph` actually fetch live (not fall back to
baked), one of:

- **A. Remove Cloudflare Access** on `/mcp*` for read-only methods
  (`tools/list`, `tools/call` with `wiki/list`, `wiki/read`,
  `goals/list`, `universe/list`). Other methods stay gated.
- **B. Add a `/mcp-public/*` Worker route** that's CORS-permissive
  (`Access-Control-Allow-Origin: https://tinyassets.io`), bypasses
  Access, allowlists read-only methods, forwards to the same tunnel.
  Then update `WebSite/site/src/lib/mcp/live.ts` to fetch that path.
- **C. Add `MCP_BEARER` repo secret** + service token at Cloudflare
  Access. Then dispatch `deploy-site` with `refresh_snapshot=true` and
  the snapshot at build time has fresh data, but browser-side live
  readout still won't work (token would have to be exposed in JS,
  which defeats the point).

Recommended: B for true public readout.

## Rollback

If something blows up after cutover, restore the previous A records at
Cloudflare (the GoDaddy hosted-site IPs, which Cloudflare can show in
the audit log) and disable the GitHub Actions deploy workflow. The
Worker route on `/mcp*` is unaffected.

## Verify deploy succeeded (CI)

GitHub Actions tab → `deploy-site` workflow → green checkmark on the
merge commit. The deploy step prints the page URL like
`https://jonnyton.github.io/TinyAssets/`. Custom domain serves the same
content at `https://tinyassets.io/`.
