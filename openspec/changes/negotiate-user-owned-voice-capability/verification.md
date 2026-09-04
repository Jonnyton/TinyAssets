# Verification

## 2026-09-04 production dark deployment

- Environment: production at `https://tinyassets.io/mcp` and `https://tinyassets.io/mcp/app`.
- Merge: PR #2841 merged as `84ee8ae6847dc4aa929b025ad65ea47fe9e96449` at `2026-09-04T06:28:16Z`.
- Deployment command: `gh run view 33844772622 --json status,conclusion,headSha,event,workflowName,jobs`.
  Result: `Deploy prod` completed successfully for the exact merge SHA at
  `2026-09-04T06:33:31Z`; the fail-safe deploy reported a healthy container on
  image digest `sha256:9fcbecabd921b12397f3d447157e9be228a43885841e4712975da1f6a2e782d0`.
- Release receipt command: `gh run view 33844772622 --log`.
  Result: the deploy published `release-state.git_sha` equal to the exact merge
  SHA, with `active_identity_status=running_healthy` and
  `forward_deploy_status=succeeded`.
- Public canary: the same authenticated deploy job ran
  `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`
  successfully after the container became healthy. The local shell did not
  contain the canary bearer, so no unauthenticated local rerun is represented as
  equivalent evidence.
- Dark-state source check: `Invoke-WebRequest https://tinyassets.io/mcp/app`
  returned HTTP 200 and the served configuration contained
  `"voice": {"enabled": false, ...}`. No Voice flag was set or changed during
  this delivery; both Voice-specific flags retain their default-off policy.
- Rendered check: a host-visible browser loaded the signed-in founder app. The
  single Voice control was present beside the composer, disabled, and the
  rendered status read `Voice is not enabled on this TinyAssets host.` No Voice
  control was clicked and no microphone, provider, credential, or disclosure
  action occurred.
- CI exception: desktop release run `33843457460` was cancelled after the PR
  merged. Its exact-artifact Windows install step was still in progress, so it
  is not claimed as passed. This server/app change instead relies on the green
  focused/required suites, platform builds, runtime mirror/import probe, exact-
  head opposite-provider review, exact merge-image deploy, and authenticated
  production canary recorded above.

Task 5.3 remains open: production proves the disabled state, while rendered
unpowered/incompatible acceptance and any ready-state proof remain deliberately
outside this dark deployment. Task 5.4 remains blocked on Jonathan naming an
eligible already-authorized current provider and explicitly authorizing the
bounded live microphone proof. Voice must not be enabled merely to close either
task.
