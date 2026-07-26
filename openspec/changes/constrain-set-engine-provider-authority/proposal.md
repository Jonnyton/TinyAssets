## Why

`set_engine` records a preferred provider without constraining
`allowed_providers`. A failed user-selected engine can therefore fall through
to an unchosen provider, consume unrelated quota, or cross a privacy boundary.
The fail-closed credential environment shipped in PR #1592 closes ambient
credential recovery but does not close this provider-destination boundary.

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
- Before that full cutover, the existing authenticated founder
  `set_engine` write closes the originating leak immediately: a successful
  explicit raw-BYOC assignment atomically replaces `allowed_providers` with
  the singleton canonical destination (`anthropic -> claude-code`,
  `openai -> codex`). Unsupported or mismatched explicit assignments fail
  before mutation; existing records and newborn defaults remain untouched.
- Requester-owned local assignments publish a singleton canonical provider
  ceiling only after their assignment and opaque credential binding reference
  are ready. Legacy `byo_api_key` is read/migration-only and converts only
  through the custody-owned post-binding writer; otherwise it fails deny-all.
  Unknown services, aliases, mismatches, and partial state fail before
  mutation. Raw-secret ingress/refusal remains solely owned by
  `retire-mcp-provider-secret-deposit`.
- Self-hosted and host-daemon intent remains held at deny-all until its owning
  activation path proves executable authority. `market_rented` always remains
  deny-all in the ordinary provider router.
- Assignment becomes one cross-process, per-universe transaction: validate,
  publish deny-all quarantine, update source/reference state, then atomically
  publish one coherent ready or held assignment.
- Each live request provider attempt intersects the fresh assignment ceiling
  with a server-minted, request-scoped `ProviderRequestCapability` owned by
  `identity-auth-and-access-control`. The capability is created only after
  credential validation and binds request nonce plus authenticated principal.
  A server registry binds its liveness lease to the owning request execution
  scope and revokes it synchronously at request end, so inherited asyncio
  contexts cannot extend it. `call_provider` explicitly carries the exact
  object through the router's synchronous helpers and thread-pool closure
  rather than depending on `ContextVar` propagation. The provider sink binds
  it again to the exact universe, credential owner, provider, host, and
  current assignment generation.
- `harden-background-provider-execution-authority` owns a durable
  `ProviderWorkAuthorityReceipt` for post-response graph/run/resume/schedule,
  daemon, retrieval, and other task/thread/process provider work. Those paths
  remain held before that owner lands. Remote execution uses its separate
  signed distributed authority and never reuses either request carrier.
- `activate-connector-requester-authority` owns the Tier-1
  streamable-HTTP accepted-market path across identity, paid market,
  distributed execution, and the live connector. No Tier-1 cutover occurs
  until its OpenSpec names an action carried by one of the seven canonical
  live connector handles and proves that path completable without raw secret
  deposit or desktop/web-app prerequisites. It cannot depend on the
  deprecated `universe` handle.
- This change is the sole owner of provider-authority propagation into the
  provider layer. It defines the frozen invocation/launch boundary and
  exhaustive call-site threading; no separate
  `provider-authority-propagation` change is required.
- **BREAKING:** A router-minted immutable `ProviderInvocation` contains only
  the authorized provider, assignment generation, opaque credential binding
  reference, credential/auth provenance, and immutable call inputs. It never
  contains native secret material. Only
  `ProviderExecutor.start(ProviderInvocation)` may resolve native material,
  call the selected provider's canonical `complete(...)`, and return a
  registered `ProviderLaunchHandle`.
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
  execution.
- Supersession: this current-main change replaces draft PR #1691 after Opus 5
  approval. PR #1617 remains closed/source-only; merged #1727 is the durable
  opposite-provider disposition.
- Dependency direction is one-way: this change publishes its assignment lock,
  request carrier, held outcome, and reference-only launch interfaces and does
  not wait for sibling acceptance before the target spec lands. Custody does
  require exact-SHA provider-owner acceptance before its dependent runtime
  advances; the merged active universe-creation and receipt changes must adapt
  their conflicting deltas before archive/sync into canonical specs.
