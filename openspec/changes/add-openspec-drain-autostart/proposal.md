## Why

The drain is operationally invisible and requires a remembered manual launch,
so the host cannot tell whether the intended all-day production system is alive.
It must start reliably with the user's Windows session, recover after abrupt
shutdown, and expose unmistakable health without weakening the drain's failure
budgets.

## What Changes

- Add a stdlib watchdog that attaches to or resumes the newest unfinished drain,
  starts a fresh bounded run when appropriate, and records compact health state.
- Add a Windows tray indicator with running, waiting, and down states plus
  status-folder, log, restart, and stop actions.
- Add an idempotent Task Scheduler installer that starts the tray/watchdog at
  user sign-in, when subscription credentials and the interactive tray exist.
- Preserve abrupt-shutdown state and the exact drain identity for same-claim
  recovery; do not silently restart failure-budget or fatal stops.
- Make `Start the OpenSpec drain` the canonical human trigger while normal
  daily operation requires no trigger.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: Require sign-in autostart, abrupt-shutdown
  recovery, fail-closed watchdog behavior, and visible drain health controls.

## Impact

Adds one Python watchdog, two PowerShell Windows integration scripts, focused
tests, Task Scheduler state under the current Windows user, tray UI, and
runbook/process conventions. It does not change product runtime or public MCP
behavior and introduces no third-party dependency.
