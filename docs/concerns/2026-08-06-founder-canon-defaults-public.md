# P1 - Founder-taught canon inherits public visibility

**Filed:** 2026-08-06 | **Verified:** 2026-08-06 | **Re-verified:** 2026-08-25, 2026-08-28 (live) | **Severity:** P1
**Status:** Codex **REPRODUCED**.

> Migrated verbatim from `STATUS.md` on 2026-08-25 when the board was retired.
> Source dates preserved. Premise re-verified against `origin/main` @ `8cbf9769`.

## Source (verbatim)

Founder-taught canon inherits `DEFAULT_CREATE_VISIBILITY="public"` with no narrowing step:
confidential input a founder gives `converse` is committed by `commit_learning` and returned by
anonymous `read_page`/search (Codex REPRODUCED). ACLs guard the destination, never upstream
entitlements.

## The structural point

*ACLs guard the destination, never upstream entitlements.* The access check asks "may this reader
see this page?" - it never asks "should this content have become a public page at all?" Anything a
founder says in confidence to `converse` is one `commit_learning` away from anonymous search.

## Re-verification 2026-08-25

`tinyassets/api/visibility.py:88` - `DEFAULT_CREATE_VISIBILITY = "public"`. Consumed at
`tinyassets/api/universe.py:5705` as the fallback when no explicit visibility is passed.
Premise holds, unchanged.

## Re-verification 2026-08-28 — confirmed end-to-end on live production

Both prior verifications were code-level. This one is the wire, against
`https://tinyassets.io/mcp`, **with no credential of any kind** — no bearer, no
cookie, no session to begin with:

```
POST /mcp  {"method":"initialize", ...}          -> 200, mcp-session-id: 71d2beda…
POST /mcp  {"method":"tools/list"}               -> 200, full tool catalogue
POST /mcp  {"method":"tools/call","params":{"name":"get_status"}}
                                                 -> 200, the founder's universe:
   persona.name = "tiny", embodied = true,
   self_model.known = [identity, founder, orgchart, body, origin]
```

Two things this settles that the code reading could not:

1. **The anonymous path is reachable from the open internet**, not merely present
   in code. An unauthenticated `initialize` mints a real session, and that session
   calls read-effect tools.
2. **It resolves to a real, named universe** rather than a blank or public
   sample one. `persona.name` came back as `tiny`.

Anonymous *read* is deliberate (`middleware.py:427` — "A *missing* token still
resolves to anonymous public read"; writes draw a 401 OAuth challenge), so this
is not a new hole. It is this concern's exact predicted consequence, now
observed in production: the default visibility decides what anonymous read can
see, and the default is `public`.

Not probed, deliberately: no write, no `converse`, no `read_page` search. Read
access is proven; going further would mutate state or spend the founder's
budget to establish something already established.

## Owner

`docs/audits/2026-08-06-cloudflare-os-architecture-implications.md`
