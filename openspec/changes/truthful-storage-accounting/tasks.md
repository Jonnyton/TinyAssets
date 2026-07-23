# Tasks — truthful storage accounting

## 1. Diagnose

- [x] 1.1 Trace `disk_usage`, `per_subsystem`, universe overlays, caps, and deploy mounts.
- [x] 1.2 Preserve live connector and deploy-run evidence; distinguish confirmed bytes from inference.
- [x] 1.3 Confirm caps and growth policy remain deferred.

## 2. Test first

- [x] 2.1 Add reconciliation and incomplete-accounting pressure assertions.
- [x] 2.2 Add a synthetic near-full assertion that cannot report `ok`.
- [x] 2.3 Run the focused test on unmodified code and record the expected RED failure.

## 3. Implement

- [x] 3.1 Add one reconciliation helper and derive the additive contract fields.
- [x] 3.2 Reconcile again after the requested-universe overlay in `get_status`.
- [x] 3.3 Mirror runtime source files and update contract documentation/comments.

## 4. Verify

- [x] 4.1 Focused storage tests and lint pass.
- [x] 4.2 Revert the production fix while retaining the regression test; prove RED; restore and prove GREEN.
- [x] 4.3 Run the proportionate broader status/storage suite.
- [x] 4.4 Independent review finds no unresolved blocking issue.

## 5. Publish without merge

- [ ] 5.1 Commit atomically, push `fix/storage-accounting`, and open a draft PR.
- [ ] 5.2 PR body includes diagnosis, commands/evidence, deferrals, and verbatim proposed STATUS row.
- [ ] 5.3 Re-run live `get_status` after deployment if/when the draft is deployed; until then state the deployment blocker explicitly rather than presenting the unchanged production payload as proof.
