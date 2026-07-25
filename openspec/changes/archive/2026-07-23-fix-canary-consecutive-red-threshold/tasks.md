## 1. Structural Regression Coverage

- [x] 1.1 Add DNS workflow tests that require a final non-tolerated red-result propagation step after output publication.
- [x] 1.2 Add LLM-binding workflow tests that require the same propagation shape while preserving the always-running alarm sink.
- [x] 1.3 Run the focused structural tests and confirm they fail for the missing propagation behavior.

## 2. Workflow Repair

- [x] 2.1 Add the final DNS probe-job status propagation step.
- [x] 2.2 Add the equivalent final LLM-binding probe-job status propagation step.
- [x] 2.3 Run the focused structural tests and actionlint successfully.

## 3. Verification

- [x] 3.1 Strictly validate the OpenSpec change.
- [x] 3.2 Review the owned diff for scope, consistency, and preservation of current-run alarm processing.
