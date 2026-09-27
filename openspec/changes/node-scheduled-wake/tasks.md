# Tasks: node-scheduled-wake

## 1. Build
- [x] 1.1 `once` trigger kind, `not_before` column, CHECK rebuild, due key and retire-after-run (`tinyassets/automations.py`).
- [x] 1.2 `enqueue_branch_run` registers a one-shot automation with `not_before`/`delay_seconds`; retire flag and shape caps (`tinyassets/graph_compiler.py`).
- [x] 1.3 Projection shows `not_before` (`tinyassets/api/automations.py`).

## 2. Prove
- [x] 2.1 Tests through the real pump: delayed wake fires once after `not_before`, self-rescheduling chain, private own branch allowed, cross-user refusals, restart mid-run retries, bounded retries, pending-cap usage limit.
- [x] 2.2 Rewrite `tests/test_node_enqueue_verb.py` node-level cases to the new contract.
- [x] 2.3 Mutation-check the floor and the due key.
- [ ] 2.4 gpt-6-astra refute round: cross-user reach and runaway cost.
- [ ] 2.5 Deploy; `python scripts/deployed_sha.py --assert-contains <sha>`.

## 3. Land
- [ ] 3.1 Sync delta into `openspec/specs/user-owned-automations/`, archive.
