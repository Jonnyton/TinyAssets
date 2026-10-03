# Spot native Computer Use connection unavailable

Observed 2026-10-02 on Jonathan's Windows desktop during the request to have
Spot send `hi` in the already-open TinyAssets desktop app. Spot task
`01a0fe62-a519-743c-b845-472c05d800fa` exposed only browser CUA controls and
reported no callable `node_repl` runtime. Its `cua_repl` initialization failed
with `connection closed: initialize response`.

Independent local check in the repair thread: the documented
`mcp__node_repl__js` initialization importing `@oai/sky` succeeds, but
`sky.list_apps()` fails with `Computer Use native pipe is unavailable: failed
to connect native pipe: The system cannot find the file specified. (os error
2)`. Resetting the JavaScript kernel and retrying initialization/listing
produces the same error. App logs report its native pipe startup ready, and
the named pipe exists; the cause of the runtime connection mismatch is not
yet established. No custom helper was spawned, no native protocol client was
built, and no permission configuration was changed.

The user's debug-mode clarification exposed an independent supported route
to the requested desktop UI: TinyAssets.exe runs with `--attach=9223` and
`GET http://127.0.0.1:9223/json/list` returns the actual desktop renderer at
`https://tinyassets.io/app`, target `210F85C488B282435CC18C58AD0A7E01`, and
its `/app/ui-frame` iframe. Python Playwright is installed. This route has
been used successfully by Spot for the authorized desktop greeting at 14:02
PDT. The app replied `Hey, I’m here.` Independent read-only screenshot/text
verification confirmed both new messages in the same live desktop window.
This achieves the requested desktop greeting, but does not establish recovery
of generic native Computer Use. Detailed proof:
`C:/Users/Jonathan/Documents/Codex/2026-10-02/browser-access-repair-01a0fdcf/desktop-repair-verified.md`.

Evidence and official app-tools transcript requests are under
`C:/Users/Jonathan/Documents/Codex/2026-10-02/browser-access-repair-01a0fdcf/`:
`spot-native-task-read.json`, `spot-native-root-diagnose.json`, and
`spot-desktop-debug-route.json`. Verification environment: Windows,
2026-10-02; supported node_repl calls above and PowerShell
`Invoke-RestMethod -Uri http://127.0.0.1:9223/json/list`.

Follow-up: diagnose runtime binding and capability registration without
altering approval policy or substituting a native protocol client.
