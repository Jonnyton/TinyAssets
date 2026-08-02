## 1. Contract Gate

- [x] 1.1 Run strict OpenSpec and bounded-flow validation, then obtain independent exact-head architecture/security approval of the narrow dark seam before implementation. Approved at exact contract head `b5f26262c2ca3a57f8ddb1162a4c7405b1400ca8`; strict validation and bounded-flow admission passed with no blocking finding after exhaustive reauthorization and parent-capability ownership corrections.

## 2. Closed Model and Projection

- [x] 2.1 Test-first, specify the closed hold classifications, action-specific resolver evidence, and a serialization-complete projection that excludes every principal, universe, target/source, digest, executor, resolver, credential, bearer, and timestamp field. RED failed on the absent projection; the focused model suite now proves closed exit derivation, exact serialization, private-value absence, and forged/non-held refusal.
- [x] 2.2 Implement the typed evidence and non-authorizing projection in the canonical model/service plus byte-identical packaged runtime mirror. `BackgroundBranchHoldProjection` is an inert eight-field typed view; 121 model tests and Ruff pass with byte-identical mirror parity.

## 3. Same-Attempt Hold Lifecycle

- [ ] 3.1 Test-first, prove exact-fence reserved/claimed/running-to-held transitions clear leases, advance claimant fencing, preserve immutable identity/budgets, have one concurrency winner, and never append work or access runtime/provider paths.
- [ ] 3.2 Implement server-constructed held replacements and atomic compare-and-swap in the existing attempt claim-lifecycle service.
- [ ] 3.3 Test-first, prove conclusive same-binding recovery and authenticated exactly-next-binding reauthorization exit the hold only after exhaustive target/source/executor/expiry/budget revalidation, while indeterminate, stale, changed-pin, widened-budget, skipped-generation, identity-transfer, revocation-regression, and forged-record cases make no write.
- [ ] 3.4 Implement recovery and exhaustive reauthorization using fresh resolver evidence plus the transaction's canonical binding snapshot; accept no caller-authored proof or actor string.

## 4. Verification and Foldback

- [ ] 4.1 Run focused model/service/store tests, authority regressions, concurrency/fault cases, Ruff, strict OpenSpec, packaged isolated import/mirror parity, and static proof that queue/dispatcher/provider/public surfaces do not import or activate the seam.
- [ ] 4.2 Obtain fresh independent exact-head code/security review, sync and archive this change, record it as partial foundation under the still-open umbrella task 2.6, and retire the exact STATUS claim on land.
