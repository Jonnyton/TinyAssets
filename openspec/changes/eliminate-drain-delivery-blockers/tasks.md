## 1. Consoleless Windows Launch

- [x] 1.1 Add failing peer-launcher coverage for Windows no-console process creation, then implement it.
- [x] 1.2 Add a windowless tray bootstrap and make the idempotent scheduled-task installer use it.
- [x] 1.3 Add focused installer/launcher regression coverage proving no direct console host is scheduled.

## 2. Linked-Worktree Delivery

- [x] 2.1 Add failing coverage for resolving and granting the Git common directory only to write-capable Codex workers.
- [x] 2.2 Implement bounded Git-common-directory discovery and Codex `--add-dir` command construction.
- [x] 2.3 Prove a Codex peer can stage and commit inside a disposable linked worktree.

## 3. Result Semantics And Operations

- [x] 3.1 Add failing supervisor-brief coverage distinguishing durable `BLOCKED` results from retryable delivery `FAILED` results.
- [x] 3.2 Update the worker brief and operator runbook with the shell Git/GitHub route and delivery-failure recovery contract.
- [ ] 3.3 Run focused tests, Ruff, strict OpenSpec validation, and an independent opposite-provider review.
- [ ] 3.4 Reinstall the scheduled task, confirm consoleless startup/health, and record the first post-fix drain evidence.
