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
- [x] 1.6 Publish the adapted exact-SHA provider-owner acceptance required by
  custody tasks 1.3a/1.3b, plus explicit supersession notices for the active
  universe-authority bundle and receipt enums. This output gate does not make
  provider routing depend on sibling acceptance.
- [x] 1.7 Fold the second exact-revision Opus 5 `ADAPT`: add the typed-held
  setup mapper, a durable host/local successor lane, archive/sync precedence,
  auth-health MODIFIED behavior, server-checkable request liveness, explicit
  newborn source, and exact field naming.
- [x] 1.8 Republish final-SHA custody acceptance and merged-change
  archive/sync precedence, explicitly carving `ProviderAuthorityHeldError`
  out of receipt `error/provider_error`.
- [x] 1.9 Fold the third exact-revision Opus 5 `ADAPT`: extend the host
  successor into identity/auth for attested stdio/plugin request authority;
  unify setup-required under the merged identity requirement; fix the default
  source/readiness predicate; and require surface-completable setup paths.
- [x] 1.10 Refresh exact-SHA custody acceptance plus universe/receipt
  archive-sync handoffs for the unified setup contract.
- [x] 1.11 Fold the fourth exact-revision Opus 5 `ADAPT`: preserve every
  pre-migration engine/read-failure/bare-exhaustion fail-safe behind a
  default-false flag; name the Tier-1 connector authority successor; and add
  universe archive/sync precedence to STATUS.
- [x] 1.12 Refresh final-SHA handoffs for the migration-compatible contract.
- [x] 1.13 Fold the fifth exact-revision Opus 5 `ADAPT`: gate newborn target
  fields while dark; state one global no-partial-enforcement gate; close the
  live leak with an immediate explicit pre-cutover `set_engine` narrow
  write; make connector action ownership exact; and remove contradictory
  current-SHA records.
- [x] 1.14 Fold the sixth exact-revision Opus 5 `ADAPT`: make the pre-cutover
  ceiling role-complete with local fallback; normalize aliases and disclose
  residual services; gate identity clauses; add a bounded post-flip-equivalent
  canary; and hand legacy-action ownership to its retirement lane.
- [x] 1.15 Refresh exact-SHA handoffs and obtain the seventh exact-revision
  Opus 5 review; it returned `ADAPT` on one bare-global launch gate,
  generated-ID birth canary coverage, dark non-BYOC compatibility, and an
  unpublished/misframed retirement handoff.
- [x] 1.16 Fold the seventh `ADAPT`: use the effective gate at every sink;
  bootstrap generated-ID birth only from a preflight-clean isolated test
  principal; preserve all non-BYOC source writes while dark; and reframe
  legacy retirement around residual migration and replacement paths.
- [x] 1.17 Publish the retirement handoff with the two exact residuals and
  add its durable comment ID to the current binding set.
- [x] 1.18 Refresh all four exact-SHA handoffs and obtain the eighth
  exact-revision Opus 5 review; it returned `ADAPT` because the
  flag-independent slice was not role-reachable on the deployed image and did
  not close the ambient maintainer-auth path.
- [x] 1.19 Apply the simplification gate: delete the deprecated-action slice
  instead of adding its own kill switch/reachability subsystem; preserve all
  shipped behavior while dark and bind the remaining exposure to gated R2-1a,
  three ready-path successors, retirement, and migration task 8.1.
- [x] 1.20 Obtain a parallel exact-`42ab3799` Claude Opus 5 review; it
  returned `ADAPT` on FastMCP structured-worker request ownership, a
  local/development dispatch ambiguity, and the canonical bounded
  subscription live probe.
- [x] 1.21 Fold that additional `ADAPT` after the simplification commit: add
  one-shot structured worker delegation without admitting detached contexts;
  clarify that dark legacy assignment gains no independent auth precondition;
  and preserve the bounded fixed private subscription viability probe outside
  user routing.
- [x] 1.22 Refresh exact-SHA review/handoff evidence and obtain the next Opus
  5 review; it approved the simplification but returned `ADAPT` because
  cloud-only target readiness emptied canonical non-writer roles and the
  completion-based auth probe lacked a background-authority bucket.
