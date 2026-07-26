## 1. Current-main reconciliation and review

- [x] 1.1 Reconstruct the target change on current `origin/main`; preserve
  draft PR #1691's parentless history as source input only.
- [x] 1.2 Fold merged Opus #1727 ADAPT: remove #1660 review circularity,
  duplicate propagation ownership, material-bearing invocation, and unnamed
  market activation.
- [x] 1.3 Fold the 2026-07-25 current-main Opus ADAPT: replace unmintable
  requester `Verified[T]` with an exact transport-minted request capability;
  bind principal/universe/provider/host/generation/digest/state at the sink;
  publish one-way sibling interfaces; name requester-host readiness; separate
  authority hold from exhaustion; add held evidence; separate fulfillment and
  credential-authority vocabulary; correct B2/B13/V6 ownership; export lock
  ordering; preserve canonical MODIFIED behavior; and make newborn deny-all an
  independent invariant.
- [x] 1.4 Publish non-blocking coordination handoffs to the active custody,
  universe-creation, and receipt owners. Provider routing does not wait for
  sibling acceptance before this target spec lands.
- [x] 1.5 Fold exact-revision Opus 5 `ADAPT`: replace the ambient ContextVar
  sink with an explicit internal router-pool carrier; name the background
  authority owner; make shipped/target source resolution total and local
  fallback reachable; declare sibling precedence; preserve all canonical
  clauses; and gate newborn deny-all on rendered setup plus ready paths.
- [ ] 1.6 Publish the adapted exact-SHA provider-owner acceptance required by
  custody tasks 1.3a/1.3b, plus explicit supersession notices for the active
  universe-authority bundle and receipt enums. This output gate does not make
  provider routing depend on sibling acceptance.
- [ ] 1.7 Obtain Claude Opus 5 re-review of the exact adapted artifacts;
  resolve every Critical and Important finding.
- [ ] 1.8 Run strict target/full-tree validation and land this target active
  and unsynced. Close/supersede draft #1691 only after the replacement and all
  citation handoffs are durable.

## Published dependent-lane expectations (not completion tasks)

- `retire-mcp-provider-secret-deposit` consumes exported
  `ProviderAssignmentAdmission`, its assignment-before-custody lock order,
  expected generation/digest checks, and reference-only launch. Re-point its
  tasks 1.3a/1.3b/4.3 and every “draft PR #1691” spec/task citation to this
  replacement exact SHA; retain raw `llm_api_key` refusal/custody/retirement
  ownership there.
- `universe-creation` removes its caller-built “immutable authority
  bundle passes eligible provider set” contract. It passes target
  universe/request lineage, consumes the provider hold/result, and renames
  `requester_owned|accepted_market` from `authority_class` to
  `fulfillment_class`. It does not block this change or mint provider
  authority.
- `provider-attempt-receipts` consumes same-call
  `credential_kind`/credential `authority_class` evidence and adds
  `outcome=authority_held` plus `route_condition=authority_held`.
  `ProviderAuthorityHeldError` is never provider `error/provider_error`.
- `activate-requester-host-engines` is a separate successor under
  `daemon-identity-and-host-pool`, `desktop-host-runtime`, and
  `provider-routing`. It consumes a stable authenticated account-to-host
  principal and `daemon_summon`, owns ready `local_model` and
  `founder_hosted_daemon` writers, and grants no authority to pool rows or
  unattested client identifiers.
- `harden-background-provider-execution-authority` is a separate successor
  that owns durable receipts for post-response graph/run/resume/schedule,
  daemon, retrieval, and every task/thread/process provider bridge.
- Paid-market/distributed ownership remains: accepted agreement in
  paid-market-economy; signed remote execution through B2 and B13 task 5.13;
  V6 only market selection/escrow/verification/settlement/reputation; D0
  remains dark fake/test-only.

## 3. Runtime claim and inventory gates

- [ ] 3.1 Before runtime work, run build-phase context feed and
  `claim_check.py --check-files` for exact auth middleware, assignment/config,
  provider authority/router/base/call, call sites, focused tests, migration,
  and deploy files. Wait for active adjacent and broad test claims or partition
  them explicitly.
- [ ] 3.2 Inventory every current-main engine source/assignment, universe
  birth, config read/write, provider call bridge, direct provider bypass, and
  `call_provider` caller, including graph run/resume/version/policy/judge,
  RAPTOR, reflexion, agentic retrieval, background work, and maintenance.
- [ ] 3.3 Compare draft #1606 lock/transaction/migration/deploy-fence commits
  to current main; select only still-applicable pieces and record why every
  other piece is obsolete or owned elsewhere.
- [ ] 3.4 Prove at least one target-ready source can be deployed before
  cutover: requester-local opaque custody, requester-host, or attested
  `local_model`. Prove every background/run/scheduled/daemon bridge has its
  owner receipt or is safely held, and record the live founder home's current
  source/credential evidence without reading or exposing secret material.

