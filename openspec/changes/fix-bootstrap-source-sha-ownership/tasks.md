## 1. Executable Contract

- [x] 1.1 Add red regressions that require owner-matched Git execution for fresh and repeat bootstrap.
- [x] 1.2 Prove bootstrap rejects an empty or malformed checkout SHA and never adds a safe-directory exception.

## 2. Implementation

- [x] 2.1 Keep fresh Git operations root-owned and route repeat operations through a service-account helper.
- [x] 2.2 Resolve and validate `HEAD` before ownership transfer, then pass the stored SHA to the shared uptime installer.

## 3. Verification And Handoff

- [x] 3.1 Run focused bootstrap/installer tests, shell syntax/lint, strict OpenSpec validation, and diff checks.
- [ ] 3.2 Obtain independent exact-SHA review, sync/archive the change, and publish the infra PR.
- [ ] 3.3 Preserve the exact-landed DR rerun and its bootstrap/restore/state/probe/deletion evidence as the production monitoring handoff.
