## 1. Build

- [ ] 1.1 `universe_paths` registry (name, kind, reset) and `platform_path` resolver; lazy + eager migration under a held lock; conflicts and links refuse; tombstones; fsync order; layout file.
- [ ] 1.2 Route every universe-scoped reader through the resolver, including `fantasy_daemon/` and `domains/`; delete each legacy root read (no fallback).
- [ ] 1.3 Source gate over `tinyassets/`, `fantasy_daemon/`, `domains/`, `scripts/` with a reasoned data-root allowlist; fixtures run through `ensure_migrated`.
- [ ] 1.4 Storage accounting counts `.runtime/state/`; scoped reset classifies through `reset`; inspect_storage_utilization follows the move.
- [ ] 1.5 Provider jails mask `.runtime/state` and tombstones; tool jail binds the root read-write only for a migrated universe, masking `.runtime/`, `workspaces/`, `.workspace-staging/` and tombstones.
- [ ] 1.6 Image label `io.tinyassets.state-layout`; `deploy_fail_safe.sh`, `deploy-prod.yml` and `release-reconcile` refuse a rollback below the data's layout.
- [ ] 1.7 Delete ownerless `.worker_supervisor.*.json` only after 2.3 confirms every reader moved.

## 2. Verify

- [ ] 2.1 Dry-run `migration_plan` against every production universe: no links, no conflicts (done 2026-10-01 by listing; rerun with the shipped code before deploy).
- [ ] 2.2 Linux jail proofs: the agent writes a new root file; a planted `.effector_consents.db` grants nothing; `.runtime/` and tombstones are invisible and unwritable from both jails.
- [ ] 2.3 After deploy: no legacy platform name left at any universe root except tombstones; storage totals unchanged; no `IsADirectoryError` in logs.
