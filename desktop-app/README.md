# TinyAssets — Desktop app (Electron)

A native desktop app that wraps the live TinyAssets web app. It is a thin,
maintainable **Electron** shell whose window loads `https://tinyassets.io/mcp/app`
(configured in `config.js` → `APP_URL`) — the **same SPA the Android app wraps**
(`mobile/`). Because that page, the `/mcp` API, and the WorkOS AuthKit sign-in all
live on the same origin (`tinyassets.io`), the OAuth round-trip stays inside the
window and Just Works — no deep-link plumbing. Web-app changes ship instantly to
all surfaces (no rebuild); the desktop build only changes when the native shell,
icon, or config change.

> **Why this is automatically synced with the phone + connector:** the universe
> and the cross-turn conversation memory are keyed on the *authenticated WorkOS
> principal*, not the device — see
> [`docs/design-notes/2026-08-22-desktop-app-client-surface.md`](../docs/design-notes/2026-08-22-desktop-app-client-surface.md)
> for the exact code cites. Sign in as the same user on desktop, phone, and the
> Claude.ai connector and you are in one universe and one continuous conversation
> thread. The desktop client builds nothing to achieve that.

> **Not the tray daemon.** This is a Tier-1 *client* of the hosted service.
> `tinyassets/desktop/` (tray, launcher, updater) is the separate Tier-2 *host*
> daemon that runs a TinyAssets server on a machine — don't confuse them.

## Architecture

App shell = Electron main (`src/main.js`) + a minimal preload (`src/preload.js`).
The main process opens a hardened `BrowserWindow` (context isolation on, no Node
in the renderer, OS sandbox on), loads the remote SPA, keeps the app's own
origins in-window (so the same-origin WorkOS OAuth works), and sends any external
link to the system browser. `src/loading.html` is a local splash/offline
fallback. iPhone is a later `npx cap add ios` on the existing `mobile/` project —
no new client codebase.

## Prerequisites

- **Node.js 18+** and npm.
- For packaging installers: platform toolchains that `electron-builder` needs
  (Windows: nothing extra for NSIS; macOS: Xcode CLT for `.dmg` + notarization;
  Linux: standard build tools for AppImage).

## Run it (development)

```bash
cd desktop-app
npm install
npm start
```

The window opens on the loading splash, then loads `https://tinyassets.io/mcp/app`.
Verify the full loop: **sign in (WorkOS)** → **connect your AI subscription** →
**chat with your universe**. To point at a local daemon instead of production:

```bash
TINYASSETS_APP_URL=http://127.0.0.1:8001/mcp/app npm start
```

(The daemon must have `TINYASSETS_ONBOARDING_APP` truthy for `/mcp/app` to serve.)

## Session persistence

Electron's default session partition is *persistent*, so the WorkOS refresh-token
cookie (`ta_rt`, HttpOnly, scoped to `/mcp/app/token`, 7-day max-age) survives
app restarts. On relaunch the SPA silently renews via `grant_type=refresh_token`,
so the user stays signed in — the same "survives app restarts and token renewals"
behavior the phone and web get.

## Build installers (later — packaging/signing is a follow-up)

```bash
npm run dist   # electron-builder → dist/ (NSIS on Windows, dmg on macOS, AppImage on Linux)
```

This produces **unsigned** artifacts. Shipping to users needs code-signing
identities (host-owned, like the Android keystore):

- **Windows:** an EV/OV code-signing certificate; wire into `electron-builder`
  `win.certificateFile`/`certificatePassword` (or Azure Trusted Signing).
- **macOS:** an Apple Developer ID ($99/yr) + notarization
  (`electron-builder` `mac.notarize`).
- **Auto-update:** add `electron-updater` + a release feed (GitHub Releases or an
  S3/R2 bucket), analogous to the tray daemon's own updater
  (`tinyassets/desktop/updater.py`).

## Follow-ups (tracked in the design note, not MVP-blocking)

1. **OpenAI one-tap loopback.** The SPA's OpenAI connect path uses a loopback
   redirect `http://127.0.0.1:<port>/auth/callback`
   (`tinyassets/onboarding/openai_device.py` → `valid_loopback_redirect`). A
   webview can't listen on a loopback port itself; the Android app runs a native
   `LocalCallbackService`. On desktop, run a short-lived Node `http` listener in
   the Electron main process, open the system browser to OpenAI's authorize URL,
   catch the `?code=`, and hand it back to the SPA (via a `contextBridge` method
   in `preload.js`) which POSTs it to `/mcp/app/openai/exchange`. Simpler than
   Android — no background-freeze problem. **WorkOS sign-in + the Claude/Codex
   browser deposit form already cover the MVP loop, so this is deferred.**
2. **App icon / splash** — add `resources/icon.png` and wire `electron-builder`
   `icon`.
3. **Packaging + signing + auto-update** (above).
4. **OpenSpec change** to front the productionization phase (the thin shell
   reuses the already-shipped `onboarding-web-app` contract, so this scaffold
   needs none; packaging/signing/loopback do).
