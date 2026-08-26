# P0 - Graph/provider code can falsely attest or run in-process

**Filed:** 2026-07-02 | **Verified:** 2026-07-25 | **Severity:** P0

> Migrated verbatim from `STATUS.md` on 2026-08-25 when the board was retired.
> Source dates preserved. Premise re-verified against `origin/main` @ `8cbf9769`.

## Source (verbatim)

Graph/provider code can falsely attest or run in-process; router fallback neutralizes isolation
refusals. See #1573.

## Why the second clause is the dangerous one

An isolation refusal is only as strong as what happens next. If the router's fallback chain catches
the refusal and re-routes to another provider, the refusal has been converted into a retry - the
confinement decision is made and then discarded.

Related to, but distinct from, `2026-04-17-provider-fallback-chain-privacy.md`: same mechanism,
different consequence.

## Owner

Issue #1573.
