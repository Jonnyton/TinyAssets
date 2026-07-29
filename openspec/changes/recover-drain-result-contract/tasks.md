## 1. Result Contract

- [x] 1.1 Add failing tests for human-label target canonicalization and the exact admitted target instruction.
- [x] 1.2 Implement strict structural result parsing and explicit admitted target prompting.

## 2. Resume Recovery

- [x] 2.1 Add failing tests for valid replay, invalid replay, and preserved admission mismatch.
- [x] 2.2 Replay a newly valid last artifact before the failure-budget guard, undoing only its parser strike.

## 3. Verification And Rollout

- [x] 3.1 Run focused tests, strict OpenSpec validation, and independent opposite-provider review.
- [ ] 3.2 Land and archive the change, retire its STATUS row, update the controller, and prove the preserved run leaves red state.
