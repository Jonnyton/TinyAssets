---
name: website-editing
description: "Conventions for editing the TinyAssets site (WebSite/site/, deploys to tinyassets.io). Use when you make any change to the site: copy, components, routes, content, styling, captures of real chatbot conversations, deploy. Covers the preview loop, transparent-capture conventions, build/ship pipeline, FUSE quirks for Cowork, and auto-iteration on recurring failures."
---

# Website editing

Conventions for the SvelteKit static site at `WebSite/site/` that deploys to `tinyassets.io`. These are project-level website rules — they apply equally to every provider (Codex, Cursor, Aider, Claude Code, Cowork), but the detailed rules live here so `AGENTS.md` can stay lean. When in doubt, add website conventions to this skill and keep provider-specific files as pointers or harness notes.

## Before you edit anything

1. **Read `WebSite/PREVIEW.md`** — the canonical preview loop. Default URL is `http://localhost:5173/`, hard-pinned. Jonathan double-clicks `WebSite/preview.bat` once per boot; from then on every edit you make to `WebSite/site/src/**` hot-reloads automatically.
2. **Read `WebSite/DEPLOY.md`** if you might ship — covers `ship.ps1`, fast-forward to main, the GitHub Actions deploy, and the playwright verify against the live URL.
3. **Read `WebSite/HOOKS_FUSE_QUIRKS.md`** if you're in Cowork — Edit/Write silently truncate on the FUSE mount; **for any existing file, use bash heredoc**:
   ```bash
   cat > "/full/path/to/file" << 'FILE_EOF'
   ... full file content ...
   FILE_EOF
   ```
   Verify with `wc -l` + `tail`. Other providers (Codex, Cursor, Claude Code on Windows) don't have this issue.

## The iteration loop

Once `preview.bat` is up and Jonathan has the tab open at `localhost:5173/`:

```
Jonathan:  "the hero subline is too long"
Agent:     [edits Hero.svelte]
Jonathan:  [tab updates by itself]   ← HMR, no F5 needed
Jonathan:  "yeah that's better"
```

You do **not** rebuild or redeploy to show a change. Vite's HMR pushes the patch over a websocket. Every browser tab open to `localhost:5173/` (Jonathan's, your playwright tab, anyone else's) receives the same update simultaneously — multi-agent / multi-tab sync is free.

If F5 is ever needed, that's a signal HMR misfired — **investigate**, don't normalize the workaround. The intended state is "edit a file, tab updates, no input from the user."

## Transparent capture — when the website shows a real chatbot conversation

The site's home (ChatDemo) and `/loop` show real conversations Jonathan had with the TinyAssets MCP connector via claude.ai. The principle: **when claiming transparency, the captured material has to BE the captured material — not a summary, not a paraphrase, not curated highlights.**

Required when capturing a real conversation for the site:

1. **Every word verbatim.** Use the Claude in Chrome browser tools to drive the actual chat in claude.ai. Use `get_page_text` to extract the rendered conversation. Don't reword. Don't shorten. Don't "tighten the prose."
2. **Mirror the source's disclosure layers exactly.** Claude.ai uses summary chips that toggle to reveal thought traces, and inside long traces it has secondary "Show more / Show less" buttons. The website should mirror **both layers** with the same defaults — chips closed by default, long thoughts truncated by default with the same Show more cut.
3. **Click every disclosure before claiming you have the full text.** Each chip has its own Show more. Re-extract via `get_page_text` after every expansion to make sure you've got it all.
4. **Render the full diagram(s).** Real diagrams have specific node counts, edge labels, color groups. Hand-rolled SVGs are fine (mermaid.js npm install can be slow on Cowork) — but the SVG must be faithful to the source: same node count, same labels, same back-edges, same color groups (blue branch, warm gate, green live/done, dashed planned/terminal).
5. **Anchor section verbatim.** When the chatbot lists "Anchors used: Goal X — …", reproduce the prose as a single block, not a bullet summary. The "honest caveat" line gets its own visually distinct callout.
6. **Footer line names the source.** *"Captured 2026-MM-DD from claude.ai with the TinyAssets MCP connector attached. Every word above appears verbatim in the original chat."*

