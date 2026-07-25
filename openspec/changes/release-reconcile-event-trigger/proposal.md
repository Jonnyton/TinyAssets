## Why

Release reconciliation currently relies on a nominal 15-minute schedule even
after GitHub has proved that current `main` builds successfully under Docker
smoke; live history shows the schedule is load-shed to roughly hourly-or-longer
intervals. The existing corrective dispatch also uses `GITHUB_TOKEN`, so its
manual image build does not reliably trigger the downstream deploy. A trusted
smoke completion is a host-independent opportunity to re-evaluate sooner, but
the release chain must preserve active work and explicitly reach deployment.

## What Changes

- Trigger release reconciliation when an own-repository `Docker build smoke`
  push or manual run completes successfully for `main`; reject pull-request,
  fork, failed, and non-main provenance.
- Retain the existing 15-minute schedule and manual dispatch paths.
- Retain the fixed `release-reconcile` concurrency group with
  `cancel-in-progress: false` so event bursts coalesce without cancelling an
  active reconciliation.
- Defer rather than dispatch when GitHub run-state queries fail or when a
  current-main image build/deploy is already queued or running.
- Ensure reconcile-initiated image builds cannot cancel active push builds,
  wait for the requested build, and explicitly dispatch `Deploy prod` with its
  immutable short-SHA tag when `main` has not advanced.
- Add exact-script contract, decision, security, and coalesced-load tests plus
  a freshness-stamped proof artifact.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: Expand scheduled release reconciliation with a trusted
  Docker-smoke completion trigger, fail-closed run-state checks, active-chain
  preservation, explicit post-build deploy dispatch, and executable
  coalescing proof.

## Impact

This changes `.github/workflows/release-reconcile.yml` and the manual-run
cancellation policy in `.github/workflows/build-image.yml`, adds focused
workflow/load tests and a proof artifact, and updates the existing
uptime-and-alarms requirement. It adds no API, secret, dependency, or elevated
permission.