- [x] 1.23 Fold that `ADAPT`: require role-complete ready ceilings with
  per-provider bindings, hold cloud-only custody until a requester-owned role
  supplement exists, and move `_AUTH_PROBE_PROMPT` behind background
  maintenance authority or a zero-output replacement.
- [x] 1.24 Obtain the exact-`c40409bd` Opus 5 and independent verifier
  reviews. Both returned `ADAPT`: stateful FastMCP messages do not execute
  under the outer ASGI task/initialize Context, worker identity cannot bind
  before AnyIO submission, and request-time completion auth probing cannot
  use host quota. The role-complete and maintenance-receipt parts landed in
  `fdb0c6a9`; the message-dispatch seam remained.
- [x] 1.25 Fold the measured message-dispatch `ADAPT`: make the outer ASGI
  context non-authorizing, re-derive current bearer identity in the owned
  FastMCP per-message hook, reserve one session/request/tool-bound token, and
  claim it against the actual worker in the TinyAssets registered wrapper on
  entry. Preserve stateful HTTP while forbidding initialize/prior-message
  Context authority.
- [ ] 1.26 Refresh exact-SHA review/handoff evidence and obtain Claude Opus 5
  approval of the exact adapted artifacts; resolve every Critical and
  Important finding.
- [ ] 1.27 Run strict target/full-tree validation and land this target active
  and unsynced. Close/supersede draft #1691 only after the replacement and all
  citation handoffs are durable.

## 2. Published dependent-lane expectations (not completion tasks)

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
  `ProviderAuthorityHeldError` is never provider `error/provider_error`;
  adapt the merged active change before archive/sync into canonical specs.
- `activate-requester-host-engines` is a separate successor under
  `daemon-identity-and-host-pool`, `desktop-host-runtime`,
  `identity-auth-and-access-control`, and `provider-routing`. It consumes a
  stable authenticated account-to-host or attested same-user installation
  principal and `daemon_summon`, owns ready `local_model` and
  `founder_hosted_daemon` writers, mints local interactive
  `ProviderHostRequestCapability`, and grants no authority to pool rows or
  unattested client identifiers.
- `harden-background-provider-execution-authority` is a separate successor
  that owns durable receipts for post-response graph/run/resume/schedule,
  daemon, retrieval, and every task/thread/process provider bridge.
- `activate-connector-requester-authority` is a separate successor across
  identity/auth, paid market, distributed execution, and the live MCP
  connector. It owns the Tier-1 accepted-market setup/result path without raw
  secret deposit or desktop/web-app dependency.
- `retire-legacy-live-mcp-tools` owns retirement of the hidden `universe`
  action; removing it strictly reduces new exposure and does not wait on
  preserving a new writer. Its handoff records two residuals: all legacy
  records with `allowed_providers=None` require gated migration task 8.1, and
  removal leaves Tier-2/Tier-3/plugin users without assignment until
  `activate-requester-host-engines` supplies the replacement. Tier-1 chatbot
  setup remains connector-successor-owned and does not revive the handle.
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
  Name `_DEFAULT_ENGINE_SOURCE`, `universe_has_assigned_engine`, every
  `engine_setup_required_payload` branch, `_AUTH_PROBE_PROMPT` and its
  completion-based Codex refresh-viability caller, and per-transport auth
  middleware. Inventory the outer ASGI `AuthContextMiddleware`, FastMCP
  stateful streamable-HTTP session/message task split, TinyAssets
  `Middleware.on_call_tool`, `_register_structured_tool`, and AnyIO worker
  entry. Classify that completion as background maintenance requiring its
  owner receipt or a zero-output replacement, never a host-local probe.
  Record that the shipped setup envelope advertises deprecated
  `universe action=set_engine` even though `universe` is not one of the seven
  live handles; do not carry that dead path into target setup.
- [ ] 3.3 Compare draft #1606 lock/transaction/migration/deploy-fence commits
  to current main; select only still-applicable pieces and record why every
  other piece is obsolete or owned elsewhere.
- [ ] 3.4 Prove at least one target-ready source can be deployed before
  cutover: requester-local opaque custody, requester-host, or attested
  `local_model`. Prove Tier-1 connector users can complete accepted-market
  setup through `activate-connector-requester-authority`, Tier-2 tray/Tier-3
  OSS/Claude-plugin local users can mint host-request authority, every
  background/run/scheduled/daemon bridge has its owner receipt, and record the
  live founder home's current source/credential evidence without reading or
  exposing secret material.

