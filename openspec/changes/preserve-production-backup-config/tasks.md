## 1. Executable Contracts

- [x] 1.1 Add a deploy-workflow regression test requiring `BACKUP_DEST` preservation while legacy overrides remain scrubbed.
- [x] 1.2 Add installer-workflow tests for the ready, absent, partial, invalid, secret-confinement, and rollback paths.

## 2. Production Workflows

- [x] 2.1 Remove `BACKUP_DEST` from the production deploy scrub set and correct its ownership comment.
- [x] 2.2 Make the exact-source host-service workflow verify or transactionally provision the documented scoped Spaces destination before installing timers.
- [x] 2.3 Keep API and Spaces credentials out of logs, outputs, artifacts, arguments, and `/etc/tinyassets/env`.
- [x] 2.4 Correct the mechanically renamed bucket identity to the existing immutable pre-rename provider resource.
- [x] 2.5 Tolerate bounded provider key propagation without broadening authority or weakening rollback.
- [x] 2.6 Remove the unnecessary S3 mkdir preflight so every data-plane request stays inside the bounded probe gate.
- [x] 2.7 Add an explicit exact-source dispatch option that verifies fresh primary archives and both GitHub release assets.
- [x] 2.8 Scope every backup evidence marker to the new systemd invocation ID rather than a time window.

## 3. Verification And Operations

- [x] 3.1 Run focused tests, actionlint, Ruff, and strict OpenSpec validation.
- [x] 3.2 Correct stale runbook truth and document the automatic absent-state convergence path.
- [ ] 3.3 Obtain independent security/diff review and land the exact reviewed head.
- [ ] 3.4 Run the exact-merge installer, a real two-tier backup, destination listing, archive validation, and a follow-up production deploy preservation check.
- [ ] 3.5 Record freshness-stamped evidence, archive/sync the change, and retire the STATUS row.
