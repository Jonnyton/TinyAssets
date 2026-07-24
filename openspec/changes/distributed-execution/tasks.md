# Tasks - distributed execution

Current-main execution ledger, refreshed against `origin/main@405a7b7e` on
2026-07-24. A checked task means its behavior is present on main, not merely
implemented on a draft branch. Only the #1485 runner/diagnostic seam is checked.

The immediate apply slice is D0, a dark fake/test-only contract spine. D0 does
not complete V1. No item may disappear because it is outside D0; the complete
V1-V8, S0-S16, and B01-B44 destination remains below.

## 0. As-built baseline

- [x] 0.1 Preserve the backend-neutral `runner/v1` typed seam, fail-closed
  unavailable backend, and detached sandbox diagnostic from #1485; keep the
  production execution path unwired and make no confinement claim.
- [ ] 0.2 Before each implementation bite, rebase the task assumptions onto the
  then-current `origin/main`, re-claim exact runtime/test files, and record any
  newly landed overlap without changing a checkbox until behavior is verified.

## 1. D0 - immediate dark authority contract spine

- [ ] 1.1 Add failing tests for direct construction, subclassing, copy, pickle,
  and token-free minting of `Verified[T]`, plus a positive mechanism-adapter
  mint after real test verification.
- [ ] 1.2 Implement the sealed verifier-neutral `Verified[T]` carrier and
  package-private mint seam; keep M1, M2, and M3 adapters separate.
- [ ] 1.3 Add canonicalization/domain-vector tests for capsule, grant,
  candidate, and terminal records, including unknown domain/version/field,
  JSON type confusion, integer bounds, and cross-domain signature reuse.
- [ ] 1.4 Implement immutable per-domain field contracts and final-shaped
  canonical carrier/verification code; provide no caller-controlled
  `unbound_fields`, binder, issuer, or verify key.
- [ ] 1.5 Add a failing generation-restore test proving a correctly signed
  superseded record cannot pass after mutable state is restored.
- [ ] 1.6 Implement monotonic generation/fence allocation and a durable
  evidence-ledger rejection floor.
- [ ] 1.7 Add replacement/UPSERT mutations for both append-only evidence tables
  and exact schema/trigger/index/namespace mismatch tests.
- [ ] 1.8 Implement replacement-resistant append-only guards and exact
  fail-closed evidence-table validation with no auto-repair.
- [ ] 1.9 Add replay tests for junk plus one valid attestation, duplicate
  identical valid attestations, two distinct valid attestations, mutable
  terminal reset, and changed-content idempotency reuse.
- [ ] 1.10 Implement verify-first, content-deduplicated replay and stable
  idempotent receipts derived from verified terminal facts.
- [ ] 1.11 Add blob mutations and forced interleavings for wrong bytes,
  stale per-instance index, physical-root aliases, and both scheduler orders.
- [ ] 1.12 Implement decision-point M2 blob proof, physical-root coordination,
  operation-local index mutation, and one blob-root-then-SQLite lock order.
- [ ] 1.13 Add the explicit `TestAuthorityRoot` and fake composition root using
  test-owned keys and temporary state through the same mechanism adapters.
- [ ] 1.14 Add production-denial tests for production/unknown mode, non-test
  storage, route registration, caller keys/verifiers, production-module import
  or call-site use, and provider, credential, queue, graph, GitHub, market, or
  money adapters.
- [ ] 1.15 Prove D0 end-to-end in focused tests:
  capsule -> grant -> candidate + verified blobs -> fenced terminal -> restart
  replay, with every production/external adapter absent.
- [ ] 1.16 Independently review the exact D0 diff and show at least one real
  authority mutation red before the fix and green after it.

## 2. Current-main extraction manifest

Never merge, rebase, or cherry-pick a named stale PR wholesale. For each step,
port a failing test onto current main, implement the least behavior, record the
source PR/commit, and verify that unrelated current-main files are unchanged.

- [ ] 2.1 Inventory #1472 only for reviewed capsule/result/device canonical
  vectors and mutation tests; exclude its S0 worker/deploy removals and broad
  runtime/config lineage.
- [ ] 2.2 Extract from #1477 only the minimal M1/B2 primitives needed by D0;
  exclude `run_graph`, transport, provider, production-root, and inherited
  unrelated changes.
- [ ] 2.3 Extract #1479's immutable domain partitions and exact owner binding
  after the base M1 carriers are green on current main.
- [ ] 2.4 Extract #1481's monotonic floor, replacement-resistant evidence
  ledger, and verify-first replay after domain contracts are green.
- [ ] 2.5 Extract #1487's fresh blob proof, physical-root identity, lock order,
  operation-local index, and exact table validation after the ledger is green.
