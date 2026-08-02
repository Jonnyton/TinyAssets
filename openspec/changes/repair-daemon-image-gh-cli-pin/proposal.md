## Why

Every daemon image build is failing because the Dockerfile pins GitHub CLI package `2.96.0`, which the configured signed apt repository no longer serves. This blocks production deployment of the approved V1 connector repair and every other uptime-track change.

## What Changes

- Replace the unavailable GitHub CLI package pin with the exact version currently published by GitHub's signed apt repository.
- Retain exact-version installation, the existing signed repository/key boundary, and fail-loud build behavior.
- Prove the repaired image through the normal build, deploy, and public-canary chain before resuming rendered V1 acceptance.

## Capabilities

### New Capabilities

- `daemon-image-build`: Exact, reproducible daemon-image dependency resolution and deployment admission.

### Modified Capabilities

None.

## Impact

`Dockerfile`, daemon image CI, the production deployment chain, and dated release evidence. No application API, storage, authorization, or runtime semantics change.
