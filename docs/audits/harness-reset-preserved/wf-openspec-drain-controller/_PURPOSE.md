# Purpose

- Lane: persistent read-only controller checkout for the all-day OpenSpec drain.
- Base: current `origin/main` at controller creation.
- Authority: the controller checkout is never an implementation workspace;
  each disposable worker creates and claims its own purpose-named worktree.
- Runtime: one Codex-backed worker at a time, one PR per worker, finite
  time/slice/failure budgets.
- Operations: `docs/ops/2026-07-28-openspec-drain-supervisor.md`.
