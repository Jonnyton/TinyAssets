## 1. Ledger and count rule

- [x] 1.1 `tinyassets/engine_admissions.py`: `admit` (atomic count-and-insert
      as `write`; refuses at `write_max` writes OR `total_max` rows in the
      window), `attach_run`, `reclassify_read`, `fired_only_reads`; additive
      schema migration (`kind`, `run_id`); tampered-ledger refusal on every
      entry point.
- [x] 1.2 `engine_mcp_server._engine_run_admit` delegates (same contract,
      same fail-open/fail-closed split); `run_graph` binds the admission to
      the started run; `_RUN_GRAPH_TOTAL_MAX = 120`.
- [x] 1.3 `effectors.run_effects_for_branch` records one `(sink, verb)` per
      effect that ran (verb from the adapter's result, else from the packet
      via `packet_verb`) and settles the admission as a read when
      `fired_only_reads`.

## 2. Tests

- [x] 2.1 `tests/test_engine_admissions.py`: cap, reclassification frees the
      write budget, total bound holds for reads, attach binds newest
      unattached row, old-ledger migration, per-universe budgets, symlink
      refusal, `fired_only_reads` table.
- [x] 2.2 Dispatcher: GET-only run → read; PUT → write; refused-before-wire
      GET → read; no effect nodes → read; non-engine run → no ledger.
- [x] 2.3 Engine: `run_graph` writes the run_id into the admission row.

## 3. Proof and close

- [ ] 3.1 Live: a one-line file change with one retry completes through the
      app without meeting the cap (run ids, date).
- [ ] 3.2 Delete `docs/concerns/2026-08-29-run-rate-cap-stalls-a-normal-github-job.md`;
      sync the spec delta into `openspec/specs/`; archive this change.