**Anti-pattern:** writing "Loading tools — Goals — Wiki Knowledge Base × 3" and calling it a thought trace. That's a summary of tool calls, not the actual text. The actual text has Claude's reasoning between each tool call. Capture all of it.

## Page conventions

- **Hero**: H1 + ritual label + ONE lead paragraph. If you find yourself writing two intro paragraphs that overlap in meaning, consolidate.
- **Home action discipline**: the homepage first screen should name the three primary user actions plainly. Live MCP/GitHub state supports those actions; it must not turn the home page into a catalog of every implementation.
- **CTAs**: don't dilute. The home hero has one primary action; secondary CTAs go further down.
- **Mobile**: TopNav has a hamburger drawer at `<=1000px`. If you add nav items, they go in `TopNav.svelte`'s `items` array — both the desktop nav and the mobile drawer auto-render.
- **Stub pages and retired routes** (`/status`, `/account`, `/goals`, `/catalog`): keep them honest. `/wiki` is the canonical community wiki and public-work lens. `/goals` and `/catalog` are compatibility redirects only; do not advertise `/goals` in primary nav, CTAs, sitemap, or graph affordances.
- **Forms**: never fake. If there's no backend yet, use `mailto:` (the alliance form does this). Real fields with `name=` attributes; `onsubmit` actually does something.
- **Affordance contract**: if something looks clickable, it must be clickable. If it is not a real control/link, remove the button/card/chip hover treatment. Clickable site elements should either navigate to a real route/source, change visible UI state backed by the current MCP/repo snapshot, trigger a real refresh/probe, copy a real value, or open a live source such as MCP/GitHub/wiki data. Prefer `<button>` and `<a>` over clickable `<div>`s.
- **Clickable cards use valid interactive markup.** If a whole card is a `<button>`, keep its children phrasing-only (`span`, `strong`, `small`, etc.); headings, paragraphs, and divs can be parsed outside the button and make only part of the card clickable. If the card needs block content, use an `<a>` for navigation or put a real button/link inside the card with a clearly bounded hit target, then verify by clicking the title/body text in Playwright.
- **Refresh labels are fixed.** Site-wide live-data buttons are always named `Refresh MCP` and `Refresh GitHub`. Page-specific variants like `Probe MCP`, `Refresh goals`, or `Refresh branches` make the same command feel like different controls.
- **Source readouts are evidence, not navigation.** `MCP source` / `GitHub source` cells should be static proof readouts unless they open the actual raw source in a clearly different context. Do not link a source readout to another page that repeats the same source readout.
- **No adjacent duplicate destinations.** If two nearby clickable surfaces go to the same route/source, keep the clearer or richer one and remove, demote, or retarget the weaker one. A duplicate link is only acceptable when it is separated by context or serves a different workflow moment.
- **Merge overlapping page jobs.** If two site pages are trying to do the same user job, pick the stronger live-data surface as canonical, remove the weaker page from primary navigation and graph affordances, and keep the old route only as a compatibility redirect/alias when existing links may exist.
- **Graph navigation theme**: when a page presents itself as a live project lens, use the shared mini graph navigation pattern where it helps orientation: render a live MCP/repo-backed graph preview that links to `/graph` and highlights the current lens, rather than a static CTA tile.
- **Graph truth layers.** `/graph` should not show project objects as visual orphans just because an explicit cross-reference has not been extracted yet. Add truthful relationship layers from live source structure first: bug tracker hub for BUG pages, goal/universe/wiki-draft hubs for MCP collections, GitHub branch hub for branch refs, and tag hubs for shared real tags. Keep explicit references visually stronger than collection/tag edges, and rename residual counts to "loose ends" or "isolated" so the page distinguishes missing specific routing from fake disconnection.
- **Stage rails stay compact.** A 1-N workflow rail is navigation/status, not the detail pane. Do not let stage tiles stretch to match a tall neighboring event stream or carry full error/output text. Keep tiles compact, clamp long labels, and route verbose failure/output details to the current-run card or event stream. If there is room, include a short latest-event summary that leads with the useful event text, such as `ran - Intake Router`; avoid prefixes like `Last event:` when they crowd out the actual event. Never put raw prompt/output JSON in the rail. For historical/no-active-run stages, preserve recency in the tile with `Last ran <timestamp>` and put `See recent events` as the bottom cue instead of replacing the timestamp with a generic `status - see recent events` line.
- **Selected-stage detail belongs below the rail when space allows.** If the user's primary interaction is clicking a 1-N rail, the clicked stage's explanation and live evidence should appear as a full-width downstream panel under the rail, not as a skinny sidecar that leaves empty space below the controls. The panel should surface real MCP/GitHub records: latest signal, source, run/node IDs, stage history, and explicit empty states. Detail cards must size to their own content, wrap long URLs/IDs, and keep long histories or raw live payloads in bounded scroll areas so selecting a busy stage cannot stretch or bleed text into neighboring boxes.
- **No phone numbers.** Per user directive: async-first project. Phone refs were removed in 2026-04. If a future need surfaces, talk to the user before adding one back.

