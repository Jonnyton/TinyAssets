## 1. Implementation

- [ ] 1.1 Define the signed handoff contract consumed by the existing custody domain's future opaque grant factory.
- [ ] 1.2 Implement founder-mapped app custody grant issuance with sealed evidence, path resolution, signing, and fail-closed validation.
- [ ] 1.3 Add mutation-proof tests for stale mapping, payload isolation, signature/key errors, TTL/action validation, one-use consumption, and concurrent issuance.

## 2. Verification and foldback

- [ ] 2.1 Run focused custody/issuer tests, adjacent ingress/mapping tests, lint, compile, and strict OpenSpec validation.
- [ ] 2.2 Obtain an independent exact-head security review before publishing.
- [ ] 2.3 After merge, sync the delta into the canonical custody spec and archive this change.
