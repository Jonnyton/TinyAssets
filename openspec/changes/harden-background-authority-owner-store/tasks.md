## 0. Admission

- [ ] 0.1 Obtain independent review of the current-main finding, proposal, design, capability delta, and bounded task plan; fold every blocking finding before implementation.

## 1. Test-first persistence correction

- [ ] 1.1 RED: prove no production owner store exists and that resolver-only recovered/reauthorized attempts can be published by the current fake-store contract.
- [ ] 1.2 Add strict canonical owner-record serialization and a dark owner table in the existing SQLite background authority database.
- [ ] 1.3 RED/GREEN: atomically persist closed missing-authority holds from exact absence, and require a present exact attempt for same-attempt recovery before updating attempt and owner in one transaction.
- [ ] 1.4 RED/GREEN: for queue reauthorization atomically validate the newer binding, insert or exactly replay the fresh reserved attempt, and update the owner; for source reauthorization validate the newer binding and any prior attempt while safely allowing no replacement attempt.

## 2. Adversarial verification

- [ ] 2.1 Prove stale owner/binding/attempt fences, malformed/digest/index corruption, conflicting fresh attempts, and injected failures between writes make no owner, binding, or attempt change.
- [ ] 2.2 Prove same-owner concurrency has one winner, source-owner exits validate canonical bindings, canonical/plugin mirrors match, isolated packaged imports pass, and no queue/dispatcher/provider/public/runtime path imports the seam.
- [ ] 2.3 Run focused authority/store/service and dependent continuation tests, Ruff, strict OpenSpec, diff/secret checks, and record freshness-stamped evidence.

## 3. Review and foldback

- [ ] 3.1 Obtain fresh independent exact-head code/security review, land through the normal PR path, leave umbrella task 2.6 explicitly partial and task 5.3 open, then sync/archive only this bounded correction and retire its STATUS row.
