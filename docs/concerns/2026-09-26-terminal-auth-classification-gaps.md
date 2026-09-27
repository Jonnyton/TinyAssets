---
severity: P2
title: Terminal auth classification is a phrase list
filed: '2026-09-26'
summary: '`_terminal_auth_failure` reads a redacted excerpt against a narrow phrase list, so a sign-in failure worded differently still reads as an outage'
---

# Phrase matching is not sufficient authentication classification

**Filed:** 2026-09-26
**Verified:** 2026-09-26, Windows/Python 3.14, PR #4032 at `776abaaf`
**Severity:** P2

## Source (verbatim)

> Phrase matching is not sufficient authentication classification.

Source: finding 9 of the Codex refute-review of PR #4032 (head `6a94d242`), recorded as a comment on that PR. The finding is quoted above in full; the review transcript is not kept in the repo.

Code at that commit: `providers/codex_provider.py:197-207, 1005, 1073; tests/test_providers.py:781`.

The PR comment carries the reviewer's verification commands and observed outputs.
Concurrent working-tree fixes were not reviewed; this finding is pinned to the
requested committed head, not a claim about those edits.

## Closure

Classify from authentication stage and structured codes where available; cover the existing exit-zero 401 case and ambiguous non-authentication text.

