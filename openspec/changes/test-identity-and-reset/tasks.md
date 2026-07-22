# Tasks — repeatable scoped reset and multi-user testing

## 1. Scoped reset
- [x] 1.1 Reset the state of a single identity (universes, home binding, ACL grants) by principal
- [x] 1.2 Idempotent: running twice equals running once; running against unknown identity is a no-op
- [x] 1.3 Prove isolation: a second identity's universes, commons, run history and wiki are untouched
- [x] 1.4 Probe proven RED without the scoping (i.e. a bug that widens it to global must fail a test)

## 2. Multiple test identities
- [x] 2.1 A supported way to present as N distinct founders against the live surface
- [x] 2.2 No shared-secret shortcut that would not exist for a real user — the test path must not be
      more privileged than the real path, or it proves nothing
- [x] 2.3 Multi-user isolation test: user A cannot see/enumerate/write user B's universes

## 3. Identity observability
- [x] 3.1 A caller can determine the RESOLVED principal for its own request without seeing secrets
- [x] 3.2 Never expose the bearer/token itself; expose only `bearer_present` + resolved subject
- [x] 3.3 ui-test uses this instead of inferring identity from cookies/UI (the 2026-07-21 error)

## 4. Fix the misleading status surface
- [x] 4.1 `get_status` runs with `allow_probe=False` yet reads as live verification. Either report the
      evidence class honestly (cached / timestamp / config-dir-present / deferred) or stop implying
      liveness. Claude currently reports `ok` from a non-empty config directory alone.
