## 1. Build

- [x] 1.1 Adapter reports `request_bytes` / `response_bytes` on delivered results.
- [x] 1.2 `EffectChain`: `dispatches`, `bytes_out`, `universe_id`; the check in
      `dispatch_node_effects` before firing (count) and the charge after
      (bytes), `effect_budget_exhausted` naming budget/usage/window.
- [x] 1.3 Ledger: `dispatch_budget(universe_id, ts, dispatches, bytes)`,
      `charge_dispatch`, rolling-hour sums, prune at one window; per-hour
      refusal.
- [x] 1.4 Taxonomy class `effect_budget_exhausted` (actionable by the chatbot:
      split the work / wait for the window), tests, plugin mirror.

## 2. Close

- [x] 2.1 Spec delta synced into `engine-run-admissions`; archive.

Closure verification, 2026-09-08: implementation landed in #2731
(`98b4896485b22c0de30d9d3285267718380cdb2d`), followed by threshold changes in
#2770. `python -m pytest -q tests/test_run_usage_budgets.py` passed all five
tests on Windows. Canonical adapter, effect-chain and admissions-ledger sources
were re-read; plugin was rebuilt in the resource-policy correction lane.
The delta/main requirement now describe actual node-level counting, current
5,000 per-run dispatch threshold, post-dispatch bytes, fail-open hourly meter
and absent commercial tier wiring. They do not assert exact pre-wire global
byte enforcement. This closes stale bookkeeping, not those remaining limitations.
