## 1. Terminal Result Handoff

- [ ] 1.1 Add failing supervisor tests for a valid result written before provider-process exit and for unstable/invalid artifacts.
- [ ] 1.2 Poll for a stable valid result during dispatch, terminate the lingering launcher tree, and preserve ordinary result validation.

## 2. Restart Recovery

- [ ] 2.1 Add failing tests for restart consumption, exact admission matching, and ambiguous-result refusal.
- [ ] 2.2 Recover an unconsumed current-attempt result before budget enforcement or replacement dispatch.

## 3. Health And Scheduling

- [ ] 3.1 Add failing watchdog tests for a settled unconsumed result and supervisor tests for blocked-candidate fallback.
- [ ] 3.2 Report result handoff as waiting and skip blocked idle only when a different eligible candidate remains.

## 4. Verification And Rollout

- [ ] 4.1 Update the operator runbook and pass focused tests, lint, OpenSpec validation, and opposite-provider review.
- [ ] 4.2 Sync/archive the change, land through a PR, restart the scheduled drain, and prove the existing result is recovered before the next dispatch.
