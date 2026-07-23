## Why

The P0 triage workflow can stop before canonical re-probe when a bounded repair
fails, preventing persistent-red escalation. Its provider-exhaustion page also
invokes `pushover_page.py` with flags the existing CLI does not support, so the
intended emergency page is not executable.

## What Changes

- Invoke the existing Pushover CLI contract for provider exhaustion and page
  independently of the auto-repair gate.
- Make class-specific repair and restart failures non-terminal so the canonical
  re-probe determines recovery or persistent-red escalation.
- Add non-vacuous workflow tests that inspect the exact shell/step behavior and
  exercise the compatible Pushover dry-run interface where feasible.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `uptime-and-alarms`: The class-specific P0 triage contract now requires
  re-probe and visible persistent-red escalation after a failed bounded repair.

## Impact

Changes `.github/workflows/p0-outage-triage.yml`, its focused workflow tests,
and an unsynced delta spec. `scripts/pushover_page.py` remains the unchanged
canonical paging CLI owner.
