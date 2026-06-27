# tinyassets.io — TinyAssets site (Track B Phase 1)

Landing-first SvelteKit static site for the TinyAssets platform, deploying to GitHub Pages with `tinyassets.io` as a custom domain. Replaces the legacy crypto-investor homepage with the TinyAssets positioning per spec `docs/specs/2026-04-18-web-app-landing-and-catalog.md`.

**Phase 1 polished:** `/`, `/connect`, `/legal`.
**Phase 1 stubbed:** `/catalog`, `/host`, `/contribute`, `/status`, `/account`, `/economy`.
**Phase 2+ to add:** real `/catalog` browse, real `/host` mode-fork, full `/economy`, `/teams`, `/novel`, `/coding`, `/editor/*`, `/earnings`, `/admin`, OG images, Realtime widgets, Supabase auth.

## Stack

- **SvelteKit 2** + **Svelte 5** (runes mode) + **Vite 5**
- **`@sveltejs/adapter-static`** — pure static output (Phase 2 swaps to dual-adapter)
- **TypeScript** throughout
- **Plain CSS** with canonical design tokens in `src/lib/styles/tokens.css` (no Tailwind — keeps bundle small per spec §1)

## Local dev

Requires Node.js 20+. Install + run:

```powershell
cd C:\Users\Jonathan\Projects\TinyAssets\WebSite\site
npm install
npm run dev          # http://localhost:5173
```

Other commands:

```powershell
npm run build        # static output in build/
npm run preview      # preview the static build
npm run check        # type-check Svelte + TS
npm run format       # prettier write
npm run lint         # eslint + prettier check
npm run test:e2e     # playwright tests (placeholder)
```

## Deploy to GitHub Pages

`static/CNAME` is set to `tinyassets.io` for custom-domain hosting. `static/.nojekyll` disables Jekyll processing on GitHub.

The build outputs to `build/`. The CI workflow at `.github/workflows/deploy-site.yml` runs on every push to `main`, builds with `npm run build`, and deploys to the `gh-pages` branch via `peaceiris/actions-gh-pages`. Cloudflare fronts the apex domain per the architecture docs.

Manual deploy if you want to bypass CI:

```powershell
npm run build
# upload contents of build/ to your gh-pages branch
```

## Layout

```
src/
├── app.html                       HTML shell (TinyAssets mark favicon, theme color)
├── app.css                        Imports tokens; tiny app-only utilities
├── app.d.ts                       TypeScript ambient types
├── routes/
│   ├── +layout.svelte             TopNav + Footer chrome
│   ├── +page.svelte               / landing — Hero + ThreeLayer + WhyTinyAssets + TokenStrip
│   ├── connect/+page.svelte       /connect — MCP URL paste + 2-step
│   ├── legal/+page.svelte         /legal — license + privacy stubs
│   ├── catalog/+page.svelte       /catalog — Phase 1.5 stub
│   ├── host/+page.svelte          /host — Phase 1.5 stub (with quick-start CLI)
│   ├── contribute/+page.svelte    /contribute — Phase 1.5 stub (CTAs to GH)
│   ├── status/+page.svelte        /status — Phase 1.5 stub (MCP probe info)
│   ├── account/+page.svelte       /account — Phase 2 stub (auth-gated)
│   └── economy/+page.svelte       /economy — Phase 1.5 stub (tinyassets reframe)
├── lib/
│   ├── components/
│   │   ├── Primitives/
│   │   │   ├── Button.svelte           primary/secondary/ghost/link
│   │   │   ├── RitualLabel.svelte      small-caps mono kicker
│   │   │   └── StatusPill.svelte       live/idle/paid/self/error pill
│   │   ├── TinyAssetsMark.svelte        TinyAssets brand mark
│   │   ├── TopNav.svelte                sticky-translucent nav
│   │   ├── Footer.svelte                footer chrome + contact
│   │   ├── ChatDemo.svelte              faux Claude.ai transcript (hero showcase)
│   │   ├── Hero.svelte                  landing hero (copy + ChatDemo)
│   │   ├── ThreeLayer.svelte            Goal · Branch · Daemon trinity
│   │   └── TokenStrip.svelte            tinyassets economy + 3-chain addresses
│   ├── content/
│   │   └── token-info.json              single source of truth for ta token (BASE/PulseChain/BSC)
│   ├── i18n/
│   │   └── en.json                      canonical product copy (from prototype/web-app-v0)
│   └── styles/
│       └── tokens.css                   canonical design tokens (Ink/Violet/Ember/Bone palette)
└── static/
    ├── logo-mark.png                    TinyAssets raster brand mark
    ├── tinyassets-mark.svg              favicon / static brand mark
    ├── tinyassets-mark.png              raster fallback for the static brand mark
    ├── CNAME                            tinyassets.io custom domain
    └── .nojekyll                        disable GitHub Jekyll processing
```

