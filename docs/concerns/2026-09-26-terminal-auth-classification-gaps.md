# Phrase matching is not sufficient authentication classification

**Filed:** 2026-09-26
**Verified:** 2026-09-26, Windows/Python 3.14, PR #4032 at `776abaaf`
**Severity:** P2

## Source (verbatim)

> Phrase matching is not sufficient authentication classification.

Source: finding 9 in [the pinned PR review](../audits/2026-09-26-pr-4032-review.md).

Code at that commit: `providers/codex_provider.py:197-207, 1005, 1073; tests/test_providers.py:781`.

The review contains the verification commands, observed probe outputs, and limits.
Concurrent working-tree fixes were not reviewed; this finding is pinned to the
requested committed head, not a claim about those edits.

## Closure

Classify from authentication stage and structured codes where available; cover the existing exit-zero 401 case and ambiguous non-authentication text.

