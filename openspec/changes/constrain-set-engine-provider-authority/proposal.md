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
and cutover had no reachable ready source. This revision names an implementable
request-scoped capability, publishes one-way sibling interfaces, preserves a
live-ready path before cutover, and removes ambiguous credential-material
handling.

## What Changes

- **BREAKING:** Every universe publishes an explicit provider-destination
  ceiling. `None` is a legacy pre-cutover encoding only. New, unassigned,
  pending, held, and failed states use `allowed_providers=[]`.
- Requester-owned local assignments publish a singleton canonical provider
  ceiling only after their assignment and opaque credential binding reference
  are ready. Unknown services, aliases, mismatches, and partial state fail
  before mutation. Raw-secret ingress/refusal remains solely owned by
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
  credential validation and binds request nonce plus authenticated principal;
  the provider sink binds it again to the exact universe, credential owner,
  provider, host, and current assignment generation. Background and remote
  execution require their own server-owned receipts and never reuse it.
- This change is the sole owner of provider-authority propagation into the
  provider layer. It defines the frozen invocation/launch boundary and
  exhaustive call-site threading; no separate
  `provider-authority-propagation` change is required.
- **BREAKING:** A router-minted immutable `ProviderInvocation` contains only
  the authorized provider, assignment generation, opaque credential binding
  reference, credential/auth provenance, and immutable call inputs. It never
  contains native secret material. Only executor-local
  `start(ProviderInvocation)` may resolve native material before returning a
  registered `ProviderLaunchHandle`.
- Every retry, policy attempt, judge call, hard pin, and stale context rechecks
  the fresh ceiling. Held authority fails before credential, quota,
  auth-health, or provider access and is never converted into fallback prose.
- The call-local result seam exposes stable provider-destination authority
  class and credential-kind inputs for the separately owned
  `provider-attempt-receipts` change without persisting a receipt here.
- Accepted-market activation has exact ownership: `paid-market-economy` owns
  the accepted economic agreement, while the distributed-execution B2
  signed-remote protocol plus anti-loss task B13 (`5.13`) owns the sole
  production composition root. V6 owns market selection/escrow/settlement, not
  authority minting. Ordinary provider routing never performs that conversion
  and never handles `market_rented` work.
- `self_hosted_endpoint` and `host_daemon` activation belongs to the named
  `activate-requester-host-engines` successor across
  `daemon-identity-and-host-pool`, `desktop-host-runtime`, and
  `provider-routing`. Cutover is forbidden until requester-local opaque
  custody or that host path is live and rendered acceptance can pass.
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
  provider capability minted only by authenticated transport middleware.
- `universe-lifecycle-and-soul`: Require every newborn universe to persist an
  explicit unassigned deny-all engine state within atomic creation.

## Impact

- Normative deltas: `provider-routing` and `universe-lifecycle-and-soul`.
- Planned runtime: universe engine assignment/config, provider authority
  context and launch boundary, provider call sites, migration/cutover, and
  focused security/concurrency tests. Runtime files remain outside this
  planning lane.
- Upstream inputs: authenticated transport middleware supplies the
  request-scoped capability; the sink derives target bindings from server
  state. `universe-creation` passes target universe/request lineage but does
  not construct another eligible-provider bundle.
- Sibling boundaries: `retire-mcp-provider-secret-deposit` owns raw
  `llm_api_key` ingress refusal and OS custody; `provider-attempt-receipts`
  owns immutable result-local evidence; credential-vault owns ambient
  credential isolation; paid-market/distributed-execution own remote market
  execution.
- Supersession: this current-main change replaces draft PR #1691 after Opus 5
  approval. PR #1617 remains closed/source-only; merged #1727 is the durable
  opposite-provider disposition.
- Sibling coordination is one-way: this change publishes its assignment lock,
  request-capability, held outcome, and reference-only launch interfaces;
  custody, universe-creation, and receipt owners consume those interfaces
  without reciprocal acceptance gates.
