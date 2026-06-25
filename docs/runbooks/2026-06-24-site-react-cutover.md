# Runbook — cut tinyassets.io over from Svelte to the React/Next site

**Status:** READY, host-gated. Nothing here has run. The live site is still the
SvelteKit build (`WebSite/site/`, `deploy-site.yml`). This documents the
deliberate switch to the React migration (`WebSite/site-react/`).

## Why a runbook (not automatic)

The site is a live public surface (Forever rule: 24/7 uptime). The React deploy
workflow (`deploy-site-react.yml`) is **workflow_dispatch only** with a typed
`confirm: deploy` guard, so it can never auto-fire. Both site workflows share the
`pages` concurrency group, so they must not both be live-triggering at once.

## Pre-cutover checklist

- [ ] React branch merged to `main` (`WebSite/site-react/`, `WebSite/design-system/`).
- [ ] `WebSite/site-react`: `npm ci && npm run build` is green locally (28 static pages).
- [ ] Visual parity spot-checked vs the live Svelte site on key routes
      (home, graph, loop, goals, fine-print, soul). Screenshot pass done 2026-06-24
      caught + fixed the home 404-on-hydration; re-verify after any further edits.
- [ ] `WebSite/site-react/public/CNAME` = `tinyassets.io` and `.nojekyll` present
      (both ship into `out/`).
- [ ] Live-data note: the React site fetches `/mcp` same-origin in prod (the
      Cloudflare Worker route is preserved); confirm the Worker route still answers.
- [ ] TinyBot, VitalSigns, goals/commons/loop/graph live reads confirmed against
      the prod `/mcp` (they degrade gracefully to "reading…/asleep" if unreachable).

## Cutover steps

1. **Deploy React once to verify** — run `deploy-site-react.yml` (Actions →
   Run workflow → `confirm: deploy`). It builds the design system, then the site,
   uploads `WebSite/site-react/out`, and deploys to the `github-pages` environment.
2. **Probe the public surface** (AGENTS.md hard rule #11):
   `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` and a
   browser load of `https://tinyassets.io/` — confirm green + the React site renders.
3. **Stop the Svelte deploy from fighting** — in `deploy-site.yml` remove the
   `push:` and `schedule:` triggers (leave `workflow_dispatch` for rollback), or
   delete the workflow. This prevents the next `WebSite/site/**` push or the 6h
   cron from redeploying the Svelte build over the React one.
4. **Snapshot freshness** — the Svelte deploy re-baked the MCP snapshot every 6h
   (`/graph`, `/commons`). Port that to the React workflow if you want the same
   auto-refresh: add a `Refresh MCP snapshot` step + a `schedule` trigger, baking
   into `WebSite/site-react/lib/mcp-snapshot.json` before build. (Left out of the
   manual workflow on purpose — the cutover deploy uses the committed snapshot.)

## Rollback

Re-enable `deploy-site.yml`'s `workflow_dispatch` (or its `push` trigger) and run
it; it redeploys the Svelte build to the same Pages environment. The Svelte source
is untouched by the migration.

## Known follow-ups (not blockers)

- `goals/[id]` static export prerenders only the 3 home-page ids; other ids rely
  on SPA-fallback (same as the original `ssr=false` page).
- Consider porting the 6h snapshot re-bake (above) before relying on `/graph`,
  `/commons` freshness.
