## 1. Ledger and count rule

- [x] 1.1 `tinyassets/engine_admissions.py`: `admit` (atomic count-and-insert
      as `write`; refuses at `write_max` writes OR `total_max` rows in the
      window), `attach_run`, `reclassify_read`, `fired_only_reads`; additive
      schema migration (`kind`, `run_id`); tampered-ledger refusal on every
      entry point.
- [x] 1.2 `engine_mcp_server._engine_run_admit` delegates (same contract,
      same fail-open/fail-closed split; `want_ticket` returns the row id);
      `run_graph` and `automations.run_due_automation` bind the ticket to
      the started run; `_RUN_GRAPH_TOTAL_MAX = 60`.
- [x] 1.4 Codex round 1 (REJECT) folded: migration inside `BEGIN IMMEDIATE`
      (P0), tickets by row id (P2), automations bind (P1), 60 total (P1),
      `method_mismatch` settles as write (P2), missing data dir created (P2).
- [x] 1.5 Codex round 2 (REJECT) folded: a settlement before the bind is
      kept in `settlements` and applied at bind time (P1); failed/cancelled
      runs settle as reads from `update_run_status` (P1); the 60 arithmetic
      stated honestly (P1); unknown sinks stay writes (P2); `ledger_path`
      uses the canonical resolver (P2); the refusal names the cap (P2); the
      fail-open sentinel is in the spec (P2).
- [x] 1.6 Codex round 3 (REJECT, the last round) folded: a write settlement
      is final so a status rewritten to FAILED after the effects fired
      cannot downgrade it (P1); settlement rows expire on every settle
      (P2); the spec says a never-admitted run may leave an expiring
      settlement row (P2); every engine surface names the refusing cap
      (P2); `design.md` added for the storage-shape change (P2).
- [x] 1.3 `effectors.run_effects_for_branch` records one `(sink, verb)` per
      effect that ran (verb from the adapter's result, else from the packet
      via `packet_verb`) and settles the admission as a read when
      `fired_only_reads`.

## 2. Tests

- [x] 2.1 `tests/test_engine_admissions.py`: cap, reclassification frees the
      write budget, total bound holds for reads, tickets bind by row id,
      old-ledger migration (kept on a refusal), per-universe budgets, symlink
      refusal, `fired_only_reads` table.
- [x] 2.2 Dispatcher: GET-only run → read; PUT → write; refused-before-wire
      GET → read; no effect nodes → read; non-engine run → no ledger.
- [x] 2.3 Engine: `run_graph` writes the run_id into the admission row;
      automation runner binds its ticket; two first touches of a legacy
      ledger under 12 threads admit exactly one; tickets bind the right row
      under interleaving; a missing data dir is created and still capped;
      method_mismatch settles as write.

## 3. Proof and close

- [x] 3.1 Live 2026-08-30 03:42–04:48Z: the README job ran with retries (branch creations 56295893cd874d91/4a7042797aca49aa/c708d054aaa44ef5/aa504498a4b1499e, writes c1cd14f98b6e4af8 → 3f86d7b9fde04bff, PR d773d4d006ae45a8, undraft b77089dfa3c14d9e, merge 631bd6d61473416f) and was never refused; the ledger showed writes ≤ 15/20 throughout while heartbeat periods settled as `read`.
- [x] 3.2 Concern deleted; spec synced to `openspec/specs/engine-run-admissions/spec.md`; archived.