- [ ] 2.6 Extract only #1491's key/thumbprint binding and non-vacuous per-fence
  mutations after the relevant current-main S3 carriers and consumers exist
  and before any authenticated B2 transport is activated.
- [ ] 2.7 Recreate #1478's CPython 3.11 and semantic authority gates from stable
  current-main test paths; keep suspicious-read scanning advisory.
- [ ] 2.8 Prove #1572 contributes no code, schema, test, or compatibility
  behavior to this change; its M2 branch-version/legacy-ID break remains
  separately design-gated.
- [ ] 2.9 Diff the extraction result against #1697 and prove its exact
  server-derived epoch-2 worker descriptor, heartbeat, lifecycle, and
  contested-registration behavior remains intact.

## 3. Vertical-slice delivery ledger (V1-V8)

- [ ] 3.1 V1 - persist one real job; authenticate the owner daemon; mint the
  exact capsule-bound M1 grant; accept the device-signed candidate plus fresh
  M2 blobs; execute through the narrow runner seam; fenced-complete with an M1
  terminal attestation; restart-replay the same fact through a non-test
  composition root.
- [ ] 3.2 V2 - externalize signer/KEK custody; confine owner-daemon execution;
  add fixed Linux/Windows backends, broker, exact-source staging/revalidation,
  destruction, coordinator, and the single B2 routing cutover.
- [ ] 3.3 V3 - consume an accepted result through M1/M2/M3 and open exactly one
  result-bound reviewable GitHub PR across retries/crashes; never approve or
  merge.
- [ ] 3.4 V4 - stage live enrollment, run the real public B2 chatbot path,
  prove Windows owner-daemon completion, stale-result choreography, authority
  CI, zero platform workers, 1,000-poller/10,000-job load, and post-fix watch.
- [ ] 3.5 V5 - add separate `source_exec` policy/result types and
  owner-controlled recipient-bound private delivery without repo-capability
  inheritance or platform-held private bytes/credentials.
- [ ] 3.6 V6 - add deterministic public-source market selection before the
  unchanged B2 protocol with fenced escrow, independent verification,
  settlement, and reputation; no platform fallback.
- [ ] 3.7 V7 - run a non-founder market job through rendered live B3,
  independent verification and current-fence settlement; prove no-host pending
  behavior and explicit host-visible-private consent.
- [ ] 3.8 V8 - make only GitHub's protected SHA-bound transaction plus fresh
  confirmation produce `merged`, then close every registered adjacent
  authority sink with the correct M1/M2/M3 proof and mutation probe.

## 4. Stage preservation map (S0-S16)

- [ ] 4.1 S0 - zero platform workers and no in-process user code beside
  platform signing/KEKs; pinned trust root and purpose-separated external
  custody; live universe-engine cutover remains host-gated.
- [ ] 4.2 S1 - exact path-free capsule bound to audience, job, lease, fence,
  source, policy, and pinned M1 capsule key.
- [ ] 4.3 S2 - atomic claim/fence/expiry/CAS, signed grant and terminal,
  monotonic generation, append-only integrity, and attestation-derived replay.
- [ ] 4.4 S3 - WorkOS stays M3; platform-decided intent/enrollment/credential/
  access/revocation use M1; device possession and exact request principal bind
  acceptance.
- [ ] 4.5 S4 - one trust-root-built composition root mounts poll, claim,
  heartbeat, candidate, and completion with no caller-injected authority;
  execution-route failure remains isolated so authoring and browsing stay
  available.
- [ ] 4.6 S5 - device-signed result, decision-point M2 blob proof,
  `Verified[BlobRef]`, fresh completion proof, and explicit owner-CAS proof.
- [ ] 4.7 S6 - fixed reviewed Linux isolation backend and policy with no
  caller-selected mounts, image, network, devices, or flags; OS attestation is
  established only inside the isolated child.
- [ ] 4.8 S7 - job/lease/fence-bound model broker capability with scoped
  budget, cancellation, process/session binding, and no raw provider key.
- [ ] 4.9 S8 - exact accepted source closure, malicious-input-safe staging,
  second-child fresh-base revalidation, cancellation map, and destruction.
- [ ] 4.10 S9 - fixed Windows WSL2/Podman path, authenticated broker bridge, no
  native/broad-mount fallback, and real escape/readiness proof.
- [ ] 4.11 S10 - all owner-daemon routes use B2; retire JSON/filesystem/local/
  cloud-worker coding execution and environment-flag bypasses.
- [ ] 4.12 S11 - rendered public-repo proof, non-special enrollment,
  stale-result rejection, zero-worker/load evidence, and clean-use/watch.
- [ ] 4.13 S12 - separate source-exec image, policy, readiness, input/output,
  and class-confusion refusal; never repo mounts or repo patches.
- [ ] 4.14 S13 - deterministic BYO-or-market selection before unchanged B2
  eligibility/claim, using verified facts and no platform fallback.
