## Why

`workflow_run` invokes the uptime canary for every completed production deploy, but the probe job intentionally skips after a failed deploy. Its empty outputs currently fall through the alarm sink's non-red branch as if they were green, which can close an active P0 incident without a successful observation.

## What Changes

- Treat the alarm sink's current-run result as an explicit `green`, `red`, or unknown state.
- Make unknown or unrecognized results a no-op: no label/issue mutation, no page, and no canary workflow failure.
- Gate recovery and incident closure on the literal `green` result while preserving the existing red threshold, issue-update, and paging behavior.
- Add workflow regression coverage for the no-op ordering and literal-green recovery gate.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: The public-canary incident lifecycle must distinguish a verified green observation from an unavailable or unrecognized probe result.

## Impact

- `.github/workflows/uptime-canary.yml`
- `tests/test_uptime_canary_workflow.py`
- `openspec/specs/uptime-and-alarms/spec.md`
