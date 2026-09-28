# Tasks: usage-limits-replace-caps

## 1. Build
- [x] 1.1 Rolling-day run meter, ledger index, day refusal (`engine_admissions.py`, `engine_mcp_server.py`).
- [x] 1.2 invoke_branch: remove the depth cap, charge and bind every child, name stack exhaustion, pool-derived bound for blocking version invokes (`graph_compiler.py`, `runs.py`).
- [x] 1.3 Automations: drop the ceiling and cadence floors; charge registration (`automations.py`, `api/automations.py`).
- [x] 1.4 Schedules/subscriptions: drop per-owner counts; floor = tick; charge registration and every triggered run (`scheduler.py`, `api/runtime_ops.py`, `api/runs.py`).
- [x] 1.5 Agent definitions: drop the component count (`custom_agents.py`, `agent_runtime.py`).
- [x] 1.6 Remove `NodeEnqueueBudget` threading; delete the served-recursion concern.

## 2. Prove
- [x] 2.1 Tests through the real ledger, compiled graph and triggered-run path (`tests/test_usage_limits.py`); cap tests rewritten to the usage contract.
- [x] 2.2 Mutation-check each meter site.
- [x] 2.3 gpt-6-astra refute round: cross-user reach and runaway cost (ADAPT; four P1s folded, foreground fail-open kept with reason).
- [ ] 2.4 Deploy; `python scripts/deployed_sha.py --assert-contains <sha>`.

## 3. Land
- [ ] 3.1 Sync deltas into `openspec/specs/`, archive.
