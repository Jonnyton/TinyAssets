## 1. Admission and design

- [x] 1.1 Reproduce the 2026-07-30 red run and identify the exact state
  transition that retains the stale admission and charges the failure budget.
- [x] 1.2 Specify bounded suppression without relaxing canonical receipt or
  merge-verification requirements.

## 2. Implementation

- [ ] 2.1 Test-first, prove a consumed merge replay clears admission/resume,
  enters the bounded exclusion set, preserves progress counts, and does not
  charge the failure budget.
- [ ] 2.2 Implement the smallest supervisor state transition and preserve all
  unverified/malformed merge failure paths.

## 3. Verification

- [ ] 3.1 Run focused supervisor tests, Ruff, strict OpenSpec validation, and
  diff checks.
- [ ] 3.2 Obtain independent exact-head review, then publish through a draft PR
  and fold back the STATUS claim after merge.
