# P1 - Founder-taught canon inherits public visibility

**Filed:** 2026-08-06 | **Verified:** 2026-08-06 | **Re-verified:** 2026-08-25 | **Severity:** P1
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

## Owner

`docs/audits/2026-08-06-cloudflare-os-architecture-implications.md`