## 4. RED tests — request capability, birth, and assignment

- [ ] 4.1 Add failing auth-middleware tests proving only a validated
  non-anonymous current `tools/call` message receives one
  non-copyable/non-serializable `ProviderRequestCapability`. Prove the outer
  ASGI task and stateful-session initialize Context authorize nothing; each
  later message (including refreshed bearer) re-derives identity through
  `get_http_request()`, reserves a distinct session/request/tool token, and
  the TinyAssets wrapper claims it only against the actual AnyIO worker on
  entry. `call_provider` explicitly carries that exact object through
  `call_sync`, `call_with_policy_sync`, retry/judge branches, and the router
  pool closure. Reject prior-message replay, lookalikes, copied reserves,
  second claims, detached/nested workers, and inherited child contexts before
  and after wrapper/message termination.
- [ ] 4.2 Add failing sink tests for exact mechanism/issuer/current identity,
  cross-principal replay, authentic A-on-A capability used on B, and same
  principal with stale assignment generation.
- [ ] 4.3 Add failing binding tests for wrong/empty principal, universe,
  provider, host, generation, digest, expired, tombstoned, or revoked state;
  prove failure precedes credential/provider access.
- [ ] 4.4 Add failing newborn tests across public, first-contact, internal
  migration, and dev paths. Pre-cutover proves optional assignment fields and
  flag=false preserve `_DEFAULT_ENGINE_SOURCE=byo_api_key`, LLM-vault and
  explicit-source readiness, unreadable-state fail-safe true, and the bare
  exhaustion carve-out. Post-cutover proves source/state `unassigned`,
  generation `0`, and `[]` before visibility; failure rolls back the
  directory plus any generated-ID canary registration. With the global flag
  false, prove a server-listed isolated test
  principal with no existing home/universe registers its generated public or
  first-contact birth ID before target initialization, while any existing-home
  principal and every caller-supplied opt-in fail before canary registration.
- [ ] 4.5 Add failing canonical requester-local mapping tests for
  `anthropic -> claude-code` and `openai -> codex`, exact cloud binding entry,
  generation increment, inferred/matching writer, and byte-exact zero
  mutation on invalid route under the effective gate. Prove cloud custody
  alone stays `held + []`; an atomic cloud-plus-attested-requester-local
  supplement publishes one per-provider binding map and a ceiling whose
  intersection with writer/judge/extract/embed is non-empty. Maintainer-owned
  local compute and any non-role-complete mapping remain held. Prove
  with the global flag false and empty canary state that all four shipped
  `set_engine` sources, all ten accepted BYOC services, config/readiness
  results, provider destination behavior, and `allowed_providers=None` no-op
  semantics remain byte-for-byte/behaviorally unchanged. No deprecated-action
  kill switch or partial ceiling may exist.
- [ ] 4.6 Add failing total-source tests for shipped `byo_api_key`,
  `self_hosted_endpoint`, `market_rented`, and `host_daemon` plus target
  `unassigned`, `requester_local`, `local_model`, and
  `founder_hosted_daemon`. Prove newborn source is `unassigned`, each maps
  through its named writer or to held/failed deny-all, raw-secret refusal stays
  custody-owned, and attested local model yields only `ollama-local`.
- [ ] 4.7 Add failure/crash injection at quarantine, reference update,
  commit-ready, final publication, and cleanup; prove deny-all recovery,
  digest matching, and unrelated credential-byte preservation.
- [ ] 4.8 Add two-writer and custody/launch lock-order tests proving coherent
  generations, assignment-before-custody order, reverse/reentrant refusal, and
  no compare-delete/dereference overlap.
- [ ] 4.9 Add failing first-contact/converse tests proving a pre-provider
  `ProviderAuthorityHeldError` maps to canonical
  `engine_setup_required_payload` without exhaustion or chain state, preserves
  completed birth/home, and never becomes generic error prose. Prove bare
  `AllProvidersExhaustedError` with null chain state retains no setup envelope;
  unmigrated credentialed/non-default and unreadable universes are never
  retold as engine-less; raw BYOC is absent; and every advertised setup path
  is completable on the tested connector/tray/stdio/plugin surface.
- [ ] 4.10 Capture the request/birth/assignment RED evidence.

