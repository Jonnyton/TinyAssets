## Why

Live 2026-08-30 04:5xZ, universe `u-01kxm1vszd8hwp7em418asq8h9`: asked for
a one-line README fix, the universe was refused by `run_graph rate limit
reached (max 20 runs that write per 60m)`. The ledger held 18 write rows in
the hour; nine were unattached engine writes — the universe's own
`write_graph` branch authoring (it built about eight branch variants while
working the job). External writes were nine. The write cap is the
effect-spam bound (Codex gate #5); branch authoring is a durable, reversible
mutation of the universe's own state and was never the spam it guards
against. Founder 2026-08-30: "drive this all to completion and testing".

## What Changes

- `engine_admissions.admit_detail` takes `kind`: `write` (a run; may settle to
  `read`) or `engine` (write_graph, remix, brain). An `engine` admission never
  counts toward the 20/h write budget; it is refused by its own bound (40/h,
  two thirds of the total, so runs always keep at least 20 — Codex: 60 failed
  `write_graph` calls could otherwise take the whole budget from runs) or by
  the total (60/h). An `engine` row is never bound to a run or reclassified.
  A ledger refusal (unusable/tampered) is reported as such, not as a quota.
  Rows outside the window are pruned on the next admission. Other kinds are
  refused (`ValueError`). Not done: refunding an engine admission whose write
  then fails validation — the engine bound already keeps runs safe from that.
- `_engine_run_admit(kind=…)`; the three durable engine writes pass
  `kind="engine"`. Runs and automations are unchanged.
- Storage: no schema change (`kind` already exists; a third value).

## Impact

`tinyassets/engine_admissions.py`, `tinyassets/engine_mcp_server.py`;
tests in `tests/test_engine_admissions.py` and `tests/test_engine_mcp_server.py`.
An honest job that authors several branch variants no longer exhausts the
effect budget; a runaway branch-authoring loop is still bounded at 60/h.