- [ ] 4.15 S14 - current-fence/result-bound escrow and settlement, independent
  verification/replay, M1 claim ownership, verified payment facts, reputation.
- [ ] 4.16 S15 - owner courier, credential stripping, recipient encryption,
  owner-controlled storage/proof, confidentiality tier, and honest host
  visibility.
- [ ] 4.17 S16 - real non-founder B3 run, unchanged B2, independent
  verification, fenced settlement, no-host pending, rendered proof, clean-use.

## 5. Anti-loss backlog (B01-B44)

### V1 foundation and hardening

- [ ] 5.1 B01 - durable monotonic generation floor rejects restored
  superseded generations using append-only evidence.
- [ ] 5.2 B02 - block duplicate, `INSERT OR REPLACE`, `REPLACE`, and UPSERT
  mutation of completion attestations without relying on `recursive_triggers`.
- [ ] 5.3 B03 - apply the same replacement protection to `lease_events`.
- [ ] 5.4 B04 - verify-first replay ignores junk, deduplicates identical valid
  facts, and rejects conflicting distinct valid facts.
- [ ] 5.5 B05 - remove caller-neutralizable unbound fields; immutable strict
  domain contracts fail closed on unknown/unclassified fields.
- [ ] 5.6 B06 - bind signed owner to the exact-request authenticated principal
  at candidate, completion, and replay with no grant-owner fallback.
- [ ] 5.7 B07 - enforce physical blob-root coordinator then SQLite transaction
  on candidate and completion.
- [ ] 5.8 B08 - key blob coordination by physical directory identity across
  supported Windows aliases and fail closed when identity is unavailable.
- [ ] 5.9 B09 - reload, validate, mutate, and atomically persist an
  operation-local blob index under the shared lock.
- [ ] 5.10 B10 - validate the exact full completion-attestation table contract
  and never auto-repair mismatched evidence state.
- [ ] 5.11 B11 - implement the S3 authority map: WorkOS M3 plus M1
  intent/approval/enrollment/credential/access/revocation and verified request.
- [ ] 5.12 B12 - bind bearer token and device-key resolution to the signed
  enrollment/credential chain; reject substitution, rollback, and cleared
  revocation.
- [ ] 5.13 B13 - build the sole complete execution-authority composition root;
  no partial runtime, caller binder/key, or unsigned fallback.
- [ ] 5.14 B14 - build release-pinned trust and purpose-separated external
  custody; private keys stay outside control-plane/user-code memory.
- [ ] 5.15 B15 - make blob acceptance decision-point M2 returning verified blob
  references; JSON/rows are consistency vetoes only.
- [ ] 5.16 B16 - build `run_graph` -> run/outbox/job -> authenticated B2 ->
  accepted-result checkpoint resume with crash/cancel/duplicate/healing tests.
- [ ] 5.17 B17 - open one M1-authorized, M2-exact, M3-reconfirmed reviewable PR
  per accepted result; retire ambient/caller-target effects; never merge.
- [ ] 5.18 B18 - land verifier-neutral M2/M3 minting without routing content or
  external facts through M1 `RecordVerifier`.

### Confinement, gates, governance, and live staging

- [ ] 5.19 B19 - deliver a usable per-job sandbox backend and confine every
  user-code route while externalizing key/KEK trust; #1485 supplies only the
  unwired seam and diagnostic.
- [ ] 5.20 B20 - add blocking site/effect/probe equality, semantic mutations,
  real CPython 3.11, exact mirror regeneration, and stable aggregate CI.
- [ ] 5.21 B21 - close mutation-probe gaps across auth, ACL/home, branch
  content, market, GitHub, run consumers, daemon control, blobs, and queue
  cancellation.
- [ ] 5.22 B22 - apply the exec-plan/PLAN amendment package only with host
  approval and exact-source overlap resolution.
- [ ] 5.23 B23 - redesign merge authority so only a fresh protected,
  SHA-bound GitHub mutation plus exact post-read mints merge confirmation.
- [ ] 5.24 B24 - stage live S3 signing with new-record shadow/dual verification,
  bounded legacy population, re-enrollment, and host-approved enforcement flip.
- [ ] 5.25 B25 - stage market claim-ownership signing and reconcile legacy
  positions before enforcing no-artifact/no-settlement.
- [ ] 5.26 B26 - preserve WorkOS JWT/JWKS as M3; never platform re-sign it or
  replace live auth implicitly.
- [ ] 5.27 B27 - remediate the live universe-engine execution path only through
  staged host go/no-go while preserving uptime and separating trust domains.

### Remaining S0-S16 implementation and integration

- [ ] 5.28 B28 - implement the fixed Linux launcher/backend and real
  escape/readiness suite with no caller-selected fallback.
