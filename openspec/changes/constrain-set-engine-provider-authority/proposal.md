## Why

`set_engine` records a preferred provider without constraining
`allowed_providers`. A failed user-selected engine can therefore fall through
to an unchosen provider, consume unrelated quota, or cross a privacy boundary.
The fail-closed credential environment shipped in PR #1592 closes ambient
credential recovery for universe-scoped calls but does not close destination
choice or the process-global/no-universe branch that can still inherit
maintainer authentication.

Draft PR #1691 identified the right boundary but is rooted on obsolete history
and received an Opus 5 `ADAPT` in merged PR #1727. A first current-main
reconstruction also received `ADAPT`: the landed dark `Verified[T]` substrate
cannot mint requester-provider authority, sibling gates were still circular,
and cutover had no reachable ready source. An exact-revision re-review then
found that an ambient `ContextVar` cannot cross the router thread pool,
background/daemon work had no authority owner, the source table was not total,
and merged-unsynced sibling deltas contradicted the proposed boundary.
Successive reviews also exposed inherited-task liveness, typed setup mapping,
unowned local transport authority, stale engine-readiness predicates, and dead
advertised setup paths. This revision closes each boundary and treats a
surface with no completable path as failed release readiness rather than safe
deny-all.

## What Changes

- **BREAKING:** Every universe publishes an explicit provider-destination
  ceiling after gated migration. `None` and absent assignment fields retain
  exact legacy semantics until the manifest is complete and the deployment
  flag flips. Post-cutover new, unassigned, pending, held, and failed states
  use `allowed_providers=[]`.
- A server-owned, default-empty set of isolated acceptance-test universes
  enables the complete post-flip-equivalent contract before the global flip.
  A separate default-empty set of isolated test principals with no existing
  home/universe bootstraps generated-ID public/first-contact birth; the server
  registers the generated ID before visibility and thereafter keys only on
  that ID. Caller data cannot opt in, unlisted universes preserve shipped
  behavior, and existing user universes are never migrated merely to obtain
  proof.
- No flag-independent legacy-action subsystem ships. While the effective gate
  is dark, every `set_engine` source/service and provider path retains exact
  shipped behavior under its configured production-auth or development-mode
  dispatch gate; this change adds no authenticated-founder precondition or
  pre-cutover ceiling write. The hidden action is unavailable to Tier-1 chatbots and
  its retirement strictly reduces new exposure. R2-1a implements destination
  authority only behind the effective gate after the three ready-path
  successors; task 8.1 migrates all legacy `allowed_providers=None` records.
  This exact owner/timing replaces the unsafe pre-cutover shortcut.
- Requester-owned cloud custody publishes only its cloud binding entry and
  writer preference. A ready assignment must cover every role with a live
  provider call site and carry one provider-specific opaque binding entry per
  authorized destination. Current Codex coverage may satisfy the live-role
  set; current Claude coverage remains held until the host successor adds an
  attested requester-owned `ollama-local` supplement. Its binding carries the
  requester endpoint and executor-host identity, and executor launch constructs
  transport solely from that endpoint. Process defaults, ambient
  `OLLAMA_HOST`, unauthenticated loopback, and maintainer compute never supply
  it. A dormant role does not block readiness, but its first live caller holds
  until covered. Only the atomic compositor publishes a multi-provider
  ceiling. Legacy `byo_api_key` is
  read/migration-only and converts only through the custody-owned
  post-binding writer; otherwise it fails deny-all. Unknown services, aliases,
  mismatches, and partial state fail before mutation. Raw-secret
  ingress/refusal remains solely owned by
  `retire-mcp-provider-secret-deposit`.
- Self-hosted and host-daemon intent remains held at deny-all until its owning
  activation path proves executable authority. `market_rented` always remains
  deny-all in the ordinary provider router.
- Assignment becomes one cross-process, per-universe transaction: validate,
  publish deny-all quarantine, update source/per-provider binding state, then
  atomically publish one coherent role-complete `ready`, remote-only
  `remote_ready`, or deny-all held assignment.
