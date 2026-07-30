## 1. Exact-head receipt validator

- [ ] 1.1 Add focused tests proving non-drain branches remain allowed and drain branches deny missing, duplicate, malformed, or stale review receipts.
- [ ] 1.2 Implement the minimal stdlib validator and CLI; verify `py -m pytest tests/test_drain_review_gate.py -q` passes.

## 2. Trusted enrollment and worker contract

- [ ] 2.1 Add failing contract tests for stale-enrollment disablement, matching-head enrollment, ordinary-PR preservation, and draft-first worker instructions.
- [ ] 2.2 Update the trusted auto-enroll workflow and generated worker brief; verify the focused drain supervisor and review-gate tests pass.

## 3. Verification and foldback

- [ ] 3.1 Run Ruff, focused/full drain tests, workflow parsing, strict OpenSpec validation, and obtain independent exact-head review with all blocking findings resolved.
- [ ] 3.2 Sync the delta idempotently, archive the completed change, retire the STATUS concern/work row, record lane/reflection metadata, and publish one draft-first PR through verified CI/merge.
