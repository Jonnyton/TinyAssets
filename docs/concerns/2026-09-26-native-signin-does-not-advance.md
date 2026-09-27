# Native sign-in failure still does not advance the turn

**Filed:** 2026-09-26
**Verified:** 2026-09-26, Windows/Python 3.14, PR #4032 at `776abaaf`
**Severity:** P1

## Source (verbatim)

> Native sign-in failure still does not advance the turn.

Source: finding 7 of the Codex refute-review of PR #4032 (head `6a94d242`), recorded as a comment on that PR. The finding is quoted above in full; the review transcript is not kept in the repo.

Code at that commit: `agent_turn_coordinator.py:147-166, 482-492; storage/agent_turn_journal.py:298`.

The PR comment carries the reviewer's verification commands and observed outputs.
Concurrent working-tree fixes were not reviewed; this finding is pinned to the
requested committed head, not a claim about those edits.

## Closure

Carry verified no-effects authentication evidence through executor, router and journal; retain the hold for uncertain effects.

