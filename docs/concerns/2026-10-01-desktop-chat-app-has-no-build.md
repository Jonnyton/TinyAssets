---
severity: P1
title: Nothing builds or delivers the Electron desktop chat app, so the installed one broke when /mcp/app retired
filed: '2026-10-01'
summary: '`desktop-release.yml` builds the PyInstaller server tray, not `desktop-app/` (Electron). No workflow builds the chat app, so installed copies keep the URL they were built with. The founder''s 2026-08-23 build loaded /mcp/app and has shown a raw `{"error":"authentication_required"}` since the 2026-09-30 retirement (#4112).'
---

# Nothing builds or delivers the Electron desktop chat app

**Filed:** 2026-10-01. **Verified:** same day, on the founder's Windows machine.

## What happened

- The founder's desktop shortcut launched `C:/Users/Jonathan/TinyAssets-Desktop/TinyAssets.exe`, an Electron build from 2026-08-23. That build loads `https://tinyassets.io/mcp/app`.
- #4112 retired `/mcp/app` with no redirect. An anonymous request to it now returns `401` with `{"error":"authentication_required"}` as JSON (checked with `curl -s https://tinyassets.io/mcp/app`). The desktop window rendered that JSON and nothing else.
- `desktop-app/config.js` on main already says `https://tinyassets.io/app`. No installed copy picks that up, because:
  - `MSYS_NO_PATHCONV=1 git grep -l desktop-app origin/main -- .github/workflows` finds nothing, so no workflow builds `desktop-app/`.
  - `.github/workflows/desktop-release.yml` runs PyInstaller and Inno Setup over `tinyassets/desktop/packaged_entrypoint.py`. That is the Tier-2 **server tray**, but its artifact is named `TinyAssetsSetup-*.exe`, the same name the Electron NSIS installer used. Installing it puts a `TinyAssets.lnk` on the desktop and in Startup that launches the tray, which exits with "unknown packaged runtime arguments" when given a flag.
- The Electron shell has no auto-update channel. Every URL or shell change therefore needs a manual rebuild on each machine.

## What was done (2026-10-01)

- Built `desktop-app/` from origin/main `8299af6f` locally with `npx electron-builder --win dir`. The unpacked build is now at `C:/Users/Jonathan/TinyAssets-Desktop`, and the old build was kept as `TinyAssets-Desktop.bak-20260823`.
- The new build loads `/app` and shows Sign in. The cookie path changed, so the founder has to sign in once.
- The test shortcut now passes `--attach=9223`. #2501 replaced the raw `--remote-debugging-port` with an `--attach` opt-in.

## What resolves this

- A workflow that builds `desktop-app/` and publishes an installer with a name distinct from the server tray's.
- Electron auto-update, or the shell loading only the live URL with nothing baked in that can go stale. That second option already holds: the stale part was the URL constant itself.
- Rename the tray artifact so the two `TinyAssetsSetup` installers can't be confused.
