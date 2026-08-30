## 1. Change

- [x] 1.1 `admit_detail(kind=…)`: `engine` counts toward the total only.
- [x] 1.2 write_graph, remix and brain writes pass `kind="engine"`.
- [x] 1.3 Tests: 30 engine writes leave the 20-write budget untouched; the
      41st engine write is refused by the engine cap while runs still get
      their 20; an engine row is never bound or reclassified; rows outside
      the window are pruned; the ledger refusal is not worded as a quota;
      write_graph is seen passing `kind="engine"`.
- [x] 1.4 Codex round 1 (ADAPT) folded: engine cap 40 (P1), ledger refusal
      wording (P2), prune at one window (P2), engine rows unbindable (P2).
      Not done: refunding a validation-failed engine write's admission.

## 2. Proof and close

- [x] 2.1 Live 2026-08-30 05:59:49Z (prod `6c8ab0ca`): write run
      `473073dd02a444c1` admitted with no cap refusal right after three
      `engine` rows (284, 286, 287 - the universe authoring its branch);
      ledger for the hour: 9 reads / 7 writes. The run itself opened a wrong
      PR (#2714, closed) - that is the `body-transform-replace` change, not
      the budget.
- [x] 2.2 Synced into `openspec/specs/engine-run-admissions/spec.md`; archived.
