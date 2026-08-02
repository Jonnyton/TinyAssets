## Why

Five unsigned Windows installer verification jobs remained inside one lifecycle step until GitHub force-cancelled them after the configured 15-minute job timeout plus its five-minute cancellation grace, even though the lifecycle script was intended to bound each phase to 180 seconds. A release gate that can lose its logs and occupy a runner for twenty minutes is not reliable evidence for the Tier-2 desktop path.

## What Changes

- Run the Windows installer lifecycle under a stdlib Python parent supervisor with one total deadline shorter than the GitHub job timeout.
- Make the inner lifecycle report phase start, completion, timeout, and exact process identity while leaving total-deadline enforcement to the supervisor.
- Capture child output in durable files and replay it before the supervisor returns so a caught hang retains diagnostic evidence.
- Add a real Windows regression that proves an intentionally hung child is terminated and reported within the outer deadline.
- Keep the job-level timeout as defense in depth, with enough separation that normal supervisor failure completes before GitHub cancellation starts.

## Capabilities

### New Capabilities

- `desktop-release-lifecycle-ci`: Bounded, diagnostic execution of the exact unsigned Windows installer lifecycle in release CI.

### Modified Capabilities

None.

## Impact

The change affects `.github/workflows/desktop-release.yml`, the Windows lifecycle script and its focused tests, and one new stdlib Python supervisor under `tests/desktop_install/`. It does not publish or sign an installer, change application runtime behavior, or satisfy the clean-machine acceptance matrix.
