# A rulebook pin can be raised without an exact-head receipt

**Filed:** 2026-09-26
**Severity:** P2
**Found by:** ChatGPT Astra review of PR #4025 (`output/astra-rulebook-cut-review.md`,
finding 1b), dispatched via `peer-agents`.

## Source (verbatim)

> Furthermore, `.github/workflows/pr-scope-guard.yml:144` does not include the
> budget checker among receipt-protected gate files, so even the promised
> mandatory review of a pin increase is unenforced.

## What is true, and what already covers it

`AGENTS.md` § *The rulebook only shrinks* says raising a pin "is not" allowed.
Two things enforce that today:

- `tests/test_rulebook_ratchet.py::test_raising_a_pin_requires_displacing_another`
  caps the SUM of the pins, so a pin may rise only if another falls by at least as
  much. It runs in `required-tests`, a required check.
- `test_pins_leave_no_stale_headroom` keeps each pin within 250 B of its file, so
  a shrink cannot bank headroom for a later regrowth.

What is NOT enforced: `scripts/check_context_budget.py` is absent from `GATE_RE`
in `pr-scope-guard.yml`, so editing the pins needs no exact-head review receipt
the way editing `tests.yml` or `known-failing-tests.txt` does. A PR could lower
`POST_CUT_TOTAL` and raise a pin in one diff and stay green.

## Why it was not fixed in PR #4025

`GATE_RE` protects `pr-scope-guard.yml` itself, so adding the checker to that
regex makes the PR that does it require its own receipt. Doing it inside #4025
would have pulled the CI gate files into a docs-and-ratchet PR and blocked it
behind a receipt for an unrelated reason. It is a one-line workflow change and
belongs in its own lane, with its own receipt.

## Fix

Add `scripts/check_context_budget\.py$` (and, if wanted,
`tests/test_rulebook_ratchet\.py$`) to `GATE_RE` in
`.github/workflows/pr-scope-guard.yml`. `GATE_RE` is read from the trusted base
checkout, so the change gates every later PR without gating itself.
