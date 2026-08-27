# P0 - Unauthenticated LAN exposure leaks sessions and permits CSRF writes

**Filed:** 2026-07-21
**Verified:** 2026-07-21
**Re-verified:** 2026-08-26 (premise holds; migrated from the retired board)
**Severity:** P0

## Source (verbatim)

> **[P0 filed:2026-07-21 verified:2026-07-21]** #1489: unauth LAN leaks sessions and permits CSRF
> writes/paid hires. Codex: ADAPT; do not LAN-run.

## Why this file exists

**This concern was dropped by the 2026-08-25 board migration.** The `docs/concerns/README.md`
recorded the *citation* problem -- that `#1489` names an unrelated merged PR
(*"feat(command-center): recover the Agent Village"*) -- and then no concern file was written for
the finding itself. A caution about a bad citation is not a record of the vulnerability. Found
2026-08-26 by diffing the retired board against this directory; three other security concerns were
missing the same way.

Per this directory's own convention: the citation rots, the premise does not. Correct the citation,
keep the finding.

## Premise, re-verified 2026-08-26

`tinyassets/universe_server.py:3115` still defaults `host: str = "0.0.0.0"`. A daemon started on a
shared network is reachable by every host on that LAN, and the write paths carry no CSRF origin
check, so a page in any browser on that network can drive authenticated writes -- including paid
hires -- against a session it never authenticated.

## Standing mitigation

Codex's verdict was **ADAPT**, not approve: **do not LAN-run.** Bind to loopback, or front the
daemon with the Cloudflare tunnel (the production path), until an origin check and an explicit bind
policy land. Production is unaffected -- it is tunnel-fronted -- so this is a self-host and
developer-machine exposure.
