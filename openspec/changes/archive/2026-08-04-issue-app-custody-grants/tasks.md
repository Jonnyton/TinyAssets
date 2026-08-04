## 1. Implementation

- [x] 1.1 Define the signed handoff contract consumed by the existing custody domain's future opaque grant factory; canonical signing-domain interoperability is proven against the existing verifier.
- [x] 1.2 Implement founder-mapped app custody grant issuance with sealed evidence, path resolution, signing, and fail-closed validation.
- [ ] 1.3 Add broader mutation-proof coverage for signature/key errors and concurrent issuance; current stale mapping, payload isolation, TTL/action validation, and cross-verifier signature tests pass, while opaque mint/replay remains the downstream custody owner.

## 2. Verification and foldback

- [x] 2.1 Focused custody/issuer, custody, ingress, and mapping tests pass (110 passed, 1 skipped); Ruff, compile, diff, and strict OpenSpec validation pass on final head `7aa41a4c`.
- [x] 2.2 Independent Claude/Sonnet exact-head security review approved final head `7aa41a4c` after fixing signing-domain and single-clock TTL defects.
- [x] 2.3 PR #2260 merged as `3b874d65`; the capability spec synced and this change archived on 2026-08-04. STATUS/worktree retirement follows in this foldback.
