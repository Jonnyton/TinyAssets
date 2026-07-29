## 1. Close The Activation Contract

- [ ] 1.1 Audit the exact landed and active contracts for Branch authoring, background target/provider authority, cloud-usable Jonathan-owned provider custody, persisted Trigger catch-up, scoped GitHub effects, and canonical-handle control; commit a machine-readable readiness matrix that fails closed for every missing edge.
  - **Verify:** focused readiness-schema tests prove missing, stale, revoked, maintainer-owned, and market-supplied references cannot become ready.
- [ ] 1.2 Obtain opposite-provider review that re-checks the authority/custody and scheduler assumptions against current source and design, adapt this change to every accepted finding, and record approval before runtime implementation.
  - **Verify:** durable review names the reviewed commit and returns approve with no unresolved correctness or scope finding.

## 2. Build Single-Active Cloud Activation

- [ ] 2.1 Test-drive the typed activation manifest, immutable Branch-version binding, readiness evaluator, durable health projection, and owner-readable blocker evidence without adding a top-level MCP handle.
  - **Depends:** 1.1, 1.2.
  - **Verify:** focused unit/storage tests plus strict schema and migration checks.
- [ ] 2.2 Test-drive compare-and-swap activation generations, lease renewal/fencing, pause/stop, cloud-version rebind, cloud rollback, and the ordered tray-to-cloud/cloud-to-tray handoff.
  - **Depends:** 2.1 and accepted background target authority.
  - **Verify:** concurrent activation, stale-generation, lost-lease, unsettled-effect, and duplicate-controller tests prove one active winner.

## 3. Compose One Governed Drain Slice

- [ ] 3.1 Materialize the private main-universe Branch/Goal/Trigger definition and test-drive fresh-current-main ranking, mechanical claim admission, isolated Git lane creation/resume, and one bounded finish-first delivery slice.
  - **Depends:** 2.1 and accepted versioned authoring contract.
  - **Verify:** stale candidate, collision, priority, scope-ceiling, and ephemeral-workspace reconstruction tests.
- [ ] 3.2 Test-drive logical continuation identities, terminal-before-next sequencing, checkpoint/restart recovery, no-progress health, budget stops, and duplicate/missed-trigger handling.
  - **Depends:** 2.2 and accepted persisted Trigger/background authority contracts.
  - **Verify:** failure injection before provider launch, during restart, after terminal result, and across missed periods produces no duplicate claim.
- [ ] 3.3 Bind the slice to the TinyAssets-only GitHub grant and replay-safe receipt path for branch/PR effects while retaining normal CI, independent review, branch protection, merge, and OpenSpec sync/archive gates.
  - **Depends:** 3.1 and accepted outbound-boundary contract.
  - **Verify:** destination mismatch, revoked grant, ambiguous write, failed publication, and refused merge all hold safely with reconciliable evidence.

## 4. Make The Phone The Complete Owner Surface

- [ ] 4.1 Route inspect/health, pause/resume/stop, full definition/diff, edit, dry-test, immutable publish, activate/rebind, and rollback through existing canonical handles with owner authorization and no desktop/operator step.
  - **Depends:** 2.2, 3.1, and accepted browser-only authoring contract.
  - **Verify:** connector integration tests keep exactly seven advertised handles and prove non-owner, stale-version, stale-generation, hidden-effect, and dry-test-effect cases fail closed.
- [ ] 4.2 Bind a cloud-usable Jonathan-owned provider authority source and prove every run/provider receipt names its current owner/binding generation with no maintainer, ambient-process, or market fallback.
  - **Depends:** accepted cloud provider-authority/custody successor; this task MUST remain blocked if only native-machine custody exists.
  - **Verify:** provider launch, revocation, budget race, restart, and wrong-authority tests plus receipt inspection.

## 5. Prove And Cut Over

- [ ] 5.1 Deploy the loop dark, complete side-effect-free cloud dry runs, public canary checks, duplicate activation/trigger/claim load tests, deliberate worker-restart recovery, and rendered phone-chatbot lifecycle/evolution acceptance while the tray remains the active bridge.
  - **Depends:** 3.2, 3.3, 4.1, 4.2.
  - **Verify:** dated production evidence identifies the immutable Branch version, activation generation, authority sources, test budgets, and zero external effects during dry runs.
- [ ] 5.2 Stop the tray drain, settle its final claim, activate exactly one cloud generation, and complete the 24-hour computer-off proof with useful progress, phone-only management/repair/evolution, and no duplicate/fallback/policy-bypass trace.
  - **Depends:** 5.1.
  - **Verify:** rendered phone transcript, production traces, receipts, restart evidence, and concurrency/load artifact cover the full acceptance window.
- [ ] 5.3 After accepted clean use, disable normal tray-drain autostart, retain the fenced emergency rollback procedure, sync/archive this change, remove its STATUS row, and leave a dated watch item only if post-fix real-user use is not yet visible.
  - **Depends:** 5.2.
  - **Verify:** fresh-boot tray does not start the drain, phone status remains healthy with the PC off, strict OpenSpec validation passes, and canonical specs match the accepted behavior.
