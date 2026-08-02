## 1. Reproduce and specify

- [x] 1.1 Add the self-consistent forged-reservation regression and capture its failure on merged head `1e5a3433`.
- [x] 1.2 Validate the proposal, design, and provider-routing delta strictly before implementation.

## 2. Repair the authority boundary

- [x] 2.1 Replace record-issued mint grants with one-use post-commit store proofs bound to exact reservation digest and PID.
- [x] 2.2 Bind carrier validation to the issuer PID and publish proof/carrier registry identities only after cleanup installation.
- [x] 2.3 Mirror the canonical provider-authority model/store exactly into the packaged Claude-plugin runtime.

## 3. Verify and land

- [x] 3.1 Run the forged-path, focused authority, provider-router, concurrency, cleanup, and canonical/package parity tests.
- [x] 3.2 Run Ruff, strict OpenSpec validation/flow audit, drift checks, and `git diff --check`.
- [x] 3.3 Record the correction audit, sync the provider-routing delta, and archive this change without enabling activation.
- [ ] 3.4 Obtain fresh independent security approval of the exact final head, merge the corrective PR, and verify current `origin/main` before the cloud lane resumes.
