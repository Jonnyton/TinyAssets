// Single source of truth for the desktop shell's target + navigation policy.
// Mirrors mobile/capacitor.config.json (server.url + allowNavigation) so the
// desktop client points at the SAME live SPA the Android app wraps.
'use strict';

// The live onboarding SPA — same origin as the /mcp API and the WorkOS AuthKit
// sign-in, so the OAuth round-trip stays inside the window with no deep-linking.
const PROD_APP_URL = 'https://tinyassets.io/mcp/app';

// Development-only override (Codex 2026-08-23 #6): a packaged build IGNORES the
// env override entirely — a launcher must never be able to start the signed
// executable pointed at an attacker page. In an UNPACKAGED dev checkout we accept
// ONLY an explicit loopback URL, validated by the caller before the first load.
function resolveAppUrl(isPackaged) {
  if (isPackaged) return PROD_APP_URL;
  const override = (process.env.TINYASSETS_APP_URL || '').trim();
  if (!override) return PROD_APP_URL;
  try {
    const u = new URL(override);
    const isLoopback =
      u.protocol === 'http:' &&
      (u.hostname === '127.0.0.1' || u.hostname === 'localhost');
    if (isLoopback) return override;
  } catch {
    /* fall through to prod */
  }
  return PROD_APP_URL;
}

// Origins the WINDOW may navigate to in-app. Everything else opens in the system
// browser (and only if it is itself a safe https URL — see isSafeExternal). This
// is an EXACT-ORIGIN allow-list (Codex 2026-08-23 #2), not a loose hostname
// contains/suffix check: scheme MUST be https and the port MUST be the default,
// so http://, alternate-port, and userinfo@ tricks all fail closed.
//
// EXACT_HOSTS: matched by full hostname equality only (no subdomain widening).
//   tinyassets.io          — the SPA + /mcp API + same-origin token exchange.
//   IDP sign-in hosts       — WorkOS AuthKit federates the top-level frame to
//                             these during "Continue with …"; they must complete
//                             in-window for the OAuth round-trip to set the cookie.
// gstatic.com / googleusercontent.com were REMOVED: they are subresource hosts
// (not top-level navigations), so allow-listing them only widened what page may
// REPLACE the app — pure downside.
const EXACT_HOSTS = [
  'tinyassets.io',
  'accounts.google.com',
  'login.microsoftonline.com',
  'login.live.com',
  'github.com',
  'appleid.apple.com',
];

// WorkOS AuthKit tenant host. The exact production tenant domain is an env-only
// deploy secret (WORKOS_AUTHKIT_DOMAIN, e.g. inventive-van-62-*.authkit.app) and
// is not knowable from this repo, so we accept the authkit.app suffix rather than
// risk breaking sign-in by pinning the wrong tenant. This is the ONE residual
// Codex #2 flagged (a different WorkOS tenant could render in-window) — bounded:
// it requires the trusted SPA itself to redirect the top frame to a foreign
// tenant, which it never does. Still https + default-port gated below.
// TODO(pin-authkit): replace with the exact prod tenant host once confirmed.
const AUTHKIT_SUFFIX = 'authkit.app';

const BACKGROUND_COLOR = '#14140f';

// A URL is navigable IN-WINDOW iff: https, default port, and the host is an exact
// allow-listed host or an *.authkit.app / authkit.app tenant.
function isAllowedNavigation(urlString) {
  let u;
  try {
    u = new URL(urlString);
  } catch {
    return false;
  }
  if (u.protocol !== 'https:') return false;
  if (u.port !== '') return false; // default port only
  const host = u.hostname.toLowerCase();
  if (EXACT_HOSTS.includes(host)) return true;
  if (host === AUTHKIT_SUFFIX || host.endsWith('.' + AUTHKIT_SUFFIX)) return true;
  return false;
}

// A URL is safe to hand to the OS (shell.openExternal) iff it is https. Custom
// schemes (file:, javascript:, data:, smb:, app-protocol:, …) are DENIED —
// openExternal on untrusted input is an RCE vector (Codex 2026-08-23 #1).
function isSafeExternal(urlString) {
  try {
    return new URL(urlString).protocol === 'https:';
  } catch {
    return false;
  }
}

module.exports = {
  PROD_APP_URL,
  resolveAppUrl,
  EXACT_HOSTS,
  AUTHKIT_SUFFIX,
  BACKGROUND_COLOR,
  isAllowedNavigation,
  isSafeExternal,
};
