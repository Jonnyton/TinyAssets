## 0. Admission

- [x] 0.1 Independently review the current-main proposal, design, capability delta, and bounded task plan across correctness, security, release safety, and scope; fold every blocking finding before implementation. Exact-head review approved `f7d817df` after narrowing the contract to GitHub CLI selection and removing a false merged-main-only deployment invariant; strict validation and diff checks passed.

## 1. Test-first repair

- [x] 1.1 Record the exact red image-build evidence and independently verify the replacement release and package version against GitHub's official release API and configured signed apt package index. Run `30734421652` failed before publication with `E: Version '2.96.0' for 'gh' was not found`; on 2026-08-01 the official release API and signed apt index both reported `2.97.0`, package SHA-256 `7c7fa3bb890db0934baf65910d97b8c0fa437b2e590f7f7daf6bdf82c5c486d7`.
- [x] 1.2 Replace only the unavailable exact GitHub CLI package pin while preserving the signed repository/key, exact-version install, and fail-loud semantics. Changed only `GH_VERSION` from `2.96.0` to the officially verified `2.97.0`; repository/key and install command are unchanged.
- [x] 1.3 Run the focused Dockerfile shape regression, diff/secret checks, and strict OpenSpec validation; record dated local evidence. On Windows/Python 3.14, 41 Dockerfile tests passed; strict change validation and `git diff --check` passed, and the diff contained no credential material. Local Docker Desktop was unavailable, so task 2.2 retains the authoritative image-build proof.

## 2. Release and acceptance

- [x] 2.1 Obtain fresh independent exact-head review, merge through the normal PR path, and verify the merged-main source. Independent review approved rebased exact head `412c239b`; PR #2149 merged as `d6072f29`, and current main preserved `GH_VERSION=2.97.0`.
- [ ] 2.2 Build and publish the exact merged-main image, complete production deploy and public canary, then rerun the rendered agent remix/binding contract on its first attempt. Image run `30737655671` and deploy/canary run `30737837143` passed for `d6072f29`. The first rendered retry exposed a separate lineage-example defect; #2152 then built as run `30738561630` and deployed/canaried as `30738667081` at `72563358`. Its clean rendered response remains unread because the visible browser route reset, so this task stays open.
- [ ] 2.3 Record post-fix organic-use evidence if available, sync `daemon-image-build` into canonical specs, and archive this change only when release and rendered acceptance are complete.
