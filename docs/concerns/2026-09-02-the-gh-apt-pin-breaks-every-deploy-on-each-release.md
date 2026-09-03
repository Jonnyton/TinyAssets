# Pinning `gh` to an exact apt version breaks every deploy, on every gh release

**Filed:** 2026-09-02, after it blocked the Play-launch lane for the second time.
**Verified:** yes, and the mechanism is provable in one command:

```
$ curl -fsSL https://cli.github.com/packages/dists/stable/main/binary-amd64/Packages \
    | grep -A1 '^Package: gh$' | grep '^Version:'
Version: 2.99.0
```

The GitHub CLI apt repository carries **exactly one** version of `gh`. So
`Dockerfile:130`'s `ARG GH_VERSION=<exact>` is not a pin against drift — it is a
fuse that blows the moment upstream ships a release, with
`E: Version 'x.y.z' for 'gh' was not found` and exit 100.

**Severity:** P2 by blast radius but it stops everything: `build-image` fails,
`deploy-prod` is skipped for want of an image, and *nothing reaches production*
however green the tests are. `main` sat undeployed for hours today
(`1cdc251e`, `4a6862f8`), which also means Hard Rule 14's "merged is not
deployed" was silently true for every PR that landed in the window.

## It has happened before

`250f931a` — *"ci: unblock deploy — bump gh 2.97.0→2.98.0"* (#2477) — is the same
incident with different digits. The fix then was to advance the fuse by one
release, which guaranteed today's outage. I have just done it again
(2.98.0 → 2.99.0) because production being undeployable is the more urgent
problem, but a third occurrence is now certain unless the shape changes.

## The shape that would end it

The pin exists for supply-chain integrity: an unpinned `apt-get install gh`
installs whatever is served that day. Both properties are achievable at once —
the repo just is not the right source for an exact version.

1. **Install the `.deb` from the GitHub release, by checksum.** `cli/cli`
   publishes per-release `.deb` assets that do not disappear. Pin the version
   *and* a `sha256sum -c`, exactly as the Dockerfile already does for the
   NodeSource key (`NODESOURCE_REPO_CHECKSUM`, line 35). Reproducible, and it
   cannot age out. This is the option I would take.
2. **Stop pinning `gh` and pin the digest of the whole image instead.** The
   deploy already resolves an immutable GHCR digest (`deploy/DEPLOY.md`,
   `TINYASSETS_IMAGE`), so the reproducibility that matters is preserved at a
   layer that does not depend on a third-party apt repo's retention policy.
3. **Keep the fuse and add a canary** that fails loudly *before* a merge rather
   than after: a scheduled job that resolves the pinned version against the repo
   daily and opens an issue when it vanishes. This keeps the outage but moves it
   off the critical path.

Note that `nodejs` is pinned the same way (`NODEJS_VERSION`, line 32) against
NodeSource, which retains more history — so it has not bitten yet. It is the
same fuse with a longer wick.
