## Why

Live-request provider authority ends when request middleware returns, but
graph runs, resumes, schedules, daemon cycles, retrieval, reflexion, ingestion,
and maintenance can reach providers afterward or in another task, thread, or
process. Today those paths can inherit ambient process identity or rely on
queue/run artifacts that identify work without authorizing provider spend;
the landed provider-authority target therefore holds them until one durable,
server-owned background authority contract exists.

## What Changes

- Add a closed `ProviderWorkAuthorityReceipt` domain with two variants:
  universe work and universe-less maintainer maintenance.
- Separate durable authorization intent (`ProviderWorkBinding`) from a
  bounded execution receipt. Schedule rows, run IDs, branch tasks, queue
  claims/leases, actor strings, and serialized receipt IDs grant nothing by
  themselves.
- Mint universe-work receipts only from a current server-owned binding after
  revalidating principal, actor/daemon, universe, branch, run, operation,
  assignment generation/digest, provider binding, revocation, and budget.
- Bind each receipt to one active execution claim across task/thread/process
  handoff, with atomic invocation-slot accounting, bounded lifetime, explicit
  cancellation/expiry, restart reconciliation, and fail-closed ambiguous
  launch handling. Retries may narrow or consume the receipt but never widen
  it.
- Define the closed universe-less maintenance path required by the shipped
  fixed private `_AUTH_PROBE_PROMPT`: host/operator principal, exact provider
  and operation, opaque credential binding/digest, private-prompt digest,
  invoking runtime/daemon identity, separate maintenance binding/budget, and
  no universe, run, branch, requester identity, requester content, or
  requester quota. Under V2 the ordinary router retains cached and read-only
  non-completion presence/freshness health checks but cannot launch the probe
  from a universe receipt.
- Require deferred/task-augmented connector work, graph/run/resume/schedule
  execution, daemon loops, retrieval/reflexion, ingestion/evaluation, and
  mirrored Claude-plugin provider bridges to carry the exact server-issued
  receipt or hold before provider, credential, outbound-proxy, auth-health, or
  quota access.
- Keep the contract internal. It adds no MCP handle/action, raw-secret path,
  Agent Village/web dependency, or alternate provider-routing sink.
- Preserve shipped behavior while provider-authority V2 is dark. A
  server-owned isolated maintenance canary may exercise the fixed probe before
  cutover; a universe gate cannot become effective for a worker/provider until
  maintenance viability and supervisor quarantine are proven, and caller data
  cannot opt in. Darkening a gate stops new issuance but never disables
  reconciliation or fences for authority records already in the ledger.

## Capabilities

### New Capabilities

- `background-provider-execution-authority`: Define durable work bindings,
  bounded provider-work receipts, execution claims, invocation accounting,
  maintenance authority, lifecycle/recovery, and non-authority inputs.

### Modified Capabilities

- `daemon-runtime-and-dispatch`: Require claimed, scheduled, resumed, and
  autonomous work to obtain background provider authority independently of
  queue identity or lease state.
- `graph-execution-substrate`: Require provider-capable graph nodes and their
  task/thread/process bridges to propagate the exact receipt and preserve its
  lineage, budget, cancellation, and terminal fences.
- `provider-routing`: Preserve ordinary router eligibility for unknown or
  inconclusive subscription health while making the worker-only V2 maintenance
  state `auth_unknown` a quarantine trigger alongside `not_logged_in`.

## Impact

Planned runtime work is internal to provider-work authority storage/issuance,
daemon/branch-task/scheduler/run execution, graph compilation/execution, and
the existing provider carrier seam. The change consumes the active
`constrain-set-engine-provider-authority` assignment/sink contract,
`ProviderAssignmentAdmission`, outbound credential-blind proxy, authenticated
request subject, daemon/runtime identity, and existing run/branch/universe
authorization; schedule/subscription issuance additionally remains inactive
until `harden-background-branch-execution-authority` supplies its
server-bound principal and target-authorization record. It does not trust the
shipped caller-controlled `owner_actor` seam or duplicate those owners.
Focused tests must cover
forgery, stale/revoked lineage, cross-process replay, concurrent claims,
budget exhaustion, cancellation, ambiguous launch, crash recovery, dark-mode
compatibility, mirrored runtime parity, and the applicable complete-system
load proof. Runtime implementation and canonical spec sync remain gated until
this target change is reviewed and landed.
