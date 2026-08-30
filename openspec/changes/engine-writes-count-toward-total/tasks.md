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

- [ ] 2.1 Live: the README fix job that was refused at 04:5xZ completes after
      deploy without a write-cap refusal while the universe authors branches.
- [ ] 2.2 Sync the delta into `openspec/specs/engine-run-admissions/spec.md`;
      archive.
