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
  `read`) or `engine` (write_graph, remix, brain). An `engine` admission is
  refused only by the total bound (60/h) and never counts toward the 20/h
  write budget. Other kinds are refused (`ValueError`).
- `_engine_run_admit(kind=…)`; the three durable engine writes pass
  `kind="engine"`. Runs and automations are unchanged.
- Storage: no schema change (`kind` already exists; a third value).

## Impact

`tinyassets/engine_admissions.py`, `tinyassets/engine_mcp_server.py`;
tests in `tests/test_engine_admissions.py` and `tests/test_engine_mcp_server.py`.
An honest job that authors several branch variants no longer exhausts the
effect budget; a runaway branch-authoring loop is still bounded at 60/h.