## 4. RED tests — request capability, birth, and assignment

- [ ] 4.1 Add failing auth-middleware tests proving only a validated
  non-anonymous bearer request receives one non-copyable/non-serializable
  `ProviderRequestCapability`; `call_provider` explicitly carries that exact
  object through `call_sync`, `call_with_policy_sync`, retry/judge branches,
  and the router pool closure; reset/prior-request replay/lookalikes fail.
- [ ] 4.2 Add failing sink tests for exact mechanism/issuer/current identity,
  cross-principal replay, authentic A-on-A capability used on B, and same
  principal with stale assignment generation.
- [ ] 4.3 Add failing binding tests for wrong/empty principal, universe,
  provider, host, generation, digest, expired, tombstoned, or revoked state;
  prove failure precedes credential/provider access.
- [ ] 4.4 Add failing newborn tests across public, first-contact, internal
  migration, and dev paths for `unassigned`, generation `0`, and `[]` before
  index/home/living visibility; failure rolls back the directory.
- [ ] 4.5 Add failing canonical requester-local mapping tests for
  `anthropic -> claude-code` and `openai -> codex`, exact opaque reference,
  generation increment, singleton ceiling, inferred/matching writer, and
  byte-exact zero mutation on invalid route.
- [ ] 4.6 Add failing total-source tests for shipped `byo_api_key`,
  `self_hosted_endpoint`, `market_rented`, and `host_daemon` plus target
  `requester_local`, `local_model`, and `founder_hosted_daemon`. Prove each
  maps through its named writer or to held/failed deny-all, raw-secret refusal
  stays custody-owned, and attested local model yields only `ollama-local`.
- [ ] 4.7 Add failure/crash injection at quarantine, reference update,
  commit-ready, final publication, and cleanup; prove deny-all recovery,
  digest matching, and unrelated credential-byte preservation.
- [ ] 4.8 Add two-writer and custody/launch lock-order tests proving coherent
  generations, assignment-before-custody order, reverse/reentrant refusal, and
  no compare-delete/dereference overlap.
- [ ] 4.9 Capture the request/birth/assignment RED evidence.

## 5. GREEN implementation — request capability, birth, and assignment

- [ ] 5.1 Implement `ProviderRequestCapability` and request-local mint/reset
  in `tinyassets/auth/middleware.py` with exact principal, nonce, mechanism,
  issuer, and identity-token invariants.
- [ ] 5.2 After the generic held/`engine_setup_required_payload` path and at
  least one ready source are live behind the deployment gate, implement
  independent newborn deny-all initialization in the atomic birth transaction
  for every entry path.
- [ ] 5.3 Implement canonical requester-local resolver accepting only an
  existing opaque binding reference and strict service/writer mapping; add
  total shipped-source migration/hold behavior and the successor-owned
  attested local/host target mappings.
- [ ] 5.4 Implement assignment generation, exclusive transaction, secret-free
  journal, pending quarantine, coherent atomic publication, failed deny-all
  recovery, and startup cleanup.
- [ ] 5.5 Export `ProviderAssignmentAdmission` with shared readers, exclusive
  writers, canonical universe keying, fixed lock order, generation/digest
  checks, and fail-loud reverse/reentrant acquisition.
- [ ] 5.6 Run focused tests GREEN and commit this reviewable slice.

## 6. RED tests — propagation, taxonomy, and reference-only launch

- [ ] 6.1 Add exhaustive call-site tests proving live requests retain the
  exact current capability across internal args and the router thread pool;
  background work requires its owner receipt across task/thread/process
  boundaries; and startup/CI inventory proves every bridge carries one exact
  authority type or holds.
- [ ] 6.2 Add non-authority tests for actor strings, ACL alone,
  process-global state, admission/replay verdicts, request
  receipts/results/events, priority grants, branch tasks, and queue
  claims/leases.
- [ ] 6.3 Add authority-vs-dynamic-filter tests: assignment/capability/binding
  emptiness holds; subscription-only, role/policy, registration, auth health,
  cooldown, quota, and authorized-pin failures remain exhaustion with
  canonical retry/fallback/chain-drain/judge behavior.
- [ ] 6.4 Add canonical-preservation tests for `preferred_writer`,
  `preferred_judge`, explicit-context-over-global resolution,
  non-request absent-context fallback, unknown-role-to-writer default,
  pin clear guidance, each judge called exactly once/no duplicate,
  three-attempt two-through-eight-second bridge bounds, no-router and
  unrelated-exception semantics, policy telemetry and authority-safe policy
  fall-through, Bubblewrap/Codex mode selection, CLI sandbox recognition, and
  all existing `UniverseContext`/`ModelConfig`/`ProviderResponse` fields.
