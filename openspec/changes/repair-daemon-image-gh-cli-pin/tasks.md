## 0. Admission

- [x] 0.1 Independently review the current-main proposal, design, capability delta, and bounded task plan across correctness, security, release safety, and scope; fold every blocking finding before implementation. Exact-head review approved `f7d817df` after narrowing the contract to GitHub CLI selection and removing a false merged-main-only deployment invariant; strict validation and diff checks passed.

## 1. Test-first repair

- [x] 1.1 Record the exact red image-build evidence and independently verify the replacement release and package version against GitHub's official release API and configured signed apt package index. Run `30734421652` failed before publication with `E: Version '2.96.0' for 'gh' was not found`; on 2026-08-01 the official release API and signed apt index both reported `2.97.0`, package SHA-256 `7c7fa3bb890db0934baf65910d97b8c0fa437b2e590f7f7daf6bdf82c5c486d7`.
- [ ] 1.2 Replace only the unavailable exact GitHub CLI package pin while preserving the signed repository/key, exact-version install, and fail-loud semantics.
- [ ] 1.3 Run the focused Dockerfile shape regression, diff/secret checks, and strict OpenSpec validation; record dated local evidence.

## 2. Release and acceptance

- [ ] 2.1 Obtain fresh independent exact-head review, merge through the normal PR path, and verify the merged-main source.
- [ ] 2.2 Build and publish the exact merged-main image, complete production deploy and public canary, then rerun the rendered agent remix/binding contract on its first attempt.
- [ ] 2.3 Record post-fix organic-use evidence if available, sync `daemon-image-build` into canonical specs, and archive this change only when release and rendered acceptance are complete.
