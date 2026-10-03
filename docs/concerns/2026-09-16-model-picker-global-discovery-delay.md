---
severity: P3
title: Model picker client-side global freshness
filed: '2026-09-16'
summary: the server no longer discovers on a picker read; the CLIENT still expires and disables the whole catalogue as one unit
---

# The client still treats freshness as one global fact

Filed 2026-09-16 as a P2 with two halves. **The server half is fixed** and the
remainder is narrower, so this is downgraded rather than deleted.

## Fixed (2026-10-03)

The original cause was synchronous per-member discovery inside
`providers/served_model_plan.py`: a picker read ran `discover_native_models_sync`
inline for every accepted member, so a slow or expired source delayed selecting
a DIFFERENT accepted source and its execution.

A display read now serves a warm per-source catalogue from
`providers/shortlist_refresh.py` and never runs discovery. Both of the things
this concern asked for are structural there rather than tuned:

- **per-source freshness** — the cache is keyed `(base, owner, universe,
  provider)`, so one source being cold, stale or broken says nothing about any
  other;
- **discovery isolation** — a read is a dict lookup, so the slowest source
  costs nothing. `test_one_wedged_source_does_not_delay_another` pins it with a
  source whose refresh never returns.

Warming happens on connect (`credential_vault._warm_after_deposit`) and then on
a TTL that a read schedules without waiting for it. Execution is untouched:
`prepare_selected_model` still discovers fresh at launch with its own custody
and freshness checks, and an entry past `USABLE_AGE` is withheld rather than
served — the concern's own warning against "enabling stale choices globally".

## What remains

`tinyassets/onboarding/app.html` still models freshness as ONE fact for the
whole catalogue:

- `fresh()` reads a single `this.expires`, set to
  `Math.min(Date.now()+300000, ...expiries)` — the earliest expiry of ANY
  source expires the entire picker;
- `refresh()` sets `this.busy`, which disables every choice while any refresh
  is in flight.

The practical impact is much smaller now, because the read it waits on no
longer performs discovery. But the shape is still global: one expired source
re-staleing the whole list, and a refresh briefly disabling choices that were
never affected. Per-source rendering would finish this.

Do not claim this closed by promoting the refresh button. The remaining work is
in the client's freshness model, not in how visible the control is.