- Each live request provider attempt intersects the fresh assignment ceiling
  with a server-minted, request-scoped `ProviderRequestCapability` owned by
  `identity-auth-and-access-control`. For every non-deferred `tools/call`,
  TinyAssets-owned FastMCP message middleware reads only the low-level current
  per-message HTTP request, re-derives its bearer identity, and reserves a
  session/request/tool-bound one-shot token; inherited/snapshotted fallback
  requests and stateful-session initialize Context never authorize later
  messages. Task-augmented/deferred calls mint no request capability and hold
  until the background owner issues a durable receipt. The TinyAssets
  registered-tool wrapper claims the reserve against the actual synchronous
  worker on entry after AnyIO selects it, and wrapper/message `finally`
  revokes the lease before result release. Detached, nested, copied, stale,
  second-claim, and caller-created contexts cannot obtain authority.
  `call_provider` explicitly carries the exact claimed capability
  through the router's synchronous helpers and thread-pool closure rather
  than depending on `ContextVar` propagation alone. The provider sink binds
  it again to the exact universe, credential owner, provider, host, and
  current assignment generation.
- `harden-background-provider-execution-authority` owns a durable
  `ProviderWorkAuthorityReceipt` for post-response graph/run/resume/schedule,
  daemon, retrieval, and other task/thread/process provider work. Those paths
  remain held before that owner lands. It also owns the closed universe-less
  maintainer-maintenance receipt for the fixed private completion auth probe,
  bound to host/operator principal, exact operation, prompt digest, and
  lifetime without universe/run/branch/requester data or quota. Remote
  execution uses its separate signed distributed authority and never reuses
  either request carrier.
- `activate-connector-requester-authority` owns the Tier-1
  streamable-HTTP accepted-market path across identity, paid market,
  distributed execution, and the live connector. No Tier-1 cutover occurs
  until its OpenSpec names an action carried by one of the seven canonical
  live connector handles and proves that path completable without raw secret
  deposit or desktop/web-app prerequisites. It cannot depend on the
  deprecated `universe` handle. It persists target source `accepted_market`
  plus references to the accepted agreement and non-executable B13 activation
  mandate. Its pre-routing seam delegates each concrete `converse` job to B13
  for a fresh exact B2 after every owner-native result is current; ordinary
  provider ceilings and role chains are not consulted.
- Main's anonymous wiki-canary bearer and
  `_WikiCanaryExecutionAuthority` remain canary-only. They never mint provider
  authority even while provider middleware composes on the same FastMCP app.
- Provider bindings do not create a parallel outbound-connection ledger. For
  remote HTTP providers, the binding consumes the current user/per-universe
  grant and credential-blind daemon-side proxy owned by
  `outbound-boundary-layer`; a missing/revoked grant holds without ambient
  fallback. `ProviderExecutor.start()` remains the sole provider-layer
  tuple validator and launch coordinator, but it passes only a redacted
  request through a grant-bound proxy handle; the outbound proxy alone
  resolves the credential reference and performs remote HTTP I/O. Runtime
  activation waits for that owner to accept the exact handle contract.
- This change is the sole owner of provider-authority propagation into the
  provider layer. It defines the frozen invocation/launch boundary and
  exhaustive call-site threading; no separate
  `provider-authority-propagation` change is required.
- **BREAKING:** A router-minted immutable `ProviderInvocation` contains only
  the authorized provider, assignment generation, opaque credential binding
  reference, credential/auth provenance, and immutable call inputs. It never
  contains native secret material.
  `ProviderExecutor.start(ProviderInvocation)` alone validates the complete
  binding tuple, coordinates canonical `complete(...)`, and returns a
  registered `ProviderLaunchHandle`. Only CLI/local/in-process transports may
  dereference inside executor child/request memory; remote HTTP receives a
  grant-bound proxy handle, and the outbound proxy alone resolves its
  credential reference and performs network I/O.
- Every retry, policy attempt, judge call, hard pin, and stale context rechecks
  the fresh ceiling. Held authority fails before credential, quota,
  auth-health, or provider access and is never converted into fallback prose.
