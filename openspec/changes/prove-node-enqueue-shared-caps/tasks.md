## 1. Authority and contract

- [x] 1.1 Refresh origin/main, inspect STATUS/PLAN/audits, and claim an isolated worktree with an explicit file boundary
- [x] 1.2 Prove production activation and replace the stale "still dark" coordination claim
- [x] 1.3 Reproduce the missing shared-cap boundaries and the stable-root and GC-lifetime lineage defects
- [x] 1.4 Write proposal, design, and two-capability delta specs with the active queue-epoch change recorded as a semantic rebase dependency

## 2. Test-first safety proof

- [ ] 2.1 Add compiled-and-invoked concurrent global-cap and shared-origin lineage-cap tests with exact winner/refusal assertions
- [ ] 2.2 Add a bounded spawn-process proof for exact global and lineage cap behavior through the real cross-process lock
- [ ] 2.3 Add a failing stable-root context test proving sibling enqueues receive one run-derived origin with explicit parent/origin precedence
- [ ] 2.4 Add failing lifetime-lineage tests for archived rows, unrelated origins, terminal global-cap exclusion, and live/archive ID de-duplication
- [ ] 2.5 Add failing corruption and interrupted-GC tests proving no archive reset, no live rewrite, and convergence without duplicate archive rows

## 3. Minimal production repair

- [ ] 3.1 Derive the trusted root origin once from the prepared run ID in `execute_branch`
- [ ] 3.2 Count distinct same-origin task IDs across live queue and valid archive within the capped append lock
- [ ] 3.3 Make garbage collection fail closed on invalid archives and de-duplicate identified rows during interrupted-move recovery
- [ ] 3.4 Refresh packaged runtime mirrors and verify canonical/mirror parity

## 4. Verification and foldback

- [ ] 4.1 Run focused enqueue, run, dispatcher, thread, and spawn-process tests on Windows
- [ ] 4.2 Run formatting, static checks, broader regressions, and strict whole-tree OpenSpec validation
- [ ] 4.3 Obtain independent concurrency/storage/security diff review and address every finding
- [ ] 4.4 Rebase against the active queue-epoch capability state, re-run strict validation, sync canonical specs, and archive the completed change
- [ ] 4.5 Publish the reviewed PR, retire the STATUS row, update worktree/reflection records, and state whether post-fix live-use evidence exists
