## 1. Reconcile authority and release collisions

- [ ] 1.1 Record the #1606 split: select exact retained assignment-lock,
  transaction, migration, and deployment-fence commits; keep auth stripping
  with the provider-auth overlay; preserve request/assignment intersection
  wording here; remove duplicate universe-creation ownership; name remaining
  graph/credential owners; mark #1606 to close without merge after preservation.
- [ ] 1.2 Wait for #1484 to release canonical and packaged
  `api/universe.py`; wait for #1623's prerequisite stack to land or for #1623
  to be rebased/retargeted and release the canonical provider-routing spec;
  wait for the provider-auth overlay to land or partition exact ownership; then
  rebase this lane.
- [ ] 1.3 Re-check active provider-auth, universe-creation, receipts, and
  paid-market lanes; update their dependency notes so none implements a second
  provider-authority boundary. Fold
  `effective = fresh assignment ceiling INTERSECT typed request eligible set`
  into universe-creation tasks 3.1/4.3; receipts must retain a separate
  credential-isolation dependency and own call-local evidence; paid-market
  execution must name the accepted-grant activation owner.
- [ ] 1.4 Propose and land a prerequisite
  `provider-authority-propagation` change: introduce the typed universe/host
  authority union and identity-validated, non-serializable bootstrap token;
  thread it without enforcement through graph/run/resume/version/policy/judge,
  RAPTOR, reflexion, agentic retrieval, and every other `call_provider` site.
- [ ] 1.5 Run the build-phase provider-context feed and collision guard, then
  broaden STATUS to the exact runtime, packaged mirror, focused tests, selected
  migration script/tests, and deployment/workflow files before editing any of
  them. The inventory must include config, provider context/base/router/call
  bridge/errors, universe creation/assignment, and every call site.

## 2. Lock the behavior with failing tests

- [ ] 2.1 Add table-driven BYO tests for exact Anthropic/OpenAI mappings,
  inferred and matching writers, strict alias/unknown/mismatch rejection, and
  byte-for-byte zero mutation on rejected input.
- [ ] 2.2 Add reassignment tests proving replacement-not-union and final
  source, vault service, preference, and singleton ceiling coherence.
- [ ] 2.3 Add source tests proving self-hosted, market-rented, and host-daemon
  assignments persist `engine_assignment_state="held"` and `[]` until
  activation; prove new universes start
  `engine_assignment_state="unassigned"` plus `[]`.
- [ ] 2.4 Add failure-injection tests at quarantine, vault, and final-config
  publication proving durable `pending -> failed` recovery, unrelated-vault
  preservation, no restored `None`/wider ceiling, and no secret in output.
- [ ] 2.5 Add crash-window tests proving atomic final-config publication is the
  commit point: a matching leftover `commit_ready` journal is safe cleanup,
  while pre-publication, mismatched, or uncommitted journals fail held.
- [ ] 2.6 Add real-assignment-to-fake-router tests proving only the selected
  provider is attempted across normal, retry, policy, pin, judge, extract, and
  embed paths when every unselected provider is healthy.
- [ ] 2.7 Add deterministic cross-process overlap tests for two assignments
  plus shared-reader overlap, writer/reader races, and stale context. Prove
  concurrent readers coexist; attempts admitted before the writer may finish;
  attempts reaching admission during/after quarantine make zero calls; the
  final assignment is coherent.
- [ ] 2.8 Add the critical admission/auth race: start a writer after provider
  admission but before auth resolution; prove the reader captures exact
  provider, credential/auth provenance and material reference, and quota/lease
  into router-minted `ProviderInvocation`, awaits the provider launch barrier,
  and permits `ProviderLaunchHandle.result()` after unlock with no
  old-provider/new-vault mix.
- [ ] 2.9 Add authority-propagation tests proving every universe graph, run,
  resume, version, policy, judge, extract, and embed path supplies universe dir
  plus typed request eligibility; omitted scope fails closed unless an explicit
  genuine host-local capability is supplied. Inventory RAPTOR, reflexion,
  agentic retrieval, and every remaining call site too.
- [ ] 2.10 Add host-capability boundary tests proving it is minted only by
  trusted daemon bootstrap, is process-internal/non-serializable and
  identity-validated, is mutually exclusive with universe scope, and cannot be
  supplied through any MCP/API/JSON/environment/node/universe input or a
  caller-created lookalike.
- [ ] 2.11 Add intersection tests proving request eligibility can narrow but
  never replace or widen the fresh persistent assignment ceiling.
- [ ] 2.12 Add parity tests for every CLI/local/HTTP/in-process provider:
  `start()` consumes only `ProviderInvocation`, post-launch vault/env/auth/config
  mutation cannot alter the attempt, and direct/caller-created/removed
  `complete(...)` bypasses fail held before external access.
- [ ] 2.13 Add launch/handle lifecycle tests: distinct 1–30s launch deadline;
  partial child/request abort and lease release before unlock; writer progress
  after verified cleanup; durable fence on unprovable cleanup; completion
  timeout/cancellation propagation; process/request reaping; exactly-once
  finalization for success/error/timeout/cancel/close/consumed-start failure;
  concurrent result/result and result/close; idempotent cached outcome; no
  abandoned handle.
