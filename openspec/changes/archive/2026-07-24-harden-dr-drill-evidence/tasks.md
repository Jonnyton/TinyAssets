## 1. Executable Contract

- [x] 1.1 Add focused red tests for primary archive confinement/safety metadata and fixed-cap, credential-redacted DigitalOcean diagnostics.
- [x] 1.2 Add focused red tests for pipeline/checksum-bound transfer, exact `BACKUP_FILE` restore, representative restored-state proof, unconditional green cleanup, and failed-DELETE escalation.

## 2. Workflow Hardening

- [x] 2.1 Implement primary-host preflight and safe archive/sample metadata outputs before provisioning.
- [x] 2.2 Implement the bounded standard-library DigitalOcean request helper and use it without converting failed lookup into absent state.
- [x] 2.3 Bind transfer, restore, and restored-state verification to the preflight archive and digests.
- [x] 2.4 Record checksum/state evidence, make destruction independent of evidence publication, and make every failed DELETE red with durable escalation.

## 3. Verification And Handoff

- [x] 3.1 Run focused workflow tests, actionlint with ShellCheck, strict OpenSpec validation, and diff checks.
- [x] 3.2 Obtain independent review, sync the canonical capability spec, and archive the completed change.
- [x] 3.3 Preserve exact-landed-SHA drill rerun and production evidence as the post-merge STATUS handoff.
