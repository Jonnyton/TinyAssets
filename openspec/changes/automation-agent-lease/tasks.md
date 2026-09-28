# Tasks: automation-agent-lease

## 1. Build
- [x] 1.1 Agent lease key, conflict-checked acquire, lease run id, `overlap` column and validation, `skip_overlapping` (`tinyassets/automations.py`).
- [x] 1.2 Per-agent submission, overlap policies, fair passes, per-key unstopped tracking (`tinyassets/runtime/assigned_queue_consumer.py`).
- [x] 1.3 Surface: `overlap` create field, projection, refusal sentence, served guidance.

## 2. Prove
- [x] 2.1 Tests through the real consumer (`tests/test_automation_agent_lease.py`); existing lease and dead-holder suites moved to agent keys.
- [x] 2.2 Mutation-check the key, the legacy exclusion both ways, each policy, fairness, and the dead-holder proof.
- [ ] 2.3 gpt-6-astra refute round: cross-user reach and runaway cost.
- [ ] 2.4 Deploy; `python scripts/deployed_sha.py --assert-contains <sha>`.

## 3. Land
- [ ] 3.1 Sync delta into `openspec/specs/user-owned-automations/`, archive.
