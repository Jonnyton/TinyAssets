## 1. Baseline and Red Proof

- [x] 1.1 Reconfirm current `deploy-prod.yml` ordering, rollback condition, release receipt, issue wording, actual daemon-container discovery, and the P2-10 audit against current `origin/main`; record no overlapping active owner for every implementation/test file before broadening the lane.
- [x] 1.2 Add failing structural tests proving: `production_mutation_started` is immediately before `Scrub stale cloud env overrides`; `image_mutation_started` is immediately before the first `TINYASSETS_IMAGE` write; terminal publication keys off the former; image rollback keys off the latter; rollback and terminal steps use `always()` in terminal order; and outputs are emitted before failure.
- [x] 1.3 Add failing matrix tests for a directly executable pure classifier/builder covering pre-host-write not-applicable, production mutation before image mutation, forward success, rollback success, rollback command/canary/identity failure, no rollback target, every rollback-step zero/nonzero exit row, terminal writer failure visibility, and `not_needed` issue wording with complete versus incomplete terminal health tuples.
- [x] 1.4 Add failing validation/projection tests covering a manually selected old tag, fresh digest-bound source provenance, v1 identity-only matching, v1 non-inheritance of every provenance/ancestry field, v2 terminal-proof acceptance/rejection, invalid base64, malformed JSON, decoded receipt sizes 65,536 and 65,537 bytes, prior identity mismatch, env/running mismatch and missing observations, exact enums, all legacy fields, and every safe `rollback_target` matrix row.
- [x] 1.5 Run the focused new tests and record the expected failures against the current env-only, success-only receipt and unconditional "Rolled back to" claim.

## 2. Pure Receipt Classifier And Builder

- [x] 2.1 Implement the small standard-library classifier/builder with a side-effect-free core that accepts explicit JSON observations, validates the canonical RepoDigest regex and exact 65,536-byte decoded prior-receipt bound, and receives `terminal_at` rather than reading a clock.
- [x] 2.2 Implement digest-bound revision provenance so workflow-run build metadata requires revision/head-SHA agreement and manual dispatch never inherits `github.sha`; allow v1 only to corroborate dual-observed identity, derive v1-matched source afresh from the digest label, and accept prior provenance/ancestry only from a matching version-2 terminal-proof receipt.
- [x] 2.3 Implement the exact marker, prior-match, outcome, active-identity, rollback, canary, and provenance enums; emit attempted/configured/running/active observations and the complete version-2 field set.
- [x] 2.4 Implement every legacy projection and the complete outcome/active-identity `rollback_target` matrix, including the invariant that a failed attempted image never becomes a future repair target.
- [x] 2.5 Run the classifier matrix tests directly and keep the core free of environment, Docker, SSH, GitHub, clock, and filesystem access.

## 3. Workflow Observation And Terminal Publication

- [x] 3.1 Complete read-only pre-host-write capture with strict base64 prior-receipt transport and independent configured/running daemon identity observation; capture a previous rollback ref only on canonical agreement.
- [x] 3.2 Emit `production_mutation_started=true` immediately before the first production-host write and `image_mutation_started=true` immediately before the atomic `TINYASSETS_IMAGE` helper call; make each output survive failure of its following command.
- [x] 3.3 Rewrite rollback handling under `if: always()` so it keys eligibility only to the image marker, emits defaults/final outputs before fallible exit, and implements every exact zero/nonzero exit-table row, including zero for valid `not_needed` and nonzero for required unavailable/unproven rollback.
- [x] 3.4 Replace the success-only writer with a post-rollback `if: always()` terminal step keyed only to the production marker: emit `not_applicable` without host contact before that boundary; otherwise emit `failed` before fallible work, expose terminal classification outputs, invoke the pure builder, atomically install with numeric `1001:1001` mode `0644`, and emit `published` only afterward.
- [x] 3.5 Make the deploy-failed issue and job summary implement the full rollback, terminal-receipt, and active-identity wording matrices; permit "proven healthy" only for terminal `deployed` + active `agreed` + applicable canary `passed`, and treat every incomplete/inconsistent tuple as unproven.
- [x] 3.6 Preserve a red job for forward, rollback, identity-proof, classifier, transfer, and writer failures; receipt publication is evidence and MUST NOT mask failure.

## 4. Verification and Spec Foldback

- [x] 4.1 Run all classifier/exit/issue matrix tests and the complete `tests/test_deploy_prod_workflow.py` regression file, including both mutation boundaries, pre-host and pre-image paths, v1/v2 trust separation, failed-step output visibility, terminal ordering/always conditions, legacy compatibility, and safe rollback targets.
- [x] 4.2 Run actionlint, YAML parsing, secret-pattern/diff checks, targeted uptime workflow tests, full strict OpenSpec validation, and `git diff --check`.
- [x] 4.3 Obtain independent workflow-correctness, rollback/security, spec, and simplicity review; resolve all Critical/Important findings and rerun affected checks.
- [x] 4.4 Rebase after the disk-remediation lane releases `openspec/specs/uptime-and-alarms/spec.md`, intelligently sync the full modified requirement, validate idempotently, archive the completed change, and remove the STATUS work row.
- [ ] 4.5 After merge, require isolated or production-safe failures both after production mutation/before image mutation and after image mutation; observe terminal publication on both, rollback only on the latter, writer outputs, issue text, red job, and installed receipt before claiming operational proof. Until observed, retain a freshness-stamped STATUS watch rather than claiming live terminal receipts.
