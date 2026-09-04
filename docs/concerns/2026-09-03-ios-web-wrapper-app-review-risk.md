# iOS shell risks App Review minimum-functionality rejection

**Filed:** 2026-09-03
**Verified:** 2026-09-03, Windows checkout plus Apple's live App Review Guidelines
**Severity:** P2

## Source (verbatim)

> “Your app should include features, content, and UI that elevate it beyond a
> repackaged website.”

Apple App Review Guidelines §4.2, checked 2026-09-03:
https://developer.apple.com/app-store/review/guidelines/#minimum-functionality

## Re-verification and scope

`mobile/capacitor.config.json` sets the installed client to load
`https://tinyassets.io/mcp/app` through Capacitor's `server.url`.
`mobile/www/index.html` is an offline/loading fallback rather than a functional
offline client. The iOS build adds real native packaging, artwork, safe-area
behavior, and a native OAuth return, but the primary product UI and content are
the same remotely served client as the web and desktop surfaces.

This does not prove rejection: the installed app provides substantive persistent
agent utility, file selection, account controls, and continuity across devices.
It does mean clean compilation, TestFlight success, and candid review notes do not
by themselves close Guideline 4.2. Apple may decide that the binary remains a
repackaged website.

Before App Review submission, make an explicit product decision between:

1. submit the current shell with honest review notes and accept the rejection
   risk; or
2. add and prove a meaningful iPhone-native interaction that improves a common
   task rather than decorating the wrapper.

Any implementation based on this research needs the required opposite-provider
review before it is built. Do not add portal capabilities, entitlements, or
credentials merely to manufacture a native-looking checkbox.
