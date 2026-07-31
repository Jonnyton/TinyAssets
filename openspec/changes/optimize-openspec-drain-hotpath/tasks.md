## 1. Research and review

- [x] 1.1 Re-check the canonical Ringer source and map the current local drain's measured hot-path failures against TinyAssets authority and delivery boundaries.
- [x] 1.2 Obtain independent review; on the documented current Claude hard limit use the host-approved fresh-context Codex fallback; fold every blocking finding and receive exact-revision approval before implementation. Initial `ADAPT` findings were folded, and the reviewer approved exact planning commit `7565ce641cc6f182c177e43df55bec65b05389f5`.

## 2. Test-first implementation

- [x] 2.1 Add failing focused tests proving provider filtering precedes per-worktree probes while preserving matching output. The red run failed exactly three new assertions before implementation and retained 149 passing focused tests.
- [x] 2.2 Implement the smallest prefilter and update the drain brief to use the exact identity-scoped 15-second diagnostic; prove zero matches grant no clean-lane or edit authority. The real scoped diagnostic completed in 2.398 seconds versus the terminated >59-second global probe.
- [x] 2.3 Add failing prompt regression coverage for partial resume, then require one fresh foldback PR and state that the PR limit is per disposable worker attempt.

## 3. Verification and foldback

- [x] 3.1 Run focused pytest, Ruff, strict OpenSpec validation, and diff checks. Fresh 2026-07-30 Windows evidence: 152 focused tests passed in 2.96s; Ruff clean; strict change validation and `git diff --check` passed.
- [x] 3.1a Prove the implementation is clean-room: no Ringer dependency and no copied or adapted Ringer source, tests, fixtures, prompts, formats, command structure, or implementation structure. The implementation diff is limited to existing TinyAssets scripts/tests and contains no Ringer source/dependency reference.
- [ ] 3.2 Obtain independent exact-head code review, publish one PR, verify merge, sync/archive the change, retire the STATUS claim, and restart the local drain from updated main.
