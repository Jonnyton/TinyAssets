## 1. Executable Contract

- [x] 1.1 Add a red workflow regression for live, region-aware Debian x64 image selection and retired-pin rejection.
- [x] 1.2 Add behavioral red tests for page-2 selection, exact provider eligibility, continuation failure, malformed/cyclic pagination, page budget, and empty aggregate.

## 2. Implementation

- [x] 2.1 Implement a bounded selector that aggregates validated DigitalOcean image pages through the credential-safe helper.
- [x] 2.2 Resolve the exact newest eligible Debian x64 image before any mutating API request.
- [x] 2.3 Persist the selected slug in PASS, probe-failure, deletion-failure, and summary evidence.
- [x] 2.4 Document `image:read` as an explicit rerun prerequisite and preserve Debian 13 bootstrap compatibility as live drill evidence.

## 3. Verification And Handoff

- [x] 3.1 Run focused tests, actionlint/ShellCheck, strict OpenSpec validation, Ruff, and diff checks.
- [x] 3.2 Obtain independent exact-SHA review, sync/archive the change, and publish the infra PR.
- [x] 3.3 Preserve exact-landed-SHA drill #3 as the production monitoring handoff.
