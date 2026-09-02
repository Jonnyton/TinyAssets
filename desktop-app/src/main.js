// TinyAssets desktop shell (Electron).
//
// A thin native window over the live SPA at https://tinyassets.io/mcp/app — the
// SAME page the Android Capacitor app wraps (mobile/capacitor.config.json). No
// second chat UI: product logic (WorkOS sign-in, connect-subscription, chat)
// lives in the SPA and is reused verbatim, so every surface stays identical and
// synced. Continuity ("the phone knows what you said on the computer") is a
// backend property — the universe + cross-turn memory are keyed on the verified
// WorkOS principal, so signing in the same user here lands in the same universe.
// See docs/design-notes/2026-08-22-desktop-app-client-surface.md.
//
// Security posture (Codex adversarial review 2026-08-23): the window renders
// REMOTE, continuously-changing code, so the shell treats the page as untrusted:
//   - hardened webPreferences (contextIsolation, no nodeIntegration, sandbox);
//   - an EXACT-origin https navigation allow-list applied to EVERY WebContents,
//     covering will-navigate, will-frame-navigate, will-redirect, and popups;
//   - shell.openExternal only for https URLs (never file:/custom schemes → RCE);
//   - all web permissions (camera/mic/geo/…) denied by default;
//   - the dev URL override is ignored in a packaged build.
'use strict';

const { app, BrowserWindow, session, shell } = require('electron');
const path = require('node:path');
const {
  resolveAppUrl,
  BACKGROUND_COLOR,
  isAllowedNavigation,
  isSafeExternal,
} = require('../config');

// ── Attachable test mode (opt-in, OFF by default) ───────────────────────────
// So a tester (or an agent) can READ and DRIVE the desktop app for QA, an
// EXPLICIT opt-in exposes Electron's remote-debugging endpoint. It is enabled
// ONLY when `--attach[=port]` is on the command line or TINYASSETS_DEVTOOLS is
// set — a normal packaged launch never opens it, so the hardened posture holds
// in production. The endpoint is bound to LOOPBACK only, and the test instance
// uses a SEPARATE user-data profile so it can run alongside the real session
// without fighting over its cookie jar. Both switches must be appended before
// app 'ready'.
function resolveAttachPort() {
  const fromEnv = (process.env.TINYASSETS_DEVTOOLS || '').trim();
  const argMatch = process.argv.find((a) => a === '--attach' || a.startsWith('--attach='));
  if (!fromEnv && !argMatch) return null;
  let raw = '';
  if (argMatch && argMatch.includes('=')) raw = argMatch.split('=')[1];
  else if (fromEnv && fromEnv !== '1') raw = fromEnv;
  const port = raw ? parseInt(raw, 10) : 9222;
  return Number.isInteger(port) && port > 0 && port < 65536 ? port : 9222;
}
const ATTACH_PORT = resolveAttachPort();
if (ATTACH_PORT !== null) {
  // Loopback only — never expose the debug endpoint off-machine. Same user-data
  // profile as a normal launch, so the tester sees the REAL signed-in session
  // (close the normal app first, then reopen via the attach shortcut).
  app.commandLine.appendSwitch('remote-debugging-port', String(ATTACH_PORT));
  app.commandLine.appendSwitch('remote-debugging-address', '127.0.0.1');
}

// Single-instance: a second launch focuses the existing window rather than
// opening a rival session that would fight over the same persistent cookie jar.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

// Resolved once, before any load. A packaged build always uses the prod URL;
// only an unpackaged dev checkout may point at an explicit loopback (config.js).
const APP_URL = resolveAppUrl(app.isPackaged);

let mainWindow = null;

// Route a blocked navigation target to the system browser — but ONLY if the URL
// itself is safe to hand to the OS (https). file:/javascript:/data:/custom
// schemes are dropped silently (openExternal on untrusted input is an RCE vector).
function openExternalIfSafe(url) {
  if (isSafeExternal(url)) {
    shell.openExternal(url).catch(() => {});
  }
}

