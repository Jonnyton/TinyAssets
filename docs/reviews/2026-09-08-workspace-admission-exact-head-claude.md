# Workspace admission exact-head review

Date: 2026-09-08. Reviewer: Claude, independent subscription subprocess.
Reviewed commit: `c97208f5a7ca369c4f3d18496dd93dd80d19276b` against
`1ccc399e7ead504163d55ac4c360168b8aad82b9`.
Wrapper exited 0 after 308 seconds; full output in
`output/workspace-admission-head-review.md`, also attached to PR #3442.

VERDICT: APPROVE. No pre-live blockers. The implementation matches the approved
shape, preserves wait policy, uses one observation across probe/retry, includes
post-admission failures, omits pre-admission/historical fabricated values, and
mirrors correctly. Reviewer independently ran `python -m pytest -q
tests/test_workspace_effector.py`: 142 passed, 2 skipped in 8.53 seconds on Windows.

Nonblocking findings retained for post-live follow-up:

- Lock conflicts include both host-slot and universe job locks; no scope/holder
  disclosure is intended. Positive count is not same-universe fairness proof.
- Add a direct effector regression for a real reconciliation sweep clearing a
  stale holder, asserting 2 attempts, 1 conflict and zero retry sleep. Existing
  coordinated tests cover actual lock release but stub the sweep.
- Attempts include a transaction attempt that raises a non-refusal database
  error; this agrees with the factual attempted-transaction contract.
- Linux CI remains a landing gate; local Docker Linux engine is unavailable.

This review is not deployed acceptance. No private workflow was changed.
