# TinyAssets retained Svelte rollback site

This SvelteKit static site is retained as the rollback implementation for
`tinyassets.io`. The current production source is the React/Next tree at
`WebSite/site-react/`, deployed manually by `deploy-site-react.yml`.

For production changes, edit and build React first, then mirror the intended
user-visible behavior here and verify parity. This tree deploys only through an
explicit rollback dispatch of `deploy-site.yml`; it has no push or cron deploy.

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

## Rollback deploy to GitHub Pages

`static/CNAME` is set to `tinyassets.io` for custom-domain hosting. `static/.nojekyll` disables Jekyll processing on GitHub.

The build outputs to `build/`. The workflow at
`.github/workflows/deploy-site.yml` is dispatch-only and exists solely to
restore this Svelte build during an explicit rollback. Normal production
publishing uses the manual React workflow.

```powershell
npm run build
# after review, dispatch deploy-site only when a Svelte rollback is required
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
│   │   ├── Hero.svelte                  landing hero
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
git push           # source update only; does not deploy either site
```

The script is `scripts/snapshot-mcp.mjs`. It uses
`@modelcontextprotocol/sdk`; snapshot refreshes run anonymously so a
caller-specific grant can never be baked into a public artifact. If the MCP is
unreachable, the existing snapshot is kept unless `SNAPSHOT_REQUIRED=1`.
`MCP_BEARER` is forbidden and makes the snapshot command fail.

**Rollback refresh:** `deploy-site.yml` has no cron or push trigger. When a
rollback specifically needs a fresh Svelte snapshot, dispatch it manually with
`refresh_snapshot=true`. The workflow performs the read anonymously and fails
closed if it cannot prove a complete public snapshot. Production React
deployment does not use this snapshot step.

## Open TODOs

1. **Rollback readiness** — keep focused checks and parity green; verify the
   dispatch-only workflow only when a rollback is deliberately exercised.
2. **OG image** — add `static/og-image.png` for social previews.
3. **Phase 1.5 component ports** — Diagrams, Economy (full), AgentTeams, Showcase, Catalog (full), Host (full with mode-fork), Contribute (full).
4. **Real Supabase wiring** — `src/lib/supabase.ts` (Phase 2 swap to dual-adapter for SSR routes).
5. **Verify daemon CLI** — `python -m fantasy_daemon` is in the /host stub; confirm it's the right entry point on the actual repo.
