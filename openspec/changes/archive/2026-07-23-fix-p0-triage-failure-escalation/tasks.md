## 1. Failure-path tests

- [x] 1.1 Add failing workflow tests for the existing Pushover CLI contract, ungated provider page, repair continuation, and exact red/green outcomes.
- [x] 1.2 Exercise the compatible Pushover dry-run invocation without changing its script.

## 2. Workflow repair

- [x] 2.1 Replace invented provider page flags with the existing CLI contract.
- [x] 2.2 Make bounded repair and restart failures continue to canonical re-probe while preserving issue-scoped concurrency.

## 3. Verification

- [x] 3.1 Make provider-page failure visible but nonblocking and cover exact workflow behavior.
- [x] 3.2 Add the executable §14 concurrency/paging proof and dated audit artifact.
- [x] 3.3 Run focused tests, lint, and strict OpenSpec validation; keep this change unsynced and unarchived for review.
