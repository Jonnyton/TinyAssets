# P1 - No live failure proof for repair escalation and reconcile caps

**Filed:** 2026-07-23 | **Verified:** 2026-07-26 | **Severity:** P1

> Migrated verbatim from `STATUS.md` on 2026-08-25 when the board was retired.
> Source dates preserved. Premise re-verified against `origin/main` @ `8cbf9769`.

## Source (verbatim)

No live failure proof: #1645 repair escalation and reconcile fail/cancel cap are CI/structural-only.

## Why it stays open

Both mechanisms are proven by construction and by CI, never by a real failure in production. A cap
that has never been hit and an escalation that has never fired are designs, not evidence. This is
the project's own standing rule (`AGENTS.md` - green tests are supporting evidence, not proof)
applied to itself.

## Closing condition

One observed production failure that exercises the escalation path, or a deliberate injected failure
against the live surface, with the trace recorded.
