# Rotated authorization is discarded after a failed save

**Filed:** 2026-09-26
**Verified:** 2026-09-26, Windows/Python 3.14, PR #4032 at `776abaaf`
**Severity:** P1

## Source (verbatim)

> Rotated authorization is discarded after a failed save.

Source: finding 1 in [the pinned PR review](../audits/2026-09-26-pr-4032-review.md).

Code at that commit: `credential_refresh.py:242-255 and subscription_refresh.py:639-640`.

The review contains the verification commands, observed probe outputs, and limits.
Concurrent working-tree fixes were not reviewed; this finding is pinned to the
requested committed head, not a claim about those edits.

## Closure

Persist a recoverable rotated result, distinguish post-spend persistence failure, and prevent launching or retrying the old token.


## Partially closed on `claude/credential-refresh`

**Verified:** 2026-09-26, Windows/Python 3.14, at the branch head that carries the
fix (not `776abaaf`, which this finding was pinned to). The LIE is fixed, not the loss: an unsaveable rotation now raises `RefreshRejected` rather than `RefreshUnavailable` (`credential_refresh.py`, `test_an_unsaveable_rotation_is_terminal_not_transient`). The refresh token has been spent by that point, so the stored one is dead and 'try later' was false; the owner is now told to sign in again, which is the only thing that works.

STILL OPEN: the rotated authorization is still lost. Closing it needs somewhere durable to put a rotated secret that the vault write could not accept -- which is a storage-shape question, not a retry-loop tweak.
