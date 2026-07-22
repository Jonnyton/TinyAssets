# Tasks — repair auto-enroll release chain

## 1. Specify and reproduce

- [x] 1.1 Record the reconciler architecture and rejected token/strict alternatives.
- [x] 1.2 Add regression tests for merged-but-not-deployed reconciliation and enrolled-behind PR updates.
- [x] 1.3 Run the focused tests and preserve the expected RED result before changing the workflow.

## 2. Implement

- [x] 2.1 Add scheduled/manual branch reconciliation to `auto-enroll-merge.yml`.
- [x] 2.2 Keep event-driven enrollment scoped to same-repository, non-draft PRs targeting `main`.
- [x] 2.3 Make per-PR update failures visible while allowing the sweep to attempt every candidate.

## 3. Verify and publish

- [ ] 3.1 Run focused tests, workflow YAML parsing, and `actionlint` on every touched workflow.
- [ ] 3.2 Obtain opposite-provider review and resolve required findings.
- [ ] 3.3 Open a draft PR, apply `infra-change`, freshness-stamp live/main drift, and include proposed verbatim STATUS concern lines.
