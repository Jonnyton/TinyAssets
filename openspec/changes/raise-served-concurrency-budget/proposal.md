# Raise served-provider in-flight budget for real concurrency

## Why

A user must be able to drive their universe from **many surfaces at once**
(connector, web app, desktop app, phone) **while concurrent LangGraph
automations run**, and **many users** must do the same simultaneously. Live
testing on 2026-08-23 showed the opposite: a burst of turns across surfaces
returned `Provider authority budget is exhausted; reconnect or rebind your
provider` after only ~2 concurrent turns.

Root cause: the serving binding's in-flight ceiling `_MAX_TOKENS = 32_768`
(`tinyassets/provider_serving_binding.py`). A served turn reserves
`len(system+prompt bytes)` of budget (`providers/router.py` — a rebuilt
persona/brain system prompt is ~15–30 KB) plus its output, so the SECOND
simultaneous turn across any surface gets `output_tokens < 1` and is held. This
ceiling bounds only UNSETTLED (concurrent) reservations — a settled turn
RELEASES — so it is a **concurrency runaway guard, not a cumulative spend
limit** (the user's own deposited subscription meters real spend upstream). It
was sized like a spend cap, which is the wrong shape for the required
concurrency.

## What Changes

- Raise `_MAX_TOKENS` 32_768 → 4_000_000 and `_MAX_COST_MICROUNITS`
  10_000_000 → 400_000_000 on the serving binding (kept consistent so the
  token cap, not the cost cap, is the effective ceiling). Sized for realistic
  single-user concurrency (~90 simultaneous worst-case ~45 KB turns).
- The true runaway backstops are unchanged: the rolling per-hour invocation cap
  (`_MAX_BINDING_INVOCATIONS = 10_000`), the engine-run rate limit (20/hr), and
  the user's metered subscription. The two independent guards in
  `reserve_served_provider_budget` (invocation-runaway + in-flight token) are
  untouched — only the token ceiling magnitude changes.
- Per-binding isolation is preserved: each universe's binding has its own
  ceiling, so many users concurrently do not contend (cross-user isolation is
  inherent, not an allowlist).

## Impact

- Affected specs: `provider-routing` (served-provider budget admission).
- Affected code: `tinyassets/provider_serving_binding.py` + packaging mirror.
- New bindings pick up the ceiling at creation; a pre-existing binding is
  re-bound once to adopt it (the error's own "reconnect or rebind" recovery).
- No change to spend enforcement (there is none here by design — spend is on the
  user's own subscription); this is a runaway-guard magnitude correction.
