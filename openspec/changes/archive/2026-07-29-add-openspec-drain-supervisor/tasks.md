## 1. Review Gate

- [x] 1.1 Obtain and fold a Claude opposite-provider review of the controller design, safety boundaries, worker contract, and default budgets.

## 2. Controller

- [x] 2.1 Add failing tests for strict final-line result parsing, self-claim resume, controller-side GitHub merge verification, budgets, state/lock handling, interruptible stop/idle, failure taxonomy, and generated worker governance.
- [x] 2.2 Implement the stdlib-only sequential supervisor and atomic persistent state until focused tests pass.

## 3. Operations And Policy

- [x] 3.1 Add the start/status/stop/recovery runbook and bounded drain-worker convention to AGENTS.md and the canonical OpenSpec skill.
- [x] 3.2 Sync the Claude skill mirror and pass skill validation and cross-provider drift checks.

## 4. Verification And Foldback

- [x] 4.1 Run a no-dispatch dry run plus focused tests, Ruff, strict OpenSpec validation, diff checks, and an exact-diff independent review.
- [x] 4.2 Sync the delta, archive the change, retire its STATUS row, and land the reviewed implementation plus auto-merge-raced foldback.