## Design system source of truth

Brand palette, typography, motion, voice, vocab kit all live in:
- `src/lib/styles/tokens.css` (CSS variables — these ARE the brand)
- `../../assets/brand/` (reusable SVG/PNG logo exports)
- `WebSite/design-source/README.md` (design-system bible — voice, palette derivation, icon rules)
- `WebSite/design-source/colors_and_type.css` (canonical source — kept identical to tokens.css)
- `WebSite/design-source/tinyassets-landing-standalone.html` (single-file bundled React preview of the full design)

The vocab kit is load-bearing: **summon** a daemon (not "create"), **bind** to a universe (not "configure"), **entrust** with a task (not "assign"), **dismiss** (not "stop"), **roam** (not "search"), **return** (not "complete"). The README has the calibration examples.

## FUSE quirks (for Cowork sessions)

The Cowork sandbox mounts this folder over FUSE. Two known quirks:
1. `Write` tool silently truncates overwrites — use `bash` heredoc instead. A `PostToolUse` hook (`.claude/hooks/fuse_write_truncation_guard.py`) catches this.
2. `node_modules/.bin/` symlinks don't materialize — always run `npm install` and dev/build commands on Windows, not in the sandbox.

See `WebSite/HOOKS_FUSE_QUIRKS.md` for details.


## Refreshing the MCP snapshot

`/wiki` and `/graph` are baked from `src/lib/content/mcp-snapshot.json`. To pull fresh data:

```powershell
npm run snapshot   # calls tinyassets.io/mcp, rewrites the JSON
git add src/lib/content/mcp-snapshot.json
git commit -m "snapshot: refresh MCP"
git push           # CI rebuilds + redeploys
```

The script is `scripts/snapshot-mcp.mjs`. It uses `@modelcontextprotocol/sdk` and fails soft — if the MCP is unreachable, the existing snapshot is kept and the build still ships. If the MCP endpoint requires auth, set `MCP_BEARER` in your shell env (or as a repo secret named the same in CI).

**CI cadence:** the GH Action runs every 6h on cron *and* on every push touching `WebSite/site/**`. By default the cron just rebuilds with whatever snapshot is checked in. To make CI also refresh from MCP, dispatch the workflow manually with `refresh_snapshot=true` — requires `MCP_BEARER` repo secret.

## Open TODOs

1. **CI deploy** — `.github/workflows/deploy-site.yml` is set up but verify the workflow runs on first push.
2. **OG image** — add `static/og-image.png` for social previews.
3. **Phase 1.5 component ports** — Diagrams, Economy (full), AgentTeams, Showcase, Catalog (full), Host (full with mode-fork), Contribute (full).
4. **Real Supabase wiring** — `src/lib/supabase.ts` (Phase 2 swap to dual-adapter for SSR routes).
5. **Verify daemon CLI** — `python -m fantasy_daemon` is in the /host stub; confirm it's the right entry point on the actual repo.
