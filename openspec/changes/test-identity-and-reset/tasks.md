# Tasks — repeatable scoped reset and multi-user testing

> **Reconciled against `origin/main` 2026-07-22.** Every task here is still
> genuinely incomplete — nothing was found on `main` that satisfies any of them,
> so nothing is checked off. Two things were confirmed rather than changed:
> no scoped-reset or multi-identity harness exists in the tree, and the premise
> behind 4.1 was re-verified as still true (evidence inline below).

## 1. Scoped reset
- [ ] 1.1 Reset the state of a single identity (universes, home binding, ACL grants) by principal
  - Verified absent on main 2026-07-22: no scoped-reset entry point in
    `tinyassets/` or `scripts/`.
- [ ] 1.2 Idempotent: running twice equals running once; running against unknown identity is a no-op
- [ ] 1.3 Prove isolation: a second identity's universes, commons, run history and wiki are untouched
- [ ] 1.4 Probe proven RED without the scoping (i.e. a bug that widens it to global must fail a test)

## 2. Multiple test identities
- [ ] 2.1 A supported way to present as N distinct founders against the live surface
- [ ] 2.2 No shared-secret shortcut that would not exist for a real user — the test path must not be
      more privileged than the real path, or it proves nothing
- [ ] 2.3 Multi-user isolation test: user A cannot see/enumerate/write user B's universes

## 3. Identity observability
- [ ] 3.1 A caller can determine the RESOLVED principal for its own request without seeing secrets
- [ ] 3.2 Never expose the bearer/token itself; expose only `bearer_present` + resolved subject
  - Verified absent on main 2026-07-22: `bearer_present` appears only in this
    change's own `spec.md` and this ledger — there is no implementation.
- [ ] 3.3 ui-test uses this instead of inferring identity from cookies/UI (the 2026-07-21 error)
  - Blocked on 3.1/3.2 — there is nothing yet for ui-test to use.

## 4. Fix the misleading status surface
- [ ] 4.1 `get_status` runs with `allow_probe=False` yet reads as live verification. Either report the
      evidence class honestly (cached / timestamp / config-dir-present / deferred) or stop implying
      liveness. Claude currently reports `ok` from a non-empty config directory alone.
  - **Partly obsolete as written — narrow it before building.** `get_status`
    does still call `subscription_auth_health(name, allow_probe=False)`
    (`tinyassets/api/status.py:386-389`), but the "reports `ok` from a non-empty
    config directory alone" premise is no longer accurate: the non-probing paths
    already report their evidence class honestly — `refresh-viable` with the
    measured age (`tinyassets/providers/base.py:426-430`) and, when
    `allow_probe=False`, an explicit "live probe deferred to the worker gate"
    (`base.py:445-450`).
  - The **actual residual** is narrower: the disk/in-memory probe-cache hit at
    `tinyassets/providers/base.py:442-443` returns the earlier verdict verbatim
    (`return dict(cached[1])`) with no cached-vs-live label and no age, so a
    stale-but-in-TTL verdict still reads as current. Scope this task to labeling
    that one path; the general honesty work is already done.
