## 1. Test-first Worker boundary

- [ ] 1.1 Add and run a failing Worker regression test proving upstream Access and application `Set-Cookie` headers cross the public response boundary while allowed headers and the body remain intact.
- [ ] 1.2 Add the minimal case-insensitive response-header boundary and prove the focused regression turns green without buffering the upstream body.

## 2. Verification and foldback

- [ ] 2.1 Run the complete Cloudflare Worker test suite, diff checks, OpenSpec validation, and the relevant repository policy checks.
- [ ] 2.2 Sync the delta into `live-mcp-connector-surface`, archive this change, record the security reflection/evidence, and retire the implementation Work row while preserving the P0 concern for post-merge live proof.
- [ ] 2.3 Obtain independent exact-head security review, add the required receipt to the draft PR, mark it ready, and verify trusted CI and merge.
- [ ] 2.4 After merge, verify deployment/public-canary state; if healthy-path, rendered-chatbot, or organic-use evidence is not yet available, preserve that residual honestly for a fresh foldback worker.
