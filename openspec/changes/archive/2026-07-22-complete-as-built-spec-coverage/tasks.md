## 1. Establish the coverage boundary

- [x] 1.1 Audit canonical specs, active changes, PLAN modules, Forever Rule surfaces, and shipped repository behavior.
- [x] 1.2 Separate clearly as-built capabilities, forward-vision canonical files, active deltas, and shipped behavior without a spec owner.
- [x] 1.3 Confirm that the eight Batch A capability names and write paths do not overlap an active change.

## 2. Specify shipped unowned behavior

- [x] 2.1 Add the `domain-plugin-runtime` and `constraint-evaluation` delta specs with current degraded modes explicit.
- [x] 2.2 Add the `daemon-identity-and-host-pool` and `evaluation-runtime-and-scenarios` delta specs.
- [x] 2.3 Add the `desktop-host-runtime` delta spec without claiming a packaged one-click installer.
- [x] 2.4 Add the `development-coordination-runtime` delta spec for the shipped coordination tools and Agent Village surface.
- [x] 2.5 Add the `oss-clone-and-install` delta spec with its platform and smoke-scope limitations.
- [x] 2.6 Add the `public-website-surface` delta spec grounded in current routes and data provenance.

## 3. Validate requirement truth

- [x] 3.1 Map every new requirement to current source, tests, workflows, or rendered site behavior and remove any unsupported target behavior.
- [x] 3.2 Run strict OpenSpec validation for the change and fix all structural findings.
- [x] 3.3 Obtain independent review of capability ownership, evidence grounding, and limitation language.

## 4. Sync canonical capability truth

- [x] 4.1 Re-run the file collision guard for all eight canonical destination paths and broaden the durable STATUS claim.
- [x] 4.2 Sync the validated delta specs into new canonical `openspec/specs/<capability>/spec.md` files.
- [x] 4.3 Run strict validation over the canonical spec tree and verify a repeated sync is idempotent.

## 5. Publish and continue the program

- [x] 5.1 Archive the completed change with its audit and verification record intact.
- [ ] 5.2 Run the foldback context gate, publish the branch, and land the reviewed PR.
- [ ] 5.3 Re-audit Batch B collisions and promote the next file-bounded reconciliation lane; do not declare full-spec completion while Batch B or C remains open.
