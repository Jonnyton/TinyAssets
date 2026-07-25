# Preview loop — read this first if you're a chat session

Goal: zero-friction iteration on the Workflow site. Jonathan and any
chat session (Cowork, Claude Code, Codex) should always be able to
look at the **same live preview** of the in-progress site without
fiddling with ports, terminals, or rebuild cycles.

## The four commands you need

| What you want                                            | How to do it                                  |
|----------------------------------------------------------|-----------------------------------------------|
| **See the current draft in a browser** (Jonathan)        | Double-click `WebSite/preview.bat`            |
| **Make a change and see it instantly**  (any agent)      | Edit any file in `WebSite/site/src/**`        |
| **Stop the background preview server** (Jonathan)        | Double-click `WebSite/preview-stop.bat`       |
| **Ship the current draft to tinyassets.io** (any agent)  | Run `WebSite/ship.ps1` from PowerShell        |

That's the whole loop.

## Lifecycle of `preview.bat` (read once, never think about again)

`preview.bat` is **hidden + persistent + idempotent**:

- **Hidden:** the dev server runs in the background. No terminal window
  for Jonathan to manage.
- **Persistent:** vite stays alive until reboot or until
  `preview-stop.bat`. Reopening the browser tab is instant — no cold
  start every time.
- **Idempotent:** double-click any time. If the server is already
  running, the script just opens the browser tab. If not, it starts
  the server, waits for it to come up (~2s), then opens the tab.

Why not "auto-close when the last tab closes"? Doable but adds
brittleness — tab refresh races, WebSocket lifecycle quirks, custom
vite plugin needed. Vite is genuinely lightweight (~80 MB RAM idle,
near-zero CPU); persistent + a one-click stop is simpler and faster.

## Multi-agent / multi-tab sync — already free

Vite's HMR is a websocket broadcast. **Every** browser tab open to
`http://localhost:5173/` (Jonathan's, my playwright tab, a teammate's,
anyone) is a separate websocket subscriber. When ANY agent saves a
file, vite pushes the patch to ALL connected tabs simultaneously. No
coordination needed.

This means: if multiple Cowork or Claude Code or Codex sessions
iterate on the site in parallel, every tab open anywhere reflects
the latest state in real time.

## Canonical preview URL

```
http://localhost:5173/
```

This is **always** the URL. `preview.bat` enforces port 5173 with
`--strictPort` — so when Jonathan or a chat session says "look at the
preview," there's no ambiguity. If 5173 is taken, vite errors out
loudly instead of silently picking another port. (If that happens, a
previous `preview.bat` is still running — switch to that terminal /
browser tab, or close it to free the port.)

## The happy path (Jonathan should almost never click anything)

Once `preview.bat` has been run once after a fresh boot, the iteration
loop is just talking:

```
Jonathan:  "the hero subline is too long"
Agent:     [edits Hero.svelte]
Jonathan:  [tab updates by itself]   ← this is the default
Jonathan:  "yeah that's better"
```

