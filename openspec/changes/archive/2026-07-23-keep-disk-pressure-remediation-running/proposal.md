## Why

`disk_watch.py` intentionally exits 1 when disk pressure is present, but systemd
currently treats that alert result as a failed `ExecStart` and can skip the
rotation and auto-prune commands that would relieve the pressure. The unit must
recognize the intentional alert status without accepting every failure status.

## What Changes

- Treat exit status 1 as successful for the disk-watch oneshot unit.
- Preserve the declared alert, transcript-rotation, then auto-prune command order.
- Correct unit comments so they describe systemd's actual sequential behavior.
- Add a regression sentinel for the accepted status and command ordering.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: Disk-pressure alert status 1 no longer stops the ordered
  transcript-rotation and auto-prune remediation chain.

## Impact

The repository systemd unit, its focused sentinel tests, and the canonical
uptime-and-alarms requirement change. `disk_watch.py` exit semantics, timer
cadence, cleanup scope, and live host installation state do not change.
