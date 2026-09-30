---
severity: P2
title: A run waiting for its account's seat occupies a thread of the run pool every account shares
filed: 2026-09-30
summary: The run pool (TINYASSETS_RUN_MAX_CONCURRENT, default 4) is shared across accounts, and a prompt node waiting for a seat waits inside one of its threads, so one busy account's queued runs delay other accounts' runs.
---

# A run waiting for its account's seat occupies a shared run-pool thread

**Found:** while finishing seats-per-account, 2026-09-30.
**Area:** `tinyassets/runs.py` `_get_executor` / `_max_workers`,
`tinyassets/graph_compiler.py` `_run_agent_with_timeout`.

Seats are taken at the agent call, inside the run's worker. Every top-level run
(run_graph, inbound events) is a thread of `_parent_pool`, whose size is a host
setting (`TINYASSETS_RUN_MAX_CONCURRENT`, default 4) shared by every account on
the box. A free account that starts six runs holds two seats and parks up to two
more pool threads in the seat wait; the rest of the pool's FIFO, including other
accounts' runs, waits behind them.

The pool's sharing is older than seats: before them those threads ran model
calls instead of waiting. Seats make the delay longer (an account's runs drain
at its seat count, not the pool size) and make the occupied threads idle.

Automations and wakes do not have this problem: they try for a seat once per
poll before they claim an attempt, and park nothing.

**Shape of the fix:** take a top-level run's seat before it takes a pool thread
-- a per-account wait outside the pool, handing the seated run to the pool, the
way the automation worker does -- or give each account its own slice of the
pool. Either changes `runs.py`'s dispatch and its `wait_for` contract, so it is
its own change.
