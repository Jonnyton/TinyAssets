## 1. Exact Coordination Truth

- [x] 1.1 Add failing claim-check regressions proving exact `STATUS.md` atoms do not collide while every non-STATUS overlap still blocks.
- [x] 1.2 Implement row-scoped STATUS overlap semantics and update the cross-provider Files-cell rule; verify `tests/test_claim_check.py` passes.
- [x] 1.3 Add failing OpenSpec-flow regressions proving `--ref` reads one immutable Git snapshot, classifies host-owned rows, and fails closed on an invalid ref.
- [x] 1.4 Implement the stdlib-only exact-ref flow snapshot and host-owned classification; verify `tests/test_openspec_flow.py` and working-tree audit behavior pass.

## 2. Deterministic Backlog Refinery

- [x] 2.1 Add failing supervisor regressions proving zero claim pressure yields bounded `REFINERY` hints from exact-current-main flow and excludes in-flight, host-owned, and invalid changes.
- [x] 2.2 Add failing lifecycle regressions proving a refinery hint rejects `NO_CANDIDATE`, appears in the worker brief, and remains subject to recent-block suppression.
- [x] 2.3 Implement combined claim/flow snapshots, the coordination-only refinery brief, and four-part exhaustion validation; verify the focused supervisor suite passes.

## 3. Verification And Live Repair

- [ ] 3.1 Update PLAN/AGENTS/runbook truth, run Ruff, focused and adjacent tests, strict OpenSpec validation, and record a short `REFLECTION.md`.
- [ ] 3.2 Obtain independent exact-head review, merge and sync/archive through a separate foldback PR, refresh the detached controller, and prove live health cannot remain idle while a refinery target exists.
