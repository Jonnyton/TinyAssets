# Implementation evidence

## Overnight baseline

- Run: `openspec-drain-auto-20260728-233434`
- Recovery: the same run identity resumed after abrupt shutdown.
- Outcome: four verified work packages were preserved, with focused test
  counts of 75, 112, a diff-only slice, and 269 respectively.
- Delivery: zero pull requests; three packages explicitly reported read-only
  linked-worktree Git metadata, cancelled publication, or both.

## Post-fix proof

- 2026-07-29 Windows disposable linked-worktree probe:
  write-capable Codex staged and committed `probe.txt` as
  `5e63171197665ff792e7ae39b9318a54b298222f`.
- 2026-07-29 focused gate: 112 tests passed; Ruff clean; strict OpenSpec
  validation passed; PowerShell and VBScript syntax/usage checks passed.
- Independent Claude review: `APPROVE` after the existing
  `approval_policy=never` invariant was pinned in a regression assertion.
- PR #1854 merged as `a56cb84c`.
- 2026-07-29 11:33 PDT installed task action:
  `wscript.exe //B //Nologo launch_openspec_drain_tray.vbs <repo>`.
- Installed process chain:
  `wscript.exe` -> hidden `powershell.exe` tray -> watchdog -> supervisor.
- Fresh run `drain-20260729-113341-edda35` reported `health=running`,
  admitted attempt 1, and launched Codex with
  `-c approval_policy=never -s danger-full-access --add-dir
  C:\Users\Jonathan\Projects\TinyAssets\.git`.
