## Why

Change `no-graph-size-caps` (2026-08-30, #2730) removed the served build's
structural limits (100 nodes, 5 effect nodes) on the founder's direction:
"we can limit them in other ways — if they want to run a big graph then
that uses up a lot". Codex's review of the workspace design named what the
shape caps had been silently covering: nothing bounds the *number* of effect
dispatches or the *bytes* a single run may move. The remaining gates are
authority and idempotency (consent, endpoint allowlists, one fire per node
per run) and per-call caps (8 MiB body, 5 MiB response, 30 s), plus 60 runs
per hour — so one run can issue unboundedly many bounded calls.

## What Changes

Usage budgets, enforced at dispatch time and named in the refusal:

- **Per root run:** at most 500 effect dispatches and 256 MiB of outbound
  bytes (request body + response body, charged at the per-call caps when a
  size is unknown).
- **Per universe per rolling hour:** at most 5,000 dispatches and 2 GiB,
  kept in the engine admissions ledger next to run admissions.
- A dispatch past a budget fails its node as `effect_budget_exhausted`
  with the budget, the usage and the window named; later nodes do not run
  (design D1 of `sandboxed-code-node` already stops the chain on a failed
  node). The numbers are defaults, tier-raisable, never a shape rule.
- The authenticated-call adapter reports `request_bytes` and
  `response_bytes` on every delivered result so the charge is exact.

## Impact

- `tinyassets/effectors/__init__.py` (`EffectChain` counters, the check in
  `dispatch_node_effects`), `tinyassets/effectors/authenticated_external_call.py`
  (byte fields), `tinyassets/engine_admissions.py` (`dispatch_budget`
  table, `charge_dispatch`, window sums), `tinyassets/runs.py` (universe id
  on the chain), taxonomy, tests, plugin mirror.
- Spec: `engine-run-admissions` (ADDED: outbound volume bounded by usage
  budgets).