- The call-local result seam exposes stable provider-destination authority
  class and credential-kind inputs for the separately owned
  `provider-attempt-receipts` change without persisting a receipt here.
- Accepted-market activation has exact ownership: `paid-market-economy` owns
  the accepted economic agreement, while distributed-execution design
  Decision B2's signed-remote protocol plus anti-loss task B13 (`5.13`) owns the sole
  production composition root. V6 owns market selection/escrow/settlement, not
  authority minting. Ordinary provider routing never performs that conversion
  and never handles `market_rented` work.
- `self_hosted_endpoint`, `host_daemon`, target
  `founder_hosted_daemon`, and attested `local_model` activation belong to the named
  `activate-requester-host-engines` successor across
  `daemon-identity-and-host-pool`, `desktop-host-runtime`,
  `identity-auth-and-access-control`, and `provider-routing`. It is the sole
  writer of ready host/local assignments, including `local_model` ->
  `["ollama-local"]`, and the sole minter of attested interactive local
  `ProviderHostRequestCapability`. Cutover is forbidden until Tier-1 connector
  market setup and Tier-2/Tier-3/plugin local setup are each completable,
  the exact typed authority hold renders only live setup paths, and every
  background/daemon authority bridge is live. All three successors have one
  durable exact-files STATUS lane.
- Draft PR #1606 remains source-only retained work. Its assignment lock,
  transaction, migration, and deployment-fence pieces may be selectively
  ported after current-main review; it does not merge as an authority owner.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-routing`: Require fail-closed provider-destination assignment,
  server-minted request capability, reference-only invocation, and frozen
  executor-local launch.
- `identity-auth-and-access-control`: Define the unforgeable request-scoped
  HTTP capability, successor-owned attested local transport capability, and
  canonical surface-live setup-required envelope.
- `universe-lifecycle-and-soul`: Require every newborn universe to persist an
  explicit unassigned deny-all engine state within atomic creation.

## Impact

- Normative deltas: `provider-routing`,
  `identity-auth-and-access-control`, and
  `universe-lifecycle-and-soul`.
- Planned runtime: universe engine assignment/config, provider authority
  context and launch boundary, provider call sites, migration/cutover, and
  focused security/concurrency tests. Runtime files remain outside this
  planning lane.
- Upstream inputs: authenticated transport middleware supplies the
  request-scoped capability; an internal typed carrier crosses the router
  pool; the sink derives target bindings from server state. The merged active
  `universe-creation` change currently supplies a caller-built eligible set,
  raw BYOC/accepted-market setup paths, and receipt `authority_class` naming.
  Before archive/sync it MUST adopt this change's same-named identity
  requirement: target lineage only, `fulfillment_class`, and setup paths
  proven completable on the current request surface.
- Sibling boundaries: `retire-mcp-provider-secret-deposit` owns raw
  `llm_api_key` ingress refusal and OS custody; `provider-attempt-receipts`
  owns immutable result-local evidence; credential-vault owns ambient
  credential isolation; paid-market/distributed-execution own remote market
  execution. `retire-legacy-live-mcp-tools` owns removal of hidden
  `universe/set_engine`; removal strictly reduces new exposure and need not
  preserve a new writer. Its handoff is instead that all legacy
  `allowed_providers=None` records require gated migration, and
  Tier-2/Tier-3/plugin assignment needs the requester-host successor after
  removal. It does not make that path Tier-1.
- Supersession: this current-main change replaces draft PR #1691 after Opus 5
  approval. PR #1617 remains closed/source-only; merged #1727 is the durable
  opposite-provider disposition.
- Dependency direction is one-way: this change publishes its assignment lock,
  request carrier, held outcome, and reference-only launch interfaces and does
  not wait for sibling acceptance before the target spec lands. Custody does
  require exact-SHA provider-owner acceptance before its dependent runtime
  advances; the merged active universe-creation and receipt changes must adapt
  their conflicting deltas before archive/sync into canonical specs.
