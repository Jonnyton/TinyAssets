## 1. Contract

- [x] 1.1 Diagnose the live red run and prove selection used stale controller
  state while admission used current `origin/main`.
- [x] 1.2 Define current-main snapshot behavior, fail-closed boundaries, and
  the explicit separation from the cloud-universe target.

## 2. Test-Driven Repair

- [x] 2.1 Add failing tests for claim classification from an explicit Git ref
  and unchanged working-tree defaults.
- [x] 2.2 Add failing supervisor tests proving fetch precedes current-main
  selection and admission revalidation still sees the local claim.
- [x] 2.3 Implement the smallest claim-helper and supervisor changes.

## 3. Verification And Rollout

- [x] 3.1 Update the operator runbook; pass 126 focused tests, lint, OpenSpec
  strict validation, a live Windows current-main snapshot probe, and
  independent Claude review (`VERDICT: APPROVE`, 2026-07-29).
- [ ] 3.2 Sync/archive the change, land through a PR, deploy the merged
  controller, restart the terminal scheduled run, and verify useful progress.
