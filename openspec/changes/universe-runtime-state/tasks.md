## 1. Build

- [ ] 1.1 `universe_paths.platform_path` resolver (no-follow dirs under `.runtime/state/`) and a source gate refusing platform names joined onto a universe dir elsewhere.
- [ ] 1.2 Route every reader in design.md's inventory through the resolver; delete each legacy root read (no fallback).
- [ ] 1.3 One-time, locked, link-refusing migration with `.migrated-v1` marker; delete ownerless `.worker_supervisor.*.json`.
- [ ] 1.4 Tool jail: root bound read-write only for a migrated universe; `.runtime/` masked by tmpfs.

## 2. Verify

- [ ] 2.1 Linux jail proofs: the agent writes a new root file; a planted `.effector_consents.db` at the root grants nothing; `.runtime/` invisible and unwritable from the jail.
- [ ] 2.2 One gpt-6-astra refute round (cross-user and forged-state paths).
- [ ] 2.3 After deploy: production listing shows no legacy platform name at any universe root; storage totals unchanged.
