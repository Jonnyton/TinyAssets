// TinyAssets desktop shell (Electron).
//
// A thin native window over the live SPA at https://tinyassets.io/mcp/app — the
// SAME page the Android Capacitor app wraps (mobile/capacitor.config.json). No
// second chat UI: product logic (WorkOS sign-in, connect-subscription, chat)
// lives in the SPA and is reused verbatim, so every surface stays identical and
// synced. Continuity ("the phone knows what you said on the computer") is a
// backend property — the universe + cross-turn memory are keyed on the verified
// WorkOS principal (tinyassets/universe_server.py converse: memory_session =
// f"principal:{current_actor_id()}"), so signing in the same user here lands in
// the same universe + same conversation thread. See
// docs/design-notes/2026-08-22-desktop-app-client-surface.md.
'use strict';

const { app, BrowserWindow, shell } = require('electron');
const path = require('node:path');
const { APP_URL, ALLOWED_HOSTS, BACKGROUND_COLOR } = require('../config');

// Single-instance: a second launch focuses the existing window rather than
// opening a rival session that would fight over the same persistent cookie jar.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

let mainWindow = null;

function isAllowedHost(urlString) {
  let host;
  try {
    host = new URL(urlString).hostname.toLowerCase();
  } catch {
    return false;
  }
  return ALLOWED_HOSTS.some(
    (allowed) => host === allowed || host.endsWith('.' + allowed),
  );
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 780,
    minWidth: 480,
    minHeight: 600,
    backgroundColor: BACKGROUND_COLOR,
    title: 'TinyAssets',
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

  // Local fallback while the remote SPA loads, or when offline. The real app is
  // then loaded over the network; on failure we fall back to this page (mirrors
  // mobile/www/index.html).
  const loadingPage = path.join(__dirname, 'loading.html');

  function loadApp() {
    mainWindow.loadURL(APP_URL).catch(() => {
      mainWindow.loadFile(loadingPage, { query: { offline: '1' } });
    });
  }

  // Show the loading page first for an instant window, then swap to the SPA.
  mainWindow.loadFile(loadingPage).finally(loadApp);

  // If the remote load fails mid-flight (offline, DNS), show the fallback and
  // keep retrying is left to the user reopening — matches the mobile shell.
  mainWindow.webContents.on('did-fail-load', (_e, errorCode, _desc, validatedURL) => {
    // -3 is ERR_ABORTED (normal during redirects); ignore it.
    if (errorCode === -3) return;
    if (validatedURL && validatedURL.startsWith('file://')) return;
    mainWindow.loadFile(loadingPage, { query: { offline: '1' } });
  });

  // Navigation policy: keep the app's own origins in-window (the WorkOS OAuth
  // round-trip must stay in-window so the same-origin token exchange + cookie
  // work); send everything else to the system browser.
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('file://') && !isAllowedHost(url)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedHost(url)) {
      return { action: 'allow' };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  // Standard desktop convention: keep the app alive on macOS, quit elsewhere.
  if (process.platform !== 'darwin') app.quit();
});
