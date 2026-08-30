## 1. Build

- [ ] 1.1 Adapter reports `request_bytes` / `response_bytes` on delivered results.
- [ ] 1.2 `EffectChain`: `dispatches`, `bytes_out`, `universe_id`; the check in
      `dispatch_node_effects` before firing (count) and the charge after
      (bytes), `effect_budget_exhausted` naming budget/usage/window.
- [ ] 1.3 Ledger: `dispatch_budget(universe_id, ts, dispatches, bytes)`,
      `charge_dispatch`, rolling-hour sums, prune at one window; per-hour
      refusal.
- [ ] 1.4 Taxonomy class `effect_budget_exhausted` (actionable by the chatbot:
      split the work / wait for the window), tests, plugin mirror.

## 2. Close

- [ ] 2.1 Spec delta synced into `engine-run-admissions`; archive.