- [ ] 5.29 B29 - implement the model broker's session binding, scoped
  credential, per-call fence, cost/budget, cancellation, and framing.
- [ ] 5.30 B30 - implement exact-source staging/extraction, isolated
  revalidation, cancellation phases, and destruction proof.
- [ ] 5.31 B31 - implement fixed Windows WSL2/Podman and authenticated
  cross-VM broker bridge with real escape/readiness tests.
- [ ] 5.32 B32 - cut every tray/owner coding route to B2 and retire legacy
  JSON/filesystem/local/cloud-worker execution.
- [ ] 5.33 B33 - build the S11 load/acceptance harness, exact live fixture,
  stale-result choreography, evidence manifest, and thresholds.
- [ ] 5.34 B34 - implement distinct source-exec policy/image/readiness and
  class-confusion tests.
- [ ] 5.35 B35 - implement deterministic BYO/market selection over unchanged B2
  eligibility and claims.
- [ ] 5.36 B36 - implement fenced escrow/settlement, independent
  verification/replay, disputes, and observed reputation.
- [ ] 5.37 B37 - implement private-source courier, stripping, owner-CAS proof,
  recipient encryption, consent, challenges, and retention; platform-hosted
  private ciphertext remains prohibited without a separately approved PLAN
  amendment.
- [ ] 5.38 B38 - run the non-founder B3 live test with unchanged B2, independent
  verification, settlement, no-host pending, rendered proof, and clean-use.
- [ ] 5.39 B39 - close adjacent positive-authority surfaces in ACL/home,
  daemon control, schedules, branch ownership/publication/execution, run
  consumers, rollback, memory promotion, and task cancellation.
- [ ] 5.40 B40 - specify and build authenticated distribution, rotation,
  revocation, and atomic activation of daemon capsule trust sets.
- [ ] 5.41 B41 - finish non-special enrollment across tray, browser/chat
  approval, inventory, revoke, re-enroll, and diagnostics.
- [ ] 5.42 B42 - enforce the platform-issued daemon capability ceiling and
  signed eligibility/policy/image registry; self-declaration only narrows.
- [ ] 5.43 B43 - own canonical public-source snapshot production, signed
  producer attribution, manifest, exact base, and pre-claim CAS commit.
- [ ] 5.44 B44 - build the durable owner-daemon coordinator from poll through
  claim, verify, heartbeat, source, broker, launch, revalidate, upload,
  completion, teardown, and crash-spool recovery.

## 6. Queue and evidence non-promotion gates

- [ ] 6.1 Add an integration test where a valid admission receipt, exact live
  #1697 descriptor, and won epoch-2 scheduling claim still cannot create an
  external lease, provider call, candidate, or terminal fact without a valid
  B2 owner/daemon/job/capsule/lease/generation/fence grant.
- [ ] 6.2 Add type/domain tests proving admission receipts, internal scheduling
  leases, provider-attempt receipts, B2 grants, candidates, and terminal
  records cannot be wrapped or promoted into one another.
- [ ] 6.3 Reconcile PLAN's file-locked claimer wording with the transactional
  epoch-2 OpenSpec contract before implementing graph-cycle claim integration;
  do not edit PLAN without host approval.
- [ ] 6.4 Implement the scheduling-to-B2 handoff only after 6.1-6.3 pass,
  preserving v1 history and #1697 descriptor derivation/liveness.

## 7. Review, rollout, and rollback gates

- [ ] 7.1 For each authority fix, prove a decision-level mutation red before
  the fix and green after it; structural/type-only tests are supporting
  evidence, not completion.
- [ ] 7.2 Before any production root or route, obtain explicit host approval of
  trust-manifest distribution, purpose-separated custody, rotation,
  revocation, and signer-failure behavior.
- [ ] 7.3 Before any live route, provider/credential use, GitHub effect,
  market/money behavior, deploy, or rendered acceptance, obtain dual-family
  review of the same integrated current-main candidate.
- [ ] 7.4 Run the applicable CPython 3.11, semantic authority, mirror parity,
  concurrency/load, and public canary gates on the integrated candidate.
- [ ] 7.5 Stage each live authority surface through bounded shadow/dual verify
  and explicit host go/no-go; signer or external-authority failure leaves work
  pending.
- [ ] 7.6 Complete final user-surface acceptance through a rendered chatbot
  conversation using the live connector and record trace/screenshot evidence.
- [ ] 7.7 Check fresh post-fix real-user clean-use evidence; if none exists,
  leave a dated watch instead of claiming proven clean use.
- [ ] 7.8 Exercise rollback: stop new claims while retaining trust manifests,
  floors, evidence ledgers, signatures, blob bindings, and terminal
  attestations; prove there is no fake, unsigned, row-authoritative, queue, or
  platform-compute fallback.
