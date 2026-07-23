## 1. Baseline and Red Proof

- [ ] 1.1 Reconfirm current `deploy-prod.yml` ordering, rollback condition, release receipt, issue wording, actual daemon-container discovery, and the P2-10 audit against current `origin/main`; record no overlapping active owner for every implementation/test file before broadening the lane.
- [ ] 1.2 Add failing structural tests proving: mutation is marked immediately before the image mutation; rollback and terminal steps use `always()` in terminal order; rollback emits bounded defaults/final outputs before failure; terminal receipt emits `failed` before fallible work and `published` only after atomic install; and issue wording consumes those outputs.
- [ ] 1.3 Add failing matrix tests for a directly executable pure classifier/builder covering pre-mutation not-applicable, forward success, rollback success, rollback command failure, rollback canary failure, rollback canary pass with identity mismatch, no rollback target, and terminal writer failure visibility.
- [ ] 1.4 Add failing validation/projection tests covering a manually selected old tag, digest-bound source provenance, invalid base64, malformed JSON, decoded receipt sizes 65,536 and 65,537 bytes, prior identity mismatch, env/running mismatch and missing observations, exact enums, all legacy fields, and every safe `rollback_target` matrix row.
- [ ] 1.5 Run the focused new tests and record the expected failures against the current env-only, success-only receipt and unconditional "Rolled back to" claim.

## 2. Pure Receipt Classifier And Builder

- [ ] 2.1 Implement the small standard-library classifier/builder with a side-effect-free core that accepts explicit JSON observations, validates the canonical RepoDigest regex and exact 65,536-byte decoded prior-receipt bound, and receives `terminal_at` rather than reading a clock.
- [ ] 2.2 Implement digest-bound revision provenance so workflow-run build metadata requires revision/head-SHA agreement and manual dispatch never inherits `github.sha`; accept prior source/ancestry only from a validated receipt matching the agreed active ref.
- [ ] 2.3 Implement the exact outcome, active-identity, rollback, canary, and provenance enums; emit attempted/configured/running/active observations and the complete version-2 field set.
- [ ] 2.4 Implement every legacy projection and the complete outcome/active-identity `rollback_target` matrix, including the invariant that a failed attempted image never becomes a future repair target.
- [ ] 2.5 Run the classifier matrix tests directly and keep the core free of environment, Docker, SSH, GitHub, clock, and filesystem access.

## 3. Workflow Observation And Terminal Publication

- [ ] 3.1 Extend pre-mutation capture with strict base64 prior-receipt transport and independent configured/running daemon identity observation; capture a previous rollback ref only on canonical agreement.
- [ ] 3.2 Mark `mutation_started=true` immediately before the atomic `TINYASSETS_IMAGE` helper call and make the output survive a helper failure.
- [ ] 3.3 Rewrite rollback handling under `if: always()` so attempted/result/canary/reason defaults are visible before fallible commands, final outputs are written before a nonzero return, and canary green without terminal identity agreement cannot become `rolled_back`.
- [ ] 3.4 Replace the success-only writer with a post-rollback `if: always()` terminal step that emits `not_applicable` before skipping pre-mutation paths, emits `failed` before post-mutation fallible work, invokes the pure builder, atomically installs with numeric `1001:1001` mode `0644`, and emits `published` only afterward.
- [ ] 3.5 Make the deploy-failed issue and job summary implement the full rollback, terminal-receipt, and active-identity wording matrices while preserving empty/inconsistent outputs as unproven.
- [ ] 3.6 Preserve a red job for forward, rollback, identity-proof, classifier, transfer, and writer failures; receipt publication is evidence and MUST NOT mask failure.

## 4. Verification and Spec Foldback

- [ ] 4.1 Run all classifier matrix tests and the complete `tests/test_deploy_prod_workflow.py` regression file, including failed-step output visibility, terminal ordering/always conditions, legacy compatibility, and safe rollback targets.
- [ ] 4.2 Run actionlint, YAML parsing, secret-pattern/diff checks, targeted uptime workflow tests, full strict OpenSpec validation, and `git diff --check`.
- [ ] 4.3 Obtain independent workflow-correctness, rollback/security, spec, and simplicity review; resolve all Critical/Important findings and rerun affected checks.
- [ ] 4.4 Rebase after the disk-remediation lane releases `openspec/specs/uptime-and-alarms/spec.md`, intelligently sync the full modified requirement, validate idempotently, archive the completed change, and remove the STATUS work row.
- [ ] 4.5 After merge, require an isolated or production-safe failed-deploy exercise that observes rollback, writer outputs, issue text, red job, and the installed receipt before claiming operational proof; until observed, retain a freshness-stamped STATUS watch rather than claiming live terminal receipts.
