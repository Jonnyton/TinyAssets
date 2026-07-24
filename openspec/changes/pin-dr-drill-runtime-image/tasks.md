## 1. Executable Contract

- [x] 1.1 Add red workflow tests for pre-provision production-image resolution, exact digest validation, and secret-free transport.
- [x] 1.2 Require ephemeral Compose injection plus distinct provider/runtime image evidence.

## 2. Implementation

- [x] 2.1 Read and validate only the primary host's configured immutable daemon image before provisioning.
- [x] 2.2 Supply the validated image to daemon-only Compose startup without persisting primary environment material.
- [x] 2.3 Record provider and runtime image identities separately in PASS, failure, deletion, and summary evidence.

## 3. Verification And Handoff

- [x] 3.1 Run focused workflow tests, actionlint, strict OpenSpec validation, Ruff, and diff checks.
- [ ] 3.2 Obtain independent exact-SHA review, sync/archive the change, and publish the infra PR.
- [ ] 3.3 Preserve the exact-landed DR rerun as the production monitoring handoff.