## Build + ship

- `WebSite/site/` is SvelteKit + adapter-static. **`src/routes/+layout.ts` has `export const prerender = true;`** — this is required; without it the static adapter outputs only assets, no HTML.
- `svelte.config.js` `prerender.entries` lists every route. Add new routes here.
- New static asset: drop in `WebSite/site/static/`. Reference via absolute `/foo.png`.
- Live MCP fetch in dev: vite proxies `/mcp-live → tinyassets.io/mcp` (see `vite.config.js`). In prod, the cloudflare worker handles `/mcp` directly.
- **Shipping**: `WebSite/ship.ps1` from Windows PowerShell. It clones a fresh `main` to `$env:TEMP\wf-ship`, fetches the bundle Cowork prepared, pushes the branch. Then fast-forward main. Watch the GitHub Actions `deploy-site` workflow. Run the playwright verify in `WebSite/DEPLOY.md` against the live URL.

## Verification before shipping

Before declaring a website edit "done":

1. **Local build**: `cd WebSite/site && npm run build` — must end with `✔ done` and produce `build/<route>.html` for every route.
2. **Playwright sweep**: hit every route via a local http server, assert `errs: 0`, `warns: 0`, key elements present (H1, expected text, expected counts).
3. **For live-data controls**: click the real refresh button and assert the page renders meaningful data, not just a successful HTTP response or a changed source label. A pass requires the user-visible content to contain current, human-readable records or an explicit empty-state reason. Reject raw placeholders such as `{}`, `[]`, `undefined`, numeric epoch timestamps, stuck disabled buttons, or a green source label with no populated rows. For `/loop`, click `Refresh MCP` and `Refresh GitHub`; verify the visible showcase is operationally current. A stale terminal MCP run must not pass as "working" or "current patch run" just because it has readable text. If MCP has no active/current loop run, the page must say that plainly and either show the GitHub community-loop monitor as the live source or show an explicit empty-state reason.
4. **For workflow rails**: measure rendered stage tiles in Playwright on desktop and mobile. Empty or lightly populated stages must not become tall vertical strips just because a neighboring event stream is tall, and long failure text must not force a tile to hundreds of pixels high. Verify stage text is visible without internal scrolling; verbose details belong in the current-run card or selected-stage panel. Click every 1-N stage control and assert a clear, nearby visible state change beyond a subtle border, such as a full-width selected-stage panel changing title, purpose, event count, live signals, source, run IDs, or node IDs.
5. **For chat-capture pages**: assert defaults match the source's collapsed state (chips closed, long thoughts truncated). Then click and re-assert each disclosure layer.
6. **For HMR-sensitive changes** (vite config, `+layout.ts`, prerender entries): rebuild from scratch (`rm -rf build` first) — stale `.svelte-kit/` artifacts can mask real failures.

