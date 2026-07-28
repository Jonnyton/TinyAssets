## 1. Specify And Pin The Boundary

- [x] 1.1 Record the three-stage authority split, exact provenance contract,
  static-artifact allowlist, per-PR version model, blocked-MCP rule, dedicated
  preview-account requirement, bootstrap dependency, and repository-wide
  secret-custody non-goal in proposal, design, and delta spec.
- [x] 1.2 Add parsed workflow/config contract tests plus positive and hostile
  validator fixtures that fail if build, intake, credential, comment, target,
  tooling, or MCP authorities collapse.

## 2. Implement The Trusted Bootstrap

- [x] 2.1 Make `preview-worker.yml` a read-only, no-secret, no-cache,
  no-persisted-credential build/test workflow that uploads one short-lived,
  attempt-specific static export.
- [x] 2.2 Add the secretless trusted intake, exact run/PR/workflow/artifact
  validator, bounded artifact sanitizer, deterministic manifest, and immutable
  sanitized transfer.
- [x] 2.3 Add the fresh protected-environment job with exact trusted checkout,
  manifest revalidation, fixed Worker/configuration, lockfile-pinned
  no-lifecycle-script Wrangler, current-head recheck, and undeployed per-PR
  version alias.
- [x] 2.4 Add the separate pull-request-comment authority and trusted Worker
  `503`/no-store block for `/mcp` and `/mcp/*`.
- [x] 2.5 Rewrite preview operator guidance so no fixed URL, live-data bridge,
  automatic Pages refresh, production token reuse, or source-unproved
  environment protection is promised.

## 3. Verify, Publish, And Activate

- [x] 3.1 Run the full website tests/builds, strict OpenSpec validation,
  actionlint, zizmor, dependency audit, and exact-target scan; record
  freshness-stamped evidence.
- [ ] 3.2 Obtain independent exact-head general/security review and a fresh
  Claude Opus 5 opposite-provider review; adapt and repeat on every code change.
- [ ] 3.3 Sync the delta into `openspec/specs/public-website-surface/spec.md`,
  archive this change, push the narrow bootstrap PR, and land it on `main`.
- [ ] 3.4 Host creates the dedicated Cloudflare preview account and protected
  `react-preview` environment credentials; never reuse production credentials.
- [ ] 3.5 Rebase PR #1812 onto the bootstrap merge and capture a real current-
  head hosted preview, blocked `/mcp` response, rendered browser conversation,
  and post-fix clean-use evidence before calling publication proven.
