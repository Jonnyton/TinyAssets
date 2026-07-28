## Why

The trusted hosted-preview source pipeline intentionally lands without a
Cloudflare credential and cannot publish until its external account,
authorization, and GitHub environment boundaries are proven. Activation needs
its own durable change so unfinished host work is neither mistaken for as-built
behavior nor lost when the source bootstrap is archived.

## What Changes

- Provision a dedicated preview-only Cloudflare account and fixed Worker with
  no production resources or credentials.
- Use a host-held credential to create one inert trusted bootstrap version and
  unique alias, without pull-request bytes or a GitHub environment secret.
- Prove deny-by-default Cloudflare Access for anonymous traffic and successful
  authorized-reviewer loading on the real base, alias, and version hostnames.
- Only after accepted Access proof, configure the restricted `react-preview`
  GitHub environment with the dedicated account ID and Workers Scripts token.
- Publish and verify the first current-head pull-request preview, including its
  provenance receipt, live blocked-service routing matrix, rendered review, and
  post-fix-use evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `public-website-surface`: activate hosted preview publication only after
  proven external isolation, and define its live evidence and revocation
  contract.

## Impact

This changes the dedicated Cloudflare preview account, Cloudflare Access
applications and policies, the GitHub `react-preview` environment, operator
evidence, and the live preview state described by
`public-website-surface`. It does not add a TinyAssets compute service,
production route, custom domain, privileged cleanup loop, or production
credential.
