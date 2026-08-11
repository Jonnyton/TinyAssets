## 1. Credential-driven execution

- [ ] 1.1 Add failing tests for assigned-credential resolution, exact-provider routing, snapshot cleanup, and `no_requester_owned_executor` holds.
- [ ] 1.2 Implement the daemon-side assigned-credential resolver and bind it to claimed BranchTask provider calls without changing serving-binding public modules.
- [ ] 1.3 Add pending hold evidence and deterministic runnable-task selection so a held task neither executes nor blocks another ready task.

## 2. Provider model retirement

- [ ] 2.1 Rewrite router/base tests and implementation to remove fallback chains, writer pins, provider fan-out, ambient host auth, and implicit provider switching while preserving exact served/background authority.
- [ ] 2.2 Remove host-pool and cloud-worker supervisor/healthcheck modules plus fleet-only tests and repair every inbound import/reference.
- [ ] 2.3 Rewire cloud automation/API/escrow execution tests to assigned credential authority and typed holds; remove writer-pinned fleet runtime paths.

## 3. Worker-free deployment

- [ ] 3.1 Rewrite compose, deploy/recovery workflows, entrypoint/env template, log aggregation, startup diagnostics, and deploy fence for daemon+tunnel+logs plus profile-gated Slack only.
- [ ] 3.2 Update all named deployment/container tests to assert the worker-free shape without weakening ownership, secret, liveness, or rollback guarantees.

## 4. Verification and foldback

- [ ] 4.1 Rebuild the Claude plugin mirror; run focused tests, changed-file Ruff, and the complete CI required-test surface with zero new failures versus origin/main.
- [ ] 4.2 Perform independent exact-diff review, resolve findings, sync as-built specs, record reflection/coordination truth, and commit without merge or deploy.