## 5. GREEN implementation — request capability, birth, and assignment

- [ ] 5.1 Implement `ProviderRequestCapability` and request-local mint/reset
  in `tinyassets/auth/middleware.py`, the TinyAssets FastMCP
  `Middleware.on_call_tool` hook, and `_register_structured_tool`. Re-derive
  current-message bearer identity, reserve the one-shot
  principal/session/request/tool token in the owning message task, claim it
  against the actual synchronous worker on wrapper entry (or owning async
  handler), and revoke in both wrapper and message `finally` before result
  release. Implement exact nonce/mechanism/issuer/identity token, thread-safe
  registry, second-claim/replay refusal, and inherited-context non-authority.
- [ ] 5.2 Implement direct `ProviderAuthorityHeldError` mapping to the
  canonical `engine_setup_required_payload`, surface-live `setup_paths`,
  optional assignment fields, and migration-aware
  `universe_has_assigned_engine` with
  `TINYASSETS_PROVIDER_AUTHORITY_V2` defaulting false and the effective
  per-universe gate controlling target behavior. Preserve the shipped default,
  vault/source/read-failure routes, and bare-exhaustion behavior while dark.
  Implement server-owned default-empty universe/principal canary state and
  generated-ID registration before birth visibility. Only after manifest plus
  canary-proven Tier-1 connector and local surface gates pass, flip the global
  flag/default and enable `engine_source=unassigned` plus newborn deny-all
  atomically. Make the secret-free generated-ID canary registry durable across
  process restart, remove failed-birth entries before returning error,
  reconcile orphan IDs with no living universe at startup before routing, and
  remove registry state during bounded-test cleanup. Document the three provider-authority
  V2 environment variables and their default-dark/caller-non-authority
  semantics in `docs/reference/environment-variables.md`.
- [ ] 5.3 Implement canonical requester-local resolver accepting only an
  existing cloud binding entry and strict service/writer mapping; add
  total shipped-source migration/hold behavior and the successor-owned
  attested local/host target mappings only under the effective gate. Persist a
  non-secret per-provider binding map; keep cloud-only assignments held and
  atomically publish ready only after a requester-owned role supplement makes
  every canonical role reachable. While dark, keep every legacy
  source/service/config/readiness/destination behavior unchanged. Refuse
  target migration/assignment before mutation if existing config is
  unparseable so fallback-empty merge cannot drop unrelated keys.
- [ ] 5.4 Implement assignment generation, exclusive transaction, secret-free
  journal, pending quarantine, coherent atomic publication, failed deny-all
  recovery, per-provider binding-map replacement, and startup cleanup.
- [ ] 5.5 Export `ProviderAssignmentAdmission` with shared readers, exclusive
  writers, canonical universe keying, fixed lock order, generation/digest
  checks, and fail-loud reverse/reentrant acquisition.
- [ ] 5.6 Run focused tests GREEN and commit this reviewable slice.

## 6. RED tests — propagation, taxonomy, and reference-only launch

- [ ] 6.1 Add exhaustive call-site tests proving live requests retain the
  exact current capability across the FastMCP per-message reserve, registered
  wrapper worker claim, internal args, and router thread pool; prove the
  reserve is one-shot, message-awaited, non-transferable, current-message
  bound, and revoked before result release;
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
  auth-health quarantine with authority-bounded local fallthrough, pin clear
  guidance, each judge called exactly once/no duplicate,
  three-attempt two-through-eight-second bridge bounds, no-router and
  unrelated-exception semantics, policy telemetry and authority-safe policy
  fall-through, Bubblewrap/Codex mode selection, CLI sandbox recognition, and
  all existing `UniverseContext`/`ModelConfig`/`ProviderResponse` fields.
- [ ] 6.5 Add host-capability forgery tests across API/MCP/JSON/config/env/node
  inputs, lookalikes, serialization, and genuine-token request substitution;
  prove its closed set is exactly three zero-output/non-completion probes.
  The host-local subscription probe performs credential inspection only. Prove
  `_AUTH_PROBE_PROMPT` completion is rejected without the background owner's
  exact maintenance receipt, cannot use ambient maintainer auth, and no
  requester prompt/quota, universe mutation, or ordinary provider route
  becomes reachable.
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

