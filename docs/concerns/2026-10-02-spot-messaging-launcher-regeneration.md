# Spot messaging launcher guard is not persistent

Observed 2026-10-02 on Windows: the desktop app regenerates its exported `codex-app-tools` launcher during Local Work executor registration/restart, overwriting the missing-only `SystemRoot` guard. Earlier real Spot-to-desktop message delivery was verified, but persistence across regeneration remains unresolved.

The browser issue is resolved separately. Actual Spot task `01a0fe3b-bc51-749b-bbe6-1a433f8f7020` successfully called `spot_browser.js` for `cua.getState()` and `cua.listTabs`, reading the connected Chrome TinyAssets tab title and URL. Missing Windows temp environment caused the runtime to create its temporary directory under protected `C:\Windows`; the persistent launcher now supplies process-only TEMP/TMP under the user's LocalApplicationData/Temp/CodexSpotBrowser. No permission or ACL changes.

Evidence: `C:/Users/Jonathan/Documents/Codex/2026-10-02/browser-access-repair-01a0fdcf/`, especially `browser-repair-verified.md`, `spot-browser-live-success.json`, `spot-native-temp-error.txt`, and `messaging-retry-received.json`. Verified through the official app-tools MCP connector, command `python -u .../app-tools-probe.py .../spot-child-read.json`, 2026-10-02, Windows.

Latest user request was browser repair; this separate finding does not block its verified completion. No TinyAssets runtime or public surface changes. Claude independent review was unavailable because its weekly quota was exhausted.
