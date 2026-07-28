## Why

The hosted React preview currently lets pull-request-controlled dependency and
build code run in the same job and workspace that later receives a Cloudflare
write credential. That collapses the trust boundary for every reviewer and
blocks safe retirement of the old privileged automation surface.

## What Changes

- Make the pull-request workflow an unprivileged build/test producer with
  read-only repository access, no persisted checkout credential, and no secret.
- Add a trusted-default-branch `workflow_run` consumer with secretless
  provenance validation and static-artifact sanitization before any protected
  environment is entered.
- Publish only an undeployed Worker version under a never-reused run/attempt
  alias from exact trusted Worker/configuration/tooling, record the
  provider-generated immutable version URL, and recheck the current
  pull-request head.
- Block `/mcp` and `/mcp/*` in the trusted preview Worker so untrusted browser
  JavaScript cannot bridge to production data.
- Require a dedicated Cloudflare preview account; production-account
  credentials do not satisfy the boundary, and require Cloudflare Access for
  Access-controlled retained preview evidence.
- Pin the boundary with hostile validator fixtures, parsed workflow contract
  tests, operator guidance, and independent exact-head review.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `public-website-surface`: define safe hosted-preview provenance,
  sanitization, credential isolation, per-run/attempt publication, and blocked-MCP
  behavior.

## Impact

This changes the three React preview workflows, trusted preview Worker and
Wrangler configuration, a small lockfile-pinned deployment toolchain, preview
operator documentation, and per-run/attempt website contract tests. The GitHub
`react-preview` environment must use a dedicated Cloudflare preview account
before credentialed publication is enabled. Production deployment and
`tinyassets.io/mcp` are not changed.