- [ ] 6.5 Add host-capability forgery tests across API/MCP/JSON/config/env/node
  inputs, lookalikes, serialization, and genuine-token request substitution;
  prove its closed set is exactly the three zero-output probes and no model,
  quota, universe mutation, or maintainer provider resource becomes reachable.
- [ ] 6.6 Add provider parity tests proving every CLI/local/HTTP/in-process
  invocation is reference-only and only `ProviderExecutor.start()`
  dereferences after full binding revalidation before calling the provider's
  canonical `complete(...)`.
- [ ] 6.7 Add shared-reader/assignment races proving `start()` freezes one
  principal/universe/provider/host/generation/digest tuple before unlock and
  result completion cannot reread authority.
- [ ] 6.8 Add launch lifecycle/crash tests for bounded start timeout, partial
  cleanup, cleanup-failed fence, startup reconciliation,
  success/error/timeout/cancel/close, concurrent result/close, and exactly one
  terminal owner.
- [ ] 6.9 Add evidence tests for exact credential-kind and credential-authority
  enums plus `authority_held/authority_held`; prove universe remote success is
  never host and held is never provider fault.
- [ ] 6.10 Capture propagation/taxonomy/launch RED evidence.

## 7. GREEN implementation — propagation and launch

- [ ] 7.1 Implement sink validation for exact current request capability or
  exact explicitly carried request capability or owner-defined background
  receipt, fresh assignment/binding tuple, and authority-derived provider set
  before dynamic filters.
- [ ] 7.2 Implement sole provider-layer propagation through every inventoried
  request call site and router pool closure; integrate the separate background
  owner's receipt at the same sink; add only the three closed zero-output
  host-local probes.
- [ ] 7.3 Implement immutable router-minted `ProviderInvocation` with request
  capability/receipt, target/principal, provider, generation, opaque
  reference/digest, provenance, classifications, call inputs, and launch
  token—never native secret material.
- [ ] 7.4 Replace direct one-phase provider execution with
  `ProviderExecutor.start() -> ProviderLaunchHandle -> result()`,
  executor-local dereference followed by canonical provider `complete()`,
  frozen transport state, and direct-bypass refusal.
- [ ] 7.5 Implement bounded launch cleanup, secret-free launch identity,
  durable fence/reconciliation, and atomic terminal state.
- [ ] 7.6 Preserve canonical dynamic exhaustion, retry, fallback,
  chain-drain, policy, pin, judge, preference, and context behavior after the
  authority gate.
- [ ] 7.7 Emit same-call credential-kind, credential-authority, and held
  evidence to `ProviderResponse` without adding receipt persistence.
- [ ] 7.8 Run focused tests GREEN and commit this reviewable slice.

## 8. Cutover and complete-system proof

- [ ] 8.1 Build a secret-free legacy manifest. Raw-key-only current records
  have no opaque reference and map to `failed + []`, never ready. A retained
  subscription maps ready only with complete current principal/universe/
  provider/host/generation/custody evidence. Non-executable intent maps held;
  unreadable/ambiguous state fails.
- [ ] 8.2 Prove conversion locked, durable, idempotent, resumable, preserves
  unrelated credential bytes, leaves no unclassified universe or post-cutover
  `None`, and cannot restore wider authority.
- [ ] 8.3 Block cutover unless requester-local opaque custody,
  requester-host, or attested local-model activation passes end-to-end; the
  generic held/setup-required chatbot path is rendered; every
  background/run/scheduled/daemon bridge carries its owner receipt or is
  safely held; and the live founder home has a reviewed ready mapping or
  explicit replacement. Stop before enabling newborn deny-all or quiescing
  legacy writers if not.
- [ ] 8.4 Run focused provider/auth/assignment/custody/birth/call-site/crash
  suites, surrounding regressions, Ruff, diff check, mirror parity, and strict
  OpenSpec validation.
- [ ] 8.5 Run the applicable real canonical `/mcp` load scenario with
  concurrent assignment/calls and retain recomputable latency, unauthorized
  provider/credential, disclosure, duplicate/lost effect, and recovery
  evidence. Shaped/mock cannot pass.
- [ ] 8.6 Obtain independent correctness, security, concurrency,
  compatibility, custody, and diff review; resolve every Critical and
  Important finding.
- [ ] 8.7 Deploy through immutable-image cutover, run daemon-only canary, and
  retain rollback/release receipts.
- [ ] 8.8 Run rendered chatbot acceptance: configure the live ready source,
  force its provider to fail, and prove no alternate provider, maintainer
  quota, or unrelated credential is used.
- [ ] 8.9 Inspect freshness-stamped post-fix clean-user evidence; if absent,
  leave a STATUS monitoring item.
- [ ] 8.10 Sync/archive after implementation, update sibling dependencies and
  citations, close superseded drafts #1606/#1691 only after preservation,
  retire the STATUS row, and publish through normal review/merge.
