## Why

TinyAssets has historical Section 14 / Track J scale targets but no reusable
current-topology harness and no verified public capacity envelope. The
2026-07-24 repository baseline at `origin/main` `412a876a` describes one MCP
origin, one shared host volume, fixed cloud-worker processes sharing provider
auth homes, and no usable OS-isolating `SandboxBackend` or proven
requester-authorized public executor. A separate bounded live probe reported
deployed SHA `519fb2ea`, but did not establish a capacity envelope; publishing
the target numbers as present capacity would be false.

Current `origin/main` `0a82dbec` adds useful control-plane substrate without
changing that dated fixture: merged PR #1693 reauthorizes replay, #1694
transactionally commits the canonical Request, admission receipt, public
committed result/event, and pending epoch-2 task, and #1696 adds the bounded
epoch-2 queue lifecycle and internal claim lease. Those artifacts prove only
their exact admission, durable-enqueue, and internal-scheduling stages. They do
not prove provider or BYOC reachability, market supply, signed B2 execution
authority, execution lifecycle, delivery, settlement, or public execution
capacity.

## What Changes

- Add a topology-adapter contract that runs one capacity/isolation scenario
  catalog against a dated, probe-verified baseline topology and later accepted
  topologies without copying scenarios into each infrastructure change.
- Define a dated baseline packet, raw evidence schema, repeatability rules, and
  a verified-envelope record. A path or metric without applicable passing
  evidence reports `unknown`; vendor quotas, design targets, skipped tests, and
  historical Track J thresholds are never promoted to verified capacity.
- Require representative steady, burst, saturation, recovery, noisy-neighbor,
  tenant-isolation, zero-host, and authority-isolation scenarios. Domain-owned
  suites remain authoritative for operator requests, paid-market workflow,
  live-price discovery, universe authority, identity/reset, and visibility.
- Stage-type every assertion and envelope cell across admission, durable
  enqueue/epoch, internal scheduling lease, provider/executor authority,
  signed B2 execution lease, execution lifecycle, delivery, and settlement.
  Evidence from one stage never promotes another stage.
- Publish both path-level capacity cells and a separate complete-platform
  readiness matrix. The matrix covers every required surface without letting
  one green request path stand in for authoring, collaboration, automation,
  model execution/training, delivery, market, moderation, or recovery.
- Define a versioned owner plug-in ABI, load-validity controls, per-stage and
  per-user metrics, an explicit isolation matrix, and provenance for
  requester-BYOC, market-rented, deterministic-fake, unavailable, and other
  capacity classes.
- Represent market capacity as a freshness-bounded, price-conditioned supply
  curve with owner-provided quote/reservation/settlement evidence, not as a
  timeless fixed worker count or vendor quota.
- Deny production writes, external effects, real payments, provider
  invocation, market purchases, and founder/maintainer credentials by default.
  Tests use isolated synthetic state plus deterministic fakes or separately
  approved requester/market sandboxes.
- Make the PostgreSQL control-plane change in draft PR #1670 provide/consume a
  PostgreSQL topology adapter and this shared evidence contract instead of
  duplicating Section 14 scenarios, metrics, or envelope publication.
- Keep this change planning-only. Planning artifacts may land, but no harness
  implementation or baseline execution is authorized until a fresh Claude
  opposite-provider verdict is accepted. Host/product-owner decisions remain
  required for PLAN or product-boundary changes, budgets, production access or
  effects, first-write/activation, and numerical public-launch SLOs; ordinary
  factual or spec corrections close through normal accepted re-review.

## Capabilities

### New Capabilities

- `public-capacity-envelope`: Reusable topology-adapter capacity/isolation
  harness, evidence and freshness contract, conservative envelope publication,
  safety defaults, and downstream domain/topology composition boundaries.

### Modified Capabilities

None. Existing capabilities retain their behavioral requirements and authority;
they consume the shared harness only after their own accepted changes authorize
implementation and execution.

## Impact

This planning lane changes only OpenSpec artifacts under
`openspec/changes/establish-public-capacity-envelope/`. A future implementation
may add a generic harness, topology adapters, isolated fixtures, evidence
artifacts, and CI/reporting, but exact paths and dependencies require the fresh
Claude review and a separately accepted implementation claim.

The change does not modify runtime, deployment, PostgreSQL, public APIs,
authorization, identity, visibility, market state, provider routing, universe
state, production data, canonical specs, or PLAN. Draft PR #1670 remains the
owner of the future PostgreSQL control-plane substrate; it depends on this
harness contract for reusable capacity proof.
