# P1 - No OS-level engine sandbox; `converse` is in-process-confined only

**Filed:** 2026-07-02
**Verified:** 2026-07-22
**Re-verified:** 2026-08-26 (premise holds; migrated from the retired board)
**Severity:** P1

## Source (verbatim)

> **[P1 filed:2026-07-02 verified:2026-07-22]** No OS engine sandbox. Live `converse` is
> in-process-confined only (WebFetch-only, cwd-pin, rot-prone denylist); #1485 is a fail-closed seam.

> [filed:2026-07-02 verified:2026-07-22] Reshape residuals: WebFetch SSRF guard, `write_page`
> scope=commons, legacy `mcp_server.py` doors.

## Why this file exists

Dropped by the 2026-08-25 board migration -- see
[the LAN/CSRF concern](2026-07-21-unauth-lan-session-leak-csrf.md) for how the gap was found. The
reshape-residuals row is folded in here because all three residuals are the same containment
surface.

## Premise, re-verified 2026-08-26

`tinyassets/providers/base.py` carries `sandbox_workspace` / `sandbox_chat` flags and a bwrap jail
(`base.py:163-169`), but the container cannot run bwrap unprivileged -- the recorded failure
signatures are still matched at `base.py:1062-1068`, and the served-codex outage traced to exactly
that (`bwrap: Can't mount proc -- Operation not permitted`). Live `converse` therefore relies on
in-process confinement: WebFetch-only, a cwd pin, and a denylist that rots as tools change.

A denylist is the wrong shape for this: it fails **open** on anything not yet listed.

## Related

The correct fix is narrow container `systempaths=unconfined` on the daemon service while keeping
`cap_drop ALL` / `no-new-privileges` / non-root / restricted egress -- which needs a container
recreate. Tracked with the deploy decision, not here.
