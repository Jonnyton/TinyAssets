## 1. Reproduce and Repair the Escape

- [x] 1.1 Test-first, reproduce a lifecycle parent that exits while an exact synthetic descendant retains inherited stdout/stderr; prove current supervisor exceeds the bounded margin and always clean up only the recorded test PID.
- [x] 1.2 Replace supervisor-owned pipes/drain threads with direct private capture handles, fixed-horizon replay, and no descendant-EOF dependency; make both parent-exit and noisy hung-root regressions pass.

## 2. Verify and Land

- [x] 2.1 Run focused cross-platform tests, Ruff, strict OpenSpec, workflow assertions, and document the recurring runs plus root-cause evidence.
- [ ] 2.2 Obtain independent exact-head review and require the PR's unsigned Windows lifecycle job to return a supervisor-authored terminal verdict before merge; sync and archive the change on land.
