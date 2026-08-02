# Daemon image GitHub CLI pin repair

Date: 2026-08-01

## Incident

Production image run `30734421652` failed in the Docker build before image publication. Apt returned:

```text
Package gh is not available, but is referred to by another package.
E: Version '2.96.0' for 'gh' was not found
```

The failing command retained the configured GitHub `signed-by` repository and requested the Dockerfile's exact `GH_VERSION=2.96.0`. The failure therefore proves repository expiry of the requested package, not an unsigned-source fallback or application regression.

## Replacement grounding

Read-only checks on 2026-08-01 used GitHub-owned sources:

- `https://api.github.com/repos/cli/cli/releases/latest` returned tag `v2.97.0`, published `2026-07-31T02:04:00Z`.
- `https://cli.github.com/packages/dists/stable/main/binary-amd64/Packages` contained:

```text
Package: gh
Version: 2.97.0
Filename: pool/main/g/gh/gh_2.97.0_amd64.deb
SHA256: 7c7fa3bb890db0934baf65910d97b8c0fa437b2e590f7f7daf6bdf82c5c486d7
```

The package index did not contain `2.96.0`.

## Safety boundary

The repair changes only the exact GitHub CLI package pin. It keeps the existing repository signing key, `signed-by` apt source, exact-version install, and fail-loud behavior. It does not float to `latest`, add an unsigned binary download, change GitHub effect authority, or alter deployment fencing.

## Review

The first spec review rejected two overclaims: a false universal merged-main-only deployment invariant and general dependency reproducibility. The corrected change limits its promise to deterministic GitHub CLI selection while the signed repository serves the exact version. Independent review approved exact spec head `f7d817df`; strict OpenSpec validation and `git diff --check` passed.

## Release evidence

Local implementation evidence on Windows/Python 3.14:

```text
python -m pytest -q tests/test_dockerfile_shape.py
41 passed
openspec validate repair-daemon-image-gh-cli-pin --strict
Change 'repair-daemon-image-gh-cli-pin' is valid
git diff --check
exit 0
```

The implementation changes only `ARG GH_VERSION=2.96.0` to `ARG GH_VERSION=2.97.0`. Local Docker Desktop was not running, so no local image-build success is claimed.

Independent review approved rebased exact head `412c239b`. PR #2149 merged as `d6072f298a1b369786788e4bd36eca10cf9a5249`; image run `30737655671` and production deploy/canary run `30737837143` passed. The deploy proved health, cloud-worker startup, canonical MCP canary, exact-seven surface, direct-URL Access fencing, writer/receipt fencing, and release-receipt publication.

A rendered Claude.ai retry then found a separate public remix-lineage example gap. Its corrective PR #2152 merged as `7256335820ef2247c4d7880455a67d88f5dc5c3d`; exact image run `30738561630` and deploy/canary run `30738667081` also passed. The browser-control session reset before the clean rendered response could be read, so rendered first-attempt acceptance is not claimed and the OpenSpec change remains active.
