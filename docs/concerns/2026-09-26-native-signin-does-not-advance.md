---
severity: P1
title: A native sign-in failure cannot advance the turn
filed: '2026-09-26'
summary: '`_finish_native_failure` produces `indeterminate` -> `held_native_unknown`, which `_next_after_signin` refuses because that state is not proof nothing ran. The founder''s own complaint ("didn''t route me to Opus"). Scoped, including the second reader: `effects_evidence` treats `capacity_no_effects` as the ONLY no-effect native terminal'
---

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


## Scoping for the fix (read-only, 2026-09-26, on `claude/credential-refresh`)

The founder's own complaint is this one ("didn't route me to Opus"), and the shape
is already in the tree -- no new evidence vehicle is needed:

- `NativeCompletionEvidence(provider, protocol_complete, process_reaped,
  side_effect_state)` (`providers/agent_capacity_boundary.py`) IS the proof
  vehicle. "Nothing ran" is `protocol_complete=True`, `process_reaped=True`,
  `side_effect_state="none"`. The adapter must attest it -- the module's own
  docstring insists the installed executor supplies it, not remote metadata.
- So the launch adapter needs to attach that evidence on a quick auth exit with
  zero protocol events, and `_finish_native_failure`
  (`agent_turn_coordinator.py:145`) needs a no-effect terminal for
  `auth_invalid` beside the existing `capacity_no_effects`, instead of falling
  through to `NativeTerminal("indeterminate")`.

**The trap: there is a SECOND reader.** `effects_evidence`
(`agent_turn_coordinator.py:169`) special-cases the string
`"capacity_no_effects"` as the only native terminal meaning nothing ran; every
other native terminal makes the turn's effects `unknown`. A new terminal status
that `_next_after_signin` accepts but `effects_evidence` does not will advance the
turn while still reporting to the owner that actions may have occurred. Both
readers have to learn the new status in the same change, and a test has to assert
the effects projection, not only the advance.

Verify each cited symbol before acting -- this note is a snapshot.
