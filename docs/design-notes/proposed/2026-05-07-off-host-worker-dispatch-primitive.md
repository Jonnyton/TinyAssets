---
title: Off-Host Worker Dispatch Primitive
date: 2026-05-07
author: codex-wiki-feature
status: proposed
request_id: WIKI-FEATURE
github_issue: 266
wiki_source: pages/feature-requests/feat-002-off-host-worker-dispatch-primitive-windows-mac-non-daemon-ho.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#multiplayer-daemon-platform
  - PLAN.md#user-capability-axis
  - PLAN.md#uptime-and-alarm-path
---

# Off-Host Worker Dispatch Primitive

## 1. Recommendation Summary

Add a narrow control-plane primitive for dispatching eligible execution work to
registered off-host workers. The primitive should make Windows, macOS, and
non-daemon hosts useful as execution capacity without making authoring depend
on a local tray, a host laptop, or a daemon subprocess running on the same
machine as the user.

This is a feature/project-design request, not a bug. The smallest useful
project change is a proposed design note because the request changes the host
pool contract, claim semantics, and review gate vocabulary. Runtime code should
wait until the design is accepted and the first implementation slice is chosen.

V1 should not add a new chatbot-visible MCP action. It should extend the
existing dispatch/claim substrate so the control plane can offer work to a
worker endpoint whose capabilities satisfy the task gate. Chat surfaces remain
control stations; they do not become worker schedulers.

## 2. Problem

Workflow already requires two user capability tiers:

- browser-only users can create, browse, and collaborate through a web chatbot;
- local-app users can additionally host local execution through a tray or code
  environment.

The current architecture also names a host pool registry, where hosts declare
capabilities, visibility, prices, and heartbeat state. The missing project
contract is the off-host dispatch primitive that lets a task leave the user's
current machine while preserving the same safety rules as local daemon work:
eligibility gates, file-locked or row-locked claiming, audit trail, provider
identity, and checker separation.

Without this primitive, Windows/macOS/non-daemon hosts become special cases:
they may be able to run work, but the control plane has no stable vocabulary
for selecting them, proving they are eligible, or explaining why a task did not
dispatch.

## 3. Proposed Shape

### Worker Registration

Each worker registers a capability card with the control plane:

```yaml
worker_id: host-macbook-pro-1
owner_id: user-or-org-id
worker_kind: tray | cli | cloud-runner | partner
platform:
  os: macos
  arch: arm64
capabilities:
  node_types:
    - code-change
    - browser-check
  providers:
    - codex
    - claude-code
  tools:
    - git
    - python
visibility: self | network | paid
heartbeat:
  status: online
  checked_at: 2026-05-07T00:00:00Z
limits:
  max_parallel_tasks: 1
  max_runtime_minutes: 45
```

The card is declaration, not trust. Claim-time verification still checks the
task gate, provider family, worker heartbeat freshness, required tools, and
any offer/payment constraints.

### Dispatch Offer

The control plane creates a dispatch offer when a work target is executable by
an off-host worker. The offer contains only the minimum required execution
envelope:

- work target id and branch/worktree metadata;
- required capability gates;
- allowed writer/checker families;
- input artifacts and output artifact destinations;
- timeout, concurrency, and payment terms when applicable;
- audit-log location and cancellation token.

The worker polls outbound for offers. The control plane does not require inbound
access to the worker. This preserves the current uptime posture and works
behind consumer NAT, corporate firewalls, and laptop sleep/wake cycles.

### Claim And Execution

An off-host worker can claim only one offer atomically under the same collision
contract as existing daemon claims. For v1, reuse the existing claim substrate
where possible:

1. Worker polls for offers matching its capability card.
2. Worker submits a claim request with current heartbeat and provider evidence.
3. Control plane atomically marks the offer claimed and writes the audit event.
4. Worker performs the task in its local environment.
5. Worker uploads outputs, logs, and verification evidence.
6. Control plane releases or closes the claim based on the review gate result.

The worker is execution-tier, not authority-tier. It cannot satisfy its own
opposite-family checker requirement for code changes.

## 4. Gate Semantics

Off-host execution must preserve the existing community request contract:

- Code-change writers are Claude/Codex only unless a later accepted design
  expands the writer set.
- Code-change writers require an opposite-family checker.
- Paid and free workers may claim only when they meet declared gate
  requirements.
- A worker capability declaration is insufficient; the claim event must include
  current evidence that the required provider/tool is reachable.
- Browser-only users can benefit from off-host execution without installing a
  local daemon or revealing private local files.

Rejected shortcut: treat a Mac or Windows tray as inherently trusted once it is
registered. Registration is inventory; claims are where trust is checked.

## 5. Tradeoffs

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Keep dispatch local-only | Lowest immediate complexity | Browser-only users and non-daemon hosts remain second-class execution surfaces | Reject |
| Add chatbot action `dispatch_worker` | Easy to expose manually | Expands MCP tool surface and makes chat clients look like schedulers | Reject for v1 |
| Polling worker offers backed by host pool registry | Works across Windows/macOS/NAT, composes with paid/free daemons, preserves control-plane audit | Requires worker heartbeat and claim tests before runtime rollout | Recommend |
| Direct inbound RPC from control plane to workers | Low latency | Fails behind NAT/firewalls and increases secret/surface area | Reject |

## 6. Implementation Slices

### Slice A: Contract And Tests

Add a typed worker capability card and dispatch-offer model, with tests for:

- capability matching;
- stale heartbeat rejection;
- writer/checker family separation;
- paid/free visibility filtering;
- claim idempotency.

No public MCP action is needed in this slice.

### Slice B: Worker Poll Endpoint

Expose a private worker polling route that lists claimable offers for the
authenticated worker. The route must return explicit skip reasons so host
operators can see why their worker is idle.

### Slice C: Claim/Upload Path

Wire a worker claim endpoint and output upload path into the same audit trail
used by daemon claims. The acceptance proof is a non-daemon worker claiming a
test offer, uploading evidence, and leaving the claim closed without double
claiming.

### Slice D: Tray/CLI Adapter

Teach the tray or CLI host to register its capability card and poll for offers.
Windows and macOS coverage should be tested explicitly before launch because
this primitive exists to close those host gaps.

## 7. Open Questions

1. Should `worker_id` be scoped to a user account, an organization, or a
   daemon soul? Recommendation: user/org ownership with optional daemon binding
   on the offer, because workers are runtime capacity and daemons are agent
   identity.

2. Where should payment settlement attach: offer claim or successful review?
   Recommendation: claim records intent; settlement waits for accepted output
   or the gate ladder's bounty requirements.

3. How should a sleeping laptop be represented? Recommendation: heartbeat
   expiry makes it ineligible without marking it faulty. Repeated failed claims
   should degrade worker reputation, not merely heartbeat status.

4. Which storage backend should hold offers first? Recommendation: use the same
   durable control-plane storage chosen for host pool registry work; do not add
   a separate queue before the accepted storage path is clear.

## References

- `PLAN.md` Multiplayer Daemon Platform
- `PLAN.md` User capability axis
- `PLAN.md` Uptime And Alarm Path
- `docs/ops/launch-readiness-checklist.md`
- `docs/notes/2026-04-20-agent-teams-on-workflow-research.md`