- [ ] 2.14 Add process-death crash injection before resource creation, after
  creation before registration, after registration before unlock, and after
  completion before finalization. Prove durable pending/active launch identity,
  tagged child or transport/market idempotency reconciliation, exactly-once
  accounting, and retained fail-loud fence when terminal state is unprovable.
- [ ] 2.15 Capture the focused red-test evidence before implementation.

## 3. Implement provider-destination authority

- [ ] 3.1 Implement one strict BYO service-to-provider resolver independent of
  the API-key environment map; reject aliases and mismatches before mutation.
- [ ] 3.2 Implement the per-universe cross-process assignment transaction:
  validate, secret-free durable journal, `pending + []` quarantine,
  unrelated-vault-preserving source update, atomic `ready|held` publication,
  `failed + []` recovery, `commit_ready` digest/identity validation, final-config
  commit linearization, and post-commit journal cleanup.
- [ ] 3.3 Publish singleton ceilings for the two executable BYO sources and
  deny-all ceilings for every non-executable source.
- [ ] 3.4 Persist every new universe as
  `engine_assignment_state="unassigned"` plus `allowed_providers=[]`.
- [ ] 3.5 Refresh and validate assignment/journal state before every provider
  attempt under shared-reader/exclusive-writer admission; intersect it with
  immutable request eligibility; mint non-serializable `ProviderInvocation`
  with exact auth/credential/lease authority; await
  `BaseProvider.start() -> ProviderLaunchHandle` under the reader; await handle
  completion after unlock; forbid provider-side authority re-resolution; ensure
  pins, policy, retry, ensembles, local fallback, and every role cannot widen
  authority.
- [ ] 3.6 Implement bounded cancellation-safe provider launch and router-owned
  handle lifecycle: fsynced secret-free pending/active launch journal and
  tagged resource/idempotency key before creation; cleanup guard; verified
  abort/reap before unlock; durable cleanup-failed fence; startup/assignment
  reconciliation; atomic terminal result/close ownership; exactly-once
  accounting across every success/failure/cancel/crash outcome.
- [ ] 3.7 Require explicit universe or genuine host-local authority at every
  call site and implement exact held outcomes:
  `ProviderAuthorityHeldError` for single/policy/ensemble calls without
  fallback prose, reserve ordinary ensemble `[]` for non-empty authority with
  no healthy judge, and return typed `set_engine` ready, setup-required, or
  failed statuses.
- [ ] 3.8 Regenerate the packaged runtime mirror and prove canonical/mirror
  parity.
- [ ] 3.9 Keep responses and documentation scoped to provider-destination
  authority; do not report credential isolation until the auth-overlay lane
  supplies its separate proof.

## 4. Convert existing assignments safely

- [ ] 4.1 Adapt #1606's secret-free inventory into a reviewed platform-wide
  decision manifest that classifies every existing universe without secrets.
- [ ] 4.2 Map unassigned universes to `unassigned + []`; map proven canonical
  or unambiguous legacy-alias Anthropic/OpenAI assignments to matching `ready`
  singletons; map non-executable intent to `held + []`; quarantine ambiguous,
  incomplete, or partially failed assignments as `failed + []`; stop on
  unreadable records.
- [ ] 4.3 Prove the conversion is locked, durable, idempotent, and leaves zero
  unclassified universes or post-cutover `None` ceilings; prove journal resume
  and preservation of unrelated vault records.
- [ ] 4.4 Execute the reviewed immutable-image deployment fence: quiesce legacy
  writers, convert the named production data volume, run the daemon-only
  loopback canary, and capture the release receipt before exposure.
- [ ] 4.5 Prove roll-forward recovery after interruption; never automatically
  restart a pre-ceiling writer or restore unrestricted state.

## 5. Verification and foldback

- [ ] 5.1 Run the focused assignment, source, router, auth-boundary regression,
  concurrency, and mirror-parity suites plus Ruff and `git diff --check`.
- [ ] 5.2 Run the full §14 concurrency/load-test proof with concurrent
  assignments and calls; retain freshness-stamped commands and results.
- [ ] 5.3 Obtain independent security/domain, concurrency, and spec/diff
  reviews; obtain the required opposite-provider re-review for any retained
  research-derived #1606 design after Claude capacity returns.
- [ ] 5.4 Validate this change and the full OpenSpec tree strictly.
- [ ] 5.5 Run rendered chatbot acceptance through the live `/mcp` connector:
  assign an engine, force the selected provider to fail, and retain a trace
  proving no alternate provider or quota was used.
- [ ] 5.6 Inspect post-fix production evidence for clean user use; if none is
  visible, leave a dated STATUS monitoring item instead of claiming proof.
- [ ] 5.7 Sync the provider-routing delta into the canonical spec, archive the
  change, update downstream dependency lanes, retire the STATUS row, and
  publish through the normal review/merge path.
