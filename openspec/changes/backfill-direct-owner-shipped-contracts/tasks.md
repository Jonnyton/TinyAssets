## 1. Draft As-Built Contracts

- [x] 1.1 Draft unique requirement headings for credential projection/write replacement, live prompt/tool metadata, status identity variants, universe switching, and four uptime controllers
- [x] 1.2 Strictly validate the complete draft change without modifying canonical specs or runtime code

## 2. Verify Current Evidence

- [x] 2.1 Run focused credential-vault, engine-assignment, and provider-env tests covering exact mapping, injection, replacement, and limitations — 20 passed
- [x] 2.2 Run focused prompt/tool metadata, status-shape, and universe-switch tests covering every public/interface scenario — 97 passed; three stale assertions exposed the retired `workflow` tag and early-response `session_boundary` mismatch
- [x] 2.3 Run focused DNS, LLM-binding, release-reconcile, disk-watch, transcript-rotation, and auto-prune evidence without running `tests/test_uptime_canary_layer2.py` through Codex on Windows — 118 passed plus release structural proof; forbidden file not run
- [ ] 2.4 Obtain independent requirement-to-source review and resolve every overclaim, omission, and active-delta collision

## 3. Clear Active Owners

- [ ] 3.1 Rebase credential requirements after the fail-closed provider-auth overlay lands and consolidate any duplicate clauses
- [ ] 3.2 Rebase prompt/status/switch requirements after connector, legacy-tool, identity/reset, and universe lifecycle owners settle
- [ ] 3.3 Rebase release reconciliation after the active release lane settles and preserve only behavior still shipped
- [ ] 3.4 Produce explicit Forever Rule section 14 concurrency/load evidence for every uptime requirement or retain a bounded unsatisfied gate

## 4. Fold Back Canonical Truth

- [ ] 4.1 Broaden the STATUS Files boundary only for dependency-cleared canonical owners
- [ ] 4.2 Sync approved deltas while preserving every untouched canonical requirement block
- [ ] 4.3 Update the full-coverage audit, legacy disposition, and spec index; strictly validate the full tree and run the drift self-test
- [ ] 4.4 Archive, land through a reviewed PR, and remove the STATUS claim
