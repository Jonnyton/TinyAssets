## 1. Establish External Isolation

- [ ] 1.1 Confirm the trusted source bootstrap merge SHA and exact-head approvals; keep preview publication credential-free until the remaining tasks pass.
- [ ] 1.2 Provision and inventory the dedicated preview-only Cloudflare account and fixed Worker, recording redacted proof that no production resource or credential is present.
- [ ] 1.3 Configure named-reviewer or approved-organization Access for both the fixed `workers.dev` route and Preview URLs with no `Everyone`, `Bypass`, or public-path exception.
- [ ] 1.4 With a host-held credential, upload one inert trusted bootstrap version under a unique alias without pull-request bytes or a GitHub credential.
- [ ] 1.5 Prove anonymous denial and authorized-reviewer loading separately on the real base, bootstrap alias, and version hostnames.
- [ ] 1.6 Obtain independent security review of the redacted account, policy, and hostname receipt.

## 2. Enable And Prove Publication

- [ ] 2.1 After task 1.6 passes, configure the main-restricted, reviewed `react-preview` GitHub environment with the dedicated account ID and least-privilege token; disable administrator bypass where supported.
- [ ] 2.2 Rebase PR #1812 onto the bootstrap merge and publish one current-head preview.
- [ ] 2.3 Verify the exact artifact ID, regenerated-manifest digest, full head SHA, run/attempt, version ID, immutable version URL, and never-reused alias receipt.
- [ ] 2.4 Exercise the live base/alias/version routing matrix for canonical and adversarial `/mcp`, `/.well-known/oauth-*`, `/.well-known/mcp*`, malformed/residual-percent, and shadow-asset paths plus unrelated well-known and ordinary assets.
- [ ] 2.5 Capture a real browser-rendered reviewer session and post-fix clean-use evidence, or leave an explicit dated monitoring item when no organic use is visible.

## 3. Operational Acceptance

- [ ] 3.1 Test and document credential removal as the future-publication stop, and Preview URL disablement or Worker/account deletion as retained-evidence revocation.
- [ ] 3.2 Update operator guidance and STATUS without recording tokens, cookies, Access assertions, or other reusable credentials.
- [ ] 3.3 Obtain independent exact-head Codex and opposite-provider review of the completed activation evidence.
- [ ] 3.4 Strict-validate and sync/archive this change only after every external activation and live-evidence task above is complete.
