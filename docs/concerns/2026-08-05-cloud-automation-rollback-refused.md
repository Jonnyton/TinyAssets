# Cloud automation rollback refused more than 24h after setup

**Filed:** 2026-08-05 | **Verified:** 2026-08-05

> Migrated verbatim from `STATUS.md` on 2026-08-25 when the board was retired.
> Source dates preserved. Premise re-verified against `origin/main` @ `8cbf9769`.

## Source (verbatim)

Cloud automation ROLLBACK is refused >24h after setup: binding id derives from the definition, so it
re-selects the expired original (forward rebind is fine). Covered by test, not fixed.

## Shape

The binding identifier is *derived from the definition* rather than stored, so asking for the
previous binding recomputes the same id and re-selects the original - which has since expired.
Forward rebinding works because it computes a new definition. Only the backward direction is broken.

**A test covers this behaviour, so it will not silently regress - but the behaviour itself is
unchanged.** Do not read the passing test as a fix.
