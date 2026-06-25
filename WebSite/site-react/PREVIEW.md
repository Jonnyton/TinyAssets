# Previewing & approving the React site

Three ways to see changes before they go live. **The live site (tinyassets.io)
is unaffected by all of these** until the host runs the gated cutover
(`docs/runbooks/2026-06-24-site-react-cutover.md`).

## 1. Local hot-reload (fastest, like the old `vite dev`)

```bash
cd WebSite/site-react
npm install        # first time
npm run dev        # → http://localhost:3000
```

Live data (vital signs, goals, graph) works: dev proxies `/mcp` →
`https://tinyassets.io/mcp` server-side (no CORS), the same role the old Svelte
`/mcp-live` proxy played.

## 2. Production-exact local preview

```bash
cd WebSite/site-react
npm run preview    # next build + serves the real static export at http://localhost:4322
```

This is byte-for-byte what GitHub Pages would publish. Live `/mcp` data does NOT
load here (no same-origin endpoint on localhost) — use #1 for live data, #3 for a
live-data hosted check.

## 3a. Live hosted snapshot (works right now, no setup)

**https://jonnyton.github.io/tiny-site-react-preview/** — a published snapshot of
this branch on GitHub Pages (separate public repo `Jonnyton/tiny-site-react-preview`,
**not** the live tinyassets.io). Open it on any device. Notes:
- It's a project-pages subpath build (`PAGES_BASE_PATH=/tiny-site-react-preview`),
  so all links are prefixed; nav + in-content links work.
- Live `/mcp` data may not load (cross-origin from github.io); widgets degrade to
  "reading…/asleep" — use `npm run dev` for live data.
- It's a **manual snapshot**, not auto-updating. To refresh after changes:
  ```bash
  cd WebSite/site-react
  MSYS_NO_PATHCONV=1 PAGES_BASE_PATH=/tiny-site-react-preview \
    NEXT_PUBLIC_MCP_PATH=https://tinyassets.io/mcp npm run build
  # re-apply the raw-link prefix fixup + rm out/CNAME, then push out/ to the
  # preview repo's gh-pages branch. (Or use the auto-updating CF Pages flow below.)
  ```

## 3b. Live-data hosted preview (Cloudflare Worker) — the good one

**https://tiny-site-react-preview.jonathan-m-farnsworth.workers.dev** — a
Cloudflare **Worker** that serves the static export and proxies `/mcp`
**same-origin** (via `cf-worker/worker.js`). So it shows **real live data** —
TinyBot is alive (open eyes, moving), vital signs/goals/graph read the live
engine — unlike the GitHub Pages snapshot (where cross-origin `/mcp` is blocked,
so TinyBot shows his ×-eyes "unreachable" face).

Deployed by `preview-worker.yml` on every PR push (and the comment posts the URL),
using the **existing** Workers-scoped `CLOUDFLARE_API_TOKEN` — **no extra
permissions or setup needed**. Separate from the production MCP worker; never
touches tinyassets.io.

## The approval loop (default: live Worker preview)

1. A change lands on a branch / PR (made by you or by an agent).
2. `preview-worker.yml` posts the live preview URL on the PR (and the GitHub Pages
   snapshot auto-refreshes within ~20 min as a no-Cloudflare fallback).
3. You review on the link; request tweaks or approve.
4. On approval → merge to `main`. **Merging does not auto-publish** — the React
   site only goes live when the host runs the cutover (`deploy-site-react.yml`,
   `confirm: deploy`). Until cutover, `main` just holds the approved React source
   while tinyassets.io stays on Svelte.
