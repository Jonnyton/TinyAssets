## Context

The daemon runtime image installs GitHub CLI from GitHub's signed apt repository at an exact package version. Main currently pins `2.96.0`; image run `30734421652` proved that version is no longer present, so apt exits 100 before an image can publish. On 2026-08-01, GitHub's official release API and signed package index both identified `2.97.0` as the current release/package.

## Goals / Non-Goals

**Goals:**

- Restore the image build with a currently served exact package pin.
- Preserve signed-origin verification, reproducibility, and fail-loud behavior.
- Prove the complete build → deploy → public-canary chain before resuming rendered acceptance.

**Non-Goals:**

- Do not unpin GitHub CLI or add a floating `latest` dependency.
- Do not change the image's GitHub effect authority, credentials, or application runtime behavior.
- Do not redesign release reconciliation in this bounded repair.

## Decisions

### Pin the exact official package version

Set `GH_VERSION=2.97.0`, the version returned by both the official GitHub CLI release API and the configured signed apt repository on 2026-08-01. An exact pin keeps builds reproducible. Floating the package would hide supply-chain drift and make rollback analysis ambiguous.

### Keep the existing signed apt boundary

Retain the existing GitHub repository signing key and `signed-by` apt source. Downloading an ad hoc release binary would require a second checksum/update mechanism and expand this repair.

### Treat repository expiry as a visible release failure

If a future exact version disappears, the image build must fail before publication or deployment. A follow-up pin repair is safer than silently accepting an unreviewed version.

## Risks / Trade-offs

- [Risk] GitHub's apt repository may retire exact versions again. → Keep the failure loud and repair the pin against the official release and signed package sources.
- [Risk] A newer CLI may change command behavior. → Retain existing Dockerfile shape tests and verify the image, deployment, canary, and affected rendered workflow.
- [Risk] A successful source merge could still fail to deploy for an unrelated production fence. → Record build and deploy run identities separately and do not claim the connector contract live until both pass.

## Migration Plan

1. Verify the exact replacement version against official sources.
2. Update only the Dockerfile pin and run focused/static checks.
3. Obtain independent exact-head review and merge normally.
4. Build and publish the exact merged-main image; allow production deployment only from that successful build.
5. Run the public canary and rendered connector acceptance.

Rollback production to the prior known-good image if deployment health regresses. The source change is independently revertible, but rebuilding the retired `2.96.0` pin is not a valid rollback while that package remains unavailable.

## Open Questions

None for this bounded repair.
