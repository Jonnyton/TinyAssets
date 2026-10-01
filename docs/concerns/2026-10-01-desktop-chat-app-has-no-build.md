---
severity: P2
title: The Electron desktop chat app now builds in CI, but installed copies still never update themselves
filed: '2026-10-01'
summary: '`desktop-chat-app.yml` builds `desktop-app/` into an unsigned CI artifact, and the server tray is renamed `TinyAssets Server` so the two installers no longer collide. No installed copy updates itself yet: there is no release feed, no electron-updater, and no signing identity, so a shell change still needs a manual reinstall on every machine.'
---

# The desktop chat app builds, but does not update itself

**Filed:** 2026-10-01, P1: nothing built `desktop-app/`, and the founder's 2026-08-23 build rendered a raw `{"error":"authentication_required"}` after #4112 retired `/mcp/app`.
**Re-verified:** 2026-10-01, P2 after the build PR described below.

## What is resolved

- `.github/workflows/desktop-chat-app.yml` builds `desktop-app/` with electron-builder (`--win nsis zip --x64 --publish never`). It runs on main pushes touching `desktop-app/**` and on dispatch. It uploads `desktop-chat-windows-x86_64`, which holds `TinyAssetsChatSetup-<v>-x64.exe` and `TinyAssetsChat-<v>-x64-win.zip`. The build fails if the packaged `config.js` does not load `https://tinyassets.io/app`, or if it mentions `/mcp/app`.
- The PyInstaller tray (`packaging/windows/TinyAssets.iss`) is now `TinyAssets Server`:
  - installer `TinyAssetsServerSetup-*`;
  - install dir `%LOCALAPPDATA%\Programs\TinyAssetsServer`;
  - shortcuts `TinyAssets Server`.

  Before this, both installers wrote `%LOCALAPPDATA%\Programs\TinyAssets\TinyAssets.exe` and a `TinyAssets` shortcut, so installing one replaced the other. `tests/desktop_install/test_two_windows_installers.py` pins the separation.

## What remains

- **Auto-update.** The chat app has no update channel, so installed copies keep whatever shell they were built with. The web app itself is always live, because the shell loads `https://tinyassets.io/app`; only changes to the shell, its config, or its navigation allow-list are affected. The cheap shape follows the `android-latest` precedent in `android-build.yml`:
  1. Stamp the version per build (`0.1.<run_number>`).
  2. Add a small publish job with `contents: write` that uploads the installer, `latest.yml` and the blockmap to a rolling prerelease such as `desktop-chat-latest`.
  3. Add `electron-updater` with a generic provider at `https://github.com/Jonnyton/TinyAssets/releases/download/desktop-chat-latest/`, and call `autoUpdater.checkForUpdatesAndNotify()` from `src/main.js`.

  It was left out of the build PR because the app would then install binaries nobody signed. That is a release-trust decision as much as a code change: electron-updater skips publisher verification when there is no `publisherName`.
- **Signing.** There is no Windows code-signing identity for the chat app, so SmartScreen warns on every install. This is the same host-owned gap as the tray's `sign-and-verify` job.
- **Hand-installed copies.** The founder's machine has an unpacked build at `C:/Users/Jonathan/TinyAssets-Desktop`. It may also have an earlier tray CI install in `Programs\TinyAssets` with `TinyAssets.lnk` shortcuts. A later tray install upgrades that one in place: same `AppId`, and Inno reuses the previous directory. It does not remove the old `TinyAssets.lnk` shortcuts. No tray release was ever published (`gh release list` shows only the Android ones), so no migration code was added.
