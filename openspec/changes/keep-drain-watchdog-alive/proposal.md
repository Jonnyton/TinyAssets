## Why

The local OpenSpec drain watchdog has twice exited while its supervisor remained healthy after Windows refused an atomic `health.json.tmp` replacement. The tray correctly turns red for stale health but never relaunches the failed watchdog, and the current logon-only scheduled task cannot recover a tray process that exits later in the session.

## What Changes

- Make transient health-publication contention non-fatal to the watchdog while preserving atomic, truthful health state.
- Have the tray detect stale or unavailable watchdog health and relaunch the watchdog with a bounded cooldown.
- Add a periodic current-user Task Scheduler trigger so a dead tray is relaunched without a terminal or daily prompt.
- Preserve single-watchdog and single-supervisor fencing and never display running while health is stale, idle, or blocked.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: require bounded self-healing after watchdog or tray failure during an interactive Windows session.

## Impact

This changes the local drain watchdog, tray host, Windows autostart installer, focused tests, and the installed `TinyAssets OpenSpec Drain` scheduled task. It does not activate cloud execution, market compute, or a second concurrent worker.
