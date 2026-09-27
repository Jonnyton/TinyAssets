---
severity: P2
title: One run error carries one failure class
filed: '2026-09-26'
summary: a summary holding both a pre-wire `[missing_consent]` refusal and a delivered 401 classifies as one of them and omits the other repair; reversing the precedence only moves the loss, so the fix is per-row classification
---

# One run error carries one failure class, so a mixed run loses a repair

**Filed:** 2026-09-26, from the Codex refute-review of PR #4021
(the Codex refute-review of PR #4021 — verdict and receipt in https://github.com/Jonnyton/TinyAssets/pull/4021#issuecomment-5850412279, full reviewer text in that PR's history (the audit file it was filed in was removed on landing, since the findings are resolved), P2 #7).
**Severity:** P2. **Owner:** unassigned.

## The finding

A run's `error` can carry up to five effect-failure rows. `_classify_external_write`
returns ONE class for the whole line, so a summary holding both a pre-wire
`[missing_consent]` refusal and a separate delivered 401 classifies as
`external_write_refused` and suggests the consent ask — omitting the credential
replacement, which is independently necessary.

Reversing the precedence does not fix it. It moves the loss: the run would
classify as `credential_rejected` and the missing consent would go unsaid. The
reviewer said so explicitly, and it is why this is filed rather than patched.

## Why it is not fixed in PR #4021

The defect is in the SHAPE of the field, not in the matcher. A run record carries
one `failure_class` string, one `suggested_action` and one `actionable_by`, read
by `list_recent_runs`, the run snapshot in `tinyassets/api/runs.py`, and
`_classify_run_outcome_error` — which is handed only the serialised error string,
because the async runner has already discarded the structured rows. Preserving a
class per row means changing what those three fields are, at every reader.
PR #4021 narrowed the classifier; widening the contract is a different change.

## What the fix probably looks like

`output["external_write_errors"]` already holds the structured rows, and each row
already carries `error_kind` and (since #4021) `destination`. The honest shape is
per-row classification with the run-level field kept as the most actionable of
them, so existing readers keep working:

- classify each ROW, not the joined summary;
- keep `failure_class` as the row that most demands action, and add the full list
  beside it;
- have `suggested_action` name every distinct repair the run needs, in the order
  they must happen (authority before retry).

The path that only has the string (`_classify_run_outcome_error`) needs the rows
persisted where it can reach them, or the classification done before the summary
is composed — which is also what the reviewer recommended.

## How to tell it still matters

A run that fails BOTH ways is rare: it needs two effect-bearing nodes whose
failures differ in kind, and design D1 fails the run at the first failing node,
so today most runs carry one row. If that stays true, this is cosmetic. Check
before acting: count real runs whose `external_write_errors` holds more than one
distinct `error_kind`.

Resolve this file by deleting it.
