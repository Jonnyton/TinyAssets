## 1. Test-first Worker boundary

- [x] 1.1 Add and run a failing Worker regression test proving upstream Access and application `Set-Cookie` headers cross the public response boundary while allowed headers and the body remain intact.
- [x] 1.2 Add the minimal case-insensitive response-header boundary and prove the focused regression turns green without buffering the upstream body.

## 2. Verification and foldback

- [x] 2.1 Run the complete Cloudflare Worker test suite, diff checks, OpenSpec validation, and the relevant repository policy checks.
- [x] 2.2 Sync the delta into `live-mcp-connector-surface`, archive this change, record the security reflection/evidence, and retire the implementation Work row while preserving the P0 concern for post-merge live proof.

## Delivery gate transfer

Independent exact-head review, merge verification, deployment, sanitized
post-fix probing, rendered-chatbot proof, and post-fix clean-use evidence are
delivery gates rather than implementation tasks. PR #1934 owns review/merge;
the dated STATUS P0 owns the post-merge gates and remains open until they pass.
