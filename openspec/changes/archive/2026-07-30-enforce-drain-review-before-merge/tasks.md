## 1. Exact-head receipt validator

- [x] 1.1 Add focused tests proving non-drain branches remain allowed and drain branches deny missing, duplicate, malformed, or stale review receipts.
- [x] 1.2 Implement the minimal stdlib validator and CLI; verify `py -m pytest tests/test_drain_review_gate.py -q` passes.

## 2. Trusted enrollment and worker contract

- [x] 2.1 Add failing contract tests for stale-enrollment disablement, matching-head enrollment, ordinary-PR preservation, and draft-first worker instructions.
- [x] 2.2 Update the trusted auto-enroll workflow and generated worker brief; verify the focused drain supervisor and review-gate tests pass.

## 3. Verification and foldback

- [x] 3.1 Run Ruff, focused/full drain tests, workflow parsing, strict OpenSpec validation, and obtain independent exact-head review with all blocking findings resolved.
- [x] 3.2 Sync the delta idempotently, retire the STATUS concern/work row, record lane/reflection metadata, archive the completed change, and publish one draft-first PR for final-head review and CI.