// One navigation policy for EVERY WebContents in the app (main window, OAuth
// popups, iframes), installed via web-contents-created so nothing escapes it.
function applyNavigationPolicy(contents) {
  // Top-frame + subframe navigations, and server redirects, must all land on an
  // allow-listed https origin; anything else is cancelled and (if safe) handed
  // to the system browser. Covering will-frame-navigate stops an iframe from
  // rendering a full-window phishing form inside the URL-less trusted window;
  // covering will-redirect stops an allowed OAuth endpoint 302-ing to an attacker.
  const guard = (event, url) => {
    if (!isAllowedNavigation(url)) {
      event.preventDefault();
      openExternalIfSafe(url);
    }
  };
  contents.on('will-navigate', guard);
  contents.on('will-redirect', guard);
  // will-frame-navigate (Electron ≥ 22) fires for subframe navigations too.
  contents.on('will-frame-navigate', (event) => {
    if (!isAllowedNavigation(event.url)) {
      event.preventDefault();
      openExternalIfSafe(event.url);
    }
  });
  // Deny ALL new windows. An allowed https target opens in the system browser;
  // nothing gets a fresh, policy-less WebContents inside the app.
  contents.setWindowOpenHandler(({ url }) => {
    openExternalIfSafe(url);
    return { action: 'deny' };
  });
}

// Deny every web permission (camera, mic, geolocation, notifications, pointer
// lock, …). This shell needs none; a compromised remote page must not be able to
// request them under the TinyAssets application identity.
function lockDownPermissions(ses) {
  ses.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  ses.setPermissionCheckHandler(() => false);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 780,
    minWidth: 480,
    minHeight: 600,
    backgroundColor: BACKGROUND_COLOR,
    title: 'TinyAssets',
    // The TinyAssets mark (build/icon.png, exported by WebSite/brand/render_marks.py).
    // Packaged Windows/macOS builds take the icon from build/icon.{ico,icns} via
    // electron-builder; this covers Linux and `npm start`.
    icon: path.join(__dirname, '..', 'build', 'icon.png'),
    autoHideMenuBar: true,
    webPreferences: {
      // Hardened defaults: the window renders a remote page, so the renderer
      // gets no Node, an isolated context, and the OS sandbox. The preload
      // exposes nothing privileged.
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  const loadingPage = path.join(__dirname, 'loading.html');

  function loadApp() {
    // Guard: the window can be closed/destroyed before this async step runs
    // (e.g. a fast quit), which otherwise throws "Object has been destroyed".
    if (!mainWindow || mainWindow.isDestroyed()) return;
    mainWindow.loadURL(APP_URL).catch(() => {
      if (!mainWindow || mainWindow.isDestroyed()) return;
      mainWindow.loadFile(loadingPage, { query: { offline: '1' } });
    });
  }

  // Show the loading page first for an instant window, then swap to the SPA.
  mainWindow.loadFile(loadingPage).finally(loadApp);

  // Fall back to the offline page only when the MAIN frame fails to load a
  // remote URL — a failing OAuth/helper IFRAME (or a hostile embedded frame
  // loading a dead URL) must not blow away the whole signed-in SPA.
  mainWindow.webContents.on(
    'did-fail-load',
    (_e, errorCode, _desc, validatedURL, isMainFrame) => {
      if (!isMainFrame) return;
      if (errorCode === -3) return; // ERR_ABORTED — normal during redirects
      if (validatedURL && validatedURL.startsWith('file://')) return;
      if (!mainWindow || mainWindow.isDestroyed()) return;
      mainWindow.loadFile(loadingPage, { query: { offline: '1' } });
    },
  );

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.on('web-contents-created', (_e, contents) => {
  applyNavigationPolicy(contents);
});

app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(() => {
  lockDownPermissions(session.defaultSession);
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  // Standard desktop convention: keep the app alive on macOS, quit elsewhere.
  if (process.platform !== 'darwin') app.quit();
});
