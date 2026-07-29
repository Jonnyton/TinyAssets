## 1. Recovery Core

- [x] 1.1 Add failing tests for run discovery, attach/resume/new/down decisions, health mapping, and terminal failure behavior.
- [x] 1.2 Implement the stdlib watchdog, atomic health state, single-instance lock, request markers, and bounded supervisor launch/attach loop.

## 2. Windows Experience

- [x] 2.1 Implement the single-instance tray indicator with healthy/waiting/down states and status/log/restart/stop/exit actions.
- [x] 2.2 Implement an idempotent current-user Task Scheduler installer and uninstaller with an interactive-logon trigger.

## 3. Policy And Review

- [x] 3.1 Update the runbook, AGENTS.md, and canonical/mirrored OpenSpec skill with automatic-start and visible-health behavior.
- [x] 3.2 Obtain and fold an opposite-provider review of recovery safety, Windows integration, and duplicate-dispatch prevention.

## 4. Verification And Landing

- [x] 4.1 Pass focused tests, Ruff, PowerShell syntax checks, strict OpenSpec validation, skill/drift checks, and an isolated no-dispatch watchdog smoke.
- [x] 4.2 Sync/archive the change, retire its STATUS row, land one PR, install the task, and verify the tray attaches to the existing live drain without a second worker.
