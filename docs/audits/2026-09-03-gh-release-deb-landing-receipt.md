# Immutable GitHub CLI release landing receipt

**Date:** 2026-09-03  
**Author family:** Codex  
**Review family:** Claude  
**Implementation head:** `632a360c3c4534dbb79590d7c40439a0b8628ebe`  
**Verdict:** APPROVE for the exact implementation head above and the receipt-only
PR head named by the `Drain-Review-Head` line in pull request #2803.

## Scope

The production image had become undeployable because the Dockerfile requested
an exact `gh` version from cli.github.com's apt repository after that repository
removed the version. This change installs the immutable GitHub release `.deb`
instead, verifies GitHub-published SHA-256 digests independently for amd64 and
arm64, adds a regression test for that supply-chain contract, and deletes the
resolved recurring-outage concern plus its index row.

## Independent review

A read-only Claude reviewer inspected the complete diff from
`33324d05555c5c5245a37dfd0d4355c33b46729c` through the implementation head and
returned `AGREE` / `VERDICT: APPROVE`.

The reviewer confirmed:

- the new final-stage `TARGETARCH` handling matches the already-proven rustup
  architecture selection in the builder stage;
- BuildKit supplies `TARGETARCH=amd64` for the repository's native Linux buildx
  jobs, while unsupported or empty values fail explicitly;
- download, checksum, and local apt-install failures all terminate the layer;
- the v2.100.0 asset names and both embedded digests match the supplied official
  GitHub release metadata;
- installing through apt from the local `.deb` preserves dependency resolution;
- removing the concern is justified because its prescribed immutable-release,
  checksum-verified fix is exactly what the implementation supplies, with no
  dangling concern reference.

## Verification

- 99 focused Dockerfile, image-workflow, and workspace-oracle tests passed on
  Windows/Python 3.11+ before review.
- The independent reviewer reran `tests/test_dockerfile_shape.py`: 43 passed.
- Ruff and `git diff --check` passed.
- A fresh query of GitHub's v2.100.0 release API returned the embedded SHA-256
  digests for both `.deb` assets.
- Docker Desktop was not running locally, so the pull request's Linux buildx
  smoke job is the authoritative real-image proof.

The later receipt-only commit changes no Dockerfile or test behavior. The PR
body binds that final documentation head to this artifact without requiring a
self-referential commit hash.