**No F5. No re-launch. No clicking.** Just talk and look. The browser
tab on `localhost:5173` is wired to vite's HMR websocket — every save
pushes a patch (or a full reload, when HMR can't apply) to the tab in
real time, automatically.

## Three layers of freshness (F5 almost never needed)

The browser tab is fresh because of three layers, each catching what
the previous one missed:

| Layer | What it does                                                   | When it fires                              |
|-------|----------------------------------------------------------------|--------------------------------------------|
| 1. **HMR**       | Vite patches the running module in-place         | Default for component / CSS / route changes |
| 2. **Auto-reload** | Vite triggers full page reload via the HMR socket | When HMR can't apply (e.g., new file added) |
| 3. **Manual F5** | You force a reload                                | Rare — only if layers 1+2 mysteriously fail |

If you ever have to F5, that's a signal the HMR pipeline misfired —
flag it so we can investigate. **The intended state is: edit a file,
tab updates, no input from you.**

## When to use which command

| Situation                                                | What to do                                  |
|----------------------------------------------------------|---------------------------------------------|
| First tab open after a reboot                            | Double-click `preview.bat` once             |
| Edit a file, see the result                              | Nothing — HMR auto-updates the open tab     |
| Open a different route while iterating                   | Click any internal link, or change the URL  |
| Tab looks stale and you don't know why                   | F5 (this should not happen — file a thread) |
| Reopen the site after closing the tab                    | Double-click `preview.bat` (idempotent — won't restart vite, just opens a new tab) |
| Done for the day / want to free port 5173                | Double-click `preview-stop.bat`             |
| Reboot                                                   | Nothing — `preview-stop` happens for free   |

The only time you need to rebuild is for the `ship.ps1` flow (which
clones a fresh main, applies the bundle, pushes — all from a temp
clone, no rebuild on Jonathan's machine).

## How edits flow (under the hood)

1. Any agent edits a file in `WebSite/site/src/**` (or `static/`,
   `lib/content/*.json`, etc.).
2. Vite's file watcher (chokidar) picks up the change in <200ms.
3. Vite tries an HMR patch first. If the module is HMR-friendly
   (most components, CSS, JSON imports), the browser updates the
   relevant component in place — keeps state, no flash, no scroll
   reset.
4. If HMR can't patch (e.g., a new route file appeared), vite emits
   a full-reload event over the websocket. Browser reloads itself.
5. Either way, syntax errors show up as a red overlay in the
   browser (`hmr.overlay: true` in `vite.config.js`) so Jonathan
   sees what broke without checking the terminal.

This means **Claude doesn't need to "rebuild" or "redeploy" to show
Jonathan a change.** Just edit the file. The preview tab reflects it.

## Working with FUSE mounts (Cowork sessions)

When Cowork edits files in `/sessions/.../mnt/WebSite/site/src/...`,
those writes land on the underlying NTFS files at
`C:\Users\Jonathan\Projects\Workflow\WebSite\site\src\...`. Windows
file events fire normally; chokidar (vite's watcher) picks them up;
the browser reloads.

If hot-reload ever feels stuck, the most likely cause is:

- A FUSE-mount truncation (always check the file with `tail` after
  any heredoc write — see `HOOKS_FUSE_QUIRKS.md`).
- A syntax error broke the build. Vite prints the error in the
  terminal AND in an overlay in the browser; check both.

If the build is genuinely stuck, in `WebSite/site/vite.config.js` you
can set `server: { watch: { usePolling: true } }` — but try the
defaults first; polling burns CPU.

## Shipping

When the preview looks right and Jonathan says **"push"** /
**"ship"** / **"deploy"** / **"push the next website version"**:

1. Run `WebSite/ship.ps1` from PowerShell. It clones a fresh `main`
   into `$env:TEMP\wf-ship`, fetches the bundle Cowork just prepared
   (`WebSite/website-ship.bundle`), and pushes the branch to GitHub.
2. Fast-forward main: `git push origin <branch>:main` from inside
   the temp clone (or open the PR URL the script prints and merge).
3. Watch the `deploy-site` workflow on GitHub Actions go green.
4. Run a playwright verify against `https://tinyassets.io/` — the
   pass criteria are pinned in the Claude Code shipping prompt
   that lives at the bottom of `WebSite/DEPLOY.md`.

If a Cowork session is preparing the bundle, it'll have written the
fresh `website-ship.bundle` to the same folder by the time it tells
Jonathan to ship.

## "Same thing on each new redesign"

The point of this convention: every chat session, every redesign,
every aesthetic iteration — Jonathan can keep one browser tab open
at `localhost:5173/`, an agent can edit files, and the tab updates.
No port-hunting, no terminal-reading, no "what address again?" loop.

Future sessions: when Jonathan asks for a design change, just edit
the file. He'll see it in the tab he already has open. If you want
to preview a specific route, link him `http://localhost:5173/<path>`
and he can click.

## Why port 5173 (and not something else)

It's vite's default. Anyone on Vite knows it. Standard convention is
worth more than novelty. Don't change it without a strong reason.

## Files involved

| File                          | What it does                                          |
|-------------------------------|-------------------------------------------------------|
| `WebSite/preview.bat`         | Hidden + persistent + idempotent launcher. Starts vite in background, opens browser tab. |
| `WebSite/preview-stop.bat`    | Kills the background vite server (frees port 5173).   |
| `WebSite/site/`               | The SvelteKit app. Vite watches everything under here.   |
| `WebSite/site/vite.config.js` | Vite settings. Includes the `/mcp-live` proxy for live MCP fetches in dev. |
| `WebSite/ship.ps1`            | Push the prepared bundle to GitHub.                   |
| `WebSite/website-ship.bundle` | Generated by Cowork. Carries the next deploy.         |
| `WebSite/DEPLOY.md`           | Deploy-day playbook + Claude Code verify prompt.      |
| `WebSite/HOOKS_FUSE_QUIRKS.md`| Why heredoc, not Edit/Write, on Cowork's FUSE mount.  |
