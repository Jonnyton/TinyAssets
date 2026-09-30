---
severity: P1
title: Account limits are keyed per universe
filed: 2026-09-30
summary: Unlimited universe creation exposes a mismatch between account-level storage and seat limits and their per-universe accounting keys.
---

Cross-family Claude review of PR #4136, merged-main code at 4454d904.
Verdict: DISAGREE_EVIDENCE. Static analysis; no multi-universe live proof run.

`tinyassets/universe_server.py::_universe_birth_refusal` now retains only the
identity check. `tinyassets/universe_seats.py::_limits` resolves tier by universe,
and seat admission counts by universe ID. `tinyassets/usage_policy.py` describes
storage and seats per universe. A subject creating N universes can therefore
receive N independent seat allowances rather than one account allowance.
The reviewer also raised storage aggregation; actual storage enforcement needs
tracing before claiming a demonstrated storage bypass. Global provider slots
remain bounded, but account-level fairness is not established by that bound.

Reconcile the account aggregate with the seat/storage implementation lane.
Preserve unlimited universe creation: a universe-count paywall is not the fix.