- [ ] 7.1 Implement sink validation for exact explicitly carried HTTP/host
  request capability or owner-defined background receipt, fresh
  assignment/binding tuple, and authority-derived provider set before dynamic
  filters. Keep enforcement observational/non-authorizing while the
  effective V2 gate does not apply to the routed universe.
- [ ] 7.2 Implement sole provider-layer propagation through every inventoried
  request call site and router pool closure; integrate the separate background
  owner's receipt and host successor's local request capability at the same
  sink; add only the three closed zero-output host-local probes; move the
  completion-based subscription refresh-viability caller behind its bounded
  background-maintenance receipt or replace it with a zero-output probe.
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
- [ ] 7.7 Emit same-call `credential_kind`, `authority_class`, and held
  evidence to `ProviderResponse` without adding receipt persistence.
- [ ] 7.8 Run focused tests GREEN and commit this reviewable slice.

## 8. Cutover and complete-system proof

- [ ] 8.1 Build a secret-free legacy manifest while the flag remains false.
  Existing LLM credentials and explicit non-default sources retain assigned
  classification; unreadable vault/config stays fail-safe and blocks
  conversion. Raw-key-only records map to `failed + []` only inside the gated
  migration. A retained subscription maps ready only with complete current
  principal/universe/provider/host/generation/custody evidence plus a
  role-complete per-provider binding map.
- [ ] 8.2 Prove conversion locked, durable, idempotent, resumable, preserves
  unrelated credential bytes, leaves no unclassified universe or post-cutover
  `None`, and cannot restore wider authority. Do not flip the flag/default
  until the manifest and 8.3 surface gates both pass.
- [ ] 8.3 Block cutover unless a Tier-1 streamable-HTTP chatbot user can
  complete an advertised accepted-market path through
  `activate-connector-requester-authority`;
  Tier-2 tray, Tier-3 OSS stdio, and Claude-plugin local users can mint
  `ProviderHostRequestCapability` and complete host/local execution; every
  background/run/scheduled/daemon bridge carries its owner receipt; and the
  live founder home has a reviewed ready mapping or explicit replacement. The
  typed `ProviderAuthorityHeldError` and legacy non-null-chain/no-engine branch
  must render only surface-live setup paths, while bare exhaustion remains
  loud. Run this proof with the global flag false and each canonical isolated
  test universe named in the server-owned canary set, proving the full
  post-flip-equivalent contract plus unchanged behavior for unlisted
  universes. For Tier-1 public/first-contact birth, use a server-listed
  isolated test principal preflight-proven to have no existing home/universe;
  prove the generated ID enters the private registry before target
  initialization/visibility and later enforcement keys only on that ID.
  Remove test universes, principal entries, and registered IDs afterward.
  Caller data cannot opt in and existing user universes cannot be migrated for
  proof. A fully held surface fails this gate. Stop before flag/default flip,
  newborn deny-all, or legacy-writer quiescence if any fails. For every ready
  ceiling, prove writer, judge, extract, and embed each have at least one
  currently registered, executable, bound authorized provider; exercise the
  live editorial `role="judge"` and ingestion `role="extract"` call sites. If
  only an absent `ollama-local` remains or any role intersection is empty,
  keep the assignment held and fail the readiness gate without widening. On
  the canonical stateful `/mcp` app, initialize a session, issue later
  authenticated tool calls (including a refreshed bearer), and prove each
  uses only its current per-message identity/capability while the initialize
  and prior-message Context/leases remain non-authority.
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
- [ ] 8.8 Run rendered acceptance on Tier-1 chatbot connector, Tier-2 tray,
  Tier-3 OSS stdio, and Claude-plugin local runtime: complete one advertised
  setup path on each, configure the live source, force its provider to fail,
  and prove no alternate provider, maintainer quota, unrelated credential, or
  dead setup instruction is used.
- [ ] 8.9 Inspect freshness-stamped post-fix clean-user evidence; if absent,
  leave a STATUS monitoring item.
- [ ] 8.10 Sync/archive after implementation, update sibling dependencies and
  citations, close superseded drafts #1606/#1691 only after preservation,
  retire the STATUS row, and publish through normal review/merge. Do not sync
  the two `ProviderExecutor.start()`-bound sandbox requirements into canonical
  `provider-routing` before task 7.4 lands; until then the as-built sandbox
  requirements remain authoritative.
