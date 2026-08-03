## 0. Admission

- [x] 0.1 Obtain independent review of the current-main finding, proposal, design, capability delta, and bounded task plan; fold every blocking finding before implementation. Approved at exact head `4ed06c5a57ae5a04821bc39c39e0ff9192f3480a` after the queue/source reauthorization and exact-absence corrections were folded.

## 1. Test-first persistence correction

- [x] 1.1 RED: prove no production owner store exists and that resolver-only recovered/reauthorized attempts can be published by the current fake-store contract. The first production-store test failed with `AttributeError: 'SQLiteBackgroundBranchAuthorityStore' object has no attribute 'insert_owner'`; existing service fakes accepted fabricated resolver output without canonical persistence.
- [x] 1.2 Add strict canonical owner-record serialization and a dark owner table in the existing SQLite background authority database.
- [x] 1.3 RED/GREEN: atomically persist closed missing-authority holds from exact absence, and require a present exact attempt for same-attempt recovery before updating attempt and owner in one transaction. Fault injection proves attempted owner/attempt split writes roll back together.
- [x] 1.4 RED/GREEN: for queue reauthorization atomically validate the newer binding, insert or exactly replay the fresh reserved attempt, and update the owner; for source reauthorization validate the newer binding and any prior attempt while safely allowing no replacement attempt. Queue/source exit shapes and rollback behavior have dedicated tests.

## 2. Adversarial verification

- [x] 2.1 Prove stale owner/binding/attempt fences, malformed/digest/index corruption, conflicting or non-canonically-issued fresh attempts, at-limit issuance, and injected failures between writes make no owner, binding, or attempt change. Exact-head review of `eace86c7` exposed the missing attempt-count admission; its failing at-limit regression was folded before the second review.
- [x] 2.2 Prove same-owner concurrency has one winner, source-owner exits validate canonical bindings, canonical/plugin mirrors match, isolated packaged imports pass, and no queue/dispatcher/provider/public/runtime path imports the seam.
- [x] 2.3 Run focused authority/store/service and dependent continuation tests, Ruff, strict OpenSpec, diff/secret checks, and record freshness-stamped evidence. On 2026-08-02 against load-hardened main `0efa8733`, the post-review focused/dependent matrix passed `394 passed in 22.21s` and the invocation/provider/load authority matrix passed `287 passed in 41.65s`; Ruff, strict OpenSpec, all-325 mirror parity, isolated owner-store packaged imports, dark-seam scan, blob-equivalence, and diff/credential checks also passed.

## 3. Review and foldback

- [x] 3.1 Obtain fresh independent exact-head code/security review, land through the normal PR path, leave umbrella task 2.6 explicitly partial and task 5.3 open, then sync/archive only this bounded correction and retire its STATUS row. PR #2171 merged as `bcfca9a4` on 2026-08-02 after independent Codex and opposite-family Claude review, adversarial forged-attempt reproduction, 394-test and 287-test authority/load matrices, strict OpenSpec and mirror validation, and green package/platform/installer/signing CI. STATUS row retirement remains a foldback commit concern because another active provider currently owns `STATUS.md`.
