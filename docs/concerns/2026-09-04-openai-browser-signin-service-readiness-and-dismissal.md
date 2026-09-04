# OpenAI browser sign-in: no service-readiness confirmation, and dismissing the tab doesn't stop the flow

**Filed:** 2026-09-04, during cross-family (Codex) review of the POST_NOTIFICATIONS
permission fix on `codex/android-store-release`. Both gaps are pre-existing —
the permission-fix diff only wraps `LocalCallbackPlugin.start()` with a
permission-request step before an unmodified `startListener()`/`keepAlive()`.

## Source (verbatim, from the Codex review)

> Service readiness is not guaranteed. `startListener()`
> (`mobile/native/android/LocalCallbackPlugin.java:113`) calls `keepAlive(true)`
> and then resolves unconditionally at line 117, while service-start failures
> are swallowed at line 346. The caller opens browser auth immediately after
> `LC.start()` resolves at `tinyassets/onboarding/app.html:1785` and `:1795`.
> Android documents that `startForegroundService()` only initiates creation;
> the service subsequently has five seconds to promote itself. Thus the
> browser can open before foreground promotion — or despite startup failure.
>
> Closing the Custom Tab does not stop the flow/service. Capacitor exposes
> `browserFinished` specifically for user closure
> (`mobile/node_modules/@capacitor/browser/README.md:78`), but the flow
> registers no such listener and relies on the ten-minute timeout at
> `app.html:1802`. A user-dismissed auth tab can therefore leave the
> notification visible for up to ten minutes.

## Why not fixed here

`keepAlive()`'s `catch (Throwable ignored)` around `startForegroundService()`
is a deliberate "best effort" (see the comment at
`LocalCallbackPlugin.java` above `keepAlive`): Android gives no synchronous
signal that a foreground service actually promoted — `onStartCommand` runs on
the same main-thread queue, asynchronously, after the plugin call has already
returned. Closing that race properly needs the service to report promotion
back to the plugin (a static callback or similar) and `start()` to wait on it
with a timeout — a real design change, not a one-line fix, and out of scope
for a permission-only diff. `browserFinished` wiring is a smaller, separate
change to `connectOpenAIBrowser()` in `app.html`.

## Severity

Both are pre-existing, not introduced or worsened by the permission fix.
Finding 1 requires either a missing-permission or background-start-restricted
service start immediately after direct user interaction (foreground context)
— low probability. Finding 2 is a UX/battery nuisance (a stale "Finishing
your sign-in…" notification for up to 10 minutes after the user backs out),
not a correctness or security issue.
