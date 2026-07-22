## 1. Specify the security boundary

- [x] 1.1 Reproduce and document the partial-overlay and swallowed-error host credential paths.
- [x] 1.2 Define the pre-strip, universe overlay, explicit failure, and host-local counter-case behavior.
- [ ] 1.3 Obtain host approval for the authentication-logic change.

## 2. Prove the defects red

- [ ] 2.1 Add a failing regression test showing a partial universe overlay retains no unrelated host subscription values.
- [ ] 2.2 Add a failing regression test showing unexpected universe overlay/resolution errors raise without preserving usable host auth.
- [ ] 2.3 Confirm the existing malformed-vault and host-local counter-case tests remain green before implementation.

## 3. Implement the fail-closed environment boundary

- [ ] 3.1 Detect explicit or environment-bound universe scope before calling vault helpers and remove inherited host subscription variables.
- [ ] 3.2 Preserve universe-supplied replacement values after the pre-strip.
- [ ] 3.3 Convert unexpected universe-scoped helper failures to secret-free `ProviderUnavailableError` while preserving host-local best-effort behavior.

## 4. Verify, sync, and publish

- [ ] 4.1 Run focused provider/credential tests and strict OpenSpec validation.
- [ ] 4.2 Obtain independent security and diff review.
- [ ] 4.3 Sync and archive the reviewed delta, publish and land the PR, and retire the STATUS row.
