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
// sign-in page. Mirrors the Capacitor allowNavigation list.
const ALLOWED_HOSTS = [
  'tinyassets.io',
  'authkit.app', // matched as a suffix, covers *.authkit.app
];

const BACKGROUND_COLOR = '#0b0b0f';

module.exports = { APP_URL, ALLOWED_HOSTS, BACKGROUND_COLOR };
