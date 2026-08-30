## 1. Change

- [x] 1.1 `admit_detail(kind=…)`: `engine` counts toward the total only.
- [x] 1.2 write_graph, remix and brain writes pass `kind="engine"`.
- [x] 1.3 Tests: 30 engine writes leave the 20-write budget untouched and are
      refused at the total; write_graph is seen passing `kind="engine"`.

## 2. Proof and close

- [ ] 2.1 Live: the README fix job that was refused at 04:5xZ completes after
      deploy without a write-cap refusal while the universe authors branches.
- [ ] 2.2 Sync the delta into `openspec/specs/engine-run-admissions/spec.md`;
      archive.
