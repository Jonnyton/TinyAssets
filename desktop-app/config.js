// Single source of truth for the desktop shell's target + navigation policy.
// Mirrors mobile/capacitor.config.json (server.url + allowNavigation) so the
// desktop client points at the SAME live SPA the Android app wraps.
'use strict';

// The live onboarding SPA — same origin as the /mcp API and the WorkOS AuthKit
// sign-in, so the OAuth round-trip stays inside the window with no deep-linking.
// Overridable for local daemon testing, e.g. TINYASSETS_APP_URL=http://127.0.0.1:8001/mcp/app
const APP_URL = process.env.TINYASSETS_APP_URL || 'https://tinyassets.io/mcp/app';

// Hosts the window may navigate to in-app. Anything else opens in the system
// browser. tinyassets.io serves the SPA + /mcp; *.authkit.app is WorkOS's hosted
// sign-in page. The identity-provider domains below MUST stay in-window too: the
// WorkOS "Continue with Google/…" step redirects the top-level frame to the IDP,
// and if the IDP host isn't allow-listed the nav handler kicks it to the system
// browser mid-redirect — which mangles the OAuth request (Google 500) and lands
// the session in the wrong browser. Keeping the IDP in-window lets the full
// round-trip complete and set the app's own cookie. Mirrors the Capacitor
// allowNavigation list + the IDPs WorkOS AuthKit federates to.
const ALLOWED_HOSTS = [
  'tinyassets.io',
  'authkit.app', // matched as a suffix, covers *.authkit.app
  // OAuth identity providers (federated by WorkOS AuthKit):
  'accounts.google.com',
  'accounts.youtube.com', // Google OAuth CheckConnection iframe/redirect
  'gstatic.com', // Google sign-in static assets
  'googleusercontent.com', // Google avatar/asset host
  'login.microsoftonline.com',
  'login.live.com',
  'github.com',
  'appleid.apple.com',
];

const BACKGROUND_COLOR = '#0b0b0f';

module.exports = { APP_URL, ALLOWED_HOSTS, BACKGROUND_COLOR };
