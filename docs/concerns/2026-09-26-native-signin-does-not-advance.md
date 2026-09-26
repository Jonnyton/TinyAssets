# Native sign-in failure still does not advance the turn

**Filed:** 2026-09-26
**Verified:** 2026-09-26, Windows/Python 3.14, PR #4032 at `776abaaf`
**Severity:** P1

## Source (verbatim)

> Native sign-in failure still does not advance the turn.

Source: finding 7 in [the pinned PR review](../audits/2026-09-26-pr-4032-review.md).

Code at that commit: `agent_turn_coordinator.py:147-166, 482-492; storage/agent_turn_journal.py:298`.

The review contains the verification commands, observed probe outputs, and limits.
Concurrent working-tree fixes were not reviewed; this finding is pinned to the
requested committed head, not a claim about those edits.

## Closure

Carry verified no-effects authentication evidence through executor, router and journal; retain the hold for uncertain effects.