## Auto-iterate on recurring website failures

This skill is itself subject to the [`auto-iterate`](../auto-iterate/SKILL.md) ratchet pattern. If a website-related failure recurs:

| Recurrence | Ratchet |
|---|---|
| 1st  | Fix in place. Note it in the relevant doc. |
| 2nd  | Add the rule to **this** SKILL.md and the relevant subsystem doc (PREVIEW.md / DEPLOY.md / HOOKS_FUSE_QUIRKS.md). |
| 3rd  | Build a runnable check in `scripts/` that catches the failure pattern. |
| 4th  | Wire as a PostToolUse hook in `.claude/hooks/` for Claude Code; runnable from any provider. |
| Next | Pre-commit / CI gate. |

Concrete examples that have already ratcheted:
- **FUSE truncation** → atomic temp+rename in snapshot script → PostToolUse hook on Write+Edit → standing rule in CLAUDE.md/AGENTS.md/memory. Ladder: `WebSite/HOOKS_FUSE_QUIRKS.md`.
- **Cross-provider drift** → AGENTS.md rule → `scripts/check_cross_provider_drift.py` → `.claude/hooks/cross_provider_drift_guard.py` PostToolUse. Ladder: `AGENTS.md` § *Where new conventions live*.
- **Build outputs no HTML** → noticed when `build/` had only static assets; root cause was missing `prerender = true` in `+layout.ts`. The "verification before shipping" rule above (assert `build/<route>.html` exists) prevents recurrence.
- **Live-data false positive** → `/loop` refresh verification passed on button/source/no console errors while the actual event stream rendered `{}` details and raw epoch timestamps. The live-data control rule above prevents declaring success until the populated records are readable.
- **Stretched workflow rail** → `/loop` 1-6 stage buttons stretched to the full event-stream height, creating tall vertical strips where sparse text sat far from the visible top. The workflow-rail verification above requires bounding-box checks on desktop and mobile.
- **Invisible stage click result** → `/loop` 1-6 stage buttons updated selection state but the page appeared unchanged to users. The workflow-rail verification above now requires clicking every stage and asserting a visible content change.
- **Stale failed loop accepted as working** → `/loop` rendered a readable Apr 29 failed bootstrap run and was incorrectly declared fixed. The live-data rule above now requires freshness/operational checks: historical terminal runs are source evidence, not the current showcase.

## Files involved

| File                                          | What it is                                     |
|-----------------------------------------------|------------------------------------------------|
| `WebSite/preview.bat`                         | Hidden + persistent + idempotent dev launcher  |
| `WebSite/preview-stop.bat`                    | Kill the background vite server                |
| `WebSite/PREVIEW.md`                          | Full preview-loop reference                    |
| `WebSite/ship.ps1`                            | Push the prepared bundle to GitHub             |
| `WebSite/website-ship.bundle`                 | Generated by Cowork; one push away from live   |
| `WebSite/DEPLOY.md`                           | Deploy-day playbook + Claude Code verify prompt |
| `WebSite/HOOKS_FUSE_QUIRKS.md`                | Why heredoc, not Edit/Write, on Cowork's FUSE  |
| `WebSite/site/src/routes/`                    | All page routes                                |
| `WebSite/site/src/lib/components/`            | Shared components                              |
| `WebSite/site/src/lib/content/*.json`         | Content (mcp-snapshot, patterns, legal-info, …) |
| `WebSite/site/src/routes/+layout.ts`          | Sets `prerender = true` — DO NOT delete        |
| `WebSite/site/svelte.config.js`               | adapter-static, prerender entries              |
| `WebSite/site/vite.config.js`                 | Dev proxy for `/mcp-live`, HMR overlay         |
