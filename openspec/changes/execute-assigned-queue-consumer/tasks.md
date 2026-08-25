## 1. Background provider authority

- [ ] 1.1 Add failing tests for the distinct `background_branch_run` binding, immutable branch roles, cross-universe/provider rejection, rotation-before-launch, snapshot cleanup, and no ambient fallback.
- [ ] 1.2 Implement the atomic assigned-provider/background-attempt/custody/budget fence and per-launch provider call until the authority tests pass.

## 2. Shared claimed-task executor

- [ ] 2.1 Add differential tests covering immutable version execution, run reservation/reuse, cancellation heartbeats, terminal metadata, and delegated-authz/confidentiality inputs.
- [ ] 2.2 Extract `execute_claimed_branch_task(base_path, claimed_task, executor_identity, provider_call)` and switch `fantasy_daemon` to the shared implementation.

## 3. Assigned queue consumer

- [ ] 3.1 Add failing claim/store tests for flag-off zero claims, epoch/version/lease CAS, two-consumer single winner, retryable authority release, and restart recovery.
- [ ] 3.2 Implement the bounded/stoppable consumer, per-universe/global caps, daemon startup integration, and exception containment behind the default-off flag.

## 4. Verification and mirror

- [ ] 4.1 Prove scheduled runs retain the assigned direct provider path and run all new plus touched-area test suites and Ruff.
- [ ] 4.2 Rebuild the Claude-plugin mirror, verify parity, review the full diff for shape/basic safety, and record residual risks without enabling or deploying.
